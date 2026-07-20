"""Fetcher HTTP unico per l'ingestion.

Protezioni:
- allowlist di domini (config), verificata anche a ogni redirect;
- solo https;
- blocco di IP privati/loopback/link-local (anti-SSRF);
- timeout e limite di dimensione;
- validazione del content type;
- redazione dei segreti nei log (mai loggare header o query con chiavi).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from app.config import get_settings

ALLOWED_CONTENT_TYPES = (
    "application/json", "application/xml", "text/xml", "text/html",
    "text/plain", "application/rss+xml", "application/atom+xml",
)


class FetchError(Exception):
    pass


def _host_allowed(host: str, allowed: list[str]) -> bool:
    host = host.lower()
    return any(host == d or host.endswith("." + d) for d in allowed)


def _resolves_to_public_ip(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def validate_url(url: str) -> None:
    settings = get_settings()
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise FetchError("Solo https è consentito per l'ingestion")
    if not parsed.hostname or not _host_allowed(parsed.hostname, settings.allowed_domains):
        raise FetchError(f"Dominio non in allowlist: {parsed.hostname}")
    if not _resolves_to_public_ip(parsed.hostname):
        raise FetchError(f"Il dominio non risolve a un IP pubblico: {parsed.hostname}")


def safe_fetch(url: str, headers: dict[str, str] | None = None,
               max_bytes: int | None = None) -> httpx.Response:
    """GET con tutte le protezioni. Ogni redirect viene rivalidato.

    `max_bytes` consente un limite maggiore per endpoint bulk noti
    (es. elenco asset del provider); il default resta prudente."""
    settings = get_settings()
    limit = max_bytes or settings.ingest_max_bytes
    validate_url(url)
    with httpx.Client(
        timeout=settings.ingest_timeout_seconds,
        follow_redirects=False,
        headers=headers or {},
    ) as client:
        current = url
        for _ in range(5):  # max 5 redirect
            resp = client.get(current)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location", "")
                validate_url(location)
                current = location
                continue
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype and not any(ctype == t for t in ALLOWED_CONTENT_TYPES):
                raise FetchError(f"Content type non consentito: {ctype}")
            if len(resp.content) > limit:
                raise FetchError("Documento oltre il limite di dimensione")
            return resp
        raise FetchError("Troppi redirect")
