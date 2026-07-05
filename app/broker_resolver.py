"""Resolve an MT5 broker server name to connectable addresses, headless.

MT5 under Wine cannot discover a broker by name on a fresh volume: the encrypted
broker directory ``servers.dat`` must already list the server, and there is no
headless way to make MT5 populate it by name. But MT5 *can* connect to a raw
access-point address passed in the startup config as ``Server=<host:port>``, and
once connected it writes the directory entry itself. This module turns a broker's
server NAME (e.g. ``Exness-MT5Trial9``) into that address, so the operator supplies
only the name and never needs to know an IP.

Addresses come from a self-aware cascade, tried in order, with automatic fallthrough:

1. A **baked table** (``broker_servers.json``) shipped in the image — offline,
   instant, no network. Covers the popular brokers.
2. **Resolver services** (``MT5_RESOLVER_URL``, e.g. ``mt5.mtapi.io`` then an
   optional self-hosted sidecar), which mirror MetaQuotes' live directory and so
   cover every real MT5 broker.
3. The server **name** itself, as a last resort against a baked/persisted
   ``servers.dat`` directory (major brokers).

Each source contributes all its access points; the boot tries the combined,
de-duplicated candidate list until one authorizes, so a stale entry or an unknown
broker falls through on its own. After the first connect MT5 self-seeds the live
directory, so later boots need no resolution.

Pure logic (keyword derivation, response parsing, candidate ordering) is separated
from the one network call so it is unit-testable without a live service.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Any

logger = logging.getLogger(__name__)

# Resolver services queried in priority order after the baked table. Public host
# first (always reachable, zero setup), self-hosted sidecar as the deeper fallback.
# Override or reorder with MT5_RESOLVER_URL (comma-separated base URLs).
DEFAULT_RESOLVERS = ("https://mt5.mtapi.io", "http://mt5-resolver:80")

# Baked broker directory shipped in the image (see scripts/harvest-broker-servers.py).
TABLE_PATH = os.path.join(os.path.dirname(__file__), "broker_servers.json")

_FALSY = {"0", "false", "no", "off"}


Fetch = Callable[[str, float], str]
BrokerTable = Mapping[str, Sequence[str]]


def resolver_urls(env: Mapping[str, str]) -> list[str]:
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


def load_table(path: str = TABLE_PATH) -> dict[str, list[str]]:
    """Baked ``server name -> [access host:port]`` map, or {} if absent/unreadable."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle) or {}
        servers: Any = data.get("servers", {})
        if not isinstance(servers, dict):
            return {}
        return {
            str(name): [str(endpoint) for endpoint in access]
            for name, access in servers.items()
            if isinstance(access, list)
        }
    except (OSError, ValueError):
        return {}


def table_access(server_name: str, table: BrokerTable | None = None) -> list[str]:
    """Access endpoints for ``server_name`` from the baked table (case-insensitive)."""
    entries = load_table() if table is None else table
    if server_name in entries:
        return list(entries[server_name])
    target = server_name.strip().lower()
    for name, access in entries.items():
        if name.strip().lower() == target:
            return list(access)
    return []


def parse_access(search_json_text: str, server_name: str) -> list[str]:
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
    out: list[str] = []
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
    if urllib.parse.urlsplit(url).scheme not in {"http", "https"}:
        raise ValueError("broker resolver URL must use http or https")
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        body: bytes = response.read()
        return body.decode("utf-8", "replace")


def query_resolver(
    base: str,
    server_name: str,
    timeout: float = 15.0,
    fetch: Fetch = _fetch,
) -> list[str]:
    """Access endpoints for ``server_name`` from one resolver, or [] on error/miss."""
    query = urllib.parse.quote(derive_keyword(server_name))
    try:
        body = fetch(f"{base}/Search?company={query}", timeout)
    except Exception as exc:  # network/HTTP/decoding — caller tries the next source
        logger.warning("broker resolver %s failed: %s", base, exc)
        return []
    return parse_access(body, server_name)


def resolve_access(
    server_name: str,
    urls: Sequence[str],
    timeout: float = 15.0,
    fetch: Fetch = _fetch,
) -> list[str]:
    """Access endpoints for ``server_name`` from the first resolver that matches."""
    if not server_name:
        return []
    for base in urls:
        access = query_resolver(base, server_name, timeout, fetch)
        if access:
            logger.info("resolved %s -> %s via %s", server_name, access, base)
            return access
    return []


def connect_candidates(
    env: Mapping[str, str],
    fetch: Fetch = _fetch,
    table: BrokerTable | None = None,
) -> list[str]:
    """Ordered, de-duplicated connect addresses for MT5_SERVER, most-preferred first.

    Precedence: explicit ``MT5_SERVER_ADDR``; else the baked table, then each
    resolver in ``MT5_RESOLVER_URL`` order, then the server name itself. Each source
    contributes all its access points. The boot tries them until one authorizes, so
    a stale address or an unknown broker falls through automatically. Returns [] when
    no server is configured.
    """
    addr = env.get("MT5_SERVER_ADDR", "").strip()
    if addr:
        return [addr]
    name = env.get("MT5_SERVER", "").strip()
    if not name:
        return []

    out: list[str] = []

    def add(items: Sequence[str]) -> None:
        for item in items:
            item = str(item).strip()
            if item and item not in out:
                out.append(item)

    add(table_access(name, table))
    if env.get("MT5_AUTORESOLVE", "1").strip().lower() not in _FALSY:
        for base in resolver_urls(env):
            add(query_resolver(base, name, fetch=fetch))
    add([name])  # last resort: baked/persisted servers.dat directory
    return out


def choose_server(
    env: Mapping[str, str],
    fetch: Fetch = _fetch,
    table: BrokerTable | None = None,
) -> str:
    """The single most-preferred ``Server=`` value, or "" if none configured.

    Convenience wrapper over :func:`connect_candidates` for callers that don't do
    per-candidate failover. e.g. MT5_SERVER="Exness-MT5Trial9" -> "96.0.46.31:443".
    """
    candidates = connect_candidates(env, fetch=fetch, table=table)
    return candidates[0] if candidates else ""
