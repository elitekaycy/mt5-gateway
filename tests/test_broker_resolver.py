import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from broker_resolver import (
    choose_server,
    derive_keyword,
    parse_access,
    resolve_access,
    resolver_urls,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "search_exness.json")


def _fixture_text():
    with open(FIXTURE, encoding="utf-8") as handle:
        return handle.read()


def test_derive_keyword_takes_token_before_first_dash():
    assert derive_keyword("Exness-MT5Trial9") == "Exness"
    assert derive_keyword("ICMarketsSC-Demo") == "ICMarketsSC"
    assert derive_keyword("FTMO-Server3") == "FTMO"


def test_parse_access_exact_matches_server_name():
    access = parse_access(_fixture_text(), "Exness-MT5Trial9")
    # The real captured response lists this server's access points; 96.0.46.31 is
    # the access point the live gateway actually connected to.
    assert "96.0.46.31:443" in access
    assert all(":" in endpoint for endpoint in access)
    assert len(access) == len(set(access))  # de-duplicated


def test_parse_access_is_case_insensitive_on_name():
    assert parse_access(_fixture_text(), "exness-mt5trial9")


def test_parse_access_unknown_server_is_empty():
    assert parse_access(_fixture_text(), "NoSuchBroker-Demo") == []


def test_parse_access_bad_json_is_empty():
    assert parse_access("not json", "Exness-MT5Trial9") == []
    assert parse_access("{}", "Exness-MT5Trial9") == []


def test_resolver_urls_defaults_and_override():
    assert resolver_urls({}) == ["http://mt5-resolver:80", "https://mt5.mtapi.io"]
    assert resolver_urls({"MT5_RESOLVER_URL": "http://a:80/, https://b "}) == [
        "http://a:80",
        "https://b",
    ]


def test_resolve_access_uses_first_resolver_that_matches():
    calls = []

    def fake_fetch(url, timeout):
        calls.append(url)
        if "mt5.mtapi.io" in url:
            return _fixture_text()
        raise OSError("sidecar down")

    access = resolve_access(
        "Exness-MT5Trial9",
        ["http://mt5-resolver:80", "https://mt5.mtapi.io"],
        fetch=fake_fetch,
    )
    assert "96.0.46.31:443" in access
    # First resolver errored; it fell through to the second.
    assert len(calls) == 2
    assert "company=Exness" in calls[0]


def test_choose_server_prefers_explicit_addr():
    def fetch_must_not_run(url, timeout):
        raise AssertionError("resolver should not be queried when addr is set")

    server = choose_server(
        {"MT5_SERVER": "Exness-MT5Trial9", "MT5_SERVER_ADDR": "1.2.3.4:443"},
        fetch=fetch_must_not_run,
    )
    assert server == "1.2.3.4:443"


def test_choose_server_resolves_name_to_address():
    server = choose_server(
        {"MT5_SERVER": "Exness-MT5Trial9"},
        fetch=lambda url, timeout: _fixture_text(),
    )
    assert server == parse_access(_fixture_text(), "Exness-MT5Trial9")[0]


def test_choose_server_falls_back_to_name_when_unresolved():
    server = choose_server(
        {"MT5_SERVER": "Exotic-Demo"},
        fetch=lambda url, timeout: "[]",
    )
    assert server == "Exotic-Demo"


def test_choose_server_autoresolve_off_keeps_name():
    def fetch_must_not_run(url, timeout):
        raise AssertionError("resolver should not run when autoresolve is off")

    server = choose_server(
        {"MT5_SERVER": "Exness-MT5Trial9", "MT5_AUTORESOLVE": "0"},
        fetch=fetch_must_not_run,
    )
    assert server == "Exness-MT5Trial9"


def test_choose_server_empty_without_server():
    assert choose_server({}) == ""
