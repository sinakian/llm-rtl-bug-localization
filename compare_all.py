import os
import glob
import argparse
import statistics

import evaluate
import random_baseline

RESULTS_DIR = "results"

# Known predictions_*.json -> display label, in the row order the user wants. Matched
# against os.path.basename(path) in label_for(), so these stay bare filenames regardless
# of which directory discover() globs (see RESULTS_DIR). Deliberately does NOT include any
# entry for "agent-qwen"/"agent-llama3": those two labels are only ever satisfied by a
# multi-seed group (see AGENT_LABELS/resolve_method below), never a single file, so there's
# no filename fallback to silently score an unrelated single run in the group's place.
FILE_LABELS = [
    ("predictions_regex.json", "regex"),
    ("predictions_singleshot_7b.json", "singleshot-7b"),
]
FILE_LABEL_MAP = dict(FILE_LABELS)

MAIN_ROW_ORDER = ["random", "regex", "singleshot-7b", "agent-qwen", "agent-llama3"]

# Labels that MUST come from a multi-seed group (run_agent_eval.py --repeats), never a
# single-file fallback -- see resolve_method.
AGENT_LABELS = {"agent-qwen", "agent-llama3"}

DISPLAY_NAMES = {
    "random": "random-in-candidates",
    "regex": "regex",
    "singleshot-7b": "single-shot 7B",
    "agent-qwen": "agent (Qwen2.5-Coder 7B)",
    "agent-llama3": "agent (Llama-3 8B)",
}

# Which label a repeats-run seed file belongs to, keyed off the "model" field
# run_agent_eval.py now records in every prediction (not the filename -- run_agent_eval.py
# --repeats names files predictions_<safe_model>_seed<k>.json, which carries no "agent_qwen"
# / "agent_llama3" marker of its own).
AGENT_LABEL_BY_MODEL_SUBSTRING = [("qwen", "agent-qwen"), ("llama", "agent-llama3")]

AGENT_V1_FILE = f"{RESULTS_DIR}/predictions_agent_v1_temp0.8.json"


def label_for(filename):
    if filename in FILE_LABEL_MAP:
        return FILE_LABEL_MAP[filename]
    stem = filename[len("predictions_"):-len(".json")] if filename.startswith("predictions_") else filename
    return stem


def discover(pattern=f"{RESULTS_DIR}/predictions_*.json"):
    """results/predictions_*.json present -> {label: path}, preferring the more explicit
    filename when two files would map to the same label. random_sample_seed0.json doesn't
    match this glob at all (no "predictions_" prefix), so it needs no exclusion.
    predictions_agent_v1_temp0.8.json DOES match and gets picked up under a harmless
    fallback label ("agent_v1_temp0.8") that MAIN_ROW_ORDER never uses -- the second table
    reads it directly via AGENT_V1_FILE instead of through this dict."""
    by_label = {}
    for path in sorted(glob.glob(pattern)):
        fname = os.path.basename(path)
        label = label_for(fname)
        if label in by_label and len(os.path.basename(by_label[label])) >= len(fname):
            continue
        by_label[label] = path
    return by_label


def label_for_model(model_name):
    m = (model_name or "").lower()
    for sub, label in AGENT_LABEL_BY_MODEL_SUBSTRING:
        if sub in m:
            return label
    return None


def discover_seed_groups(pattern=f"{RESULTS_DIR}/predictions_*_seed*.json"):
    """label -> sorted list of seed-run file paths, one run_agent_eval.py --repeats
    produced per seed. Grouped by the 'model' field recorded inside each file rather
    than the filename (see AGENT_LABEL_BY_MODEL_SUBSTRING)."""
    groups = {}
    for path in sorted(glob.glob(pattern)):
        try:
            data = evaluate.load(path)
        except Exception:
            continue
        if not data or "model" not in data[0]:
            continue
        label = label_for_model(data[0]["model"])
        if label:
            groups.setdefault(label, []).append(path)
    return groups


def aggregate_rates(rate_dicts):
    """List of evaluate.rates()-shaped dicts (one per seed) -> {metric: (mean, std)}."""
    out = {}
    for k in rate_dicts[0]:
        if k == "n":
            out[k] = rate_dicts[0][k]
            continue
        xs = [r[k] for r in rate_dicts]
        out[k] = (statistics.mean(xs), statistics.stdev(xs) if len(xs) > 1 else 0.0)
    return out


def resolve_method(label, by_label, seed_groups, labels_path, tol):
    """(rates, paths) for a label -- rates is evaluate.rates()'s plain-float dict for a
    single file, or an aggregate_rates() {metric: (mean, std)} dict for a multi-seed group.
    len(paths) tells the caller how many seeds went in.

    AGENT_LABELS ("agent-qwen"/"agent-llama3") have NO single-file fallback: if the
    multi-seed group is missing or incomplete, this raises rather than silently scoring
    some other, unrelated single run under that name (e.g. a stale default-output file)."""
    if label in AGENT_LABELS:
        paths = seed_groups.get(label, [])
        if len(paths) < 2:
            raise SystemExit(
                f"{label!r} needs a multi-seed group (2+ files matching "
                f"{RESULTS_DIR}/predictions_*_seed*.json whose 'model' field resolves to "
                f"{label!r}), found {len(paths)}. Run "
                f"`python run_agent_eval.py --model <model> --repeats 3` to generate one -- "
                f"there is no single-file fallback for this label."
            )
        per_file = []
        for p in paths:
            _, tot, _, _ = evaluate.score(p, labels_path, tol)
            per_file.append(evaluate.rates(tot))
        return aggregate_rates(per_file), paths

    path = by_label[label]
    _, tot, _, _ = evaluate.score(path, labels_path, tol)
    return evaluate.rates(tot), [path]


