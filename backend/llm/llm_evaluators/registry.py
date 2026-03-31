from __future__ import annotations

from backend.schemas.evaluators import EvaluationMode

from .base import BaseEvaluator
from .defence import DefenceEvaluator
from .educational import EducationalEvaluator
from .marketing import MarketingEvaluator
from .socialmedia import SocialMediaEvaluator

EVALUATOR_REGISTRY: dict[str, type[BaseEvaluator]] = {
    EvaluationMode.EDUCATIONAL.value: EducationalEvaluator,
    EvaluationMode.DEFENCE.value: DefenceEvaluator,
    EvaluationMode.MARKETING.value: MarketingEvaluator,
    EvaluationMode.SOCIAL_MEDIA.value: SocialMediaEvaluator,
}


def get_evaluator(mode: EvaluationMode | str) -> BaseEvaluator:
    normalized_mode = mode.value if isinstance(mode, EvaluationMode) else str(mode)
    try:
        evaluator_cls = EVALUATOR_REGISTRY[normalized_mode]
    except KeyError as exc:
        valid = ", ".join(sorted(EVALUATOR_REGISTRY))
        raise ValueError(f"Unsupported evaluation mode '{normalized_mode}'. Valid modes: {valid}") from exc
    return evaluator_cls()
