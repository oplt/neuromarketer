#!/usr/bin/env python3
# ruff: noqa: T201
"""Print fields that drive Compare table scores vs composite (needs DATABASE_URL).

Usage (from repo root, with venv or uv and .env loaded):

  PYTHONPATH=. python3 scripts/inspect_analysis_comparison_inputs.py <job-uuid> [job-uuid ...]

For API inspection instead (no DB), with auth cookie/token:

  curl -sS -H "Authorization: Bearer $TOKEN" \\
    http://127.0.0.1:8000/api/v1/analysis/jobs/<job-uuid>/results | jq ...
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock
from uuid import UUID

from backend.application.services.analysis import AnalysisApplicationService
from backend.application.services.analysis_comparisons import AnalysisComparisonApplicationService
from backend.db.models import InferenceJob
from backend.db.session import AsyncSessionLocal
from sqlalchemy import select
from sqlalchemy.orm import selectinload


def _parse_uuids(argv: list[str]) -> list[UUID]:
    out: list[UUID] = []
    for raw in argv:
        try:
            out.append(UUID(raw.strip()))
        except ValueError as exc:
            raise SystemExit(f"Invalid UUID: {raw!r}") from exc
    return out


async def _inspect_job(job_id: UUID) -> None:
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(InferenceJob)
            .options(selectinload(InferenceJob.analysis_result_record))
            .where(InferenceJob.id == job_id)
        )
        job = row.scalar_one_or_none()
        if job is None:
            print(f"\n=== {job_id} ===\n  (no inference_jobs row)\n")
            return

        analysis_svc = AnalysisApplicationService(session)
        result = analysis_svc._build_result(job)
        if result is None:
            print(f"\n=== {job_id} ===\n  (no analysis result yet)\n")
            return

        cmp_svc = AnalysisComparisonApplicationService(AsyncMock())
        summary = result.summary_json
        neutral = cmp_svc._summary_looks_like_llm_neutral_defaults(summary)

        metrics_by_key = {str(m.key): float(m.value) for m in result.metrics_json}
        conv = metrics_by_key.get("conversion_proxy_score")

        timeline = result.timeline_json or []
        engagements = [float(p.engagement_score) for p in timeline]
        eng_span = max(engagements) - min(engagements) if engagements else 0.0

        memories = [float(p.memory_proxy) for p in timeline]
        mem_span = max(memories) - min(memories) if memories else 0.0

        segs = result.segments_json or []
        loads = [float(s.cognitive_load) for s in segs]
        load_span = max(loads) - min(loads) if loads else 0.0

        tribe_eng = cmp_svc._tribe_timeline_engagement_scores(result)
        tribe_mem = cmp_svc._tribe_timeline_memory_score(result)
        tribe_low = cmp_svc._tribe_segment_low_cognitive_load(result)
        score_map = cmp_svc._extract_score_map(result)

        print(f"\n=== Job {job_id} ===")
        print("  summary_json (dashboard / LLM):")
        print(f"    overall_attention_score:   {summary.overall_attention_score}")
        print(f"    hook_score_first_3s:      {summary.hook_score_first_3_seconds}")
        print(f"    sustained_engagement:     {summary.sustained_engagement_score}")
        print(f"    memory_proxy_score:       {summary.memory_proxy_score}")
        print(f"    cognitive_load_proxy:     {summary.cognitive_load_proxy}")
        print(f"  looks_like_llm_neutral_band (49-51 on all five): {neutral}")
        print(f"  metrics_json conversion_proxy_score: {conv}")
        print(
            f"  timeline: {len(timeline)} points | engagement span={eng_span:.4f} "
            f"(needs >=0.25 for TRIBE override)"
        )
        print(f"  timeline memory_proxy span: {mem_span:.4f} (needs >=0.25 for memory override)")
        print(
            f"  segments: {len(segs)} | cognitive_load span: {load_span:.4f} "
            f"(needs >=0.25 for low-load override)"
        )
        print("  TRIBE fallbacks when neutral:")
        print(f"    _tribe_timeline_engagement_scores: {tribe_eng}")
        print(f"    _tribe_timeline_memory_score:       {tribe_mem}")
        print(f"    _tribe_segment_low_cognitive_load:   {tribe_low}")
        print("  scores_json used in Compare (after _extract_score_map):")
        for k in sorted(score_map):
            print(f"    {k}: {score_map[k]}")


async def main(argv: list[str]) -> None:
    job_ids = _parse_uuids(argv[1:])
    if not job_ids:
        raise SystemExit(
            "Usage: PYTHONPATH=. python3 scripts/inspect_analysis_comparison_inputs.py "
            "<job-uuid> [job-uuid ...]"
        )
    for jid in job_ids:
        await _inspect_job(jid)


if __name__ == "__main__":
    asyncio.run(main(sys.argv))
