"""Templates are created once and never overwritten by a scan."""

AGENT_INSTRUCTIONS = """# Agent Instructions — Repository Navigation

The source code is authoritative; `.ai/` is a navigation aid, not an oracle.

## Before editing
1. Read `.ai/INDEX.md` to find relevant files and functions.
2. Use `.ai/symbols.json` for exact symbol IDs, signatures, and line numbers.
3. Read the actual code and its callers before proposing modifications.
4. Check `.ai/architecture.md` for project-level ownership guidance.
5. Prefer extending an existing owner over adding duplicate managers or state.

## After editing
1. Run `repo-nav scan .` to update structural indexes.
2. Run `repo-nav status .` to see definitions needing review.
3. For every missing/stale symbol, inspect the *current source code* and update
   `.ai/semantics.json` under `entries[symbol_id]` with:
   - `purpose`: a concise, accurate explanation of behavior
   - `owner`: the owning module or class
   - `side_effects`: a JSON list (empty if none)
   - `reviewed_hash`: copy the current `source_hash` from `.ai/symbols.json`
4. Run `repo-nav scan .` again to refresh `.ai/INDEX.md`.
5. Run `repo-nav check .` and relevant project tests.

Never invent semantics from a function name alone. Check implementations.
Do not mark a definition reviewed if you have not read the current code.
A function's dependencies may change without its own hash changing; validate
relevant callers and callees when assessing behavior.

## Complexity guardrails
- One clear owner per state or responsibility.
- Avoid duplicate logic and unnecessary abstractions.
- Do not mix refactoring with unrelated behavior changes.
- Update `.ai/architecture.md` only when architecture actually changes.
"""

ARCHITECTURE = """# Architecture

> Agent-maintained, not automatically inferred. Verify claims against source.

## Overview

Describe the major subsystems and data flow here.

## Ownership map

Document which module owns each important state or behavior.

## Important constraints

Record architectural constraints and intentional design choices.
"""
