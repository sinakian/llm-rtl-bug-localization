import os
import re
import json
import argparse

DATASET_DIR = "dataset"
RESULTS_DIR = "results"

def parse_log_for_baseline(log_path):
    with open(log_path, "r") as f:
        content = f.read()

    # Python/cocotb tracebacks OR Icarus errors
    pattern = r"(?:File\s+[\"'](.*?)[\"'],\s+line\s+(\d+))|(?:([a-zA-Z0-9_/\.]+\.[vpq]):(\d+):)"
    matches = re.findall(pattern, content)

    predicted_lines = []
    for match in matches:
        line = match[1] if match[1] else match[3]
        try:
            n = int(line)
            if n not in predicted_lines:
                predicted_lines.append(n)
        except ValueError:
            pass

    lower = content.lower()
    if "timeout" in lower:
        pred_class = "timeout"
    elif "assert" in lower or "fail" in lower:
        pred_class = "assertion_failure"
    else:
        pred_class = "unknown"

    return {"predicted_lines": predicted_lines[:3], "predicted_class": pred_class}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=f"{RESULTS_DIR}/predictions_regex.json")
    args = ap.parse_args()

    predictions = []
    for file in os.listdir(DATASET_DIR):
        if file.endswith(".log"):
            run_id = file.replace(".log", "")
            result = parse_log_for_baseline(os.path.join(DATASET_DIR, file))
            result["run_id"] = run_id
            predictions.append(result)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(predictions, f, indent=4)
    print(f"Regex baseline predictions -> {args.out}")

if __name__ == "__main__":
    main()