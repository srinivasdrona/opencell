"""Main workflow pipeline: spec → SBML → implement → review.

Coordinates the agent workflow for building sub-models.
This is the imperative coordination layer (Layer 2).
Layer 1 is .github/copilot-instructions.md (declarative).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opencell.orchestrator.panel import ExpertPanel, ClaimGraph
from opencell.orchestrator.router import ModelRouter, TaskType, Tier
from opencell.orchestrator.cost_tracker import CostTracker

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result from a pipeline step."""

    step: str
    success: bool
    output: Any = None
    errors: list[str] | None = None


class OpenCellPipeline:
    """Coordinates the full sub-model build workflow.

    Workflow:
    1. Biology panel deliberates modeling approach (Tier 1, cloud)
    2. Math modeler formulates SBML from decision (Tier 2)
    3. Data curator extracts parameters (Tier 3)
    4. Software engineer implements code (Tier 2)
    5. Cross-model reviewer reviews (Tier 2, different model)
    6. Validator runs tests (Tier 2)
    """

    def __init__(
        self,
        router: ModelRouter | None = None,
        panel: ExpertPanel | None = None,
        cost_tracker: CostTracker | None = None,
        decisions_dir: str | Path = "decisions",
    ) -> None:
        self.router = router or ModelRouter()
        self.panel = panel or ExpertPanel()
        self.cost_tracker = cost_tracker or CostTracker()
        self.decisions_dir = Path(decisions_dir)
        self.decisions_dir.mkdir(parents=True, exist_ok=True)

    def build_submodel(self, name: str) -> list[PipelineResult]:
        """Run the full pipeline for a sub-model.

        Returns list of PipelineResult for each step.
        """
        results: list[PipelineResult] = []

        # Step 1: Biology panel deliberation
        logger.info(f"Step 1: Biology panel for {name}")
        claim_graph = self.panel.deliberate(
            f"How should we model {name} in a minimal cell?"
        )
        results.append(PipelineResult(
            step="biology_panel",
            success=True,
            output=claim_graph,
        ))

        if claim_graph.needs_human_review:
            logger.warning(
                f"Panel output for {name} needs human review before proceeding"
            )

        # Step 2: Route to appropriate model for implementation
        model, temp = self.router.route(Tier.STANDARD, TaskType.CODE_GENERATION)
        logger.info(f"Step 2: Implementation routed to {model.provider}/{model.model_id}")
        results.append(PipelineResult(
            step="model_routing",
            success=True,
            output={"model": f"{model.provider}/{model.model_id}", "temperature": temp},
        ))

        # Steps 3-6 are placeholders — real implementation calls cloud APIs
        for step_name in ["data_curation", "implementation", "review", "validation"]:
            results.append(PipelineResult(
                step=step_name,
                success=True,
                output=f"Placeholder — {step_name} not yet connected to APIs",
            ))

        return results

    def build_all(self, organism: str = "toy_cell") -> dict[str, list[PipelineResult]]:
        """Run pipeline for all sub-models of an organism."""
        submodels = ["metabolism", "transcription", "translation"]
        return {name: self.build_submodel(name) for name in submodels}
