# Changelog

## 1.4.0 - 2026-03-14

### Added
- Added a live local web panel for the collaboration dashboard with `/api/dashboard` and Server-Sent Events (`/events`) endpoints.
- Added real-time client-side updates for the mission-control UI without full-page reloads.

### Changed
- Upgraded `collaboration_dashboard.py --serve` from static file hosting to a real-time local dashboard server.
- Updated collaboration dashboard signatures so change events only fire on substantive task/agent updates.

### Fixed
- Avoided noisy continuous dashboard events caused by timestamp-only changes.
- Preserved static snapshot generation while enabling a live browser panel for the same dashboard.

## 1.3.0 - 2026-03-14

### Added
- Added `templates/scripts/collaboration_dashboard.py` to generate an HTML + JSON mission-control view for live multi-agent collaboration.
- Added automatic collaboration dashboard generation during install, task refresh, and theme switching.

### Changed
- Updated the README to surface the collaboration dashboard and visual coordination workflow.
- Extended installation validation to require the collaboration dashboard runtime script.

### Fixed
- Ensured theme switching preserves the visual dashboard capability after agent/workspace migrations.

## 1.2.0 - 2026-03-14

### Added
- Added `bin/switch_theme.py` and `bin/switch_theme.sh` so existing installations can switch themes without reinstalling.
- Added theme schema validation and shared migration helpers in `bin/theme_utils.py`.

### Changed
- Preserved existing channel config, models, memory search settings, and task prefixes when regenerating `openclaw.json`.
- Preserved existing secrets and gateway token when rerunning `setup.sh`.
- Tightened default elevated allowlists so new installs no longer inherit wildcard access by default.

### Fixed
- Replaced the old `eval`-based theme loading in `setup.sh` with validated Python parsing.
- Deployed `health_dashboard.py` to every workspace and updated validation to check it.
- Made `health_dashboard.py` support `--dir`, `OPENCLAW_DIR`, and per-workspace auto-detection.
- Replaced the Unix-only `fcntl` JSON lock with a cross-platform lock implementation.
- Migrated task boards, agent session directories, and workspace artifacts across themes when switching.

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
