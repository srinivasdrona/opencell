"""Resource ledger: partition-merge allocation for shared metabolites.

In a whole-cell model, multiple sub-models consume and produce the same
species (ATP, GTP, amino acids, ribosomes, tRNAs). Write-exclusion
(each species owned by exactly one sub-model) doesn't work here.

Instead, we use the Karr 2012 approach:
1. PARTITION: At each sync point, the ledger distributes available
   resources to sub-models proportionally to their requests.
2. EVOLVE: Each sub-model runs independently with its allocated share.
3. MERGE: Results are combined back into the global state.

This ensures mass conservation and prevents double-counting.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ResourceRequest:
    """A sub-model's request for shared resources.

    Attributes:
        sub_model_id: Who is requesting
        species_id: What they want
        amount: How much they want (positive = consume, negative = produce)
        priority: Higher priority gets allocated first (default: equal)
    """

    sub_model_id: str
    species_id: str
    amount: float
    priority: float = 1.0


@dataclass
class AllocationResult:
    """Result of resource allocation for one species.

    Attributes:
        species_id: Which species
        available: Total available before allocation
        requests: Dict of sub_model_id → requested amount
        allocated: Dict of sub_model_id → actually allocated amount
        shortfall: Total unmet demand (0 if all requests satisfied)
    """

    species_id: str
    available: float
    requests: dict[str, float]
    allocated: dict[str, float]
    shortfall: float = 0.0


class ResourceLedger:
    """Global resource allocation via partition-merge.

    Usage:
        ledger = ResourceLedger()

        # Sub-models submit requests
        ledger.request("metabolism", "atp_c", 1000)
        ledger.request("translation", "atp_c", 500)

        # Allocate proportionally from available pool
        results = ledger.allocate(available={"atp_c": 1200})

        # results["atp_c"].allocated == {"metabolism": 800, "translation": 400}

        # After sub-models evolve, merge results back
        ledger.clear()  # ready for next sync point
    """

    def __init__(self) -> None:
        self._requests: list[ResourceRequest] = []
        self._history: list[dict[str, AllocationResult]] = []

    def request(
        self,
        sub_model_id: str,
        species_id: str,
        amount: float,
        priority: float = 1.0,
    ) -> None:
        """Submit a resource request."""
        self._requests.append(
            ResourceRequest(
                sub_model_id=sub_model_id,
                species_id=species_id,
                amount=amount,
                priority=priority,
            )
        )

    def allocate(
        self,
        available: dict[str, float],
    ) -> dict[str, AllocationResult]:
        """Allocate resources proportionally to requests.

        For each shared species:
        - If total demand ≤ available: everyone gets what they asked for
        - If total demand > available: allocate proportionally by priority-weighted request

        Args:
            available: Dict of species_id → available amount

        Returns:
            Dict of species_id → AllocationResult
        """
        # Group requests by species
        by_species: dict[str, list[ResourceRequest]] = {}
        for req in self._requests:
            if req.amount > 0:  # only allocate consumption requests
                by_species.setdefault(req.species_id, []).append(req)

        results: dict[str, AllocationResult] = {}

        for species_id, requests in by_species.items():
            avail = available.get(species_id, 0.0)
            total_weighted = sum(r.amount * r.priority for r in requests)
            total_demand = sum(r.amount for r in requests)

            req_dict: dict[str, float] = {}
            alloc_dict: dict[str, float] = {}

            for req in requests:
                req_dict[req.sub_model_id] = req.amount

                if total_demand <= avail:
                    alloc_dict[req.sub_model_id] = req.amount
                elif total_weighted > 0:
                    # Proportional allocation weighted by priority
                    fraction = (req.amount * req.priority) / total_weighted
                    alloc_dict[req.sub_model_id] = fraction * avail
                else:
                    alloc_dict[req.sub_model_id] = 0.0

            shortfall = max(0.0, total_demand - avail)

            results[species_id] = AllocationResult(
                species_id=species_id,
                available=avail,
                requests=req_dict,
                allocated=alloc_dict,
                shortfall=shortfall,
            )

        self._history.append(results)
        return results

    def merge_productions(
        self,
        productions: dict[str, dict[str, float]],
    ) -> dict[str, float]:
        """Merge production outputs from multiple sub-models.

        Args:
            productions: Dict of sub_model_id → {species_id: amount_produced}

        Returns:
            Dict of species_id → total produced
        """
        totals: dict[str, float] = {}
        for _sub_model_id, species_amounts in productions.items():
            for species_id, amount in species_amounts.items():
                totals[species_id] = totals.get(species_id, 0.0) + amount
        return totals

    def conservation_check(
        self,
        pre_state: dict[str, float],
        post_state: dict[str, float],
        tolerance: float = 1e-10,
    ) -> dict[str, float]:
        """Check mass conservation across a partition-merge cycle.

        Returns dict of species_id → residual (should be ~0 for conserved).
        """
        residuals: dict[str, float] = {}
        all_species = set(pre_state.keys()) | set(post_state.keys())
        for species_id in all_species:
            pre = pre_state.get(species_id, 0.0)
            post = post_state.get(species_id, 0.0)
            residuals[species_id] = post - pre
        return residuals

    def clear(self) -> None:
        """Clear all pending requests for the next sync point."""
        self._requests.clear()

    @property
    def history(self) -> list[dict[str, AllocationResult]]:
        """Allocation history for debugging."""
        return self._history
