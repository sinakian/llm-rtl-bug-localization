import json
import os
import shutil
import subprocess

ORIGINAL_FILE = "src/fifo.v"
COMPILE_TARGET = "src/fifo_buggy.v"   # the file the tests/Makefile actually compiles
MUTANT_DIR = "src/mutants"            # per-case copies preserved for the agent to read
DATASET_DIR = "dataset"

MUTATIONS = [
    {"id": "bug_001", "target": "wr_ptr <= wr_ptr + 1;", "replacement": "wr_ptr <= wr_ptr - 1;", "type": "operator_flip"},
    {"id": "bug_002", "target": "rd_ptr <= rd_ptr + 1;", "replacement": "rd_ptr <= rd_ptr - 1;", "type": "operator_flip"},
    {"id": "bug_003", "target": "assign full = (count == DEPTH);", "replacement": "assign full = (count == DEPTH - 1);", "type": "off_by_one"},
    {"id": "bug_004", "target": "data_out <= mem[rd_ptr];", "replacement": "data_out <= 0;", "type": "stuck_at"},
    {"id": "bug_005", "target": "count <= 0;", "replacement": "count <= 1;", "type": "wrong_reset"},
]

def main():
    os.makedirs(DATASET_DIR, exist_ok=True)
    os.makedirs(MUTANT_DIR, exist_ok=True)

    with open(ORIGINAL_FILE, "r") as f:
        original_lines = f.readlines()

    all_labels = []

    for mutation in MUTATIONS:
        # Build the mutant fresh from the ORIGINAL every time (single-bug isolation)
        mutated_lines = []
        label_data = None
        for i, line in enumerate(original_lines):
            if mutation["target"] in line:
                mutated_lines.append(line.replace(mutation["target"], mutation["replacement"]))
                # per-case preserved path is what the agent will read -> label points at it
                mutant_path = os.path.join(MUTANT_DIR, f"{mutation['id']}.v")
                label_data = {
                    "run_id": mutation["id"],
                    "file": mutant_path,
                    "line": i + 1,
                    "bug_type": mutation["type"],
                }
            else:
                mutated_lines.append(line)

        if not label_data:
            print(f"[{mutation['id']}] SKIPPED: could not find '{mutation['target']}' in {ORIGINAL_FILE}")
            continue

        # 1) preserve a per-case copy for the agent
        with open(label_data["file"], "w") as f:
            f.writelines(mutated_lines)
        # 2) write the SAME content to the file the Makefile compiles
        with open(COMPILE_TARGET, "w") as f:
            f.writelines(mutated_lines)

        # Run the simulation on THIS mutant (same make invocation you already use)
        src_path = os.path.abspath(COMPILE_TARGET)
        dump_path = os.path.abspath("tests/dump.v")
        result = subprocess.run(
            ["make", "-C", "tests", f"VERILOG_SOURCES={src_path} {dump_path}"],
            capture_output=True, text=True,
        )
        output = result.stdout + result.stderr

        # Always save the log (even on unexpected pass) so you can inspect it
        log_path = os.path.join(DATASET_DIR, f"{mutation['id']}.log")
        with open(log_path, "w") as f:
            f.write(output)

        if "FAIL=1" in output:
            all_labels.append(label_data)
            symptom = ""
            for ln in output.splitlines():
                if "AssertionError" in ln:
                    symptom = ln.strip()[:100]
                    break
            print(f"[{mutation['id']}] OK  ({mutation['type']}, line {label_data['line']})  {symptom}")
        else:
            print(f"[{mutation['id']}] WARNING: no FAIL=1 -> not adding to labels. Last lines:")
            print("\n".join(output.strip().split("\n")[-3:]))

    with open(os.path.join(DATASET_DIR, "labels.json"), "w") as f:
        json.dump(all_labels, f, indent=4)
    print(f"\nWrote {len(all_labels)} labels to {DATASET_DIR}/labels.json")

if __name__ == "__main__":
    main()