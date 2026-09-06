import os
import json
from agent import triage_run

DATASET_DIR = "dataset"
VERILOG_FILE = "src/fifo_buggy.v"
OUTPUT_FILE = "predictions.json"

def main():
    predictions = []
    log_files = sorted([f for f in os.listdir(DATASET_DIR) if f.endswith(".log")])
    
    for file in log_files:
        run_id = file.replace(".log", "")
        log_path = os.path.join(DATASET_DIR, file)
        print(f"Running LangGraph agent on {run_id}...")
        
        result = triage_run(run_id, log_path, VERILOG_FILE)
        predictions.append(result)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(predictions, f, indent=4)
        
    print(f"\nAgent triage complete. Results written to {OUTPUT_FILE}.")

if __name__ == "__main__":
    main()
