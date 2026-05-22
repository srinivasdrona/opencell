"""Model router: task-specific model selection with temperature policy.

Routes tasks to the cheapest model meeting quality requirements.
Temperature is task-specific (mandatory policy):
- 0 for code generation, parameter extraction, data formatting
- 0.3-0.5 for literature search, hypothesis generation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto

logger = logging.getLogger(__name__)


class Tier(Enum):
    """Task criticality tiers."""

    CRITICAL = auto()  # Multi-model panel + human approval
    STANDARD = auto()  # Single model + cross-model review
    ROUTINE = auto()  # Cheapest model
    BULK = auto()  # Batch processing


class TaskType(Enum):
    """Task types with associated temperature policies."""

    CODE_GENERATION = auto()
    PARAMETER_EXTRACTION = auto()
    DATA_FORMATTING = auto()
    LITERATURE_SEARCH = auto()
    HYPOTHESIS_GENERATION = auto()
    REVIEW = auto()
    BIOLOGY_DECISION = auto()


# Temperature policy: mandatory, not optional
TEMPERATURE_POLICY: dict[TaskType, float] = {
    TaskType.CODE_GENERATION: 0.0,
    TaskType.PARAMETER_EXTRACTION: 0.0,
    TaskType.DATA_FORMATTING: 0.0,
    TaskType.LITERATURE_SEARCH: 0.3,
    TaskType.HYPOTHESIS_GENERATION: 0.5,
    TaskType.REVIEW: 0.0,
    TaskType.BIOLOGY_DECISION: 0.0,
}


@dataclass
class ModelConfig:
    """Configuration for a model provider."""

    provider: str  # e.g., "anthropic", "openai", "xai"
    model_id: str  # e.g., "claude-opus-4", "gpt-5"
    tier: Tier
    supports_web: bool = False
    max_context_tokens: int = 200_000


# Default model configurations
DEFAULT_MODELS: dict[Tier, list[ModelConfig]] = {
    Tier.CRITICAL: [
        ModelConfig("anthropic", "claude-opus-4", Tier.CRITICAL),
        ModelConfig("openai", "gpt-5", Tier.CRITICAL),
        ModelConfig("xai", "grok-3", Tier.CRITICAL, supports_web=True),
    ],
    Tier.STANDARD: [
        ModelConfig("anthropic", "claude-sonnet-4", Tier.STANDARD),
        ModelConfig("openai", "gpt-5", Tier.STANDARD),
    ],
    Tier.ROUTINE: [
        ModelConfig("anthropic", "claude-haiku", Tier.ROUTINE),
    ],
    Tier.BULK: [
        ModelConfig("openai", "gpt-4.1-mini", Tier.BULK),
    ],
}


class ModelRouter:
    """Route tasks to appropriate models based on tier and requirements."""

    def __init__(
        self,
        models: dict[Tier, list[ModelConfig]] | None = None,
    ) -> None:
        self.models = models if models is not None else DEFAULT_MODELS

    def route(
        self,
        tier: Tier,
        task_type: TaskType = TaskType.CODE_GENERATION,
        needs_web: bool = False,
        needs_long_context: bool = False,
    ) -> tuple[ModelConfig, float]:
        """Select model and temperature for a task.

        Returns:
            Tuple of (model_config, temperature)
        """
        temperature = TEMPERATURE_POLICY.get(task_type, 0.0)

        if needs_web:
            # Grok has built-in web search
            web_models = [m for m in self.models.get(Tier.CRITICAL, []) if m.supports_web]
            if web_models:
                return web_models[0], temperature

        candidates = self.models.get(tier, [])
        if not candidates:
            raise ValueError(f"No models configured for tier {tier}")

        if needs_long_context:
            candidates = sorted(candidates, key=lambda m: m.max_context_tokens, reverse=True)

        selected = candidates[0]
        logger.info(
            f"Routed {task_type.name} (tier={tier.name}) → "
            f"{selected.provider}/{selected.model_id} @ temp={temperature}"
        )
        return selected, temperature
