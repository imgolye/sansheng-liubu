# Changelog

## 1.1.0 - 2026-03-14

### Changed
- Upgraded the installer and validator to fully provision and verify all 11 agents, including the briefing role.
- Aligned generated `openclaw.json` defaults with the current OpenClaw 2026.3.12 session and gateway settings.
- Added `sessions_yield` to theme tool allowlists and generated SOUL guidance for planner, dispatcher, departments, and briefing roles.

### Fixed
- Fixed `setup.sh` so the theme task prefix is honored by default and the briefing agent is no longer skipped during installation.
- Fixed `validate.sh` so `--dir` works as documented and incomplete installations fail validation.
- Fixed `kanban_update.py` so missing tasks return non-zero exit codes instead of logging false success.
- Fixed task state transitions to preserve the real responsible department during `Doing` and `Done` phases.
- Fixed `health_dashboard.py` so active tasks are loaded from the current router workspace instead of hardcoding `workspace-taizi`.

### Compatibility
- Verified against OpenClaw `2026.3.12`.
- Confirmed clean isolated installs for `startup` and `corporate` themes.

## 1.0.0 - 2026-03-12

- Initial release of the sansheng-liubu multi-agent orchestration template for OpenClaw.
