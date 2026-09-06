import os
import re
import json

DATASET_DIR = "dataset"
OUTPUT_FILE = "predictions.json"

def parse_log_for_baseline(log_path):
    with open(log_path, "r") as f:
        content = f.read()

    # Regex to catch standard Python/cocotb tracebacks OR Icarus Verilog errors
    # Matches: File "test_fifo.py", line 36
    # Matches: src/fifo.v:42: error: ...
    pattern = r"(?:File\s+[\"'](.*?)[\"'],\s+line\s+(\d+))|(?:([a-zA-Z0-9_/\.]+\.[vpq]):(\d+):)"
    
    matches = re.findall(pattern, content)
    
    predicted_lines = []
    for match in matches:
        # Extract line number depending on which regex group matched
        line = match[1] if match[1] else match[3]
        try:
            line_num = int(line)
            if line_num not in predicted_lines:
                predicted_lines.append(line_num)
        except ValueError:
            pass

    # A very basic, heuristic classification guess
    pred_class = "unknown"
    lower_content = content.lower()
    if "timeout" in lower_content:
        pred_class = "timeout"
    elif "assert" in lower_content or "fail" in lower_content:
        pred_class = "assertion_failure"

    return {
        "predicted_lines": predicted_lines[:3], # Keep only the top 3 guesses
        "predicted_class": pred_class
    }

def main():
    predictions = []
    # Loop through all generated logs
    for file in os.listdir(DATASET_DIR):
        if file.endswith(".log"):
            run_id = file.replace(".log", "")
            log_path = os.path.join(DATASET_DIR, file)
            
            result = parse_log_for_baseline(log_path)
            result["run_id"] = run_id
            predictions.append(result)

    # Overwrite the dummy predictions with our regex baseline
    with open(OUTPUT_FILE, "w") as f:
        json.dump(predictions, f, indent=4)
    
    print(f"Regex baseline predictions saved to {OUTPUT_FILE}.")

if __name__ == "__main__":
    main()
