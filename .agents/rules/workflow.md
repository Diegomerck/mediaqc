# MediaQC — Permanent Workflow & Token Optimization Rules

These rules govern the development workflow for MediaQC within this conversation and any implementation agent operating on this repository.

---

## 1. Default Mode is ALWAYS PLANNING (Zero Code Edits)

- Unless the user explicitly begins their prompt with **`IMPLEMENTATION`** or **`QUICK FIX`**, the assistant **MUST ALWAYS** operate in **PLANNING / Brainstorming Mode**.
- In **PLANNING Mode**:
  - **NEVER** edit, create, or delete application or test code files.
  - **NEVER** run builds, tests, or state-modifying terminal commands.
  - Read-only file inspection, git status checks, and read-only searches are permitted to verify facts.
  - Focus exclusively on discussing requirements, edge cases, design trade-offs, architecture alignment with `MASTER_SPEC.md` and `AGENTS.md`, and agreeing on exact specifications.
  - Keep responses lightweight, concise, and structured to preserve token quota and AI credits.
  - Always state the assessed task complexity tier (Standard Tier or High Tier) and provide copy-ready instructions/prompts for when implementation is approved.

---

## 2. Single Conversation Structure

- Planning, architecture alignment, review, and implementation execution occur within this single conversation thread to preserve complete context and project memory without duplicating context across multiple chats.
- When conversation history grows long or context limits are approached, the assistant must proactively remind the user to trigger the `/compact` slash command to free context space and minimize tokens per turn.

---

## 3. Automatic Complexity Assessment & Subagent Delegation

During the PLANNING phase, the assistant must automatically assess the proposed task's complexity and declare the execution tier:

### Execution Tiers

1. **Quick Fix (Direct / No Subagent)**:
   - **Scope:** Tiny, single-line or single-token fixes (e.g., fixing a typo, updating a version string, tweaking an isolated CSS class).
   - **Execution:** Handled directly in the main conversation when prompted with `QUICK FIX`, followed immediately by verification.
2. **Standard Tier (Subagent with `flash`)**:
   - **Scope:** 1–2 files, localized UI adjustments, styling updates, simple isolated component tweaks, minor documentation fixes.
   - **Execution:** Dispatched via `invoke_subagent` with `Model: "flash"` to conserve quota.
3. **High Tier (Subagent with `pro`)**:
   - **Scope:** Multi-file refactors, IPC protocol changes, engine DSP/CV detector logic, database schema migrations, complex state/backend synchronization, or packaging modifications.
   - **Execution:** Dispatched via `invoke_subagent` with `Model: "pro"`.

### Strict Safeguards on Delegation & Models

- **NEVER** invoke expensive models (such as Argon or custom heavy models) unless the user explicitly requests them by name in their prompt.
- **One Subagent at a Time:** Never run concurrent conflicting subagents on the same codebase.
- **Verification on Completion:** When `IMPLEMENTATION` is completed, the agent must run the appropriate focused lint/test/build command, verify success, and return a concise summary of modified files and verification results.
- **Source Media Immutability:** Never modify, move, or rename test or source media files.
- **No Unapproved Git Actions:** Never commit, push, create PRs, or tag releases without explicit user permission.

