# Analysis Stream Validation and Ops Checklist

Date: 2026-04-27  
Scope: `/api/v1/analysis/jobs/{job_id}/events` SSE transport with Redis pub/sub + polling fallback.

## Reverse Proxy Validation Checklist

- Confirm upstream sends:
  - `Content-Type: text/event-stream`
  - `Cache-Control: no-cache`
  - `Connection: keep-alive`
  - `X-Accel-Buffering: no`
- Confirm proxy config keeps SSE stream open:
  - `proxy_http_version 1.1`
  - `proxy_buffering off`
  - `proxy_read_timeout` >= 75s
  - no gzip/compression on SSE path
- Confirm heartbeat event observed at <= 15s while job active.
- Confirm terminal `done` event emitted on `completed` and `failed`.

## Worker + Redis Validation Matrix

| Scenario | Expected | Result |
| --- | --- | --- |
| Redis available + running workers | Stream mode stays live; progress events emitted | Passed |
| Redis unavailable during session open | API falls back to snapshot polling mode | Passed |
| SSE disconnect from client | Client reconnects; fallback event tracked | Passed |
| Long-running job through proxy | Heartbeats prevent silent proxy close | Passed |

## Metrics Added for Observability

Metrics exposed on `/metrics`:

- `analysis_stream_sessions_total{mode=...}`
- `analysis_stream_session_seconds_*{mode=...,close_reason=...}`
- `analysis_stream_fallback_total{source=...}` (server fallback) and `{mode=...}` (client fallback telemetry)
- `analysis_stream_decode_errors_total`
- `analysis_stream_connected_total`
- `analysis_stream_reconnect_count_*{mode=...}`
- `analysis_client_events_total{event=...,media_type=...}`

Use these dashboards/alerts:

- Stream error rate: `analysis_stream_decode_errors_total / analysis_stream_sessions_total`
- Fallback frequency: `analysis_stream_fallback_total / analysis_stream_sessions_total`
- Reconnect pressure: percentile on `analysis_stream_reconnect_count`
- Session duration regression: `analysis_stream_session_seconds_sum / analysis_stream_session_seconds_count`

## Release Gate

Mark release-ready only when:

- no sustained increase in fallback ratio after deploy,
- decode errors remain near zero,
- median stream duration tracks median job duration for active runs,
- reconnect spikes are investigated within same business day.
