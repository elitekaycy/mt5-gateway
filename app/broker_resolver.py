"""Resolve an MT5 broker server name to a connectable address, headless.

MT5 under Wine cannot discover a broker by name on a fresh volume: the encrypted
broker directory ``servers.dat`` must already list the server, and there is no
headless way to make MT5 populate it by name. But MT5 *can* connect to a raw
access-point address passed in the startup config as ``Server=<host:port>``, and
once connected it writes the directory entry itself. This module turns a broker's
server NAME (e.g. ``Exness-MT5Trial9``) into that address by querying a
broker-search service that mirrors MetaQuotes' broker directory, so the operator
supplies only the name and never needs to know an IP.

The service (self-hosted ``timurila/mt5rest`` sidecar, public ``mt5.mtapi.io`` as
fallback) answers ``GET /Search?company=<keyword>`` with
``[{companyName, results:[{name:<server>, access:[<host:port>, ...]}]}]``.

Pure logic (keyword derivation, response parsing, address precedence) is separated
from the one network call so it is unit-testable without a live service.
e.g. keyword of ``Exness-MT5Trial9`` -> ``Exness``; that search response ->
``["96.0.46.31:443", ...]``.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

# Broker-search services queried in priority order. The first is a self-hosted
# sidecar (in-network, no rate limits); the public host is the fallback. Override
# or extend with MT5_RESOLVER_URL (comma-separated base URLs).
DEFAULT_RESOLVERS = ("http://mt5-resolver:80", "https://mt5.mtapi.io")

_FALSY = {"0", "false", "no", "off"}


def resolver_urls(env) -> list:
    """Resolver base URLs in priority order, from MT5_RESOLVER_URL or defaults."""
    raw = env.get("MT5_RESOLVER_URL", "").strip()
    if raw:
        return [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]
    return [u.rstrip("/") for u in DEFAULT_RESOLVERS]


def derive_keyword(server_name: str) -> str:
    """Search keyword for a server name: the token before the first '-'.

    The service matches this against server names as a prefix, so the broker part
    is enough. e.g. ``Exness-MT5Trial9`` -> ``Exness``; ``ICMarketsSC-Demo`` ->
    ``ICMarketsSC`` (which matches ``ICMarketsSC-Demo``).
    """
    return server_name.split("-", 1)[0].strip()


def parse_access(search_json_text: str, server_name: str) -> list:
    """Access endpoints for an exact server-name match in a /Search response.

    Returns the ordered, de-duplicated ``access`` list (``host:port`` strings) of
    the record whose ``name`` equals ``server_name`` (case-insensitive), or [].
    """
    try:
        data = json.loads(search_json_text)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    target = server_name.strip().lower()
    out: list = []
    for company in data:
        if not isinstance(company, dict):
            continue
        for server in company.get("results") or []:
            if str(server.get("name", "")).strip().lower() != target:
                continue
            for endpoint in server.get("access") or []:
                endpoint = str(endpoint).strip()
                if endpoint and endpoint not in out:
                    out.append(endpoint)
    return out


def _fetch(url: str, timeout: float) -> str:
    """Fetch a URL and return the body text. Seam for tests to substitute."""
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def resolve_access(server_name: str, urls, timeout: float = 15.0, fetch=_fetch) -> list:
    """Access endpoints for ``server_name``, querying resolvers in order.

    Returns the first non-empty match (list of ``host:port`` strings), or [] if no
    resolver knows the server. A resolver that errors is skipped, not fatal.
    """
    if not server_name:
        return []
    query = urllib.parse.quote(derive_keyword(server_name))
    for base in urls:
        url = f"{base}/Search?company={query}"
        try:
            body = fetch(url, timeout)
        except Exception as exc:  # network/HTTP/decoding — try the next resolver
            logger.warning("broker resolver %s failed: %s", base, exc)
            continue
        access = parse_access(body, server_name)
        if access:
            logger.info("resolved %s -> %s via %s", server_name, access, base)
            return access
        logger.info("resolver %s returned no match for %s", base, server_name)
    logger.warning("no access points resolved for %s", server_name)
    return []


def choose_server(env, fetch=_fetch) -> str:
    """Final ``Server=`` value for the startup ini, resolving the name if needed.

    Precedence:
      1. ``MT5_SERVER_ADDR`` (explicit ``host:port`` override) — skip resolution.
      2. A resolved access point for ``MT5_SERVER`` — the universal headless path.
      3. ``MT5_SERVER`` name unchanged — baked-directory fallback (majors), also
         used when the resolver is unreachable or ``MT5_AUTORESOLVE`` is off.

    Returns "" when no server is configured. e.g. MT5_SERVER="Exness-MT5Trial9"
    with a reachable resolver -> "96.0.46.31:443"; resolver down -> the name.
    """
    addr = env.get("MT5_SERVER_ADDR", "").strip()
    if addr:
        return addr
    name = env.get("MT5_SERVER", "").strip()
    if not name:
        return ""
    if env.get("MT5_AUTORESOLVE", "1").strip().lower() in _FALSY:
        return name
    access = resolve_access(name, resolver_urls(env), fetch=fetch)
    return access[0] if access else name
