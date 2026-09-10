import os
import sys
import json
import re

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from agent import _stage_signals, _src_lines, _candidate_lines, _is_structural
from agent_tools import parse_log, ast_trace_signal, find_condition_lines

LABELS_FILE = "dataset/labels.json"
DATASET_DIR = "dataset"

# The full signal vocabulary _stage_signals ever hands out, across all stages.
ALL_SIGNALS = sorted({sig for stage_log in
                       ["RESET STAGE", "FILL STAGE", "READBACK STAGE", ""]
                       for sig in _stage_signals(stage_log)})


def assign_traced_lines(vpath, sig):
    t = ast_trace_signal(vpath, sig, top_module="fifo")
    return [int(n) for n in re.findall(r"Line (\d+):", t)]


def cond_traced_lines(vpath, sig):
    t = find_condition_lines(vpath, sig)
    return [int(n) for n in re.findall(r"Line (\d+):", t)]


def gather_lines(vpath, sigs):
    """Mirrors agent.gather_context_node: assignment hits first, then condition hits,
    deduped with order preserved. Returns (ast_lines, cond_line_set) so callers can
    reproduce _candidate_lines(ast_lines, src, cond_line_set) exactly."""
    assign_lines = [n for sig in sigs for n in assign_traced_lines(vpath, sig)]
    cond_lines = [n for sig in sigs for n in cond_traced_lines(vpath, sig)]
    ast_lines, seen = [], set()
    for n in assign_lines + cond_lines:
        if n not in seen:
            seen.add(n)
            ast_lines.append(n)
    return ast_lines, set(cond_lines)


def assign_signals_matching_line(vpath, line_no):
    """Signals whose ast_trace_signal LHS regex actually fires on this exact line."""
    return [sig for sig in ALL_SIGNALS if line_no in assign_traced_lines(vpath, sig)]


def cond_signals_matching_line(vpath, line_no):
    """Signals whose find_condition_lines regex actually fires on this exact line."""
    return [sig for sig in ALL_SIGNALS if line_no in cond_traced_lines(vpath, sig)]


def unanchored_assignment_hits(text):
    """Signals assigned somewhere in the line (still '<=' or '=', not '=='), but not
    necessarily at the very start of the statement the way ast_trace_signal requires.
    Deliberately assignment-shaped so 'mem[rd_ptr] <= x' does NOT count rd_ptr (it's an
    index, not an assignment target) -- that case is a different signal (mem) entirely,
    not a regex-formatting miss."""
    return [sig for sig in ALL_SIGNALS
            if re.search(rf"{re.escape(sig)}\s*(\[[^\]]*\])?\s*(<=|=)(?!=)", text)]


def unanchored_condition_hits(text):
    """Signals that sit inside an if/while/case(...) or a ternary on this line, even if
    find_condition_lines' own single-paren-group / single-'?' parsing missed it (e.g.
    nested parens defeating its '[^)]*' capture)."""
    has_cond_kw = re.search(r"\b(if|while|case)\s*\(", text)
    has_ternary = "?" in text and ":" in text
    if not (has_cond_kw or has_ternary):
        return []
    return [sig for sig in ALL_SIGNALS if re.search(rf"\b{re.escape(sig)}\b", text)]


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

        src = _src_lines(vpath)
        ast_lines, cond_line_set = gather_lines(vpath, sigs)
        candidate_lines = _candidate_lines(ast_lines, src, cond_line_set)

        if true_line not in candidate_lines:
            misses.append((entry, log_summary, sigs, src, cond_line_set))

    print(f"{len(misses)}/{len(labels)} runs have the true line outside candidate_lines.\n")

    for entry, log_summary, sigs, src, cond_line_set in misses:
        run_id, vpath, true_line, bug_type = entry["run_id"], entry["file"], entry["line"], entry["bug_type"]
        text = src[true_line - 1].strip() if 1 <= true_line <= len(src) else "<line out of range>"
        stage_m = re.search(r"FAILURE STAGE: (.+)", log_summary)
        stage = stage_m.group(1) if stage_m else "<unparsed>"

        assign_hits = assign_signals_matching_line(vpath, true_line)
        cond_hits = cond_signals_matching_line(vpath, true_line)
        unanchored_assign = unanchored_assignment_hits(text)
        unanchored_cond = unanchored_condition_hits(text)
        bare_hits = bare_signal_mentions(text)

        print("=" * 78)
        print(f"{run_id}  [{bug_type}]")
        print(f"  true line {true_line}: {text}")
        print(f"  failure stage: {stage}")
        print(f"  _stage_signals returned: {sigs}")

        if assign_hits:
            for sig in assign_hits:
                if sig in sigs:
                    is_cond = true_line in cond_line_set
                    print(f"  VERDICT: ast_trace_signal DOES match '{sig}' on this line, and '{sig}' "
                          f"IS in the stage's signal list -> the line reached ast_lines but "
                          f"_is_structural()/_keep_line() dropped it before candidate_lines "
                          f"(is_structural={_is_structural(src[true_line - 1], is_cond)})")
                else:
                    print(f"  VERDICT: ast_trace_signal DOES match '{sig}' on this line, but '{sig}' "
                          f"is NOT in the stage's signal list -> _stage_signals is missing "
                          f"'{sig}' for this failure stage (MAP GAP, assignment path)")
        elif cond_hits:
            for sig in cond_hits:
                if sig in sigs:
                    print(f"  VERDICT: find_condition_lines DOES match '{sig}' on this line, and '{sig}' "
                          f"IS in the stage's signal list -> this SHOULD be covered by the condition "
                          f"path already; candidate_lines still excluding it points at a bug in how "
                          f"condition_lines is threaded through _candidate_lines, not the map or regex")
                else:
                    print(f"  VERDICT: find_condition_lines DOES match '{sig}' on this line, but '{sig}' "
                          f"is NOT in the stage's signal list -> _stage_signals is missing "
                          f"'{sig}' for this failure stage (MAP GAP, condition path)")
        elif unanchored_assign:
            print(f"  VERDICT: signal(s) {unanchored_assign} ARE assigned on this line (just not where "
                  f"ast_trace_signal's start-of-statement anchor looks) -> REGEX MISS "
                  f"(assignment syntax/formatting defeats the anchored pattern)")
        elif unanchored_cond:
            print(f"  VERDICT: signal(s) {unanchored_cond} sit inside a condition/ternary on this line, "
                  f"but find_condition_lines' regex didn't match it (likely nested parens) -> "
                  f"CONDITION REGEX MISS")
        else:
            note = f" (line references {bare_hits} but doesn't assign or guard with it)" if bare_hits else ""
            print(f"  VERDICT: no tracked signal is assigned or used as a guard on this line{note} -> "
                  f"the true bug is on a signal outside {ALL_SIGNALS} entirely (UNKNOWN SIGNAL, "
                  f"not a map/regex bug)")
    print("=" * 78)


if __name__ == "__main__":
    main()
