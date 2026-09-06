import os
import json
import argparse
from agent import triage_run

DATASET_DIR = "dataset"
LABELS_FILE = "dataset/labels.json"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="predictions_agent.json")
    args = ap.parse_args()

    # Map run_id -> that case's OWN mutant file (the fix: no single hardcoded file)
    with open(LABELS_FILE) as f:
        labels = {x["run_id"]: x for x in json.load(f)}

    predictions = []
    log_files = sorted(f for f in os.listdir(DATASET_DIR) if f.endswith(".log"))

    for file in log_files:
        run_id = file.replace(".log", "")
        if run_id not in labels:
            print(f"Skipping {run_id}: no label entry.")
            continue
        log_path = os.path.join(DATASET_DIR, file)
        verilog_path = labels[run_id]["file"]      # per-case mutant path
        print(f"Running agent on {run_id}  (src={verilog_path}) ...")
        predictions.append(triage_run(run_id, log_path, verilog_path))

    with open(args.out, "w") as f:
        json.dump(predictions, f, indent=4)
    print(f"\nAgent triage complete -> {args.out}")

if __name__ == "__main__":
    main()