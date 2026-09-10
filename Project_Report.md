# Agentic Triage of RTL Verification Failures — Project Report

*Prepared for review / consultation. The goal of this document is to describe what was
built, the evaluation, and the results, and to ask for direction on what to do next.*

---

## 1. Summary

I built an LLM-agent pipeline that triages RTL (SystemVerilog) verification failures: given
a failing simulation log and the design source, it predicts (a) the source **line(s)** most
likely responsible and (b) the **bug class**. I evaluate it against a dataset of **30 seeded
bugs with known ground truth**, compare two local LLMs (Qwen2.5-Coder 7B and Llama-3 8B),
and compare against two non-LLM baselines.

The pipeline works end to end and beats both baselines. The headline finding is that
**localization accuracy is bounded by the ambiguity of the failing assertion**: when an
assertion uniquely identifies the faulty stage (reset), accuracy is high; when many distinct
bugs trip the same assertion, accuracy drops. This is a property of the design-under-test,
and I made it measurable.

Context: this is a portfolio project aimed at two Infineon internship applications
(AI-agent development for IC verification, and AI/ML for chip-design/EDA workflows).

---

## 2. Problem

Verification engineers spend significant time reading simulation logs to find the root cause
of a failing test. I framed this as an automatable triage task and asked: *can an LLM agent,
given a failing log and the RTL, localize the bug and classify it — and how well?*

To answer "how well" rigorously I needed labeled failures. I generate them by **fault
injection**: mutate a known-good design so I know exactly which line and which class each
failure corresponds to.

---

## 3. Design under test and dataset

- **DUT:** a synchronous FIFO in SystemVerilog (`WIDTH=8`, `DEPTH=8`), with pointer/count
  logic and `full`/`empty` flags.
- **Testbench:** a cocotb (Python) testbench simulated with Icarus Verilog. It checks, in
  order: `empty` after reset → `full` after 8 writes → correct data on 8 reads. It stops at
  the first failing assertion.
- **Fault injection (`inject_bug.py`):** 30 single-line mutations across 4 classes:
  - `operator_flip` (e.g. `+`→`-`, `==`→`!=`, inverted condition)
  - `off_by_one` (e.g. `== DEPTH` → `== DEPTH-1`, `+1`→`+2`)
  - `wrong_reset` (e.g. `count <= 0` → `count <= 1`)
  - `stuck_at` (e.g. `data_out <= mem[rd_ptr]` → `data_out <= 0`)
  Each mutant is built from the original, simulated, and kept only if the test actually
  fails. **30/30 produced a failure (0 escaped).** Each case stores its own mutant file, log,
  and ground-truth label `{file, line, bug_type}`.

**Important dataset property:** ~22 of 30 bugs fail at the **same** `full`-after-8-writes
assertion, because many different root causes (pointer flips, stuck signals, counter bugs)
all prevent `full` from asserting. Only reset bugs (5) and a few readback bugs (3) fail at a
distinct assertion. This concentration is central to the results below.

---

## 4. Architecture

A 3-node LangGraph pipeline. All LLM calls are to a **local** model via Ollama
(`/api/generate`, JSON mode) — chosen deliberately so proprietary RTL never leaves the
machine, which is a real constraint in a semiconductor setting.

```
 failing log + mutant RTL
          │
          ▼
 [1] classify  ── parse_log(): extract the failing assertion + testbench line,
          │        derive a deterministic FAILURE STAGE (reset / fill / readback),
          │        which acts as a prior for the bug class.
          ▼
 [2] gather_context ── from the stage, pick the set of signals that could plausibly
          │            cause that assertion; for each, deterministically find its
          │            assignment lines in the RTL (regex over the source).
          │            -> a CANDIDATE LINE SET (contains the true line by construction).
          ▼
 [3] hypothesize ── give the model: the log summary, the full numbered source, the
                    dataflow traces, and the candidate line list. The model RANKS the
                    candidates (most-likely first, up to 5) and picks the bug class.
                    A deterministic backstop appends any un-ranked candidates so the
                    true line stays in the shortlist. Structural lines (always/begin/if)
                    are filtered out.
          │
          ▼
 {predicted_class, predicted_lines[1..5], rationale, suggested_fix}
```

Design rationale for the split of labor: the **deterministic** parts (stage detection,
candidate-line extraction) are reliable and version-proof; the **LLM** part is used only for
the genuinely hard judgment — ranking which candidate is wrong and naming the class. This
also bounds hallucination: the model may only rank lines from the candidate set, so it can't
invent line numbers.

Note: I initially used pyverilog for dataflow, but its API exposed neither a stable signal
name (`ScopeChain`) nor source line numbers across versions, so I replaced it with a small
regex-based assignment finder — deterministic and version-independent.

---

## 5. Baselines

- **Regex baseline:** extracts line numbers from the log via regex and keyword-classifies.
  It recovers the *testbench* assertion line, not the RTL line, so it does not localize the
  bug in the design.
- **Single-shot LLM baseline:** a small model (1.5B) is given the log + source in one call,
  no tools, no candidate set. It frequently returned empty/invalid JSON.

*(Baseline runs on the full 30-bug set are pending; on the initial 5-case set both scored 0%
localization. I plan to complete the 30-bug baseline runs so the ablation table is uniform.)*

---

## 6. Evaluation

Metrics, per bug category and overall:

- **Top-1:** true line is the first prediction.
- **Top-3:** true line within the first 3 predictions.
- **Top-3± (tolerant):** a prediction within ±2 lines of the true line, in the top 3.
- **Rec@5 (recall@5):** true line anywhere in the top 5 — the "did the bug make the
  shortlist a human should inspect" metric, which I argue is the right one for triage.
