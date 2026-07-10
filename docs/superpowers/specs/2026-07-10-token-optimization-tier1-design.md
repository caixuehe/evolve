# Design: Tier 1 Token Optimizations

Date: 2026-07-10
Status: approved
中文版: [2026-07-10-token-optimization-tier1-design.zh.md](./2026-07-10-token-optimization-tier1-design.zh.md)
Builds on: [2026-07-10-cascade-population-worktree-design.md](./2026-07-10-cascade-population-worktree-design.md) (same branch)

## Motivation

Industry data on agent-loop economics: agents burn 50x more tokens than
chats, re-sent context is ~62% of the bill, and naive loops compound at
O(N²). The mature levers are prompt caching, context compaction, model
routing, externalized memory, and read-on-demand. Evolve's file-based
architecture already exploits externalized memory (fresh context per round,
state in `.evolve/`), and the deterministic cascade already kills the most
wasteful judge calls. This spec applies the remaining low-risk levers.

**Hard constraint: zero functional change.** No scoring semantics, no
pass/fail behavior, no dispatch-decision changes. Every item is
independently revertible and env-overridable where it has a knob.

## Item 1 — Previous Round Evidence truncation (compaction)

**Where:** `prepare.py`, `prepare_dispatch()`, the `## Previous Round
Evidence` block added for target C.

**Current:** the previous `eval_*.md` is inlined untruncated — judge files
run 15–30KB; the middle is process transcript, while scores live at the
head and conclusions/rationale at the tail.

**Change:**

```python
EVIDENCE_CAP = int(os.environ.get("EVOLVE_EVIDENCE_CAP", "6000"))  # chars
```

When the file exceeds `EVIDENCE_CAP` (and cap > 0): keep the first 1,000
chars + the last `EVIDENCE_CAP - 1000` chars, joined by an explicit marker
`[... truncated N chars ...]`. `EVOLVE_EVIDENCE_CAP=0` disables truncation
entirely.

**Why safe:** pairwise verdicts feed trajectory analysis only (never the
pass gate), and `analyze_trajectory`'s contradiction→`noisy` rule is the
backstop if a truncated rationale ever skews a verdict.

## Item 0 — Prerequisite bugfix: build_manifest leaks build_lock

**Where:** `prepare.py`, `build_manifest()` (~line 771).

**Current:** the "build lock status" line is produced by CALLING
`acquire_build_lock()` — which actually acquires the lock — and never
releasing it. Pre-existing leak that self-healed within the old 120s
staleness; with `BUILD_LOCK_STALE_SECONDS = 1800` (this branch's I3 fix)
every manifest build now poisons merges for up to 30 minutes.

**Change:** probe without holding — if `acquire_build_lock` succeeds,
immediately `release_build_lock(evolve_dir, token)` and report "free";
if it fails, report the locked reason. Regression test: after
`build_manifest()`, a fresh `acquire_build_lock()` must succeed.

## Item 2 — Manifest summary caching (eliminate repeat computation)

**Where:** `prepare.py`, `build_manifest()`.

**Current:** every call runs `_haiku_summarize()` — a real LLM API call —
even when nothing changed since the previous round. At 1-minute cadence
with a 20-minute build in flight, that is ~19 wasted calls.

**Change — cache the SUMMARY, never the manifest.** The manifest's
`Status` / `Feature States` sections include volatile state (lock
holders, `in_progress` flags, time-based should_stop) that changes
without any file changing — caching the whole manifest would serve stale
state and violate the zero-functional-change constraint. So the manifest
is always assembled fresh (cheap, deterministic), and only the expensive
summary call is cached:

- fingerprint = `sha256(json of {round, phase, feature, raw_files})`
  where `raw_files` is exactly the dict passed to `_haiku_summarize`
- cache file `.evolve/manifest_summary.json`:
  `{"fingerprint": ..., "summary": ...}`
- fingerprint match → reuse cached summary, zero LLM calls; miss →
  summarize and rewrite the cache

**Why safe:** the fingerprint covers every content input the summary
narrates; volatile lock/timing state never enters the summary's inputs
and is always recomputed in the structured sections. Worst failure mode
is a corrupt cache file → one redundant summarize call.

## Item 3 — Manifest summary on a small model (routing)

**Where:** `prepare.py`, constants + `_haiku_summarize()`.

**Current:** when H was upgraded to Sonnet 4.6 (`HELPER_MODEL`), the
manifest summary call silently rode along. It is a ≤300-output-token
"compress this status into 3–5 lines" call — small-model work.

**Change:**

```python
MANIFEST_MODEL = os.environ.get(
    "EVOLVE_MANIFEST_MODEL", "claude-haiku-4-5-20251001")
```

`_haiku_summarize()` uses `MANIFEST_MODEL`. H's own agent (context
scoping, dispatch assembly) stays on `HELPER_MODEL` — only this one call
is routed down.

