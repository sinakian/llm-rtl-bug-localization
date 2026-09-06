import json
import os
import subprocess

ORIGINAL_FILE = "src/fifo.v"
MUTATED_FILE = "src/fifo_buggy.v"
DATASET_DIR = "dataset"

MUTATIONS = [
    {"id": "bug_001", "target": "wr_ptr <= wr_ptr + 1;", "replacement": "wr_ptr <= wr_ptr - 1;", "type": "operator_flip"},
    {"id": "bug_002", "target": "rd_ptr <= rd_ptr + 1;", "replacement": "rd_ptr <= rd_ptr - 1;", "type": "operator_flip"},
    {"id": "bug_003", "target": "assign full = (count == DEPTH);", "replacement": "assign full = (count == DEPTH - 1);", "type": "off_by_one"},
    {"id": "bug_004", "target": "data_out <= mem[rd_ptr];", "replacement": "data_out <= 0;", "type": "stuck_at"},
    {"id": "bug_005", "target": "count <= 0;", "replacement": "count <= 1;", "type": "wrong_reset"}
]

def main():
    os.makedirs(DATASET_DIR, exist_ok=True)
    with open(ORIGINAL_FILE, "r") as f:
        original_lines = f.readlines()

    all_labels = []

    for mutation in MUTATIONS:
        mutated_lines = []
        label_data = None

        for i, line in enumerate(original_lines):
            if mutation["target"] in line:
                mutated_lines.append(line.replace(mutation["target"], mutation["replacement"]))
                label_data = {"run_id": mutation["id"], "file": "fifo.v", "line": i + 1, "bug_type": mutation["type"]}
            else:
                mutated_lines.append(line)
        
        if not label_data:
            print(f"[{mutation['id']}] SKIPPED: Could not find exactly '{mutation['target']}' in src/fifo.v")
            continue

        with open(MUTATED_FILE, "w") as f:
            f.writelines(mutated_lines)

        # Run simulation
        src_path = os.path.abspath(MUTATED_FILE)
        dump_path = os.path.abspath("tests/dump.v")
        result = subprocess.run(["make", "-C", "tests", f"VERILOG_SOURCES={src_path} {dump_path}"], capture_output=True, text=True)

        # Check result
        if "FAIL=1" in result.stdout:
            log_path = os.path.join(DATASET_DIR, f"{mutation['id']}.log")
            with open(log_path, "w") as f:
                f.write(result.stdout + result.stderr)
            all_labels.append(label_data)
            print(f"[{mutation['id']}] SUCCESS: Captured {mutation['type']}")
        else:
            print(f"[{mutation['id']}] SKIPPED: Simulation did not report FAIL=1. Last 3 lines of output:")
            # Print the last few lines of the terminal output so we can see the error
            print("\n".join((result.stdout + result.stderr).strip().split('\n')[-3:]))

    with open(os.path.join(DATASET_DIR, "labels.json"), "w") as f:
        json.dump(all_labels, f, indent=4)
        print("\nMaster labels.json updated.")

if __name__ == "__main__":
    main()
