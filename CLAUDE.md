# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo does

A research harness that benchmarks LLM-based bug localization on a buggy Verilog FIFO. A
`fifo.v` design is mutated with known single-line bugs (`inject_bug.py`), each mutant is
simulated against a cocotb testbench to produce a failure log, and three different triage
methods try to predict which source line caused the failure:

- **regex baseline** (`regex_baseline.py`) — parses file:line refs straight out of the log/traceback.
- **single-shot LLM baseline** (`single_shot_baseline.py`) — dumps the whole numbered source + log to a small model (`qwen2.5-coder:1.5b`) in one shot.
- **agent** (`agent.py` + `agent_tools.py`) — a LangGraph pipeline that classifies the failure stage, deterministically traces candidate signals through the source, and has a larger model (`llama3:latest`, configurable) rank/select from that deterministic candidate set only.

`evaluate.py` scores any of the three prediction files against `dataset/labels.json` with
Top-1 / Top-3 / Top-3±tolerance / Recall@5 / class-accuracy metrics, broken out per bug
category (`operator_flip`, `off_by_one`, `stuck_at`, `wrong_reset`).

The core research bet under test: constraining an LLM to rank within a deterministically-derived
candidate set (dataflow trace of signals implicated by the failing test stage) beats letting it
free-hallucinate line numbers over the raw source. Don't lose this constraint when touching
`agent.py` — the model's `predicted_lines` are always filtered down to `ast_lines` in `_coerce`,
with the full deterministic candidate list appended as a backstop so weak models can't tank
recall.

## Prerequisites

- Ollama running locally (`OLLAMA_URL = http://localhost:11434/api/generate`) with the models
  referenced in `agent.py` (`MODEL_NAME`) and `single_shot_baseline.py` (`OLLAMA_MODEL`) pulled.
- `iverilog`/`vvp` (Icarus Verilog) on PATH for cocotb simulation.
- Python deps from `requirements.txt` (a `venv/` already exists in-repo — activate it rather
  than reinstalling globally).

## Common commands

```bash
source venv/bin/activate

# Regenerate the mutant dataset (mutants + per-case logs + dataset/labels.json)
python inject_bug.py

# Run each triage method over dataset/*.log
python regex_baseline.py           # -> predictions_regex.json
python single_shot_baseline.py     # -> predictions_singleshot.json
python run_agent_eval.py           # -> predictions_agent.json (drives agent.py's LangGraph pipeline)

# Score a predictions file against dataset/labels.json
python evaluate.py predictions_agent.json
python evaluate.py predictions_regex.json --tol 3   # adjust the +/- line tolerance metric

# Run the cocotb testbench directly against a single Verilog file
make -C tests VERILOG_SOURCES="$(pwd)/src/fifo.v $(pwd)/tests/dump.v"

# Debug a single case end-to-end (stage classification -> AST trace -> raw model output -> coercion)
python debug_probe.py   # edit `rid = "bug_NNN"` at the top to target a different case
```

There is no test suite for the harness code itself — `tests/` holds the cocotb testbench
(`test_fifo.py`) used to *generate* the dataset, not to test this repo's Python.

## Architecture

**Mutation pipeline** (`inject_bug.py`): `MUTATIONS` is a hardcoded list of single-line
find/replace edits against `src/fifo.v`, each tagged with a bug class. For every mutation it
writes a per-case mutant to `src/mutants/bug_NNN.v`, copies it to `src/fifo_buggy.v` (the fixed
path the `tests/Makefile` compiles), runs the cocotb sim via `make -C tests`, and captures the
output to `dataset/bug_NNN.log`. Mutations that don't actually fail the testbench are silently
dropped ("escaped") — a bug is only kept if it's observable. Ground truth accumulates in
`dataset/labels.json` as `{run_id, file, line, bug_type}`, where `file` points at that case's own
`src/mutants/*.v` copy (not the shared `fifo_buggy.v`, which gets overwritten each run).

**Testbench structure matters**: `tests/test_fifo.py` checks reset → fill (8 writes) → readback
(8 reads) *in order* and aborts at the first failing assertion. This ordering is the basis for
`agent_tools.parse_log`'s "failure stage" classification (RESET / FILL / READBACK / UNKNOWN),
which both the agent and (implicitly) the bug taxonomy are built around.

**Agent pipeline** (`agent.py`, LangGraph `StateGraph` over `AgentState`):
1. `classify_node` → `agent_tools.parse_log` extracts the failing assertion and derives the
   failure stage + a coarse bug-class prior.
2. `gather_context_node` → `_stage_signals` maps the stage to a fixed union of candidate signal
   names (e.g. FILL stage → `full, count, wr_ptr, rd_ptr, data_out`), then
   `agent_tools.ast_trace_signal` regex-matches each signal's assignment sites (LHS of `<=`/`=`,
   not `==`) to get exact candidate line numbers. This is deliberately *not* a real AST walk
   (pyverilog's dataflow graph doesn't reliably carry source line numbers) — it's a targeted,
   version-independent regex anchored to statement starts.
3. `hypothesize_and_emit_node` → prompts the model with the full source, the stage prior, and
   the closed candidate line list, asking it to rank within that list and emit a bug class.
   `_coerce` is the safety net: it parses the model's (possibly malformed) JSON, keeps only
   predicted lines that are in the deterministic candidate set, ranks the model's ordering first
   and appends any unranked candidates after, and falls back to the raw candidate list if the
   model output is unusable. Structural lines (`always`, `begin`/`end`, `module`, comments,
   blank lines) are always filtered out via `_is_structural`.

**Evaluation** (`evaluate.py`): joins predictions to `dataset/labels.json` by `run_id`, and per
bug category reports Top-1, Top-3, Top-3-with-line-tolerance, Recall@5, and predicted-class
accuracy, plus an aggregate row.

## Working in this repo

- `src/fifo_buggy.v` and `tests/dump.v`/`tests/sim_build/` are build artifacts regenerated by
  `inject_bug.py` / the cocotb Makefile — don't hand-edit them, edit `src/fifo.v` or
  `MUTATIONS` instead.
- The top-level `labels.json` and `predictions.json` are stale, pre-refactor artifacts from
  before the per-case `dataset/labels.json` / `src/mutants/*.v` scheme; the dataset-scoped files
  are the current source of truth.
- `parser.out` / `parsetab.py` are leftover PLY parser tables from an earlier pyverilog-based
  approach that `agent_tools.ast_trace_signal` explicitly moved away from (see the docstring) —
  they aren't imported by any current code path.
- When adding a new mutation type or signal to trace, update `_stage_signals` in `agent.py` (the
  candidate signal set per failure stage) — the agent's recall is bounded by whether the true
  bug's signal is in that union.
