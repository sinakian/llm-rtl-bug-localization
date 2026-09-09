import json
import os
import subprocess

ORIGINAL_FILE = "src/fifo.v"
COMPILE_TARGET = "src/fifo_buggy.v"   # file the tests/Makefile compiles
MUTANT_DIR = "src/mutants"            # per-case copies preserved for the agent
DATASET_DIR = "dataset"

# ~30 single-line mutations. Each target string is unique in fifo.v; each mutant is built
# fresh from the ORIGINAL, so reusing a target across entries is fine. Mutations that don't
# make the testbench FAIL are auto-skipped (reported as escaped).
MUTATIONS = [
    # --- operator_flip ---
    {"id": "bug_001", "target": "wr_ptr <= wr_ptr + 1;", "replacement": "wr_ptr <= wr_ptr - 1;", "type": "operator_flip"},
    {"id": "bug_002", "target": "rd_ptr <= rd_ptr + 1;", "replacement": "rd_ptr <= rd_ptr - 1;", "type": "operator_flip"},
    {"id": "bug_008", "target": "assign full = (count == DEPTH);", "replacement": "assign full = (count != DEPTH);", "type": "operator_flip"},
    {"id": "bug_009", "target": "assign empty = (count == 0);", "replacement": "assign empty = (count != 0);", "type": "operator_flip"},
    {"id": "bug_010", "target": "count <= count + 1;", "replacement": "count <= count - 1;", "type": "operator_flip"},
    {"id": "bug_011", "target": "count <= count - 1;", "replacement": "count <= count + 1;", "type": "operator_flip"},
    {"id": "bug_018", "target": "data_out <= mem[rd_ptr];", "replacement": "data_out <= mem[wr_ptr];", "type": "operator_flip"},
    {"id": "bug_019", "target": "mem[wr_ptr] <= data_in;", "replacement": "mem[rd_ptr] <= data_in;", "type": "operator_flip"},
    {"id": "bug_020", "target": "if (wr_en && !full) begin", "replacement": "if (wr_en && full) begin", "type": "operator_flip"},
    {"id": "bug_021", "target": "if (rd_en && !empty) begin", "replacement": "if (rd_en && empty) begin", "type": "operator_flip"},
    # --- off_by_one ---
    {"id": "bug_003", "target": "assign full = (count == DEPTH);", "replacement": "assign full = (count == DEPTH - 1);", "type": "off_by_one"},
    {"id": "bug_006", "target": "assign full = (count == DEPTH);", "replacement": "assign full = (count == DEPTH + 1);", "type": "off_by_one"},
    {"id": "bug_007", "target": "assign empty = (count == 0);", "replacement": "assign empty = (count == 1);", "type": "off_by_one"},
    {"id": "bug_012", "target": "count <= count + 1;", "replacement": "count <= count + 2;", "type": "off_by_one"},
    {"id": "bug_013", "target": "wr_ptr <= wr_ptr + 1;", "replacement": "wr_ptr <= wr_ptr + 2;", "type": "off_by_one"},
    {"id": "bug_014", "target": "rd_ptr <= rd_ptr + 1;", "replacement": "rd_ptr <= rd_ptr + 2;", "type": "off_by_one"},
    {"id": "bug_022", "target": "data_out <= mem[rd_ptr];", "replacement": "data_out <= mem[rd_ptr] + 1;", "type": "off_by_one"},
    {"id": "bug_029", "target": "data_out <= mem[rd_ptr];", "replacement": "data_out <= mem[rd_ptr - 1];", "type": "off_by_one"},
    # --- wrong_reset ---
    {"id": "bug_005", "target": "count <= 0;", "replacement": "count <= 1;", "type": "wrong_reset"},
    {"id": "bug_015", "target": "count <= 0;", "replacement": "count <= 2;", "type": "wrong_reset"},
    {"id": "bug_016", "target": "wr_ptr <= 0;", "replacement": "wr_ptr <= 1;", "type": "wrong_reset"},
    {"id": "bug_017", "target": "rd_ptr <= 0;", "replacement": "rd_ptr <= 1;", "type": "wrong_reset"},
    {"id": "bug_030", "target": "count <= 0;", "replacement": "count <= 3;", "type": "wrong_reset"},
    # --- stuck_at ---
    {"id": "bug_004", "target": "data_out <= mem[rd_ptr];", "replacement": "data_out <= 0;", "type": "stuck_at"},
    {"id": "bug_023", "target": "count <= count + 1;", "replacement": "count <= count;", "type": "stuck_at"},
    {"id": "bug_024", "target": "wr_ptr <= wr_ptr + 1;", "replacement": "wr_ptr <= wr_ptr;", "type": "stuck_at"},
    {"id": "bug_025", "target": "rd_ptr <= rd_ptr + 1;", "replacement": "rd_ptr <= rd_ptr;", "type": "stuck_at"},
    {"id": "bug_026", "target": "assign full = (count == DEPTH);", "replacement": "assign full = 1'b0;", "type": "stuck_at"},
    {"id": "bug_027", "target": "assign empty = (count == 0);", "replacement": "assign empty = 1'b1;", "type": "stuck_at"},
    {"id": "bug_028", "target": "mem[wr_ptr] <= data_in;", "replacement": "mem[wr_ptr] <= 0;", "type": "stuck_at"},
]


def main():
    os.makedirs(DATASET_DIR, exist_ok=True)
    os.makedirs(MUTANT_DIR, exist_ok=True)

    with open(ORIGINAL_FILE, "r") as f:
        original_lines = f.readlines()

    all_labels = []
    kept, escaped = 0, 0

    for mutation in MUTATIONS:
        mutated_lines = []
        label_data = None
        for i, line in enumerate(original_lines):
            if mutation["target"] in line:
                mutated_lines.append(line.replace(mutation["target"], mutation["replacement"]))
                mutant_path = os.path.join(MUTANT_DIR, f"{mutation['id']}.v")
                label_data = {"run_id": mutation["id"], "file": mutant_path,
                              "line": i + 1, "bug_type": mutation["type"]}
            else:
                mutated_lines.append(line)

        if not label_data:
            print(f"[{mutation['id']}] SKIP: target not found: '{mutation['target']}'")
            continue

        with open(label_data["file"], "w") as f:
            f.writelines(mutated_lines)
        with open(COMPILE_TARGET, "w") as f:
            f.writelines(mutated_lines)

        src_path = os.path.abspath(COMPILE_TARGET)
        dump_path = os.path.abspath("tests/dump.v")
        result = subprocess.run(
            ["make", "-C", "tests", f"VERILOG_SOURCES={src_path} {dump_path}"],
            capture_output=True, text=True,
        )
        output = result.stdout + result.stderr

        log_path = os.path.join(DATASET_DIR, f"{mutation['id']}.log")
        with open(log_path, "w") as f:
            f.write(output)

        if "FAIL=1" in output:
            all_labels.append(label_data)
            kept += 1
            sym = next((l.strip()[:70] for l in output.splitlines() if "AssertionError" in l), "")
            print(f"[{mutation['id']}] OK  {mutation['type']:<13} line {label_data['line']:<3} {sym}")
        else:
            escaped += 1
            os.remove(log_path)  # not a real case; keep dataset clean
            print(f"[{mutation['id']}] ESCAPED (no FAIL) -> skipped")

    with open(os.path.join(DATASET_DIR, "labels.json"), "w") as f:
        json.dump(all_labels, f, indent=4)
    print(f"\nWrote {kept} labels ({escaped} escaped) to {DATASET_DIR}/labels.json")


if __name__ == "__main__":
    main()