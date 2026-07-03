from collections import namedtuple

import pytest

import lib


Position = namedtuple("Position", "ticket type magic")
Result = namedtuple("Result", "retcode comment volume")


@pytest.fixture
def positions(monkeypatch):
    values = (Position(1, 0, 7), Position(2, 1, 7))
    monkeypatch.setattr(lib.mt5, "positions_total", lambda: 2, raising=False)
    monkeypatch.setattr(lib.mt5, "positions_get", lambda: values, raising=False)
    return values


def test_close_all_reports_all_successes(positions, monkeypatch):
    monkeypatch.setattr(
        lib,
        "close_position",
        lambda position: Result(10009, "done", 1.0),
    )

    outcome = lib.close_all_positions()

    assert len(outcome["closed"]) == 2
    assert outcome["failed"] == []


def test_close_all_reports_partial_as_success(positions, monkeypatch):
    monkeypatch.setattr(
        lib,
        "close_position",
        lambda position: Result(10010, "partial", 0.5),
    )

    outcome = lib.close_all_positions()

    assert all(result["partial"] for result in outcome["closed"])
    assert outcome["failed"] == []


def test_close_all_lists_failed_tickets(positions, monkeypatch):
    def close(position):
        if int(position["ticket"]) == 1:
            return Result(10009, "done", 1.0)
        return Result(10019, "no money", 0.0)

    monkeypatch.setattr(lib, "close_position", close)

    outcome = lib.close_all_positions()

    assert len(outcome["closed"]) == 1
    assert outcome["failed"] == [
        {
            "ticket": 2,
            "retcode": 10019,
            "retcode_name": "NO_MONEY",
            "comment": "no money",
        }
    ]


def test_close_all_reports_all_failures(positions, monkeypatch):
    monkeypatch.setattr(lib, "close_position", lambda position: None)

    outcome = lib.close_all_positions()

    assert outcome["closed"] == []
    assert [failure["ticket"] for failure in outcome["failed"]] == [1, 2]
