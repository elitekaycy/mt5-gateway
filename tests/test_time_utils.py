from datetime import timezone

import pytest

from time_utils import (
    ServerOffsetUnavailable,
    derive_offset_from_server_epoch,
    parse_iso_utc,
    resolve_offset_seconds,
    server_epoch_to_utc,
    set_derived_offset,
    utc_epoch_to_server,
)

_HOUR = 3600


@pytest.fixture(autouse=True)
def _reset_offset_state(monkeypatch):
    """Isolate the module-level derived-offset cache and env between tests."""
    monkeypatch.delenv("MT5_SERVER_UTC_OFFSET_SECONDS", raising=False)
    set_derived_offset(None)
    yield
    set_derived_offset(None)


def test_iso_parser_accepts_z_offset_and_naive():
    values = [
        parse_iso_utc("2026-01-01T00:00:00Z"),
        parse_iso_utc("2026-01-01T00:00:00+00:00"),
        parse_iso_utc("2026-01-01T00:00:00"),
    ]

    assert all(value.tzinfo is timezone.utc for value in values)
    assert len(set(values)) == 1


def test_server_time_conversion_uses_configured_offset(monkeypatch):
    monkeypatch.setenv("MT5_SERVER_UTC_OFFSET_SECONDS", "7200")

    assert server_epoch_to_utc(7200).timestamp() == 0
    assert utc_epoch_to_server(0) == 7200


def test_explicit_env_offset_overrides_a_derived_value(monkeypatch):
    set_derived_offset(_HOUR)
    monkeypatch.setenv("MT5_SERVER_UTC_OFFSET_SECONDS", "10800")

    assert resolve_offset_seconds() == 10800
    assert utc_epoch_to_server(0) == 10800


def test_derived_offset_is_used_when_env_is_unset():
    set_derived_offset(10800)

    assert resolve_offset_seconds() == 10800
    assert utc_epoch_to_server(1_000_000) == 1_010_800


def test_utc_epoch_to_server_raises_when_offset_unresolved():
    with pytest.raises(ServerOffsetUnavailable):
        utc_epoch_to_server(1_000_000)


def test_server_epoch_to_utc_degrades_to_raw_server_time_when_unresolved():
    # Reads must never fail on an unknown offset; they fall back to the raw epoch.
    assert server_epoch_to_utc(0).timestamp() == 0


def test_derive_rounds_a_fresh_quote_to_a_whole_hour():
    utc_now = 1_785_000_000
    # UTC+3 server, last quote 5s old.
    assert (
        derive_offset_from_server_epoch(utc_now + 3 * _HOUR + 5, utc_now) == 3 * _HOUR
    )


def test_derive_accepts_a_utc_broker_as_zero_offset():
    utc_now = 1_785_000_000
    assert derive_offset_from_server_epoch(utc_now + 4, utc_now) == 0


def test_derive_rejects_a_stale_quote_between_hour_boundaries():
    utc_now = 1_785_000_000
    # 2.5h delta rounds to no clean hour -> quote is stale, offset untrustworthy.
    assert derive_offset_from_server_epoch(utc_now + 9000, utc_now) is None


def test_derive_rejects_an_implausible_offset():
    utc_now = 1_785_000_000
    # 20h ahead is outside any real broker-server offset even though it rounds clean.
    assert derive_offset_from_server_epoch(utc_now + 20 * _HOUR, utc_now) is None
