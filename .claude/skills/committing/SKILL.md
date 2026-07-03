# Committing

1. Run `git status`; never stage secrets, `.env`, `config/`, captured
   `servers.dat`, or local deploy scripts.
2. Stage one logical change explicitly.
3. Run `ruff check . && ruff format --check . && mypy app/ && pytest -q --cov`.
4. Use `type(scope): imperative subject` (≤72 characters), where type is
   `feat|fix|perf|refactor|test|docs|build|ci|chore`.
5. Use scopes such as `order`, `position`, `resolver`, `boot`, `docker`, `ci`,
   or `readme`. Commit generated artifacts separately.
6. SemVer: `feat` is minor, `fix`/`perf` patch, `BREAKING CHANGE` major.
   Change `VERSION` only in a release PR.
