# dsh-eval-harness

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![dsh-plugin](https://img.shields.io/badge/dsh-plugin-8A2BE2)](https://github.com/topics/dsh-plugin)

An **agent application development evaluation toolkit** for DeepSeek Harness (DSH). The point is not to produce scores but to make **every number reproducible, comparable, and honest**: judgments come from external facts (audit tables, server-side structured results, deterministic rules), criteria are bidirectional (should-have-answered vs. should-not-have-answered), and mutation tests prove the evaluators themselves catch regressions. Covers RAG retrieval, tool calls, prompt safety, and multi-turn evaluation design.

> The skill body and evaluator docs are written in Chinese; see the [Chinese README](README.md) for the full narrative. This file is a functional summary.

## When to use

| scenario | what it does for you |
|---|---|
| building quality metrics for an LLM/agent app | stand up the three-layer loop: offline assertions + online model-in-the-loop + baseline diff |
| proving a RAG / tool / prompt change did not regress | compare case-by-case against the baseline; any drop goes red, safety regressions have zero tolerance |
| evals are green but users still hit failures | walk the four-trap catalog and the root-cause layers to find the false green |
| suspecting your eval script lies to itself | run `mutation_check.py`: break the implementation, see whether the assertions dare to go red |
| numbers "look right" but you cannot trust them | five-state result contract, denominator discipline, small-n annotations 鈥?every number explains itself |

## Install

```sh
dsh plugin add https://github.com/LTJ002/dsh-eval-harness
```

The skill registers as a bundled provider on `ctx.skills` (rank 600) 鈥?no need to copy anything into a project's `.agents/skills`.

## What it is / is not

This is a **skill pack**: `skills/ai-eval-harness/SKILL.md` is the methodology the model reads (criterion design, trap catalog, baseline discipline), and `skills/ai-eval-harness/assets/` contains ready-to-run evaluation implementations (Python standard library; a Java writer for JUnit result shards). It ships no UI and no session commands 鈥?everything lives in the skill body and the asset scripts.

## Scope: works with every agent development framework

The toolkit is **framework-agnostic**: it binds to, embeds, and requires no agent framework SDK. Agent applications built with any framework 鈥?LangChain, LangChain4j, Spring AI, AutoGen, CrewAI, Dify, and others 鈥?can be evaluated by the same suite given two prerequisites:

1. **Programmable chat access** 鈥?the app exposes a callable chat endpoint (HTTP/SSE both fine; `eval_online.py` talks to it with the Python standard library, rewrite `login()` / `chat()` for your contract);
2. **Queryable side effects** 鈥?tool calls and writes leave queryable records (audit table, structured logs, or DB) 鈥?criteria read external facts, never the model's self-report.

Because the prerequisites are decoupled from the framework, the methodology (bidirectional criteria, denominator discipline, baseline diff, mutation testing) transfers across frameworks; switching frameworks changes the adapter, not the criteria. The evaluator integration layer follows your project language:

- **Python projects**: the `assets/` scripts work as-is (stdlib only);
- **Java/JUnit projects**: `EvalResults.java` produces JSON shards shaped identically to the Python ones;
- **Any other language**: anything that can write result shards in the agreed JSON shape feeds `eval_baseline.py` (shape documented in [assets/README.md](skills/ai-eval-harness/assets/README.md)).

LangChain / LangChain4j appear in the docs only as examples when explaining chunker size units 鈥?**this is not an integration statement for any specific framework**.

## Assets

| File | Purpose |
|---|---|
| `assets/eval_results.py` | Result shards (per-suite files + `kind` field, concurrency-safe) |
| `assets/eval_baseline.py` | Baseline diff: regression by absolute counts; offline / **live-strict** / live tiers; Wilson CI, case-level diff, flaky-run escalation; denominator change -> undecided |
| `assets/eval_online.py` | Online skeleton: four suites (`tool` / `inject` / `answer` / `multi-turn`), five anti-false-signal disciplines, `expected` structured criteria, tool five stages |
| `assets/eval_rag.py` | RAG retrieval: Recall@K / MRR / nDCG@K / Precision@K |
| `assets/eval_rag_answer.py` | RAG generation: Faithfulness / Citation Correctness / Completeness / contradiction, from human annotation pairs (no model-on-model scoring) |
| `assets/eval_governance.py` | Governance: root-cause tiers / dataset governance / Judge calibration (agreement + kappa; failing either blocks the gate) |
| `assets/eval_manifest.py` | Run manifest: prompt/dataset sha256 fingerprints + config diff |
| `assets/eval_report.py` | Read-only aggregated report (Markdown/JSON) + effect size and **read-only** threshold suggestion |
| `assets/markers.py` + `markers.default.json` | Externalized word lists (7 groups); override with `EVAL_MARKERS`; deploy both together |
| `assets/adapters.py` | Adapter registry: `EVAL_ADAPTER` points at your module; unimplemented functions fall back to built-in base |
| `assets/selftest.py` | Regression self-test for the denominator/criteria discipline (run after touching any script) |
| `assets/mutation_check.py` | Mutation testing: break the implementation, assert the tests go red; mutations applied to a temp copy |
| `assets/EvalResults.java` / `EvalResults.mjs` | JUnit / Node result writers, JSON shape identical to the Python one |
| `assets/CROSS_LANGUAGE.md` | JSON shape contract and write discipline for other languages |
| `assets/ci-eval.yml.example` | Three-gate CI/CD template for adopters |
| `assets/datasets/*.example.jsonl` | Dataset samples (`<placeholder>` format templates; replace wholesale for your project) |
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

All four were green before release (all assertions pass; all mutations caught — counts evolve with the skill, run it locally for the current numbers). `npm test` also compiles and runs `EvalResults.java` and checks the JSON shape against the Python side (explicitly skipped, not silently faked, when no JDK is present).

## Exit codes

| code | meaning |
|---|---|
| 0 | pass |
| 1 | quality failure (real regression, real leak) |
| 2 | results unusable (bad path, missing dataset, all degraded, unobservable, denominator change, 401/402) 鈥?fix the harness first |

## Known limits

- `eval_online.py` is a **skeleton**: rewrite `login()` / `chat()` / `tool_calls_of()` for your project contract; the sample datasets are `<placeholder>` format templates and must be replaced wholesale.
- The self-test monkeypatches module-level functions; it validates the judging discipline, not real network paths — a real online run is still needed.
- `EvalResults.java` is verified by `npm test` (javac compile + run + JSON-shape check against Python). `install.ps1`'s install branch still needs a manual `install.ps1 -VerifyOnly` in an environment that has the repo copy.
- `eval_rag.py` / `eval_rag_answer.py` do not talk to any retrieval or generation service: `retrieved` lists and `supportFacts` / `citations` / `requiredPoints` annotation pairs are exported by your system or labeled by humans; the metrics only judge those external facts.
- This repo runs its own CI at [.github/workflows/eval-gate.yml](.github/workflows/eval-gate.yml) (selftest + mutation + Java smoke + dataset governance, really executed); `assets/ci-eval.yml.example` is a template for adopters.
- Sentence-level semantic similarity and "naturalness" are outside this toolkit — they need model-on-model scoring or human review and, by the first principle, never gate; `eval_governance.py judge` only calibrates whether a Judge qualifies as an **auxiliary** signal.
- The multi-turn suite and tool-call five-stage **criteria** are implemented (`run_multi_turn_suite` / `check_tool_stages`), but dataset samples must be rewritten for your business, and `tool_call_records()` needs wiring to your audit table.

## License

[MIT](LICENSE)
