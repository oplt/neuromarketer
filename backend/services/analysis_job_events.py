from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from backend.core.config import settings
from backend.core.logging import get_logger, log_event, log_exception

logger = get_logger(__name__)
CHANNEL_PREFIX = "analysis-job-events"


def build_analysis_job_channel(job_id: UUID) -> str:
    return f"{CHANNEL_PREFIX}:{job_id}"


def _resolve_redis_event_url() -> str | None:
    candidates = [settings.celery_broker_url, settings.celery_result_backend]
    for candidate in candidates:
        parsed = urlparse(candidate)
        if parsed.scheme.lower() in {"redis", "rediss"} and parsed.hostname:
            return candidate
    return None


async def publish_analysis_job_event(
    *,
    job_id: UUID,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> bool:
    redis_url = _resolve_redis_event_url()
    if redis_url is None:
        return False

    client = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    try:
        await client.publish(
            build_analysis_job_channel(job_id),
            json.dumps(
                {
                    "event_type": event_type,
                    "job_id": str(job_id),
                    "payload": payload or {},
                }
            ),
        )
        return True
    except Exception as exc:
        log_exception(
            logger,
            "analysis_job_event_publish_failed",
            exc,
            level="warning",
            job_id=str(job_id),
            event_type=event_type,
            status="degraded",
        )
        return False
    finally:
        await client.aclose()


async def open_analysis_job_subscription(job_id: UUID) -> tuple[Redis, PubSub] | None:
    redis_url = _resolve_redis_event_url()
    if redis_url is None:
        return None

    client = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    try:
        pubsub = client.pubsub()
        await pubsub.subscribe(build_analysis_job_channel(job_id))
        return client, pubsub
    except Exception as exc:
        log_exception(
            logger,
            "analysis_job_event_subscribe_failed",
            exc,
            level="warning",
            job_id=str(job_id),
            status="fallback",
        )
        await client.aclose()
        return None


async def close_analysis_job_subscription(
    subscription: tuple[Redis, PubSub] | None,
) -> None:
    if subscription is None:
        return

    client, pubsub = subscription
    try:
        await pubsub.aclose()
    except Exception as exc:
        log_event(
            logger,
            "analysis_job_event_pubsub_close_failed",
            level="warning",
            error=str(exc),
            status="ignored",
        )
    finally:
        await client.aclose()
