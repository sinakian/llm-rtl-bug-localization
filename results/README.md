# results/

Every file this repo's scripts read or write by default. All scripts' default output paths
point here — see the root `README.md` (Section 8) for the commands that regenerate any of these.

| File | Model | Seed | Temperature | Candidate set | Cited in root README table |
|---|---|---|---|---|---|
| `predictions_qwen2.5-coder-latest_seed0.json` | qwen2.5-coder:latest | 0 | 0 | v2 (16-candidate) | **Baseline comparison** — agent (Qwen2.5-Coder 7B); **Effect of candidate-set expansion** — v2 row; also the candidate-set source for the random-in-candidates control |
| `predictions_qwen2.5-coder-latest_seed1.json` | qwen2.5-coder:latest | 1 | 0 | v2 (16-candidate) | **Baseline comparison** — agent (Qwen2.5-Coder 7B) |
| `predictions_qwen2.5-coder-latest_seed2.json` | qwen2.5-coder:latest | 2 | 0 | v2 (16-candidate) | **Baseline comparison** — agent (Qwen2.5-Coder 7B) |
| `predictions_llama3-latest_seed0.json` | llama3:latest | 0 | 0 | v2 (16-candidate) | **Baseline comparison** — agent (Llama-3 8B) |
| `predictions_llama3-latest_seed1.json` | llama3:latest | 1 | 0 | v2 (16-candidate) | **Baseline comparison** — agent (Llama-3 8B) |
| `predictions_llama3-latest_seed2.json` | llama3:latest | 2 | 0 | v2 (16-candidate) | **Baseline comparison** — agent (Llama-3 8B) |
| `predictions_agent_v1_temp0.8.json` | qwen2.5-coder:latest | not recorded | 0.8 (Ollama default) | v1 (10-candidate) | **Effect of candidate-set expansion** — agent_v1 row |
| `predictions_regex.json` | n/a (no LLM) | n/a | n/a | n/a (no retrieval step) | **Baseline comparison** — regex |
| `predictions_singleshot_7b.json` | qwen2.5-coder:latest | 0 | 0 | n/a (sees the whole file, no candidate-set retrieval) | **Baseline comparison** — single-shot 7B |
| `random_sample_seed0.json` | n/a (synthetic shuffle, no LLM) | 0 | n/a | v2 (16-candidate, borrowed from the qwen seed-0 file) | Not cited — see below |

## agent_v1_temp0.8: a single uncontrolled run

Stated plainly: `predictions_agent_v1_temp0.8.json` is **one single run at Ollama's default
sampling temperature (0.8), with no seed recorded**. It predates the `temperature=0` + fixed-seed
change described in the root README (Section 8), which is why the temperature is written into
the filename instead of being a field inside it. It is not a seed-averaged figure — there is
no `±` on its numbers because there is nothing to average — and it should not be compared
statistically against the seed-averaged v2 rows next to it in the "Effect of candidate-set
expansion" table. It also predates the `model`/`seed`/`candidate_lines` fields other files here
carry; its model (qwen2.5-coder:latest) is known only from the `agent.py` `MODEL_NAME` history at
the time it was generated, not from the file itself.

## random_sample_seed0.json: not scored by any table

This file is a representative sample, not an input to any table. The actual random-in-candidates
row in both root README tables is computed live, seed-averaged over 100 seeds
(`random_baseline.py --seeds 100`), sourced from whichever file backs the current agent-qwen
seed group. `random_sample_seed0.json` is just what that shuffle looks like for one seed (0), kept
for manual inspection; it deliberately isn't named `predictions_*.json` so `compare_all.py`'s
discovery never has to special-case excluding it.

## Deleted, not just moved

Four earlier files were removed with `git rm` (recoverable from git history, not from this
directory): `predictions_agent.json` and `predictions_agent_llama3.json` (both superseded once
their respective 3-seed groups existed — `compare_all.py` never had a way to prefer them once the
seed group was present), `predictions_llama3.json` (an earlier, non-standard-named llama3 run,
fully superseded), and `predictions_singleshot_7b_v1.json` (a byte-for-byte duplicate of
`predictions_singleshot_7b.json`).