def fmt_pct(mean, std=None):
    return f"{mean:.0f}%±{std:.0f}%" if std is not None else f"{mean:.0f}%"


def fmt_ratio(mean, std=None):
    return f"{mean:.2f}±{std:.2f}" if std is not None else f"{mean:.2f}"


def metric_cells(rates, with_std=None):
    """rates: evaluate.rates()-shaped dict, or {metric: (mean, std)} when with_std is a
    set of metric names that should render with ±std (only used for the random row)."""
    with_std = with_std or set()

    def cell(key, fmt):
        val = rates[key]
        if isinstance(val, tuple):
            mean, std = val
        else:
            mean, std = val, None
        return fmt(mean, std if key in with_std else None)

    return [cell("top1", fmt_pct), cell("top3", fmt_pct), cell("mrr", fmt_ratio),
            cell("recall5", fmt_pct), cell("class", fmt_pct)]


def candidate_set_stats(predictions_path, labels_path):
    """Median candidate_lines size and coverage (% of runs whose true line is in
    candidate_lines) for a predictions file -- same definition as
    random_baseline.print_diagnostics, computed directly from the file so the second
    table can't drift from what the file actually contains."""
    labels = {x["run_id"]: x for x in evaluate.load(labels_path)}
    preds = {x["run_id"]: x for x in evaluate.load(predictions_path)}
    sizes, covered = [], 0
    for run_id, t in labels.items():
        cand = preds.get(run_id, {}).get("candidate_lines", [])
        sizes.append(len(cand))
        if t["line"] in cand:
            covered += 1
    return statistics.median(sizes), covered / len(labels) * 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="dataset/labels.json")
    ap.add_argument("--tol", type=int, default=2)
    ap.add_argument("--seeds", type=int, default=random_baseline.N_SEEDS,
                     help="seeds to average the random-in-candidates row over")
    ap.add_argument("--out", help="also write the markdown tables to this file")
    args = ap.parse_args()

    by_label = discover()
    seed_groups = discover_seed_groups()

    def available(label):
        if label in AGENT_LABELS:
            return len(seed_groups.get(label, [])) >= 2
        return label in by_label

    missing_rows = [l for l in MAIN_ROW_ORDER if l != "random" and not available(l)]
    if missing_rows:
        raise SystemExit(
            f"Missing results for: {', '.join(missing_rows)}. Agent labels "
            f"({', '.join(sorted(AGENT_LABELS))}) need a multi-seed group under "
            f"{RESULTS_DIR}/ (see run_agent_eval.py --repeats); others need their named "
            f"predictions_*.json under {RESULTS_DIR}/."
        )

    lines = [
        "**Baseline comparison** (v2 / 16-candidate sets)",
        "",
        "| Method | Top-1 | Top-3 | MRR | Rec@5 | Class |",
        "|---|---|---|---|---|---|",
    ]
    for label in MAIN_ROW_ORDER:
        if label == "random":
            # The "random" candidate source tracks whichever file backs agent-qwen,
            # whether that's a single run or a multi-seed group (any one seed's
            # candidate_lines will do -- they're deterministic, seed doesn't affect them).
            _, agent_paths = resolve_method("agent-qwen", by_label, seed_groups, args.labels, args.tol)
            rand_labels, rand_cands = random_baseline.load_labels_and_candidates(
                agent_paths[0], args.labels)
            rates = random_baseline.seed_averaged_overall(rand_labels, rand_cands, args.seeds)
            cells = metric_cells(rates, with_std={"top1", "mrr"})
            row_name = DISPLAY_NAMES[label]
        else:
            rates, paths = resolve_method(label, by_label, seed_groups, args.labels, args.tol)
            with_std = {"top1", "top3", "mrr", "recall5", "class"} if len(paths) > 1 else set()
            cells = metric_cells(rates, with_std=with_std)
            row_name = DISPLAY_NAMES[label]
            if len(paths) > 1:
                row_name += f" ({len(paths)} seeds)"
        lines.append(f"| {row_name} | " + " | ".join(cells) + " |")

    print("\n".join(lines))

    # --- Effect of candidate-set expansion: agent_v1 (10-candidate) vs agent-qwen (16-candidate) ---
    v2_rates, v2_paths = resolve_method("agent-qwen", by_label, seed_groups, args.labels, args.tol)
    v1_size, v1_cov = candidate_set_stats(AGENT_V1_FILE, args.labels)
    v2_size, v2_cov = candidate_set_stats(v2_paths[0], args.labels)  # candidate_lines is seed-invariant
    _, tot_v1, _, _ = evaluate.score(AGENT_V1_FILE, args.labels, args.tol)

    v2_row_name = DISPLAY_NAMES["agent-qwen"]
    v2_with_std = {"top1", "top3", "mrr", "recall5", "class"} if len(v2_paths) > 1 else set()
    if len(v2_paths) > 1:
        v2_row_name += f" ({len(v2_paths)} seeds)"

    lines2 = [
        "",
        "**Effect of candidate-set expansion**",
        "",
        "| Version | Candidate-set size | Coverage | Top-1 | Top-3 | MRR | Rec@5 | Class |",
        "|---|---|---|---|---|---|---|---|",
        f"| agent_v1 | {v1_size:.0f} | {v1_cov:.0f}% | " +
        " | ".join(metric_cells(evaluate.rates(tot_v1))) + " |",
        f"| {v2_row_name} | {v2_size:.0f} | {v2_cov:.0f}% | " +
        " | ".join(metric_cells(v2_rates, with_std=v2_with_std)) + " |",
    ]
    print("\n".join(lines2))

    if args.out:
        with open(args.out, "w") as f:
            f.write("\n".join(lines + lines2) + "\n")
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
