import os
import json
import argparse
import requests

DATASET_DIR = "dataset"
LABELS_FILE = "dataset/labels.json"
OLLAMA_MODEL = "qwen2.5-coder:1.5b"   # deliberately small: this is the weak baseline to beat
OLLAMA_URL = "http://localhost:11434/api/generate"

def numbered(path):
    with open(path) as f:
        return "".join(f"{i+1}: {ln}" for i, ln in enumerate(f.readlines()))

def get_llm_prediction(log_content, verilog_numbered):
    prompt = f"""You are an expert hardware verification engineer.
A SystemVerilog simulation has failed.

Verilog source (line numbers are authoritative):
{verilog_numbered}

Failing simulation log:
{log_content}

Task:
1. List the top 3 most likely line numbers (from the numbered source) causing the bug.
2. Classify into EXACTLY one of: operator_flip, off_by_one, stuck_at, wrong_reset.

Output ONLY this JSON:
{{"predicted_lines": [l1, l2, l3], "predicted_class": "category"}}"""
    payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"}
    try:
        r = requests.post(OLLAMA_URL, json=payload)
        return json.loads(r.json().get("response", "{}"))
    except Exception as e:
        print(f"  error: {e}")
        return {"predicted_lines": [], "predicted_class": "unknown"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="predictions_singleshot.json")
    args = ap.parse_args()

    with open(LABELS_FILE) as f:
        labels = {x["run_id"]: x for x in json.load(f)}

    predictions = []
    for file in sorted(f for f in os.listdir(DATASET_DIR) if f.endswith(".log")):
        run_id = file.replace(".log", "")
        if run_id not in labels:
            continue
        with open(os.path.join(DATASET_DIR, file)) as f:
            log_content = f.read()
        verilog_numbered = numbered(labels[run_id]["file"])   # per-case mutant, numbered
        print(f"Analyzing {run_id}...")
        result = get_llm_prediction(log_content, verilog_numbered)
        result["run_id"] = run_id
        predictions.append(result)

    with open(args.out, "w") as f:
        json.dump(predictions, f, indent=4)
    print(f"Single-shot predictions -> {args.out}")

if __name__ == "__main__":
    main()