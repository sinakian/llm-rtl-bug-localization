import os
import glob
import argparse

import evaluate

# Known predictions_*.json -> display label, in the row order the user wants.
# Multiple filenames can map to the same label (e.g. the un-suffixed default
# output uses whichever model is currently the default in that baseline).
FILE_LABELS = [
    ("predictions_random.json", "random"),
    ("predictions_regex.json", "regex"),
    ("predictions_singleshot_7b.json", "singleshot-7b"),
    ("predictions_agent_qwen.json", "agent-qwen"),
    ("predictions_agent_llama3.json", "agent-llama3"),
    ("predictions_agent.json", "agent-qwen"),                  # default MODEL_NAME is qwen2.5-coder:latest
]
FILE_LABEL_MAP = dict(FILE_LABELS)

ROW_ORDER = ["random", "regex", "singleshot-7b", "agent-qwen", "agent-llama3"]


def label_for(filename):
    if filename in FILE_LABEL_MAP:
        return FILE_LABEL_MAP[filename]
    stem = filename[len("predictions_"):-len(".json")] if filename.startswith("predictions_") else filename
    return stem


def discover(pattern="predictions_*.json"):
    """predictions_*.json present -> {label: path}, preferring the more explicit
    filename when two files would map to the same label."""
    by_label = {}
    for path in sorted(glob.glob(pattern)):
        fname = os.path.basename(path)
        label = label_for(fname)
        if label in by_label and len(os.path.basename(by_label[label])) >= len(fname):
            continue
        by_label[label] = path
    return by_label


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="dataset/labels.json")
    ap.add_argument("--tol", type=int, default=2)
    ap.add_argument("--out", help="also write the markdown table to this file")
    args = ap.parse_args()

    by_label = discover()
    order = [l for l in ROW_ORDER if l in by_label] + \
            sorted(l for l in by_label if l not in ROW_ORDER)

    if not order:
        raise SystemExit("No predictions_*.json files found.")

    lines = [
        "| Method | Top-1 | Top-3 | MRR | Rec@5 | Class |",
        "|---|---|---|---|---|---|",
    ]
    for label in order:
        _, tot, _, _ = evaluate.score(by_label[label], args.labels, args.tol)
        r = evaluate.rates(tot)
        lines.append(f"| {label} | {r['top1']:.0f}% | {r['top3']:.0f}% | {r['mrr']:.2f} | "
                      f"{r['recall5']:.0f}% | {r['class']:.0f}% |")

    table = "\n".join(lines)
    print(table)
    if args.out:
        with open(args.out, "w") as f:
            f.write(table + "\n")
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
