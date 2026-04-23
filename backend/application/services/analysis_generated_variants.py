from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.application.services.predictions import PredictionApplicationService
from backend.core.exceptions import ConflictAppError, NotFoundAppError, ValidationAppError
from backend.db.models import GeneratedVariant, InferenceJob
from backend.schemas.analysis import (
    AnalysisGeneratedVariantCreateRequest,
    AnalysisGeneratedVariantListResponse,
    AnalysisGeneratedVariantMetricDeltaRead,
    AnalysisGeneratedVariantRead,
    AnalysisGeneratedVariantSectionRead,
    AnalysisGeneratedVariantType,
    AnalysisSummaryPayload,
)
from backend.schemas.schemas import OptimizationSuggestionRead

VARIANT_TYPE_ORDER: tuple[AnalysisGeneratedVariantType, ...] = (
    "hook_rewrite",
    "cta_rewrite",
    "shorter_script",
    "alternate_thumbnail",
)
VARIANT_PREFERENCE_MAP: dict[AnalysisGeneratedVariantType, tuple[str, ...]] = {
    "hook_rewrite": ("pacing", "framing", "copy"),
    "cta_rewrite": ("cta", "copy", "branding"),
    "shorter_script": ("pacing", "copy", "framing"),
    "alternate_thumbnail": ("thumbnail", "framing", "branding"),
}
VARIANT_TITLES: dict[AnalysisGeneratedVariantType, str] = {
    "hook_rewrite": "Hook rewrite",
    "cta_rewrite": "CTA rewrite",
    "shorter_script": "Shorter script",
    "alternate_thumbnail": "Alternate thumbnail",
}
COMPARE_METRICS: tuple[tuple[str, str], ...] = (
    ("overall_attention_score", "Overall attention"),
    ("hook_score_first_3_seconds", "Hook score"),
    ("sustained_engagement_score", "Sustained engagement"),
    ("memory_proxy_score", "Memory proxy"),
    ("cognitive_load_proxy", "Cognitive load"),
)
BASE_LIFT_MAP: dict[AnalysisGeneratedVariantType, dict[str, float]] = {
    "hook_rewrite": {
        "overall_attention_score": 4.0,
        "hook_score_first_3_seconds": 9.0,
        "sustained_engagement_score": 3.0,
        "memory_proxy_score": 2.0,
        "cognitive_load_proxy": -2.0,
    },
    "cta_rewrite": {
        "overall_attention_score": 2.0,
        "hook_score_first_3_seconds": 1.0,
        "sustained_engagement_score": 3.0,
        "memory_proxy_score": 1.5,
        "cognitive_load_proxy": -1.5,
    },
    "shorter_script": {
        "overall_attention_score": 3.0,
        "hook_score_first_3_seconds": 2.0,
        "sustained_engagement_score": 6.0,
        "memory_proxy_score": 2.0,
        "cognitive_load_proxy": -7.0,
    },
    "alternate_thumbnail": {
        "overall_attention_score": 5.0,
        "hook_score_first_3_seconds": 8.0,
        "sustained_engagement_score": 2.0,
        "memory_proxy_score": 3.0,
        "cognitive_load_proxy": -1.0,
    },
}
VARIANT_KEYWORD_MAP: dict[AnalysisGeneratedVariantType, tuple[str, ...]] = {
    "hook_rewrite": ("hook", "opening", "front-load", "earlier", "attention"),
    "cta_rewrite": ("cta", "decision", "action", "conversion"),
    "shorter_script": ("density", "simplify", "pacing", "retention"),
    "alternate_thumbnail": ("thumbnail", "framing", "brand", "contrast"),
}


class AnalysisGeneratedVariantsApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.predictions = PredictionApplicationService(session)

    async def list_variants(
        self,
        *,
        user_id: UUID,
        job_id: UUID,
    ) -> AnalysisGeneratedVariantListResponse:
        job = await self._load_analysis_job(user_id=user_id, job_id=job_id)
        items = [
            self._build_variant_read(job=job, variant=variant)
            for variant in await self._load_generated_variants(job=job)
        ]
        return AnalysisGeneratedVariantListResponse(job_id=job.id, items=items)

    async def generate_variants(
        self,
        *,
        user_id: UUID,
        job_id: UUID,
        payload: AnalysisGeneratedVariantCreateRequest,
    ) -> AnalysisGeneratedVariantListResponse:
        job = await self._load_analysis_job(user_id=user_id, job_id=job_id)
        if job.status.value != "succeeded" or job.analysis_result_record is None:
            raise ConflictAppError("Analysis results are not ready yet.")
        if job.creative_version_id is None:
            raise ValidationAppError("The analysis job is missing its creative version context.")

        variant_types = self._normalize_variant_types(payload.variant_types)
        existing_variants = await self._load_generated_variants(job=job)
        existing_by_type = {
            cast(
                AnalysisGeneratedVariantType, str((variant.metadata_json or {}).get("variant_type"))
            ): variant
            for variant in existing_variants
            if str((variant.metadata_json or {}).get("variant_type") or "") in VARIANT_TYPE_ORDER
        }

        for variant_type in variant_types:
            suggestion = self._select_source_suggestion(job=job, variant_type=variant_type)
            variant_payload = self._build_variant_payload(
                job=job,
                variant_type=variant_type,
                source_suggestion=suggestion,
            )
            target_variant = (
                existing_by_type.get(variant_type) if payload.replace_existing else None
            )
            if target_variant is None:
                target_variant = GeneratedVariant(
                    parent_creative_version_id=job.creative_version_id,
                    optimization_suggestion_id=suggestion.id if suggestion is not None else None,
                    source_uri=f"generated://analysis/{job.id}/{variant_type}",
                    metadata_json=variant_payload,
                    was_promoted_to_creative_version=False,
                )
                self.session.add(target_variant)
                existing_by_type[variant_type] = target_variant
            else:
                target_variant.optimization_suggestion_id = (
                    suggestion.id if suggestion is not None else None
                )
                target_variant.source_uri = f"generated://analysis/{job.id}/{variant_type}"
                target_variant.metadata_json = variant_payload
                target_variant.was_promoted_to_creative_version = False

        await self.session.commit()
        return await self.list_variants(user_id=user_id, job_id=job_id)

    async def _load_analysis_job(self, *, user_id: UUID, job_id: UUID) -> InferenceJob:
        job = await self.predictions.get_job(job_id)
        if job.created_by_user_id != user_id:
            raise NotFoundAppError("Analysis job not found.")
        return job

    async def _load_generated_variants(self, *, job: InferenceJob) -> list[GeneratedVariant]:
        result = await self.session.execute(
            select(GeneratedVariant)
            .where(GeneratedVariant.parent_creative_version_id == job.creative_version_id)
            .order_by(desc(GeneratedVariant.updated_at), desc(GeneratedVariant.created_at))
        )
        variants = []
        for variant in result.scalars().all():
            metadata_json = variant.metadata_json or {}
            if str(metadata_json.get("source_job_id") or "") != str(job.id):
                continue
            if str(metadata_json.get("variant_type") or "") not in VARIANT_TYPE_ORDER:
                continue
            variants.append(variant)
        variants.sort(
            key=lambda item: (
                VARIANT_TYPE_ORDER.index(
                    cast(
                        AnalysisGeneratedVariantType,
                        str((item.metadata_json or {}).get("variant_type")),
                    )
                ),
                -item.updated_at.timestamp(),
            )
        )
        return variants

    def _build_variant_read(
        self,
        *,
        job: InferenceJob,
        variant: GeneratedVariant,
    ) -> AnalysisGeneratedVariantRead:
        metadata_json = variant.metadata_json or {}
        expected_score_lift = {
            str(key): round(float(value), 2)
            for key, value in (metadata_json.get("expected_score_lift_json") or {}).items()
            if isinstance(value, (int, float))
        }
        sections = [
            AnalysisGeneratedVariantSectionRead.model_validate(item)
            for item in metadata_json.get("sections") or []
        ]
        compare_metrics = [
            AnalysisGeneratedVariantMetricDeltaRead.model_validate(item)
            for item in metadata_json.get("compare_metrics") or []
        ]
        return AnalysisGeneratedVariantRead(
            id=variant.id,
            job_id=job.id,
            parent_creative_version_id=variant.parent_creative_version_id,
            variant_type=cast(AnalysisGeneratedVariantType, str(metadata_json.get("variant_type"))),
            title=str(
                metadata_json.get("title")
                or VARIANT_TITLES.get(
                    cast(AnalysisGeneratedVariantType, str(metadata_json.get("variant_type"))),
                    "Generated variant",
                )
            ),
            summary=str(metadata_json.get("summary") or ""),
            focus_recommendations=[
                str(item)
                for item in metadata_json.get("focus_recommendations") or []
                if str(item).strip()
            ],
            source_suggestion_title=str(metadata_json.get("source_suggestion_title") or "").strip()
            or None,
            source_suggestion_type=str(metadata_json.get("source_suggestion_type") or "").strip()
            or None,
            sections=sections,
            expected_score_lift_json=expected_score_lift,
            projected_summary_json=AnalysisSummaryPayload.model_validate(
                metadata_json.get("projected_summary_json") or {}
            ),
            compare_metrics=compare_metrics,
            compare_summary=str(metadata_json.get("compare_summary") or ""),
            created_at=variant.created_at,
            updated_at=variant.updated_at,
        )

    def _normalize_variant_types(
        self,
        variant_types: Iterable[AnalysisGeneratedVariantType],
    ) -> list[AnalysisGeneratedVariantType]:
        unique_types: list[AnalysisGeneratedVariantType] = []
        for variant_type in variant_types:
            if variant_type in VARIANT_TYPE_ORDER and variant_type not in unique_types:
                unique_types.append(variant_type)
        return unique_types or list(VARIANT_TYPE_ORDER)

    def _select_source_suggestion(
        self,
        *,
        job: InferenceJob,
        variant_type: AnalysisGeneratedVariantType,
    ) -> OptimizationSuggestionRead | None:
        raw_suggestions = list(
            (job.prediction.suggestions if job.prediction is not None else []) or []
        )
        if not raw_suggestions:
            return None
        suggestions = [OptimizationSuggestionRead.model_validate(item) for item in raw_suggestions]
        preferred_types = VARIANT_PREFERENCE_MAP[variant_type]
        filtered = [
            suggestion
            for suggestion in suggestions
            if str(suggestion.suggestion_type or "") in preferred_types
        ]
        candidates = filtered or suggestions
        candidates.sort(
            key=lambda suggestion: (
                self._suggestion_type_rank(suggestion.suggestion_type, preferred_types),
                self._suggestion_value_rank(suggestion.expected_score_lift_json),
                float(suggestion.confidence or 0),
            ),
            reverse=True,
        )
        return candidates[0] if candidates else None

    def _build_variant_payload(
        self,
        *,
        job: InferenceJob,
        variant_type: AnalysisGeneratedVariantType,
        source_suggestion: OptimizationSuggestionRead | None,
    ) -> dict[str, Any]:
        if job.analysis_result_record is None:
            raise ConflictAppError("Analysis results are not ready yet.")

        summary = AnalysisSummaryPayload.model_validate(
            job.analysis_result_record.summary_json or {}
        )
        recommendations = list(job.analysis_result_record.recommendations_json or [])
        projected_summary = self._build_projected_summary(
            summary=summary,
            variant_type=variant_type,
            source_suggestion=source_suggestion,
        )
        compare_metrics = self._build_compare_metrics(
            summary=summary,
            projected_summary=projected_summary,
        )
        focus_recommendations = self._collect_focus_recommendations(
            variant_type=variant_type,
            recommendations=recommendations,
            source_suggestion=source_suggestion,
        )
        sections = self._build_variant_sections(
            job=job,
            variant_type=variant_type,
            source_suggestion=source_suggestion,
            focus_recommendations=focus_recommendations,
        )

        return {
            "source_job_id": str(job.id),
            "variant_type": variant_type,
            "title": VARIANT_TITLES[variant_type],
            "summary": self._build_variant_summary(
                variant_type=variant_type,
                source_suggestion=source_suggestion,
                focus_recommendations=focus_recommendations,
            ),
            "focus_recommendations": focus_recommendations,
            "source_suggestion_title": source_suggestion.title
            if source_suggestion is not None
            else None,
            "source_suggestion_type": source_suggestion.suggestion_type
            if source_suggestion is not None
            else None,
            "sections": sections,
            "expected_score_lift_json": self._build_expected_score_lift(
                variant_type=variant_type,
                source_suggestion=source_suggestion,
            ),
            "projected_summary_json": projected_summary.model_dump(mode="json"),
            "compare_metrics": [metric.model_dump(mode="json") for metric in compare_metrics],
            "compare_summary": self._build_compare_summary(compare_metrics=compare_metrics),
        }

    def _build_variant_sections(
        self,
        *,
        job: InferenceJob,
        variant_type: AnalysisGeneratedVariantType,
        source_suggestion: OptimizationSuggestionRead | None,
        focus_recommendations: list[str],
    ) -> list[dict[str, str]]:
        campaign_context = (job.request_payload or {}).get("campaign_context") or {}
        audience = (
            str(campaign_context.get("audience_segment") or "").strip() or "the target audience"
        )
        channel = str(campaign_context.get("channel") or "").strip() or "the target channel"
        objective = (
            str(campaign_context.get("objective") or "").strip() or "the current creative objective"
        )
        source_title = (
            source_suggestion.title
            if source_suggestion is not None
            else "the strongest recommendation"
        )
        first_recommendation = focus_recommendations[0] if focus_recommendations else source_title

        if variant_type == "hook_rewrite":
            return [
                {
                    "key": "primary_hook",
                    "label": "Primary hook",
                    "value": (
                        f"Lead with the clearest payoff for {audience} before context builds. "
                        f"Anchor the first beat around {first_recommendation.lower()}."
                    ),
                },
                {
                    "key": "alternate_hooks",
                    "label": "Alternate hooks",
                    "value": (
                        "1. Open on the strongest outcome, then show proof.\n"
                        "2. Start with the friction question, then answer it immediately.\n"
                        "3. Reveal the brand or product cue in the first beat, then widen the story."
                    ),
                },
                {
                    "key": "delivery_note",
                    "label": "Delivery note",
                    "value": (
                        f"Keep the opening under one fast read for {channel}. "
                        f"Use the first 1-2 seconds to cash in on {source_title.lower()}."
                    ),
                },
            ]

        if variant_type == "cta_rewrite":
            return [
                {
                    "key": "primary_cta",
                    "label": "Primary CTA",
                    "value": "Make the next step explicit and low-friction: see it, understand it, act on it.",
                },
                {
                    "key": "low_friction_cta",
                    "label": "Low-friction CTA",
                    "value": "Try the lighter ask first: preview it, get the guide, or see how it works.",
                },
                {
                    "key": "urgency_cta",
                    "label": "Urgency CTA",
                    "value": "Tie urgency to the audience payoff, not to generic scarcity language.",
                },
                {
                    "key": "placement_note",
                    "label": "Placement note",
                    "value": (
                        f"Bring the CTA closer to the highest-attention moment on {channel}. "
                        f"That directly addresses {source_title.lower()}."
                    ),
                },
            ]

        if variant_type == "shorter_script":
            return [
                {
                    "key": "compressed_script",
                    "label": "Compressed script",
                    "value": (
                        f"0-2s Hook: state the strongest payoff for {audience}.\n"
                        "2-5s Proof: show one concrete proof point or mechanism.\n"
                        "5-8s Brand: re-anchor the product or brand while attention is high.\n"
                        "8-10s CTA: close with one clear ask and one reason to act now."
                    ),
                },
                {
                    "key": "trim_guidance",
                    "label": "Trim guidance",
                    "value": (
                        f"Remove any line that repeats {objective.lower()} without adding new proof. "
                        "Keep one idea per beat."
                    ),
                },
                {
                    "key": "pacing_note",
                    "label": "Pacing note",
                    "value": (
                        f"Use shorter sentence lengths and fewer scene transitions. "
                        f"This variant is built to respond to {source_title.lower()}."
                    ),
                },
            ]

        return [
            {
                "key": "headline_overlay",
                "label": "Headline overlay",
                "value": "Use 3-5 words that state the outcome, not the category.",
            },
            {
                "key": "primary_visual",
                "label": "Primary visual",
                "value": (
                    f"Feature the single most expressive product cue or human reaction for {audience}. "
                    "Keep the subject large and unmistakable."
                ),
            },
            {
                "key": "composition_note",
                "label": "Composition note",
                "value": (
                    "Keep one focal point, a quiet background, and a brand cue that is visible without competing "
                    "with the headline."
                ),
            },
            {
                "key": "contrast_cue",
                "label": "Contrast cue",
                "value": (
                    f"Increase contrast around the focal subject so the entry frame sells {first_recommendation.lower()} "
                    "before a viewer reads any supporting copy."
                ),
            },
        ]

    def _build_variant_summary(
        self,
        *,
        variant_type: AnalysisGeneratedVariantType,
        source_suggestion: OptimizationSuggestionRead | None,
        focus_recommendations: list[str],
    ) -> str:
        summary_map = {
            "hook_rewrite": "A faster opening variant designed to improve first-impression hold strength.",
            "cta_rewrite": "A clearer action variant designed to reduce decision friction near the close.",
            "shorter_script": "A compressed script pass designed to preserve the strongest proof while reducing load.",
            "alternate_thumbnail": "A stronger entry-frame concept designed to earn attention before playback or read depth.",
        }
        summary = summary_map[variant_type]
        if source_suggestion is not None:
            summary += f" Built from “{source_suggestion.title}”."
        elif focus_recommendations:
            summary += f" Built from “{focus_recommendations[0]}”."
        return summary

    def _build_expected_score_lift(
        self,
        *,
        variant_type: AnalysisGeneratedVariantType,
        source_suggestion: OptimizationSuggestionRead | None,
    ) -> dict[str, float]:
        expected = dict(BASE_LIFT_MAP[variant_type])
        if source_suggestion is not None:
            for metric_key, metric_value in self._translate_suggestion_lifts(
                variant_type=variant_type,
                expected_lift=source_suggestion.expected_score_lift_json,
            ).items():
                expected[metric_key] = round(expected.get(metric_key, 0.0) + metric_value, 2)
        return {key: round(value, 2) for key, value in expected.items()}

    def _build_projected_summary(
        self,
        *,
        summary: AnalysisSummaryPayload,
        variant_type: AnalysisGeneratedVariantType,
        source_suggestion: OptimizationSuggestionRead | None,
    ) -> AnalysisSummaryPayload:
        next_values = {
            "overall_attention_score": float(summary.overall_attention_score),
            "hook_score_first_3_seconds": float(summary.hook_score_first_3_seconds),
            "sustained_engagement_score": float(summary.sustained_engagement_score),
            "memory_proxy_score": float(summary.memory_proxy_score),
            "cognitive_load_proxy": float(summary.cognitive_load_proxy),
        }
        for metric_key, metric_value in self._build_expected_score_lift(
            variant_type=variant_type,
            source_suggestion=source_suggestion,
        ).items():
            if metric_key in next_values:
                next_values[metric_key] = round(
                    self._clamp(next_values[metric_key] + metric_value), 2
                )
        metadata = dict(summary.metadata or {})
        metadata.update(
            {
                "variant_type": variant_type,
                "projection_kind": "generated_variant",
            }
        )
        return AnalysisSummaryPayload(
            modality=summary.modality,
            overall_attention_score=next_values["overall_attention_score"],
            hook_score_first_3_seconds=next_values["hook_score_first_3_seconds"],
            sustained_engagement_score=next_values["sustained_engagement_score"],
            memory_proxy_score=next_values["memory_proxy_score"],
            cognitive_load_proxy=next_values["cognitive_load_proxy"],
            confidence=summary.confidence,
            completeness=summary.completeness,
            notes=list(summary.notes or []),
            metadata=metadata,
        )

    def _build_compare_metrics(
        self,
        *,
        summary: AnalysisSummaryPayload,
        projected_summary: AnalysisSummaryPayload,
    ) -> list[AnalysisGeneratedVariantMetricDeltaRead]:
        rows: list[AnalysisGeneratedVariantMetricDeltaRead] = []
        for metric_key, label in COMPARE_METRICS:
            original_value = round(float(getattr(summary, metric_key)), 2)
            variant_value = round(float(getattr(projected_summary, metric_key)), 2)
            rows.append(
                AnalysisGeneratedVariantMetricDeltaRead(
                    key=metric_key,
                    label=label,
                    original_value=original_value,
                    variant_value=variant_value,
                    delta=round(variant_value - original_value, 2),
                )
            )
        return rows

    def _build_compare_summary(
        self,
        *,
        compare_metrics: list[AnalysisGeneratedVariantMetricDeltaRead],
    ) -> str:
        if not compare_metrics:
            return "No comparison metrics are available for this variant."
        ranked_improvements = sorted(
            compare_metrics,
            key=self._comparison_metric_priority,
            reverse=True,
        )
        top_two = ranked_improvements[:2]
        fragments = []
        for metric in top_two:
            signed_delta = (
                abs(metric.delta)
                if metric.key == "cognitive_load_proxy" and metric.delta < 0
                else abs(metric.delta)
            )
            direction = (
                "reduce" if metric.key == "cognitive_load_proxy" and metric.delta < 0 else "lift"
            )
            if metric.key == "cognitive_load_proxy" and metric.delta > 0:
                direction = "increase"
            fragments.append(f"{direction} {metric.label.lower()} by {signed_delta:.1f}")
        if not fragments:
            return "This variant is stored and ready for comparison against the original."
        return (
            f"Compared with the original, this variant is projected to {' and '.join(fragments)}."
        )

    def _collect_focus_recommendations(
        self,
        *,
        variant_type: AnalysisGeneratedVariantType,
        recommendations: list[dict[str, Any]],
        source_suggestion: OptimizationSuggestionRead | None,
    ) -> list[str]:
        keywords = VARIANT_KEYWORD_MAP[variant_type]
        selected: list[str] = []
        if source_suggestion is not None and source_suggestion.title.strip():
            selected.append(source_suggestion.title.strip())
        for recommendation in recommendations:
            title = str(recommendation.get("title") or "").strip()
            detail = str(recommendation.get("detail") or "").strip().lower()
            if not title:
                continue
            if any(keyword in title.lower() or keyword in detail for keyword in keywords):
                if title not in selected:
                    selected.append(title)
        for recommendation in recommendations:
            title = str(recommendation.get("title") or "").strip()
            if title and title not in selected:
                selected.append(title)
            if len(selected) >= 3:
                break
        return selected[:3]

    def _translate_suggestion_lifts(
        self,
        *,
        variant_type: AnalysisGeneratedVariantType,
        expected_lift: dict[str, Any],
    ) -> dict[str, float]:
        translated = {
            "overall_attention_score": 0.0,
            "hook_score_first_3_seconds": 0.0,
            "sustained_engagement_score": 0.0,
            "memory_proxy_score": 0.0,
            "cognitive_load_proxy": 0.0,
        }
        for raw_key, raw_value in expected_lift.items():
            if not isinstance(raw_value, (int, float)):
                continue
            value = float(raw_value)
            if raw_key == "attention":
                translated["overall_attention_score"] += value
                translated["hook_score_first_3_seconds"] += value * (
                    1.15 if variant_type in {"hook_rewrite", "alternate_thumbnail"} else 0.55
                )
                translated["sustained_engagement_score"] += value * 0.45
            elif raw_key == "memory":
                translated["memory_proxy_score"] += value
                translated["overall_attention_score"] += value * 0.2
            elif raw_key == "cognitive_load":
                translated["cognitive_load_proxy"] += value
                translated["sustained_engagement_score"] += (
                    abs(value) * 0.35 if value < 0 else -value * 0.2
                )
            elif raw_key == "conversion_proxy":
                translated["sustained_engagement_score"] += value * 0.5
                translated["overall_attention_score"] += value * 0.35
                if variant_type == "cta_rewrite":
                    translated["memory_proxy_score"] += value * 0.15
            elif raw_key == "emotion":
                translated["overall_attention_score"] += value * 0.3
                translated["memory_proxy_score"] += value * 0.4
                translated["sustained_engagement_score"] += value * 0.3
        return {key: round(value, 2) for key, value in translated.items()}

    def _suggestion_type_rank(self, value: str | None, preferred_types: tuple[str, ...]) -> int:
        if value not in preferred_types:
            return 0
        return len(preferred_types) - preferred_types.index(value)

    def _suggestion_value_rank(self, expected_lift_json: dict[str, Any]) -> float:
        return round(
            sum(
                abs(float(value))
                for value in expected_lift_json.values()
                if isinstance(value, (int, float))
            ),
            2,
        )

    def _comparison_metric_priority(self, metric: AnalysisGeneratedVariantMetricDeltaRead) -> float:
        if metric.key == "cognitive_load_proxy":
            return -metric.delta
        return metric.delta

    def _clamp(self, value: float) -> float:
        return max(0.0, min(100.0, value))
