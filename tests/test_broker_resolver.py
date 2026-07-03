import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from broker_resolver import (
    choose_server,
    connect_candidates,
    derive_keyword,
    parse_access,
    resolve_access,
    resolver_urls,
    table_access,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "search_exness.json")

# A small in-test baked table, so tests don't depend on the shipped broker_servers.json.
TABLE = {
    "Exness-MT5Trial9": ["10.0.0.1:443", "10.0.0.2:443"],
    "ICMarketsSC-Demo": ["10.0.1.1:443"],
}


def _fixture_text():
    with open(FIXTURE, encoding="utf-8") as handle:
        return handle.read()


def test_derive_keyword_takes_token_before_first_dash():
    assert derive_keyword("Exness-MT5Trial9") == "Exness"
    assert derive_keyword("ICMarketsSC-Demo") == "ICMarketsSC"
    assert derive_keyword("FTMO-Server3") == "FTMO"


def test_parse_access_exact_matches_server_name():
    access = parse_access(_fixture_text(), "Exness-MT5Trial9")
    # 96.0.46.31 is the access point the live gateway actually connected to.
    assert "96.0.46.31:443" in access
    assert all(":" in endpoint for endpoint in access)
    assert len(access) == len(set(access))


def test_parse_access_unknown_or_bad_is_empty():
    assert parse_access(_fixture_text(), "NoSuchBroker-Demo") == []
    assert parse_access("not json", "Exness-MT5Trial9") == []
    assert parse_access("{}", "Exness-MT5Trial9") == []


def test_table_access_is_case_insensitive():
    assert table_access("Exness-MT5Trial9", TABLE) == ["10.0.0.1:443", "10.0.0.2:443"]
    assert table_access("exness-mt5trial9", TABLE) == ["10.0.0.1:443", "10.0.0.2:443"]
    assert table_access("Unknown-Demo", TABLE) == []


def test_shipped_table_is_loadable_and_covers_demo():
    # The harvested broker_servers.json ships in the image; sanity-check it parses
    # and contains a known server with access points.
    from broker_resolver import load_table

    servers = load_table()
    assert isinstance(servers, dict) and servers
    assert servers.get("Exness-MT5Trial9"), "demo server missing from baked table"


def test_resolver_urls_defaults_and_override():
    assert resolver_urls({}) == ["https://mt5.mtapi.io", "http://mt5-resolver:80"]
    assert resolver_urls({"MT5_RESOLVER_URL": "http://a:80/, https://b "}) == [
        "http://a:80",
        "https://b",
    ]


def test_resolve_access_uses_first_resolver_that_matches():
    calls = []

    def fake_fetch(url, timeout):
        calls.append(url)
        if "mtapi.io" in url:
            return _fixture_text()
        raise OSError("sidecar down")

    access = resolve_access(
        "Exness-MT5Trial9",
        ["http://mt5-resolver:80", "https://mt5.mtapi.io"],
        fetch=fake_fetch,
    )
    assert "96.0.46.31:443" in access
    assert len(calls) == 2  # first errored, fell through to the second


def test_connect_candidates_cascade_order():
    # Baked table first, then resolver access points, then the name last.
    candidates = connect_candidates(
        {"MT5_SERVER": "Exness-MT5Trial9", "MT5_RESOLVER_URL": "https://mt5.mtapi.io"},
        fetch=lambda url, timeout: _fixture_text(),
        table=TABLE,
    )
    assert candidates[0] == "10.0.0.1:443"  # baked table wins
    assert candidates[1] == "10.0.0.2:443"
    assert "96.0.46.31:443" in candidates  # resolver contributes its access points
    assert candidates[-1] == "Exness-MT5Trial9"  # name is the final fallback
    assert len(candidates) == len(set(candidates))  # de-duplicated


def test_connect_candidates_falls_through_when_table_misses():
    candidates = connect_candidates(
        {"MT5_SERVER": "Exness-MT5Trial9", "MT5_RESOLVER_URL": "https://mt5.mtapi.io"},
        fetch=lambda url, timeout: _fixture_text(),
        table={},  # not in the baked table -> resolver supplies addresses
    )
    assert candidates[0] == parse_access(_fixture_text(), "Exness-MT5Trial9")[0]
    assert candidates[-1] == "Exness-MT5Trial9"


def test_connect_candidates_explicit_addr_wins():
    def fetch_must_not_run(url, timeout):
        raise AssertionError("resolver should not be queried when addr is set")

    candidates = connect_candidates(
        {"MT5_SERVER": "Exness-MT5Trial9", "MT5_SERVER_ADDR": "1.2.3.4:443"},
        fetch=fetch_must_not_run,
        table=TABLE,
    )
    assert candidates == ["1.2.3.4:443"]


def test_connect_candidates_autoresolve_off_skips_network():
    def fetch_must_not_run(url, timeout):
        raise AssertionError("resolver should not run when autoresolve is off")

    candidates = connect_candidates(
        {"MT5_SERVER": "ICMarketsSC-Demo", "MT5_AUTORESOLVE": "0"},
        fetch=fetch_must_not_run,
        table=TABLE,
    )
    # Baked table + name only; no network query.
    assert candidates == ["10.0.1.1:443", "ICMarketsSC-Demo"]


def test_connect_candidates_empty_without_server():
    assert connect_candidates({}) == []


def test_choose_server_returns_first_candidate():
    assert choose_server({"MT5_SERVER": "Exness-MT5Trial9"}, table=TABLE) == "10.0.0.1:443"
    assert choose_server({}) == ""
