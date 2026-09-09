# MediaQC V1 Specification Package

This repository-ready package defines the authoritative V1 specification for **MediaQC**, a Windows-first, offline desktop application for technical audio/video quality control.

## Start here

1. Read `MASTER_SPEC.md`.
2. Read `AGENTS.md`.
3. Implement the project in the phase order defined in `MASTER_SPEC.md`.
4. Treat files under `specs/` as normative requirements.
5. Do not change architecture, schemas, detector IDs, IPC contracts, or acceptance criteria without updating the relevant specification first.

## V1 product definition

MediaQC V1 SHALL allow a user on Windows 10/11 to:

- create/open a local QC project;
- select a local media file;
- inspect media metadata;
- choose a versioned QC profile;
- run offline deterministic audio/video QC;
- receive structured PASS/WARN/FAIL findings;
- inspect timestamped evidence;
- mark findings confirmed, false positive, or ignored;
- export HTML and PDF reports;
- operate without internet access, cloud services, accounts, or external developer tooling.

The source media file is always treated as read-only.

## Package contents

- `MASTER_SPEC.md` — project authority, scope, build phases, and global acceptance criteria.
- `AGENTS.md` — mandatory rules for AI coding agents.
- `specs/01_PRODUCT_SPEC.md`
- `specs/02_ARCHITECTURE.md`
- `specs/03_DATABASE.md`
- `specs/04_DETECTOR_SPEC.md`
- `specs/05_QC_PROFILE_SPEC.md`
- `specs/06_IPC_SPEC.md`
- `specs/07_UI_SPEC.md`
- `specs/08_AI_SPEC.md`
- `specs/09_TESTING_SPEC.md`
- `specs/10_WINDOWS_BUILD.md`

## Requirement language

The words **SHALL**, **MUST**, **SHOULD**, **MAY**, and **MUST NOT** are normative.

- **SHALL / MUST** — required for V1.
- **SHOULD** — expected unless a documented technical reason prevents it.
- **MAY** — optional.
- **MUST NOT** — prohibited in V1.
