PYTHON := venv/bin/python

.PHONY: all dataset agent baselines eval help

.DEFAULT_GOAL := eval

# --- eval: scoring only, no LLM, no prerequisites -----------------------------------
# Runs entirely against the predictions/dataset files already committed in results/ and
# dataset/. Reviewers can run this with no Ollama server and no iverilog/vvp installed.
eval:
	$(PYTHON) eval/random_baseline.py --agent-predictions results/predictions_qwen2.5-coder-latest_seed0.json --seeds 100
	$(PYTHON) eval/evaluate.py results/predictions_qwen2.5-coder-latest_seed0.json
	$(PYTHON) eval/compare_all.py --seeds 100

# --- Everything below here calls Ollama and/or overwrites committed files. -----------

# Regenerate the mutant dataset (mutants + per-case logs + dataset/labels.json).
# Overwrites the committed dataset/ fixture.
dataset:
	@echo "WARNING: regenerates dataset/*.log, src/mutants/*.v, and dataset/labels.json,"
	@echo "         overwriting the committed dataset/ fixture. ~1 min."
	$(PYTHON) src/inject_bug.py

# The full LLM sweep: both models, 3 seeds each, via run_agent_eval.py --repeats.
# Overwrites the committed results/predictions_<model>_seed<k>.json files.
agent:
	@echo "WARNING: runs the full agent LLM sweep against a local Ollama server and"
	@echo "         OVERWRITES the committed results/predictions_*_seed*.json files."
	@echo "         ~35 min PER MODEL (~70 min total for both). Requires Ollama running."
	$(PYTHON) eval/run_agent_eval.py --model qwen2.5-coder:latest --repeats 3
	$(PYTHON) eval/run_agent_eval.py --model llama3:latest --repeats 3

# Non-agent baselines: regex (no LLM) + single-shot 7B (needs Ollama).
# Overwrites the committed results/predictions_regex.json and results/predictions_singleshot_7b.json.
baselines:
	@echo "WARNING: single-shot 7B needs a local Ollama server, and both baselines"
	@echo "         OVERWRITE their committed results/*.json files. ~2 min."
	$(PYTHON) eval/regex_baseline.py
	$(PYTHON) eval/single_shot_baseline.py --model qwen2.5-coder:latest --seed 0 --out results/predictions_singleshot_7b.json

# Full rebuild from scratch: regenerate the dataset, re-run every method, then score.
# ~2 hours total. Requires Ollama running and iverilog/vvp on PATH.
all: dataset agent baselines eval

help:
	@echo "Targets:"
	@echo "  eval        (default) score the predictions/dataset already committed in"
	@echo "              results/ and dataset/. No Ollama needed. ~seconds."
	@echo "  baselines   regenerate regex + single-shot 7B predictions. Needs Ollama."
	@echo "              Overwrites committed results/*.json. ~2 min."
	@echo "  agent       run the full LLM sweep (qwen2.5-coder + llama3, 3 seeds each)."
	@echo "              Needs Ollama. Overwrites committed results/*.json."
	@echo "              ~35 min PER MODEL, ~70 min total."
	@echo "  dataset     regenerate dataset/*.log + labels.json from src/fifo.v mutations."
	@echo "              Overwrites committed dataset/. ~1 min."
	@echo "  all         dataset + agent + baselines + eval -- full rebuild from scratch."
	@echo "              ~2 hours total. Needs Ollama and iverilog/vvp on PATH."
