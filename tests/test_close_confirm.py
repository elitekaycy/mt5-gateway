"""Closes report the executed deal. Dealer-desk servers (The5ers'
FivePercentOnline) acknowledge a close with price 0.0 and deal 0; relaying that
made qkt book an entry-sized loss and flatten a live book on 2026-09-24."""

from collections import namedtuple
from types import SimpleNamespace

import close_confirm
import pytest
from flask import Flask

import lib
import routes.history as history_route
import routes.position as position_route
from mt5_connection import MT5Connection

CloseResult = namedtuple(
    "CloseResult", "retcode comment volume price order deal request_id"
)
Deal = namedtuple("Deal", "ticket order position_id entry price volume time time_msc")

OPEN = Deal(900, 800, 800, 0, 4364.0, 0.01, 1790276000, 1790276000000)
CLOSE = Deal(901, 811, 800, 1, 4256.78, 0.01, 1790276411, 1790276411052)


@pytest.fixture(autouse=True)
def fast_confirm(monkeypatch):
    monkeypatch.setattr(close_confirm, "CLOSE_CONFIRM_TIMEOUT_MS", 40)
    monkeypatch.setattr(close_confirm, "CLOSE_CONFIRM_POLL_MS", 1)


class FakeHistory:
    """history_deals_get that shows the closing deal only after `delay` reads."""

    def __init__(self, deals, delay=0):
        self.deals = deals
        self.delay = delay
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        visible = [
            d for d in self.deals if d.entry == 0 or len(self.calls) > self.delay
        ]
        if "ticket" in kwargs:
            return tuple(d for d in visible if d.ticket == kwargs["ticket"])
        if "position" in kwargs:
            return tuple(d for d in visible if d.position_id == kwargs["position"])
        return tuple(visible)


def test_async_close_is_confirmed_from_the_positions_closing_deal(monkeypatch):
    history = FakeHistory([OPEN, CLOSE], delay=2)
    monkeypatch.setattr(close_confirm.mt5, "history_deals_get", history, raising=False)
    result = {"price": 0.0, "deal": 0, "order": 811, "volume": 0.01}

    source = close_confirm.confirm_close(result, position_ticket=800, request_id="r")

    assert source == "deal"
    assert result["price"] == 4256.78
    assert result["deal"] == 901
    assert all("position" in kw and not args for args, kw in history.calls)


def test_a_close_the_server_already_priced_makes_no_extra_call(monkeypatch):
    history = FakeHistory([OPEN, CLOSE])
    monkeypatch.setattr(close_confirm.mt5, "history_deals_get", history, raising=False)
    result = {"price": 84590.23, "deal": 2721641393, "order": 3279824111}

    assert close_confirm.confirm_close(result, 3279823939, "r") == "order_send"
    assert history.calls == []


def test_an_older_partial_close_is_not_taken_for_this_close(monkeypatch):
    older = Deal(899, 805, 800, 1, 4300.0, 0.01, 1790276100, 1790276100000)
    history = FakeHistory([OPEN, older, CLOSE], delay=1)
    monkeypatch.setattr(close_confirm.mt5, "history_deals_get", history, raising=False)
    result = {"price": 0.0, "deal": 0, "order": 811}

    close_confirm.confirm_close(result, 800, "r")

    assert result["price"] == 4256.78


def test_an_unconfirmed_close_is_relayed_raw_and_says_so(monkeypatch):
    history = FakeHistory([OPEN])
    monkeypatch.setattr(close_confirm.mt5, "history_deals_get", history, raising=False)
    result = {"price": 0.0, "deal": 0, "order": 811}

    assert close_confirm.confirm_close(result, 800, "r") == "unresolved"
    assert result["price"] == 0.0


def test_a_named_deal_is_read_directly(monkeypatch):
    history = FakeHistory([OPEN, CLOSE])
    monkeypatch.setattr(close_confirm.mt5, "history_deals_get", history, raising=False)
    result = {"price": 0.0, "deal": 901, "order": 811}

    assert close_confirm.confirm_close(result, 800, "r") == "deal"
    assert result["price"] == 4256.78
    assert history.calls[0][1] == {"ticket": 901}


@pytest.fixture
def position_client(monkeypatch):
    connection = SimpleNamespace(ensure_connection=lambda: True)
    monkeypatch.setattr(
        MT5Connection, "get_instance", classmethod(lambda cls: connection)
    )
    app = Flask(__name__)
    app.register_blueprint(position_route.position_bp)
    return app.test_client()


def test_close_position_route_returns_the_confirmed_price(position_client, monkeypatch):
    monkeypatch.setattr(
        position_route,
        "close_position",
        lambda position: CloseResult(10009, "Request executed", 0.01, 0.0, 811, 0, 1),
    )
    monkeypatch.setattr(
        close_confirm.mt5,
        "history_deals_get",
        FakeHistory([OPEN, CLOSE], delay=1),
        raising=False,
    )

    body = position_client.post(
        "/close_position", json={"position": {"ticket": 800}}
    ).get_json()

    assert body["result"]["price"] == 4256.78
    assert body["result"]["deal"] == 901
    assert body["fill_price_source"] == "deal"


def test_close_all_confirms_each_close(monkeypatch):
    Position = namedtuple("Position", "ticket type magic")
    monkeypatch.setattr(lib.mt5, "positions_total", lambda: 1, raising=False)
    monkeypatch.setattr(
        lib.mt5, "positions_get", lambda: (Position(800, 0, 7),), raising=False
    )
    monkeypatch.setattr(
        lib,
        "close_position",
        lambda position: CloseResult(10009, "done", 0.01, 0.0, 811, 0, 1),
    )
    monkeypatch.setattr(
        close_confirm.mt5,
        "history_deals_get",
        FakeHistory([OPEN, CLOSE]),
        raising=False,
    )

    outcome = lib.close_all_positions()

    assert outcome["closed"][0]["price"] == 4256.78
    assert outcome["closed"][0]["fill_price_source"] == "deal"


@pytest.fixture
def history_client(monkeypatch):
    connection = SimpleNamespace(ensure_connection=lambda: True)
    monkeypatch.setattr(
        MT5Connection, "get_instance", classmethod(lambda cls: connection)
    )
    app = Flask(__name__)
    app.register_blueprint(history_route.history_bp)
    return app.test_client()


def test_history_deals_by_position_returns_only_that_position(
    history_client, monkeypatch
):
    other = Deal(950, 870, 870, 0, 1.13, 0.01, 1790276200, 1790276200000)
    history = FakeHistory([OPEN, CLOSE, other])
    monkeypatch.setattr(history_route.mt5, "history_deals_get", history, raising=False)

    rows = history_client.get(
        "/history_deals_get?from_date=2026-09-23T00:00:00Z&to_date=2026-09-25T00:00:00Z&position=800"
    ).get_json()

    assert sorted(r["ticket"] for r in rows) == [900, 901]
    assert history.calls == [((), {"position": 800})]


def test_history_deals_by_position_still_honours_the_window(
    history_client, monkeypatch
):
    monkeypatch.setattr(
        history_route.mt5,
        "history_deals_get",
        FakeHistory([OPEN, CLOSE]),
        raising=False,
    )

    rows = history_client.get(
        "/history_deals_get?from_date=2026-09-24T18:55:00Z&to_date=2026-09-25T00:00:00Z&position=800"
    ).get_json()

    assert [r["ticket"] for r in rows] == [901]
