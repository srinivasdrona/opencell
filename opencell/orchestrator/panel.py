"""Expert panel: multi-model evidence extraction with claim graphs.

Panels are evidence extractors and draft generators, NOT decision-makers.
Critical decisions require human approval + automated DOI verification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class Confidence(Enum):
    HIGH = auto()
    MEDIUM = auto()
    LOW = auto()
    UNKNOWN = auto()


@dataclass
class EvidenceItem:
    """A single piece of evidence for or against a claim."""

    doi: str
    excerpt: str
    species: str = ""
    conditions: dict[str, Any] = field(default_factory=dict)
    verified: bool = False  # Has DOI been checked to contain this excerpt?


@dataclass
class Claim:
    """A scientific claim with supporting and contradicting evidence."""

    claim_text: str
    evidence_for: list[EvidenceItem] = field(default_factory=list)
    evidence_against: list[EvidenceItem] = field(default_factory=list)
    confidence: Confidence = Confidence.UNKNOWN
    recommendation: str = ""
    human_approved: bool = False


@dataclass
class ClaimGraph:
    """Structured output from an expert panel deliberation."""

    question: str
    claims: list[Claim] = field(default_factory=list)
    panel_models: list[str] = field(default_factory=list)
    moderator_model: str = ""
    contradictions: list[str] = field(default_factory=list)
    needs_human_review: bool = True

    def approved_claims(self) -> list[Claim]:
        """Return only human-approved claims."""
        return [c for c in self.claims if c.human_approved]

    def unverified_dois(self) -> list[str]:
        """Return all DOIs that haven't been verified."""
        dois = []
        for claim in self.claims:
            for ev in claim.evidence_for + claim.evidence_against:
                if not ev.verified:
                    dois.append(ev.doi)
        return dois


class ExpertPanel:
    """Multi-model evidence extraction panel.

    Architecture:
    - Multiple panelist models contribute evidence independently
    - Non-participating moderator synthesizes into claim graph
    - Human approves critical decisions

    NOTE: Non-participating moderator pattern is UNVALIDATED.
    Ablation study planned after Phase 2.
    """

    def __init__(
        self,
        panelist_model_ids: list[str] | None = None,
        moderator_model_id: str = "google/gemini-2.5-pro",
    ) -> None:
        self.panelist_model_ids = panelist_model_ids or [
            "anthropic/claude-opus-4",
            "openai/gpt-5",
            "xai/grok-3",
        ]
        self.moderator_model_id = moderator_model_id

    def deliberate(self, question: str) -> ClaimGraph:
        """Run panel deliberation on a question.

        In production, this calls cloud APIs for each panelist,
        collects evidence, and has the moderator synthesize.
        Currently returns a placeholder for framework validation.
        """
        logger.info(f"Panel deliberation requested: {question}")
        logger.info(f"Panelists: {self.panelist_model_ids}")
        logger.info(f"Moderator: {self.moderator_model_id}")

        # Placeholder — real implementation calls cloud APIs
        graph = ClaimGraph(
            question=question,
            panel_models=self.panelist_model_ids,
            moderator_model=self.moderator_model_id,
            needs_human_review=True,
        )
        return graph

    def verify_doi(self, doi: str) -> bool:
        """Check that a DOI exists (basic validation).

        In production, checks doi.org resolution.
        """
        if not doi:
            return False
        # Placeholder — real implementation hits doi.org API
        return doi.startswith("10.")
