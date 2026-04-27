from __future__ import annotations

import ipaddress

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.core.config import settings


def _is_trusted_proxy(host: str | None) -> bool:
    if host is None:
        return False
    trusted_values = [value.strip() for value in settings.trusted_proxy_ips if value.strip()]
    if not trusted_values:
        return False
    try:
        client_ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    for trusted_value in trusted_values:
        try:
            network = ipaddress.ip_network(trusted_value, strict=False)
        except ValueError:
            try:
                if client_ip == ipaddress.ip_address(trusted_value):
                    return True
            except ValueError:
                continue
        else:
            if client_ip in network:
                return True
    return False


# Key function: use the real IP from X-Forwarded-For when behind a proxy,
# falling back to the direct client address.
def _get_client_ip(request: Request) -> str:
    remote_host = request.client.host if request.client is not None else None
    if _is_trusted_proxy(remote_host):
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            candidate = forwarded_for.split(",")[0].strip()
            if candidate:
                return candidate
        real_ip = request.headers.get("X-Real-IP")
        if real_ip and real_ip.strip():
            return real_ip.strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_get_client_ip, default_limits=[])
