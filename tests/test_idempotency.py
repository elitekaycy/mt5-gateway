from idempotency import (
    Decision,
    IdempotencyStore,
    magic_from_key,
    request_fingerprint,
)


def test_duplicate_key_replays_completed_response():
    store = IdempotencyStore()
    fingerprint = request_fingerprint({"symbol": "EURUSD", "volume": 0.1})

    assert store.begin("order-1", fingerprint) == (Decision.NEW, None)
    store.complete("order-1", fingerprint, {"order": 123}, 200)

    decision, response = store.begin("order-1", fingerprint)
    assert decision is Decision.REPLAY
    assert response.payload == {"order": 123}
    assert response.status_code == 200


def test_same_key_with_different_parameters_is_conflict():
    store = IdempotencyStore()
    first = request_fingerprint({"volume": 0.1})
    second = request_fingerprint({"volume": 0.2})

    store.begin("order-1", first)

    assert store.begin("order-1", second) == (Decision.CONFLICT, None)


def test_in_flight_duplicate_does_not_get_a_second_reservation():
    store = IdempotencyStore()
    fingerprint = request_fingerprint({"volume": 0.1})

    store.begin("order-1", fingerprint)

    assert store.begin("order-1", fingerprint) == (Decision.IN_PROGRESS, None)


def test_key_can_be_reused_after_ttl_expiry():
    now = [100.0]
    store = IdempotencyStore(ttl_seconds=60, clock=lambda: now[0])
    fingerprint = request_fingerprint({"volume": 0.1})
    store.begin("order-1", fingerprint)
    store.complete("order-1", fingerprint, {"order": 123}, 200)

    now[0] += 60

    assert store.begin("order-1", fingerprint) == (Decision.NEW, None)


def test_fingerprint_ignores_body_key_and_magic_is_stable():
    assert request_fingerprint(
        {"volume": 0.1, "client_order_id": "body-key"}
    ) == request_fingerprint({"volume": 0.1})
    assert magic_from_key("order-1") == magic_from_key("order-1")
    assert 0 < magic_from_key("order-1") <= 0xFFFFFFFF
