from __future__ import annotations

from typing import Any, Literal

GoalTemplate = Literal[
    "paid_social_hook",
    "ugc_native_social",
    "landing_page_clarity",
    "email_clickthrough",
    "education_explainer",
    "brand_story_film",
]
AnalysisChannel = Literal[
    "meta_feed",
    "instagram_reels",
    "tiktok",
    "youtube_pre_roll",
    "landing_page",
    "email",
]
AnalysisMediaType = Literal["video", "audio", "text"]

GOAL_TEMPLATE_ALIASES: dict[str, GoalTemplate] = {
    "brand_story": "brand_story_film",
}

CHANNEL_ALIASES: dict[str, AnalysisChannel] = {}

GOAL_TEMPLATE_OPTIONS: list[dict[str, Any]] = [
    {
        "value": "paid_social_hook",
        "label": "Paid social hook",
        "description": "Front-loaded hold strength, pacing, and CTA readiness.",
        "supported_media_types": ["video", "audio"],
        "default_channel": "meta_feed",
        "group_id": "paid_social",
    },
    {
        "value": "ugc_native_social",
        "label": "UGC / native social",
        "description": "Authenticity, creator pacing, and native platform fit.",
        "supported_media_types": ["video"],
        "default_channel": "tiktok",
        "group_id": "paid_social",
    },
    {
        "value": "landing_page_clarity",
        "label": "Landing page hero",
        "description": "Message clarity, cognitive load, and conversion friction above the fold.",
        "supported_media_types": ["video", "text"],
        "default_channel": "landing_page",
        "group_id": "web_conversion",
    },
    {
        "value": "email_clickthrough",
        "label": "Email clickthrough",
        "description": "Subject-to-body continuity, scanning flow, and CTA intent.",
        "supported_media_types": ["text"],
        "default_channel": "email",
        "group_id": "web_conversion",
    },
    {
        "value": "education_explainer",
        "label": "Education / explainer",
        "description": "Comprehension, retention, and overload risk.",
        "supported_media_types": ["video", "audio", "text"],
        "default_channel": "youtube_pre_roll",
        "group_id": "education",
    },
    {
        "value": "brand_story_film",
        "label": "Brand film",
        "description": "Memory lift, emotional continuity, and brand anchoring.",
        "supported_media_types": ["video", "audio"],
        "default_channel": "youtube_pre_roll",
        "group_id": "storytelling",
    },
]

CHANNEL_OPTIONS: list[dict[str, Any]] = [
    {
        "value": "meta_feed",
        "label": "Meta feed",
        "supported_media_types": ["video", "audio"],
    },
    {
        "value": "instagram_reels",
        "label": "Instagram Reels",
        "supported_media_types": ["video"],
    },
    {
        "value": "tiktok",
        "label": "TikTok",
        "supported_media_types": ["video"],
    },
    {
        "value": "youtube_pre_roll",
        "label": "YouTube pre-roll",
        "supported_media_types": ["video", "audio"],
    },
    {
        "value": "landing_page",
        "label": "Landing page",
        "supported_media_types": ["video", "text"],
    },
    {
        "value": "email",
        "label": "Email",
        "supported_media_types": ["text"],
    },
]

GOAL_PRESET_GROUPS: list[dict[str, Any]] = [
    {
        "id": "paid_social",
        "label": "Paid social",
        "description": "Fast hook and native-feed review modes for short-form launches.",
        "template_values": ["paid_social_hook", "ugc_native_social"],
    },
    {
        "id": "web_conversion",
        "label": "Web conversion",
        "description": "Message clarity and clickthrough workflows for owned surfaces.",
        "template_values": ["landing_page_clarity", "email_clickthrough"],
    },
    {
        "id": "education",
        "label": "Education",
        "description": "Teaching-oriented reviews for explainers, demos, and onboarding content.",
        "template_values": ["education_explainer"],
    },
    {
        "id": "storytelling",
        "label": "Storytelling",
        "description": "Memory, emotion, and brand anchoring for campaign films.",
        "template_values": ["brand_story_film"],
    },
]

GOAL_SUGGESTIONS: list[dict[str, Any]] = [
    {
        "media_type": "video",
        "goal_template": "paid_social_hook",
        "channel": "meta_feed",
        "audience_placeholder": "Cold prospecting, retargeting, creator-led lookalikes",
        "rationale": "Video uploads usually benefit from a short-form hook review first.",
    },
    {
        "media_type": "audio",
        "goal_template": "education_explainer",
        "channel": "youtube_pre_roll",
        "audience_placeholder": "Podcast listeners, webinar registrants, warm audio audiences",
        "rationale": "Audio assets usually need pacing and comprehension checks before channel-specific polish.",
    },
    {
        "media_type": "text",
        "goal_template": "landing_page_clarity",
        "channel": "landing_page",
        "audience_placeholder": "New visitors, ICP accounts, lifecycle email segments",
        "rationale": "Text uploads usually start with clarity and conversion-friction review.",
    },
]


def normalize_goal_template(value: str | None) -> GoalTemplate | None:
    normalized = _normalize_token(value)
    if normalized is None:
        return None
    if normalized in GOAL_TEMPLATE_ALIASES:
        return GOAL_TEMPLATE_ALIASES[normalized]
    for option in GOAL_TEMPLATE_OPTIONS:
        if option["value"] == normalized:
            return option["value"]
    return None


def normalize_analysis_channel(value: str | None) -> AnalysisChannel | None:
    normalized = _normalize_token(value)
    if normalized is None:
        return None
    if normalized in CHANNEL_ALIASES:
        return CHANNEL_ALIASES[normalized]
    for option in CHANNEL_OPTIONS:
        if option["value"] == normalized:
            return option["value"]
    return None


def get_goal_presets_payload() -> dict[str, Any]:
    return {
        "goal_templates": GOAL_TEMPLATE_OPTIONS,
        "channels": CHANNEL_OPTIONS,
        "preset_groups": GOAL_PRESET_GROUPS,
        "suggestions": GOAL_SUGGESTIONS,
    }


def _normalize_token(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized.lower()
