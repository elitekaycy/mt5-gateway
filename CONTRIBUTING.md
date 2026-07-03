# Contributing

Install test dependencies with `pip install -r requirements-dev.txt`, then run
the exact local/CI gate:

```bash
ruff check .
ruff format --check .
mypy app/
pytest -q --cov
```

Branch from `dev`, use Conventional Commits, and open a PR back to `dev`.
Keep pure trading logic outside the MT5 boundary so Linux tests can stub only
the native module. Route changes must update Swagger. Execution-path changes
must include demo-account cold-boot evidence from `scripts/test-coldboot.sh`.

Read [CLAUDE.md](CLAUDE.md) and the repository-local
`.claude/skills/feature-development/SKILL.md` checklist before changing order
execution.
