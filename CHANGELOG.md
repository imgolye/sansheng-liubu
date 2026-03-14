# Changelog

## 1.12.0 - 2026-03-14

### Added
- Added a Conversation Center inside Mission Control with `/conversations`, real OpenClaw session browsing, transcript inspection, and direct in-product dialogue with agents.
- Added `/api/conversations` and `/api/conversations/transcript` so the product can read native OpenClaw sessions and per-session jsonl transcripts without inventing a parallel chat store.
- Added authenticated in-product conversation actions backed by `openclaw agent --json`, including transcript refresh after each message.

### Changed
- Expanded Mission Control from “see + operate” into “see + operate + converse”, so operators can stay inside the product for both task control and live agent dialogue.
- Introduced a dedicated conversation permission for `Owner / Operator`, keeping `Viewer` read-only while still exposing real transcript visibility.

### Fixed
- Fixed mixed-output parsing for `openclaw agent --json` and `openclaw sessions --json`, so plugin logs no longer break conversation data or chat actions.
- Fixed product refresh behavior so sending a conversation message immediately refreshes the session list and transcript instead of waiting for passive polling.

## 1.11.0 - 2026-03-14

### Added
- Added an OpenClaw Control Center inside Mission Control with `/openclaw` and `/api/openclaw` surfaces for native version, schema, gateway, and skills visibility.
- Added in-product publishing from local repo skills into the current OpenClaw managed skills directory, so owner users can promote a skill without leaving the product.
- Added managed-skills directory visibility and OpenClaw baseline compatibility signals for `2026.3.12+`.

### Changed
- Tightened Skills Center to focus on repo-local skills while letting the OpenClaw view own native managed-skill runtime visibility.
- Upgraded OpenClaw JSON parsing to tolerate mixed CLI output where plugin or warning logs are interleaved with structured JSON.

### Fixed
- Fixed stale post-action UI state by clearing cached OpenClaw and skill payloads after product mutations such as skill publish, theme switch, or packaging.
- Fixed deep-link support for the OpenClaw workspace so `/openclaw` now renders like the rest of the product routes.
- Fixed local publish-state detection to work even when `openclaw skills list --json` truncates discovery on very large managed skill roots.

## 1.10.0 - 2026-03-14

### Added
- Added `bin/skill_utils.py` to scan, validate, scaffold, and package Claude-style skill folders using Anthropic's published skill structure patterns.
- Added a new Skills Center product workspace in Mission Control with skill catalog visibility, quality signals, scaffold actions, and zip packaging.
- Added a sample `mission-control-release-ops` skill to demonstrate progressive disclosure with `references/` and release-oriented workflow guidance.

### Changed
- Expanded Mission Control from an operations/admin surface into a local skills product as well, with `/skills` and `/api/skills` routes.
- Wired the dashboard runtime to read skill metadata from the source repository and surface distribution-ready commands directly in the UI.

### Fixed
- Ensured generated skill scaffolds now pass their first validation instead of emitting malformed YAML frontmatter.
- Ignored packaged `dist/` artifacts so skill zip creation does not dirty the repository with generated files.

## 1.9.0 - 2026-03-14

### Added
- Added multi-user Mission Control access with local product accounts, role-based permissions, and Owner Token fallback bootstrap.
- Added a commercial admin workspace inside Mission Control for seat provisioning, role/state governance, password resets, and audit visibility.
- Added secure password hashing plus signed session cookies for local product login.

### Changed
- Split dashboard admin data into public summaries and authenticated sensitive detail, so static snapshots no longer expose seat rosters or audit trails.
- Elevated Mission Control from a protected local tool to a more commercial-grade product surface with account lifecycle and governance workflows.

### Fixed
- Restored the missing `now_iso()` helper so account, audit, and session features no longer fail at runtime.
- Prevented the last active Owner from being downgraded or suspended, avoiding accidental product lockout.
- Normalized account status handling so suspended seats are enforced consistently across login, admin UI, and stored records.

## 1.8.0 - 2026-03-14

### Added
- Added an in-product task action studio so users can create work directly from the Tasks module without leaving Mission Control.
- Added task-operation forms inside the task replay drawer for progress updates, blocking, and completion handoff.
- Added authenticated product action endpoints for task creation, progress, blocking, completion, and live theme switching.

### Changed
- Linked generated installs back to the source repository so the product can invoke `switch_theme.py` safely from inside the UI.
- Promoted Mission Control from a read-only dashboard into an operational product surface with toast feedback and action-aware runtime state.

### Fixed
- Returned a non-zero exit code when task creation is rejected, so product actions no longer report false success.
- Allowed navigation to continue while a drawer is open instead of letting the scrim block the left menu.
- Kept generated config metadata in sync with the current release version.

## 1.7.0 - 2026-03-14

### Added
- Added a local login flow at `/login` with cookie-based session access for Mission Control routes, APIs, and live events.
- Added layout controls for collapsing the left menu and switching between operations, focus, and compact product layouts with persisted preferences.

### Changed
- Turned the Mission Control shell into a protected local product surface with navigation, authenticated app routes, and signed local session state.
- Expanded the top navigation to include menu controls, layout switching, and authenticated sign-out actions.

### Fixed
- Ensured unauthenticated requests to product APIs and SSE streams now return proper auth gating instead of exposing data directly.
- Preserved layout choices across reloads so the product opens in the same working mode the user last selected.

## 1.6.0 - 2026-03-14

### Added
- Added a product-style Mission Control app shell with dedicated Overview, Agents, Tasks, Activity, and Themes modules.
- Added local API endpoints for agents, tasks, events, themes, and deliverables so the dashboard can act as a real product surface instead of a single visual page.
- Added integrated product runbook cards that expose common local commands directly inside the app.

### Changed
- Reframed `collaboration_dashboard.py --serve` as a local multi-view application with navigation, search, deep-linkable routes, and dedicated work areas for operations and delivery.
- Expanded dashboard payloads with theme catalog, router context, command palette data, and deliverables inventory to support richer product workflows.

### Fixed
- Kept browser console output clean across the new multi-route app experience.
- Preserved drawer-based drill-downs while expanding the app beyond a single-page overview.

## 1.5.0 - 2026-03-14

### Added
- Added clickable agent inspector drawers so users can open any agent card and inspect live focus, recent signals, and in-hand tasks.
- Added task replay drawers that expose route, TODO progress, and chronological handoff/progress history from both task cards and timeline events.

### Changed
- Refactored `templates/scripts/collaboration_dashboard.py` into a richer mission-control UI with drill-down interactions while keeping HTML + JSON snapshot generation and the live SSE server.
- Expanded dashboard JSON payloads with `taskIndex`, replay entries, recent agent signals, and active task cards to support richer downstream visualizations.

### Fixed
- Counted only non-terminal tasks toward agent active-state metrics so completed work no longer leaves agents falsely marked active.
- Suppressed the browser `favicon.ico` 404 noise in the live dashboard UI.

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
