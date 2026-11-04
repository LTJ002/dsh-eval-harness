# dsh-eval-harness

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![dsh-plugin](https://img.shields.io/badge/dsh-plugin-8A2BE2)](https://github.com/topics/dsh-plugin)

An **agent application development evaluation toolkit** for DeepSeek Harness (DSH). The point is not to produce scores but to make **every number reproducible, comparable, and honest**: judgments come from external facts (audit tables, server-side structured results, deterministic rules), criteria are bidirectional (should-have-answered vs. should-not-have-answered), and mutation tests prove the evaluators themselves catch regressions. Covers RAG retrieval, tool calls, prompt safety, and multi-turn evaluation design.

> The skill body and evaluator docs are written in Chinese; see the [Chinese README](README.md) for the full narrative. This file is a functional summary.

## Install

```sh
dsh plugin add https://github.com/LTJ002/dsh-eval-harness
```

The skill registers as a bundled provider on `ctx.skills` (rank 600) — no need to copy anything into a project's `.agents/skills`.

## What it is / is not

This is a **skill pack**: `skills/ai-eval-harness/SKILL.md` is the methodology the model reads (criterion design, trap catalog, baseline discipline), and `skills/ai-eval-harness/assets/` contains ready-to-run evaluation implementations (Python standard library; a Java writer for JUnit result shards). It ships no UI and no session commands — everything lives in the skill body and the asset scripts.

## Assets

| File | Purpose |
|---|---|
| `assets/eval_results.py` | Result shards (per-suite files + `kind` field, concurrency-safe) |
| `assets/eval_baseline.py` | Baseline diff: regression by absolute counts; offline / **live-strict** / live strictness tiers; denominator change ⇒ undecided |
| `assets/eval_online.py` | Online suite skeleton: `tool` / `inject` / `answer`, with five anti-false-signal disciplines built in |
| `assets/selftest.py` | Regression self-test for the denominator/criteria discipline (run after touching any script) |
| `assets/mutation_check.py` | Mutation testing: break the implementation, assert the tests go red; mutations applied to a temp copy |
| `assets/EvalResults.java` | JUnit-side result writer, JSON shape identical to the Python one |
| `assets/datasets/*.example.jsonl` | Dataset samples (replace wholesale for your project) |
| `assets/install.ps1` | Install the bundle from a repo copy to the user-level skill root; `-VerifyOnly` checks for drift |

## Five anti-false-signal disciplines (executable in `eval_online.py`)

```python
# 1. Was the tool called -> check audit logs, never the reply wording
called = tool_calls_of(conversation_id)

# 2. Degraded answers are skipped: negative assertions are trivially true on empty text
if is_degraded(text, cost):
    continue

# 3. PII means "unmasked", not a broad forbid-word
UNMASKED_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

# 4. Unobservable -> None: not in the denominator, not a failure
called = tool_calls_of(cid)                   # list / empty list / None
if called is None and needs_tool:
    unobservable += 1
    continue

# 5. 401/402 infrastructure errors are counted separately: they never heal on retry, exit code 2
except urllib.error.HTTPError as exc:
    if exc.code in (401, 402):
        errors += 1
```

## Strictness tiers

| kind | default allowed flips | rationale |
|---|---|---|
| `offline` | 0 | pure functions are deterministic; one drop is a real drop |
| `live-strict` | 0 | safety/fabrication gates (prompt leakage, PII, forbidden tools): randomness explains capability noise, not a leak |
| `live` | 1 | ordinary capability suites; flips must be logged, never silent |

## Local verification

```sh
npm test
python skills/ai-eval-harness/assets/selftest.py
python skills/ai-eval-harness/assets/mutation_check.py
```

All three were green before release (96 assertions passed; 24/24 mutations caught).

## Exit codes

| code | meaning |
|---|---|
| 0 | pass |
| 1 | quality failure (real regression, real leak) |
| 2 | results unusable (bad path, missing dataset, all degraded, unobservable, denominator change, 401/402) — fix the harness first |

## Known limits

- `eval_online.py` is a **skeleton**: rewrite `login()` / `chat()` / `tool_calls_of()` for your project contract; the sample datasets come from a photography-order project and must be replaced wholesale.
- The self-test monkeypatches module-level functions; it validates the judging discipline, not real network paths.
- `EvalResults.java` and `install.ps1` are not CI-verified; smoke-test them on first integration.

## License

[MIT](LICENSE)
