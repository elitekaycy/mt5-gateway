from datetime import timezone

from time_utils import parse_iso_utc, server_epoch_to_utc, utc_epoch_to_server


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
