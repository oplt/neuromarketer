from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.llm.context_builder import EvaluationContextBuilder
from backend.llm.llm_client import (
    LLMClientConfig,
    LLMResponseFormatError,
    LLMTransportError,
    OpenAICompatibleLLMClient,
    StructuredGeneration,
)
from backend.llm.router import LLMRouteConfig, LLMRouter


class _FakeClient:
    def __init__(self, events):
        self.events = list(events)
        self.calls = 0
        self.repair_calls = 0

    async def generate_structured(self, *, messages, response_schema=None, options=None):
        _ = (messages, response_schema, options)
        self.calls += 1
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return event

    async def generate_structured_with_repair(
        self, *, messages, response_schema=None, options=None
    ):
        _ = (messages, response_schema, options)
        self.repair_calls += 1
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return event

    async def aclose(self):
        return None


def _generation() -> StructuredGeneration:
    return StructuredGeneration(
        parsed_json={"ok": True},
        metadata={
            "provider_id": "p",
            "provider": "openai_compatible",
            "model": "m",
            "tokens_in": 10,
            "tokens_out": 20,
            "raw_text": '{"ok":true}',
        },
    )


class TestLLMRouterRetryPolicy(unittest.IsolatedAsyncioTestCase):
    async def test_router_skips_retry_for_non_retryable_transport_error(self) -> None:
        router = LLMRouter(
            routes=[
                LLMRouteConfig("a", "openai_compatible", "http://a", "m", max_attempts=3),
                LLMRouteConfig("b", "openai_compatible", "http://b", "m", max_attempts=2),
            ]
        )
        first = _FakeClient([LLMTransportError("not found", retryable=False, status_code=404)])
        second = _FakeClient([_generation()])
        router.clients = {"a": first, "b": second}
        result = await router.generate_structured(
            mode="x", messages=[{"role": "user", "content": "hi"}]
        )
        self.assertTrue(result.parsed_json["ok"])
        self.assertEqual(first.calls, 1)
        self.assertEqual(second.calls, 1)

    async def test_router_retries_transient_transport_error(self) -> None:
        router = LLMRouter(
            routes=[LLMRouteConfig("a", "openai_compatible", "http://a", "m", max_attempts=2)]
        )
        client = _FakeClient(
            [LLMTransportError("temp", retryable=True, status_code=503), _generation()]
        )
        router.clients = {"a": client}
        await router.generate_structured(mode="x", messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(client.calls, 2)

    async def test_router_retries_malformed_json_once_with_repair(self) -> None:
        router = LLMRouter(
            routes=[LLMRouteConfig("a", "openai_compatible", "http://a", "m", max_attempts=2)]
        )
        client = _FakeClient([LLMResponseFormatError("bad json"), _generation()])
        router.clients = {"a": client}
        await router.generate_structured(mode="x", messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(client.calls, 1)
        self.assertEqual(client.repair_calls, 1)

    async def test_budget_estimate_uses_request_token_option(self) -> None:
        router = LLMRouter(
            routes=[
                LLMRouteConfig(
                    "a",
                    "openai_compatible",
                    "http://a",
                    "m",
                    max_tokens=4000,
                    cost_output_per_1k_tokens=1.0,
                    request_budget_usd=0.1,
                )
            ]
        )
        router.clients = {"a": _FakeClient([_generation()])}
        await router.generate_structured(
            mode="x",
            messages=[{"role": "user", "content": "hi"}],
            options={"max_tokens": 50},
        )


class TestLLMClientAndContext(unittest.IsolatedAsyncioTestCase):
    async def test_http_client_reused_and_closable(self) -> None:
        client = OpenAICompatibleLLMClient(
            LLMClientConfig(provider="openai_compatible", base_url="http://x", model="m")
        )
        first = await client._client()
        second = await client._client()
        self.assertIs(first, second)
        await client.aclose()
        third = await client._client()
        self.assertIsNot(first, third)
        await client.aclose()

    async def test_openai_client_json_schema_only_when_enabled(self) -> None:
        captured: list[dict] = []
        client = OpenAICompatibleLLMClient(
            LLMClientConfig(
                provider="openai_compatible",
                base_url="http://x",
                model="m",
                supports_json_schema=True,
            )
        )
        client._post_json = AsyncMock(
            side_effect=lambda **kwargs: (
                captured.append(kwargs["payload"])
                or {
                    "choices": [{"message": {"content": '{"ok":true}'}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            )
        )
        await client.generate_structured(
            messages=[{"role": "user", "content": "hi"}],
            response_schema={"type": "object"},
        )
        self.assertEqual(captured[-1]["response_format"]["type"], "json_schema")
        await client.aclose()

    async def test_context_builder_uses_topk_and_skips_asset_loading_by_default(self) -> None:
        builder = EvaluationContextBuilder()
        builder.asset_loader = SimpleNamespace(load=AsyncMock(side_effect=AssertionError("no io")))
        creative = SimpleNamespace(
            id="c1",
            raw_text="",
            preprocessing_summary={"modality": "text", "text_excerpt": "short excerpt"},
            source_uri="s3://x/a.txt",
            mime_type="text/plain",
            extracted_metadata={},
        )
        job = SimpleNamespace(
            id="j",
            creative_version_id="cv",
            request_payload={"campaign_context": {}},
            created_at=None,
        )
        analysis = SimpleNamespace(
            summary_json={"metadata": {}},
            metrics_json=[],
            timeline_json=[
                {"timestamp_ms": 0, "attention_score": 10, "engagement_score": 10},
                {"timestamp_ms": 1, "attention_score": 90, "engagement_score": 11},
                {"timestamp_ms": 2, "attention_score": 20, "engagement_score": 12},
                {"timestamp_ms": 3, "attention_score": 80, "engagement_score": 13},
                {"timestamp_ms": 4, "attention_score": 30, "engagement_score": 14},
            ],
            segments_json=[
                {"label": "a", "segment_index": 0, "attention_score": 10, "engagement_delta": 1},
                {"label": "b", "segment_index": 1, "attention_score": 80, "engagement_delta": 2},
                {"label": "c", "segment_index": 2, "attention_score": 5, "engagement_delta": -1},
                {"label": "d", "segment_index": 3, "attention_score": 70, "engagement_delta": 3},
            ],
            visualizations_json={},
            recommendations_json=[],
            created_at=None,
        )
        payload = builder.build(job=job, analysis_result=analysis, creative_version=creative)
        self.assertEqual(
            payload["timeline_highlights"]["peak_attention_points"][0]["attention_score"], 90
        )
        self.assertEqual(payload["transcript_excerpt"], "short excerpt")


if __name__ == "__main__":
    unittest.main()
