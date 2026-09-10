PYTHON := venv/bin/python

.PHONY: all dataset agent baselines eval

all: eval

# Regenerate the mutant dataset (mutants + per-case logs + dataset/labels.json)
dataset:
	$(PYTHON) inject_bug.py

# Agent triage, single run (seed 0) against the default model
agent: dataset
	$(PYTHON) run_agent_eval.py --model qwen2.5-coder:latest --seed 0 --out predictions_agent.json

# Non-agent baselines, plus the random-in-candidates control (needs agent's candidate_lines)
baselines: agent
	$(PYTHON) regex_baseline.py
	$(PYTHON) single_shot_baseline.py --model qwen2.5-coder:latest --seed 0 --out predictions_singleshot_7b.json
	$(PYTHON) random_baseline.py --agent-predictions predictions_agent.json --seeds 100

# Score everything
eval: baselines
	$(PYTHON) evaluate.py predictions_agent.json
	$(PYTHON) compare_all.py --seeds 100
