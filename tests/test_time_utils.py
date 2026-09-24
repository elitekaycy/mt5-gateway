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


def test_zone_override_follows_dst_for_the_instant_converted(monkeypatch):
    # Europe/Athens: UTC+2 in January, UTC+3 in July. A zone survives DST; a fixed
    # seconds value does not.
    monkeypatch.setenv("MT5_SERVER_TIME_ZONE", "Europe/Athens")
    january = 1_767_225_600  # 2026-01-01T00:00:00Z
    july = 1_782_864_000  # 2026-07-01T00:00:00Z

    assert utc_epoch_to_server(january) == january + 2 * _HOUR
    assert utc_epoch_to_server(july) == july + 3 * _HOUR
    assert resolve_offset_seconds(at_epoch=july) == 3 * _HOUR


def test_zone_override_wins_over_seconds_env_and_derived(monkeypatch):
    monkeypatch.setenv("MT5_SERVER_TIME_ZONE", "Etc/UTC")
    monkeypatch.setenv("MT5_SERVER_UTC_OFFSET_SECONDS", "10800")
    set_derived_offset(7200)

    assert utc_epoch_to_server(1_000_000) == 1_000_000


def test_derive_from_tick_caches_and_reports_its_source():
    from time_utils import derive_from_tick, offset_status

    now = 1_785_000_000
    assert derive_from_tick("BTCUSDm", now + 3, utc_now=now) == 0
    status = offset_status(now=now + 12)
    assert status["offset_seconds"] == 0
    assert status["source"] == "derived"
    assert status["symbol"] == "BTCUSDm"
    assert status["age_seconds"] == 12


def test_derive_from_tick_ignores_a_stale_tick_and_keeps_the_cache():
    from time_utils import derive_from_tick

    now = 1_785_000_000
    assert derive_from_tick("EURUSDm", now + 3 * _HOUR, utc_now=now) == 3 * _HOUR
    # 2.5h off: stale, rejected, cache untouched.
    assert derive_from_tick("EURUSDm", now + 9000, utc_now=now) is None
    assert resolve_offset_seconds() == 3 * _HOUR


def test_a_changed_offset_is_adopted_only_once_confirmed(caplog):
    # A DST switch: the new value arrives twice in a row and is adopted, with a WARNING.
    from time_utils import derive_from_tick

    now = 1_785_000_000
    derive_from_tick("EURUSDm", now + 3 * _HOUR, utc_now=now)
    with caplog.at_level("WARNING", logger="time_utils"):
        derive_from_tick("EURUSDm", now + 2 * _HOUR, utc_now=now)
        assert resolve_offset_seconds() == 3 * _HOUR
        derive_from_tick("EURUSDm", now + 600 + 2 * _HOUR, utc_now=now + 600)
    assert resolve_offset_seconds() == 2 * _HOUR
    assert any("10800 -> 7200" in record.getMessage() for record in caplog.records)


def test_a_single_disagreeing_reading_never_replaces_the_offset():
    # The 2026-09-23 incident: one reading of -3600 on a UTC server must not stick.
    from time_utils import derive_from_tick

    now = 1_785_000_000
    derive_from_tick("BTCUSDm", now + 1, utc_now=now)
    derive_from_tick("BTCUSDm", now + 600 - _HOUR, utc_now=now + 600)
    derive_from_tick("BTCUSDm", now + 1200 + 1, utc_now=now + 1200)
    derive_from_tick("BTCUSDm", now + 1800 - _HOUR, utc_now=now + 1800)

    assert resolve_offset_seconds() == 0


def test_the_confirmation_count_is_configurable(monkeypatch):
    from time_utils import derive_from_tick

    monkeypatch.setenv("MT5_TIME_OFFSET_CONFIRMATIONS", "3")
    now = 1_785_000_000
    derive_from_tick("EURUSDm", now + 3 * _HOUR, utc_now=now)
    for step in (1, 2):
        derive_from_tick("EURUSDm", now + step + 2 * _HOUR, utc_now=now + step)
        assert resolve_offset_seconds() == 3 * _HOUR
    derive_from_tick("EURUSDm", now + 3 + 2 * _HOUR, utc_now=now + 3)
    assert resolve_offset_seconds() == 2 * _HOUR


def test_clearing_the_offset_also_drops_a_pending_candidate():
    from time_utils import derive_from_tick

    now = 1_785_000_000
    derive_from_tick("EURUSDm", now, utc_now=now)
    derive_from_tick("EURUSDm", now + _HOUR, utc_now=now)
    set_derived_offset(None)
    derive_from_tick("EURUSDm", now + _HOUR, utc_now=now)

    assert resolve_offset_seconds() == _HOUR


def test_live_tick_is_the_freshest_symbol_whose_quote_advanced():
    from time_utils import live_tick

    before = {"EURUSDm": 1_000, "BTCUSDm": 5_000, "XAUUSDm": 9_000}
    after = {"EURUSDm": 1_250, "BTCUSDm": 5_400, "XAUUSDm": 9_000}
    # XAUUSDm is newest but did not move; BTCUSDm is the freshest live quote.
    assert live_tick(before, after) == ("BTCUSDm", 5_400)


def test_live_tick_is_none_when_every_quote_is_frozen():
    # A stalled feed, however old, repeats its last tick and never derives.
    from time_utils import live_tick

    frozen = {"EURUSDm": 1_000, "BTCUSDm": 5_000}
    assert live_tick(frozen, dict(frozen)) is None
    assert live_tick({}, {"BTCUSDm": 5_000}) is None
    assert live_tick({"BTCUSDm": 5_000}, {"BTCUSDm": None}) is None


def test_a_cached_offset_older_than_the_max_age_is_not_used_for_gtd(monkeypatch):
    from time_utils import derive_from_tick

    monkeypatch.setenv("MT5_TIME_MAX_OFFSET_AGE_SECONDS", "3600")
    now = 1_785_000_000
    derive_from_tick("EURUSDm", now + 3 * _HOUR, utc_now=now)

    assert utc_epoch_to_server(now + 1800, utc_now=now + 1800) == now + 1800 + 3 * _HOUR
    with pytest.raises(ServerOffsetUnavailable):
        utc_epoch_to_server(now + 7200, utc_now=now + 7200)


def test_status_reports_unresolved_when_nothing_is_known():
    from time_utils import offset_status

    status = offset_status(now=1_785_000_000)
    assert status == {
        "offset_seconds": None,
        "source": None,
        "symbol": None,
        "derived_at": None,
        "age_seconds": None,
    }
