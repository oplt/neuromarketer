from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.exceptions import NotFoundAppError, ValidationAppError
from backend.core.logging import get_logger
from backend.core.metrics import metrics
from backend.db.models import CreativeVersion
from backend.db.repositories import CreativeRepository, InferenceRepository
from backend.schemas.schemas import PredictRequest
from backend.services.asset_loader import AssetLoader, LoadedAsset
from backend.services.preprocess import PreprocessService
from backend.services.scoring import NeuroScoringService
from backend.services.tribe_runtime import (
    TribeRuntimeInput,
    get_shared_tribe_runtime,
)

logger = get_logger(__name__)


class PredictionApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.creatives = CreativeRepository(session)
        self.inference = InferenceRepository(session)
        self.asset_loader = AssetLoader()
        self.runtime = get_shared_tribe_runtime()
        self.scoring = NeuroScoringService()
        self.preprocess = PreprocessService()

    async def create_prediction_job(self, payload: PredictRequest):
        creative = await self.creatives.get_creative(payload.creative_id)
        if creative is None:
            raise NotFoundAppError("Creative not found.")
        if creative.project_id != payload.project_id:
            raise ValidationAppError("Creative does not belong to project.")

        creative_version = await self.creatives.get_creative_version(payload.creative_version_id)
        if creative_version is None:
            raise NotFoundAppError("Creative version not found.")
        if creative_version.creative_id != payload.creative_id:
            raise ValidationAppError("Creative version does not belong to creative.")

        modality = self._resolve_modality(creative_version)
        self.runtime.assert_supported_modality(modality)
        self._validate_inference_source(creative_version=creative_version, modality=modality)

        job = await self.inference.create_job(
            project_id=payload.project_id,
            creative_id=payload.creative_id,
            creative_version_id=payload.creative_version_id,
            created_by_user_id=payload.created_by_user_id,
            request_payload={
                "audience_context": payload.audience_context,
                "campaign_context": payload.campaign_context,
            },
            runtime_params=payload.runtime_params,
        )
        await self.session.commit()
        hydrated = await self.inference.get_job_with_prediction(job.id)
        return hydrated or job

    async def get_job(self, job_id: UUID):
        job = await self.inference.get_job_with_prediction(job_id)
        if job is None:
            raise NotFoundAppError("Job not found.")
        return job

    async def get_prediction_result(self, prediction_result_id: UUID):
        prediction = await self.inference.get_prediction_result_full(prediction_result_id)
        if prediction is None:
            raise NotFoundAppError("Prediction result not found.")
        return prediction

    async def process_prediction_job(self, job_id: UUID) -> None:
        job = await self.inference.acquire_job(
            job_id,
            stale_after_seconds=settings.celery_job_stale_after_seconds,
        )
        if job is None:
            logger.info(
                "Prediction job skipped.",
                extra={"event": "prediction_job_skipped", "extra_fields": {"job_id": str(job_id)}},
            )
            return

        creative_version = await self.creatives.get_creative_version(job.creative_version_id)
        if creative_version is None:
            raise NotFoundAppError("Creative version not found.")

        modality = self._resolve_modality(creative_version)
        self.runtime.assert_supported_modality(modality)
        self._validate_inference_source(creative_version=creative_version, modality=modality)

        loaded_asset: LoadedAsset | None = None
        try:
            runtime_input, loaded_asset = self._build_runtime_input(
                creative_version=creative_version,
                modality=modality,
                request_payload=job.request_payload,
                runtime_params=job.runtime_params,
            )
            runtime_output = self.runtime.infer(runtime_input)
            scoring_bundle = await self.scoring.score(
                reduced_feature_vector=runtime_output.reduced_feature_vector,
                region_activation_summary=runtime_output.region_activation_summary,
                context=job.request_payload,
                modality=modality,
            )
            await self.inference.replace_prediction_result(
                job=job,
                runtime_output=runtime_output,
                scoring_bundle=scoring_bundle,
                model_name=self.runtime.model_name,
            )
            await self.inference.mark_job_succeeded(job)
            metrics.increment("prediction_jobs_total", labels={"status": "succeeded"})
        finally:
            if loaded_asset is not None:
                loaded_asset.cleanup()

    async def mark_job_failed(self, job_id: UUID, error_message: str) -> None:
        job = await self.inference.get_job(job_id)
        if job is None:
            return
        await self.inference.mark_job_failed(job, error_message)
        metrics.increment("prediction_jobs_total", labels={"status": "failed"})

    def _resolve_modality(self, creative_version: CreativeVersion) -> str:
        preprocessing_summary = creative_version.preprocessing_summary or {}
        modality = preprocessing_summary.get("modality")
        if isinstance(modality, str) and modality:
            return modality
        if creative_version.raw_text:
            return "text"
        return self.preprocess.detect_modality(filename=None, mime_type=creative_version.mime_type)

    def _validate_inference_source(self, *, creative_version: CreativeVersion, modality: str) -> None:
        if modality == "text":
            if creative_version.raw_text and creative_version.raw_text.strip():
                return
            if creative_version.source_uri:
                return
            raise ValidationAppError("Text creative versions require raw_text or a text source_uri for TRIBE inference.")

        if modality in {"video", "audio"}:
            if creative_version.source_uri:
                return
            raise ValidationAppError(f"{modality.title()} creative versions require source_uri for TRIBE inference.")

    def _build_runtime_input(
        self,
        *,
        creative_version: CreativeVersion,
        modality: str,
        request_payload: dict,
        runtime_params: dict,
    ) -> tuple[TribeRuntimeInput, LoadedAsset | None]:
        loaded_asset: LoadedAsset | None = None

        if modality in {"video", "audio"}:
            loaded_asset = self._load_asset_for_version(creative_version)
        elif modality == "text" and not (creative_version.raw_text and creative_version.raw_text.strip()):
            loaded_asset = self._load_asset_for_version(creative_version)

        runtime_input = TribeRuntimeInput(
            modality=modality,
            local_path=loaded_asset.local_path if loaded_asset else None,
            mime_type=creative_version.mime_type,
            raw_text=creative_version.raw_text if modality == "text" else None,
            metadata_json=creative_version.extracted_metadata or {},
            request_context={
                "request_payload": request_payload,
                "runtime_params": runtime_params,
            },
        )
        return runtime_input, loaded_asset

    def _load_asset_for_version(self, creative_version: CreativeVersion) -> LoadedAsset:
        if not creative_version.source_uri:
            raise ValidationAppError("Creative version source_uri is required for asset-backed TRIBE inference.")
        try:
            return self.asset_loader.load(
                storage_uri=creative_version.source_uri,
                mime_type=creative_version.mime_type,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise ValidationAppError(str(exc)) from exc
