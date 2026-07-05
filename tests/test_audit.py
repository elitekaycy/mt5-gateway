import json

from audit import REQUIRED_FIELDS, OrderAuditLog


def test_audit_record_is_append_only_complete_and_scrubbed(tmp_path):
    path = tmp_path / "audit.jsonl"
    audit = OrderAuditLog(path)

    audit.emit("broker_response", symbol="EURUSD", authorization="secret")
    audit.emit("broker_response", symbol="GBPUSD", MT5_PASSWORD="password")

    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(records) == 2
    assert set(REQUIRED_FIELDS).issubset(records[0])
    assert "secret" not in path.read_text()
    assert "password" not in path.read_text()
