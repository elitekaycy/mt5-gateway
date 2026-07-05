import app as app_module


def test_app_factory_has_no_mt5_startup_when_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(app_module, "_start_mt5", lambda: calls.append("start"))

    application = app_module.create_app(start_mt5=False)

    assert calls == []
    assert "/health/live" in {rule.rule for rule in application.url_map.iter_rules()}
