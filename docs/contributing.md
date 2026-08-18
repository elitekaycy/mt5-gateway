# Contributing

Read
[CONTRIBUTING.md](https://github.com/elitekaycy/mt5-gateway/blob/main/CONTRIBUTING.md)
and the trading-system engineering standards in
[CLAUDE.md](https://github.com/elitekaycy/mt5-gateway/blob/main/CLAUDE.md)
before opening a PR.

In short:

```bash
ruff check .
mypy app/
pytest -q --cov
```

Branch from `dev`; spec non-trivial behavior in `docs/specs`; write tests
before pure implementation; cold-boot execution changes on a demo account;
PR to `dev`; promote to `main` only through the release workflow.
