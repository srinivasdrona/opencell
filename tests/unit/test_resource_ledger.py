"""Tests for core/resource_ledger.py — Partition-merge resource allocation."""

from opencell.core.resource_ledger import ResourceLedger


class TestResourceLedger:
    def test_sufficient_resources_full_allocation(self) -> None:
        ledger = ResourceLedger()
        ledger.request("metabolism", "atp_c", 500)
        ledger.request("translation", "atp_c", 300)

        results = ledger.allocate(available={"atp_c": 1000})

        assert results["atp_c"].allocated["metabolism"] == 500
        assert results["atp_c"].allocated["translation"] == 300
        assert results["atp_c"].shortfall == 0.0

    def test_insufficient_resources_proportional(self) -> None:
        ledger = ResourceLedger()
        ledger.request("metabolism", "atp_c", 600)
        ledger.request("translation", "atp_c", 400)

        results = ledger.allocate(available={"atp_c": 500})

        # Proportional: metabolism gets 60%, translation 40%
        assert abs(results["atp_c"].allocated["metabolism"] - 300) < 1e-10
        assert abs(results["atp_c"].allocated["translation"] - 200) < 1e-10
        assert abs(results["atp_c"].shortfall - 500) < 1e-10

    def test_zero_available(self) -> None:
        ledger = ResourceLedger()
        ledger.request("metabolism", "atp_c", 100)
        results = ledger.allocate(available={"atp_c": 0})
        assert results["atp_c"].allocated["metabolism"] == 0.0

    def test_merge_productions(self) -> None:
        ledger = ResourceLedger()
        productions = {
            "metabolism": {"atp_c": 100, "adp_c": -100},
            "translation": {"atp_c": -50},
        }
        totals = ledger.merge_productions(productions)
        assert totals["atp_c"] == 50  # 100 - 50
        assert totals["adp_c"] == -100

    def test_clear_resets(self) -> None:
        ledger = ResourceLedger()
        ledger.request("metabolism", "atp_c", 100)
        ledger.clear()
        results = ledger.allocate(available={"atp_c": 1000})
        assert len(results) == 0  # no requests after clear

    def test_priority_weighting(self) -> None:
        ledger = ResourceLedger()
        ledger.request("critical", "atp_c", 100, priority=10.0)
        ledger.request("routine", "atp_c", 100, priority=1.0)

        results = ledger.allocate(available={"atp_c": 110})

        # critical has 10x priority, so gets ~10/11 of 110 ≈ 100
        critical_alloc = results["atp_c"].allocated["critical"]
        routine_alloc = results["atp_c"].allocated["routine"]
        assert critical_alloc > routine_alloc
        assert abs(critical_alloc + routine_alloc - 110) < 1e-10

    def test_history_recorded(self) -> None:
        ledger = ResourceLedger()
        ledger.request("m", "atp_c", 50)
        ledger.allocate(available={"atp_c": 100})
        assert len(ledger.history) == 1
