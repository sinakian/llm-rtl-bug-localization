import os
import re
import sys
import json
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from agent import triage_run, MODEL_NAME

DATASET_DIR = "dataset"
LABELS_FILE = "dataset/labels.json"
RESULTS_DIR = "results"

def safe_model_name(model):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model)

def run_sweep(labels, log_files, model, seed):
    predictions = []
    for file in log_files:
        run_id = file.replace(".log", "")
        if run_id not in labels:
            print(f"Skipping {run_id}: no label entry.")
            continue
        log_path = os.path.join(DATASET_DIR, file)
        verilog_path = labels[run_id]["file"]      # per-case mutant path
        print(f"Running agent on {run_id}  (model={model}, seed={seed}, src={verilog_path}) ...")
        predictions.append(triage_run(run_id, log_path, verilog_path, model=model, seed=seed))
    return predictions

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL_NAME,
                    help=f"Ollama model to use, overriding agent.MODEL_NAME (default: {MODEL_NAME})")
    ap.add_argument("--seed", type=int, default=0,
                    help="Ollama sampling seed, paired with temperature=0 (default: 0)")
    ap.add_argument("--repeats", type=int, default=None,
                    help="run the whole 30-case sweep this many times with seeds 0..N-1, "
                         f"writing {RESULTS_DIR}/predictions_<model>_seed<k>.json each time "
                         "(ignores --out)")
    ap.add_argument("--out", default=f"{RESULTS_DIR}/predictions_agent.json")
    args = ap.parse_args()

    # Map run_id -> that case's OWN mutant file (the fix: no single hardcoded file)
    with open(LABELS_FILE) as f:
        labels = {x["run_id"]: x for x in json.load(f)}

    log_files = sorted(f for f in os.listdir(DATASET_DIR) if f.endswith(".log"))
    os.makedirs(RESULTS_DIR, exist_ok=True)

    if args.repeats:
        for k in range(args.repeats):
            predictions = run_sweep(labels, log_files, args.model, k)
            out_path = f"{RESULTS_DIR}/predictions_{safe_model_name(args.model)}_seed{k}.json"
            with open(out_path, "w") as f:
                json.dump(predictions, f, indent=4)
            print(f"\nAgent triage complete ({args.model}, seed={k}) -> {out_path}")
    else:
        predictions = run_sweep(labels, log_files, args.model, args.seed)
        with open(args.out, "w") as f:
            json.dump(predictions, f, indent=4)
        print(f"\nAgent triage complete ({args.model}, seed={args.seed}) -> {args.out}")

if __name__ == "__main__":
    main()