- **Class accuracy:** predicted bug class matches ground truth.

One harness scores any predictions file; the agent, both baselines, and both models all run
through it.

---

## 7. Results (30 bugs)

### Qwen2.5-Coder 7B — per category

| Bug class      | N  | Top-1 | Top-3 | Top-3± | Rec@5 | Class |
|----------------|----|-------|-------|--------|-------|-------|
| operator_flip  | 10 |  10%  |  30%  |  30%   |  40%  |  10%  |
| off_by_one     |  8 |  12%  |  25%  |  25%   |  25%  |  62%  |
| wrong_reset    |  5 |  60%  |  60%  |  80%   |  80%  |  60%  |
| stuck_at       |  7 |  29%  |  29%  |  71%   |  43%  |   0%  |
| **OVERALL**    | 30 | **23%** | **33%** | **47%** | **43%** | **30%** |

### Llama-3 8B — per category

| Bug class      | N  | Top-1 | Top-3 | Top-3± | Rec@5 | Class |
|----------------|----|-------|-------|--------|-------|-------|
| operator_flip  | 10 |   0%  |  30%  |  50%   |  30%  |  40%  |
| off_by_one     |  8 |   0%  |  12%  |  25%   |  50%  |  38%  |
| wrong_reset    |  5 |  60%  |  60%  |  60%   |  80%  |  20%  |
| stuck_at       |  7 |   0%  |   0%  |  14%   |  29%  |   0%  |
| **OVERALL**    | 30 | **10%** | **23%** | **37%** | **43%** | **27%** |

### Model comparison (overall)

| Metric  | Qwen2.5-Coder 7B | Llama-3 8B |
|---------|------------------|------------|
| Top-1   | 23%              | 10%        |
| Top-3   | 33%              | 23%        |
| Top-3±  | 47%              | 37%        |
| Rec@5   | 43%              | 43%        |
| Class   | 30%              | 27%        |

Qwen leads on exact localization; both tie on Rec@5 and show the **same structural pattern**
across categories, which suggests the ceiling is set by the problem, not the model.

---

## 8. Key finding

**Localization accuracy tracks assertion uniqueness.** The `wrong_reset` class fails at a
distinct assertion (empty-after-reset) and scores highest (Qwen 60% Top-1, 80% Rec@5). The
FILL-path classes — where ~22 different bugs all trip the same `full` assertion — score in
the single digits to ~30%. No triage tool can deterministically rank the exact line first
when several candidate lines produce an identical symptom.

I therefore argue **Rec@5 over a dataflow-derived candidate set** is the honest metric for
this task, and that the per-category spread (not the single overall number) is the real
result: it quantifies how observability limits automated triage.

---

## 9. Limitations (known and, I think, honest)

- **Small DUT** (one FIFO). Conclusions may not transfer to larger designs.
- **Ambiguous assertions cap accuracy** — see §8. Better observability (more/assertions per
  signal) would raise the ceiling; I did not add that.
- **stuck_at vs operator_flip on the readback path** are hard to separate from the log alone;
  class accuracy for stuck_at is 0%.
- **Baseline runs on 30 bugs are pending** (5-case results only so far).
- Local small/mid models only; no frontier/API model tested.

---

## 10. Engineering notes (debugging arc)

Worth recording because it shaped the design:
1. Initial 0% was a **data-pipeline bug** — every case was being scored against a single
   shared mutant file. Fixed by writing per-case mutant files and wiring ground-truth paths.
2. A hang traced to LangChain's structured-output/JSON-schema negotiation; replaced with a
   raw Ollama JSON call + timeout.
3. pyverilog returned different object shapes across versions; replaced its dataflow with a
   deterministic regex assignment finder.
4. Letting the LLM name the failing signal was unreliable; replaced with deterministic
   stage→signal routing.
5. Discovered the shared-assertion ambiguity and switched the headline metric to Rec@5.

---

## 11. Reproducibility

```
inject_bug.py         # generate 30 mutants + logs + labels
run_agent_eval.py     # run the agent -> predictions_agent.json
single_shot_baseline.py / regex_baseline.py
evaluate.py <preds>   # scores any predictions file
agent.py / agent_tools.py   # the 3-node pipeline + deterministic tools
src/fifo.v, src/mutants/*.v, tests/ (cocotb + Makefile), dataset/
```
Models run locally via Ollama (`qwen2.5-coder`, `llama3`).

---

## 12. Questions I'd like your view on

1. **Is the scope right for an internship portfolio piece, or should I deepen it?** Options
   I see: (a) add a second, larger DUT (e.g. an open RISC-V core) to test generalization;
   (b) add assertion-level observability to attack the ambiguity ceiling; (c) leave the
   pipeline as-is and invest in the write-up.
2. **Is Rec@5 over a candidate set a defensible primary metric**, or would a reviewer expect
   Top-1 / mean-reciprocal-rank? Should I report MRR as well?
3. **Class accuracy is low on the FILL-path classes.** Is that acceptable given the
   ambiguity argument, or is it worth adding features (e.g. inspecting whether a driver is a
   constant vs a flipped operator) to separate stuck_at from operator_flip?
4. **Baselines:** is a regex + a weak single-shot LLM a fair comparison, or should I add a
   stronger single-shot (same 7B model, no agent structure) to isolate the value of the
   agentic pipeline specifically?
5. **Presentation:** for the application, is the debugging arc (§10) worth foregrounding as
   evidence of engineering judgment, or should the report stay purely results-focused?
6. **Anything that would make this credibly "Infineon-relevant"** that I'm missing —
   integration with a real EDA flow, a different failure taxonomy, etc.?
```