## Item 4 — Structured judge output (compaction, doc contract)

**Where:** `agents/critic.md` (+ the Evaluator Prompt guidance H embeds in
`dispatch_C.md`).

**Current:** no output format constraint; judges write essays. The output
costs twice: once as judge output, once as next round's Previous Round
Evidence input.

**Change:** add a mandatory output contract:

- one line per dimension: `<dimension>: <score> — <rationale, ≤30 words>`
- then one pairwise block: `<dimension>: better|same|worse — <one-line basis>`
- then at most 3 summary lines
- never transcribe conversation content or paste raw logs — reference
  evidence file paths instead

**Why safe:** detailed grounds remain in the evidence directory (gate
reports, log samples); the judge stops re-narrating them. Compounds with
Item 1: most eval files will no longer even hit the truncation cap.

## Item 5 — Mentor input budget (compaction, doc contract)

**Where:** `agents/mentor.md`.

**Current:** three Opus mentors read unbounded history hourly — full
results.tsv, full evidence files, full commit log. Late in a session this
is tens of thousands of tokens × 3 × hourly.

**Change:** add a mandatory input budget section:

- results.tsv: last 30 rows only (`tail -30`); summarize anything older as
  one line ("N earlier rounds, M passes")
- evidence/log files: ≤2,000 chars per file, prefer the tail
- git history: `git log --oneline -20`, no per-commit diffs
- each META report ≤60 lines

**Why safe:** the mentor closed loop already carries forward prior advice
and its measured consequences via META files — cross-window conclusions
survive without re-reading raw history.

## Item 6 — Cache-friendly dispatch ordering (prompt caching)

**Where:** `prepare.py`, `prepare_dispatch()` section assembly.

**Current:** sections are assembled as: header → `## Note from O`
(volatile, changes every round) → file contents → evidence. A volatile
section first means any provider-side prefix cache is invalidated at
byte 1.

**Change:** deterministic stable-first ordering:

1. header (`# Dispatch: B|C`)
2. known-stable files from `file_list`, preserving relative order —
   stability judged on the parsed filename (the part before any `:range`
   or `#section` suffix): `program.md`, `eval.yml`, `spec.md`, `adapter.py`
3. all other `file_list` entries (strategy.md, tails, mentor advice…),
   preserving relative order
4. `## Note from O` (volatile)
5. `## Previous Round Evidence` (volatile, C only)

**Why safe:** dispatch files are consumed whole by B/C; section order
carries no semantics (the existing docs never promise an order). Whether
codex exec benefits from provider prefix caching is outside our control,
but the ordering costs nothing and O's own Claude session does benefit
from stable-prefix layout.

## Testing

Unit tests (tmp-dir pattern, no network — the summarizer is monkeypatched):

- Item 1: over-cap file truncated with marker and correct head/tail sizes;
  under-cap file untouched; cap=0 disables.
- Item 0: after `build_manifest()`, a fresh `acquire_build_lock()`
  succeeds (no leaked lock).
- Item 2: second `build_manifest` call with unchanged inputs does NOT
  invoke the summarizer (monkeypatched sentinel raises if called) and
  reuses the cached summary; any raw-input change invalidates; the
  structured Status section stays fresh on cache hits (e.g. a lock-state
  change is reflected even when the summary is cached).
- Item 3: `MANIFEST_MODEL` default + env override; `_haiku_summarize`
  passes it as `model`.
- Item 6: assembled dispatch places `program.md` content before
  strategy.md content and `## Note from O` after all file sections;
  evidence last.
- Items 4–5 are agent-contract docs: verified by review, no unit tests.

## Out of scope (Tier 2, pending real-usage measurement)

- Reference-by-path dispatches (stop inlining program.md; codex reads
  on demand)
- loop.md restructure into a compact per-round runtime card
- Judge call batching / merging dimensions into one call
- Any change to scoring semantics, thresholds, or the escalation ladder
