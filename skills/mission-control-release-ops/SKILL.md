---
name: mission-control-release-ops
description: Prepares sansheng-liubu releases with a repeatable validation, packaging, and release-notes workflow. Use when the user asks to prepare a release, validate a release candidate, package skill archives, or finalize version notes.
compatibility: Claude Code, Codex, and local repository environments with git, Python, and filesystem access.
metadata:
  author: sansheng-liubu
  version: 1.0.0
---
# Mission Control Release Ops

## Instructions
- Start by identifying the exact release target: version number, scope, and whether the user wants code changes, packaging, or publication.
- Keep the main workflow here and load `references/release-checklist.md` when you need the detailed validation checklist.
- Prefer deterministic commands and built-in repo scripts over manual repetition.
- Before any release action, confirm the repository state, validation status, and changelog/release-notes readiness.

## Workflow
### Step 1: Establish release scope
- Read the current version markers, changelog head, and any uncommitted changes.
- Summarize what is ready, what is missing, and what still blocks a release candidate.

### Step 2: Run validation
- Execute the relevant validation commands for the changed areas.
- If the work touches Mission Control, verify product behavior and document any gaps.
- Consult `references/release-checklist.md` before finalizing.

### Step 3: Prepare release artifacts
- Update version markers, README highlights, and changelog entries if needed.
- Package any skill archives or distribution assets required for the release.
- Make sure generated artifacts are reproducible and stored in the expected output directory.

### Step 4: Final release handoff
- Produce a concise release summary with features, fixes, risks, and validation results.
- If publication is requested, make sure commit/tag/release steps are in the correct order.

## Examples
- User says: "Prepare the next sansheng-liubu release candidate."
  Result: validate changes, check version markers, confirm release notes, and report remaining blockers.
- User says: "Package the skill archives and finalize release notes."
  Result: build the archives, verify them, update notes, and summarize publish-ready artifacts.

## Troubleshooting
- If validation fails, stop release publication work and surface the failing check first.
- If the repo is dirty, distinguish intentional local work from generated artifacts before packaging.
- If version markers disagree, update all release surfaces together before continuing.
