import json
import re

from agent import _stage_signals, _src_lines, _candidate_lines, _is_structural
from agent_tools import parse_log, ast_trace_signal

LABELS_FILE = "dataset/labels.json"
DATASET_DIR = "dataset"

# The full signal vocabulary _stage_signals ever hands out, across all stages.
ALL_SIGNALS = sorted({sig for stage_log in
                       ["RESET STAGE", "FILL STAGE", "READBACK STAGE", ""]
                       for sig in _stage_signals(stage_log)})


def traced_lines(vpath, sig):
    t = ast_trace_signal(vpath, sig, top_module="fifo")
    return [int(n) for n in re.findall(r"Line (\d+):", t)]


def signals_matching_line(vpath, line_no):
    """Signals whose ast_trace_signal LHS regex actually fires on this exact line."""
    return [sig for sig in ALL_SIGNALS if line_no in traced_lines(vpath, sig)]


def unanchored_assignment_hits(text):
    """Signals assigned somewhere in the line (still '<=' or '=', not '=='), but not
    necessarily at the very start of the statement the way ast_trace_signal requires.
    Deliberately assignment-shaped so 'mem[rd_ptr] <= x' does NOT count rd_ptr (it's an
    index, not an assignment target) -- that case is a different signal (mem) entirely,
    not a regex-formatting miss."""
    return [sig for sig in ALL_SIGNALS
            if re.search(rf"{re.escape(sig)}\s*(\[[^\]]*\])?\s*(<=|=)(?!=)", text)]


def bare_signal_mentions(text):
    """Signal names appearing anywhere in the line at all, assigned or not -- just context."""
    return [sig for sig in ALL_SIGNALS if re.search(rf"\b{re.escape(sig)}\b", text)]


def main():
    labels = json.load(open(LABELS_FILE))
    misses = []

    for entry in labels:
        vpath = entry["file"]
        true_line = entry["line"]
        log_path = f"{DATASET_DIR}/{entry['run_id']}.log"

        log_summary = parse_log(log_path)
        sigs = _stage_signals(log_summary)

        ast_lines = []
        for sig in sigs:
            ast_lines.extend(traced_lines(vpath, sig))

        src = _src_lines(vpath)
        candidate_lines = _candidate_lines(ast_lines, src)

        if true_line not in candidate_lines:
            misses.append((entry, log_summary, sigs, src))

    print(f"{len(misses)}/{len(labels)} runs have the true line outside candidate_lines.\n")

    for entry, log_summary, sigs, src in misses:
        run_id, vpath, true_line, bug_type = entry["run_id"], entry["file"], entry["line"], entry["bug_type"]
        text = src[true_line - 1].strip() if 1 <= true_line <= len(src) else "<line out of range>"
        stage_m = re.search(r"FAILURE STAGE: (.+)", log_summary)
        stage = stage_m.group(1) if stage_m else "<unparsed>"

        strict_hits = signals_matching_line(vpath, true_line)
        unanchored_hits = unanchored_assignment_hits(text)
        bare_hits = bare_signal_mentions(text)

        print("=" * 78)
        print(f"{run_id}  [{bug_type}]")
        print(f"  true line {true_line}: {text}")
        print(f"  failure stage: {stage}")
        print(f"  _stage_signals returned: {sigs}")

        if strict_hits:
            for sig in strict_hits:
                if sig in sigs:
                    print(f"  VERDICT: ast_trace_signal DOES match '{sig}' on this line, and '{sig}' "
                          f"IS in the stage's signal list -> the line reached ast_lines but "
                          f"_is_structural()/_keep_line() dropped it before candidate_lines "
                          f"(is_structural={_is_structural(src[true_line - 1])})")
                else:
                    print(f"  VERDICT: ast_trace_signal DOES match '{sig}' on this line, but '{sig}' "
                          f"is NOT in the stage's signal list -> _stage_signals is missing "
                          f"'{sig}' for this failure stage (MAP GAP)")
        elif unanchored_hits:
            print(f"  VERDICT: signal(s) {unanchored_hits} ARE assigned on this line (just not where "
                  f"ast_trace_signal's start-of-statement anchor looks) -> REGEX MISS "
                  f"(assignment syntax/formatting defeats the anchored pattern)")
        else:
            note = f" (line references {bare_hits} but doesn't assign to it)" if bare_hits else ""
            print(f"  VERDICT: no tracked signal is assigned on this line{note} -> the true bug is on "
                  f"a signal outside {ALL_SIGNALS} entirely (UNKNOWN SIGNAL, not a map/regex bug)")
    print("=" * 78)


if __name__ == "__main__":
    main()
