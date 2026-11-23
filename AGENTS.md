# Repository guidance

AI4S is a local research calendar and project organizer. Keep the runtime dependency-free and preserve the separation between application code and personal workspace data.

- Read `AI4S_ARCHITECTURE.md`, `docs/API.md`, and `docs/DATA_MODEL.md` before changing module boundaries or persistence.
- Add project behavior to `desktop_services.py`, schemas to `desktop_contract.py`, and keep HTTP/MCP as adapters. Do not duplicate business logic in transports.
- Generate `openapi.json` with `python examples/export_openapi.py` after contract changes.
- Use temporary synthetic workspaces for tests. Never edit real research data, real conversations, or the user's calendar as test fixtures.
- Preserve revision conflict checks, cross-process locking, atomic writes, stable IDs, and registered-target navigation.
- Keep private workspace JSON, filesystem indexes, credentials, machine-specific MCP configs, and real chat IDs out of commits. Public screenshots must use synthetic projects.
- Update usage and API documentation when behavior changes. Explain limitations in plain language; project status is registered metadata unless an explicit adapter supplies it.
- Run `python -B -m unittest discover -p "test_*.py" -v` before publishing. Review the actual page for visible UI changes.
- Do not add dependencies, a chat SDK, or hosted infrastructure without a concrete requirement. The app is intended for single-user loopback deployment.

