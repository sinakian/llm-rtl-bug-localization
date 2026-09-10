import re
import json
import time
import argparse

from agent import (
    classify_node, gather_context_node, _stage_signals, _src_lines, _candidate_lines, MODEL_NAME,
)

DATASET_DIR = "dataset"
LABELS_FILE = "dataset/labels.json"
REPLAY_FILE = "results/predictions_qwen2.5-coder-latest_seed1.json"


def header(n, title):
    print()
    print("=" * 70)
    print(f" STEP {n}: {title}")
    print("=" * 70)


def load_json_by_run_id(path):
    return {x["run_id"]: x for x in json.load(open(path))}


def trimmed_log_excerpt(log_path):
    """The raw log, trimmed down to the traceback that names the failing assertion --
    not the derived failure-stage classification, which is agent_tools.parse_log's job
    and belongs to Step 3, not this raw excerpt."""
    lines = open(log_path).read().splitlines()
    start = end = None
    for i, line in enumerate(lines):
        if "Traceback (most recent call last):" in line:
            start = i
        if "AssertionError:" in line:
            end = i
            break
    if start is None or end is None:
        return "\n".join(lines[-5:])
    return "\n".join(l.strip() for l in lines[start:end + 1])


def mrr_for(predicted_lines, true_line):
    return (1.0 / (predicted_lines.index(true_line) + 1)) if true_line in predicted_lines else 0.0


def step1_bug(entry, src):
    header(1, "THE INJECTED BUG (hidden from the agent)")
    line = entry["line"]
    print(f"File:      {entry['file']}")
    print(f"Line:      {line}")
    print(f"Source:    {src[line - 1].strip()}")
    print(f"Bug class: {entry['bug_type']}   <-- hidden from the agent")


def step2_log(log_path):
    header(2, "FAILING SIMULATION LOG (trimmed to the failing assertion)")
    print(trimmed_log_excerpt(log_path))


def step3_retrieval(run_id, log_path, verilog_path, src):
    header(3, "DETERMINISTIC RETRIEVAL")
    # classify_node/gather_context_node print their own "[classify]"/"[gather_context]"
    # progress lines -- run them here, after the header, so those lines land under STEP 3
    # (where they belong) instead of trailing STEP 2's log excerpt.
    state = {"run_id": run_id, "log_path": log_path, "verilog_path": verilog_path}
    state.update(classify_node(state))
    state.update(gather_context_node(state))
    state["candidate_lines"] = _candidate_lines(state["ast_lines"], src, set(state["condition_lines"]))

    stage = re.search(r"FAILURE STAGE: (.+)", state["log_summary"])
    signals = _stage_signals(state["log_summary"])
    n_cand = len(state["candidate_lines"])
    print(f"Failure stage: {stage.group(1) if stage else '?'}")
    print(f"Signal list:   {signals}")
    print(f"Candidate set: {n_cand} candidates out of {len(src)} source lines")
    return state


def step4_agent(result, src):
    header(4, "AGENT OUTPUT (ranked)")
    for i, n in enumerate(result["predicted_lines"], 1):
        text = src[n - 1].strip() if 1 <= n <= len(src) else "?"
        print(f"  {i}. line {n:>3}: {text}")
    print(f"\npredicted_class: {result['predicted_class']}")
    print(f"rationale: {result['rationale']}")


def step5_verdict(result, entry):
    header(5, "VERDICT")
    true_line = entry["line"]
    true_class = entry["bug_type"]
    pls = result["predicted_lines"]
    pcls = result["predicted_class"]

    rank1 = bool(pls) and pls[0] == true_line
    class_hit = pcls == true_class

    label_rank = f"True line {true_line} ranked #1:"
    label_class = f"Class {true_class} predicted:"
    label_rr = "Reciprocal rank for this case:"
    width = max(len(label_rank), len(label_class), len(label_rr)) + 1

    print(f"{label_rank:<{width}}{'YES' if rank1 else 'NO'}")
    class_line = f"{label_class:<{width}}{'YES' if class_hit else 'NO'}"
    if not class_hit:
        class_line += f" (predicted {pcls})"
    print(class_line)  # always shown, correct or not
    print(f"{label_rr:<{width}}{mrr_for(pls, true_line):.2f}")


def print_closing_note():
    print()
    print("Localization beats chance (22% Top-1 vs 6% random); class prediction does not")
    print("(26% vs 25% chance). See README section 6.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default="bug_001", help="dataset case to demo (see dataset/labels.json)")
    ap.add_argument("--replay", action=argparse.BooleanOptionalAction, default=True,
                     help=f"read {REPLAY_FILE} instead of calling Ollama (default: on). "
                          f"Pass --no-replay to run the live agent instead.")
    ap.add_argument("--replay-file", default=REPLAY_FILE)
    ap.add_argument("--model", default=MODEL_NAME, help="model to use with --no-replay")
    ap.add_argument("--seed", type=int, default=1, help="seed to use with --no-replay")
    ap.add_argument("--pause", type=float, default=1.5, help="seconds to pause between sections")
    args = ap.parse_args()

    labels = load_json_by_run_id(LABELS_FILE)
    if args.run_id not in labels:
        raise SystemExit(f"Unknown run_id {args.run_id!r}; see dataset/labels.json")
    entry = labels[args.run_id]
    log_path = f"{DATASET_DIR}/{args.run_id}.log"
    src = _src_lines(entry["file"])

    step1_bug(entry, src)
    time.sleep(args.pause)

    step2_log(log_path)
    time.sleep(args.pause)

    # classify + gather_context are deterministic (no LLM call) in both modes -- step3_retrieval
    # runs them itself, after printing its own header, so their "[classify]"/"[gather_context]"
    # progress lines land under STEP 3 instead of trailing STEP 2's log excerpt.
    step3_retrieval(args.run_id, log_path, entry["file"], src)
    time.sleep(args.pause)

    if args.replay:
        replay_preds = load_json_by_run_id(args.replay_file)
        if args.run_id not in replay_preds:
            raise SystemExit(f"{args.run_id!r} not found in {args.replay_file}")
        result = replay_preds[args.run_id]
    else:
        from agent import triage_run
        result = triage_run(args.run_id, log_path, entry["file"], model=args.model, seed=args.seed)

    step4_agent(result, src)
    time.sleep(args.pause)

    step5_verdict(result, entry)
    print_closing_note()


if __name__ == "__main__":
    main()


# Recommended commands:
#   python demo.py --run-id bug_001   # agent ranks the true line #1 (a clean win)
#   python demo.py --run-id bug_004   # agent misses the true line entirely (an honest failure)
