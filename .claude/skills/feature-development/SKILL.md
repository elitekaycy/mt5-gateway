# Feature Development

1. Classify whether execution safety is affected. Preserve idempotency,
   pre-trade validation, magic ownership, and centralized retcodes.
2. Write a short `docs/specs/YYYY-MM-DD-name.md` for non-trivial behavior.
3. Test pure logic first; stub MetaTrader5 only at its module boundary.
4. Implement on a branch from `dev`; update Swagger for route changes.
5. Run the gate in `CONTRIBUTING.md`.
6. Cold-boot execution changes against a demo account and attach authorization,
   account, and test evidence to the PR.
7. Open the PR to `dev`; promote green `dev` to `main` through the workflow.
