from __future__ import annotations

from starlette.requests import Request

from backend.api import rate_limit


def _request_for(*, host: str, xff: str | None = None, x_real_ip: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("utf-8")))
    if x_real_ip is not None:
        headers.append((b"x-real-ip", x_real_ip.encode("utf-8")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": (host, 1234),
        }
    )


def test_get_client_ip_uses_remote_host_without_forwarded_headers(monkeypatch) -> None:
    monkeypatch.setattr(rate_limit.settings, "trusted_proxy_ips", [])
    request = _request_for(host="198.51.100.7")
    assert rate_limit._get_client_ip(request) == "198.51.100.7"


def test_get_client_ip_ignores_spoofed_xff_from_untrusted_client(monkeypatch) -> None:
    monkeypatch.setattr(rate_limit.settings, "trusted_proxy_ips", ["10.0.0.0/8"])
    request = _request_for(host="198.51.100.7", xff="203.0.113.9")
    assert rate_limit._get_client_ip(request) == "198.51.100.7"


def test_get_client_ip_trusts_xff_from_trusted_proxy(monkeypatch) -> None:
    monkeypatch.setattr(rate_limit.settings, "trusted_proxy_ips", ["10.0.0.0/8"])
    request = _request_for(host="10.1.2.3", xff="203.0.113.9, 10.1.2.3")
    assert rate_limit._get_client_ip(request) == "203.0.113.9"
