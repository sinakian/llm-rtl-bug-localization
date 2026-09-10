import json
import random
import argparse
import statistics

from agent import VALID_CLASSES

N_PRED = 5
N_SEEDS = 100
TOL = 2
METRIC_KEYS = ["top1", "top3", "top3_tol", "recall5", "class"]


def load(path):
    with open(path) as f:
        return json.load(f)


def compute_metrics(pls, pcls, true_line, cat):
    return {
        "top1": len(pls) > 0 and pls[0] == true_line,
        "top3": true_line in pls[:3],
        "top3_tol": any(abs(x - true_line) <= TOL for x in pls[:3]),
        "recall5": true_line in pls[:5],
        "class": pcls == cat,
    }


def run_for_seed(labels, candidates, seed):
    """One full pass over the dataset for a given seed: shuffle each run's OWN
    candidate_lines (the same candidate set the agent got, no LLM call), take
    top 5, pick a uniform-random class. Returns (predictions, per_run_metrics)
    so seed 0 and the seed-averaging loop share this one code path."""
    rng = random.Random(seed)
    preds, per_run = {}, {}
    for run_id, t in labels.items():
        cand = list(candidates[run_id])
        rng.shuffle(cand)
        pls = cand[:N_PRED]
        pcls = rng.choice(VALID_CLASSES)
        preds[run_id] = {
            "run_id": run_id,
            "predicted_lines": pls,
            "predicted_class": pcls,
            "rationale": f"random baseline: shuffled agent candidate_lines (seed={seed})",
            "suggested_fix": "",
        }
        per_run[run_id] = compute_metrics(pls, pcls, t["line"], t["bug_type"])
    return preds, per_run


def print_diagnostics(labels, candidates):
    sizes, ranks, covered = [], [], 0
    for run_id, t in labels.items():
        cand = candidates[run_id]
        sizes.append(len(cand))
        if t["line"] in cand:
            covered += 1
            ranks.append(cand.index(t["line"]) + 1)

    n = len(labels)
    print("===================== CANDIDATE SET DIAGNOSTICS =====================")
    print(f"coverage (true line in candidate_lines): {covered}/{n} ({covered / n * 100:.1f}%)")
    print(f"candidate set size: median={statistics.median(sizes):.1f}  max={max(sizes)}")
    if ranks:
        print(f"median rank of true line in agent's deterministic order: "
              f"{statistics.median(ranks):.1f}  (over {len(ranks)} covered runs)")
    else:
        print("median rank of true line: n/a (no run has the true line in its candidate set)")
    print("=======================================================================\n")


def fmt_cell(mean, std, width=13):
    return f"{mean:4.1f}±{std:<4.1f}%".ljust(width)


def print_seed_averaged(labels, candidates, n_seeds):
    cats = sorted({t["bug_type"] for t in labels.values()})
    cat_counts = {cat: sum(1 for t in labels.values() if t["bug_type"] == cat) for cat in cats}
    n = len(labels)

    per_seed_cat_rates = {cat: {k: [] for k in METRIC_KEYS} for cat in cats}
    per_seed_overall_rates = {k: [] for k in METRIC_KEYS}

    for seed in range(n_seeds):
        _, per_run = run_for_seed(labels, candidates, seed)
        cat_hits = {cat: {k: 0 for k in METRIC_KEYS} for cat in cats}
        overall_hits = {k: 0 for k in METRIC_KEYS}
        for run_id, t in labels.items():
            m = per_run[run_id]
            for k in METRIC_KEYS:
                cat_hits[t["bug_type"]][k] += m[k]
                overall_hits[k] += m[k]
        for cat in cats:
            for k in METRIC_KEYS:
                per_seed_cat_rates[cat][k].append(cat_hits[cat][k] / cat_counts[cat] * 100)
        for k in METRIC_KEYS:
            per_seed_overall_rates[k].append(overall_hits[k] / n * 100)

    def mean_std(xs):
        return statistics.mean(xs), (statistics.stdev(xs) if len(xs) > 1 else 0.0)

    title = f"RANDOM BASELINE — seed-averaged over {n_seeds} seeds (mean±std)"
    print(f"===== {title} =====")
    header = (f"{'Bug Category':<15} | {'N':<3} | {'Top-1':<13} | {'Top-3':<13} | "
              f"{'Top-3±' + str(TOL):<13} | {'Rec@5':<13} | {'Class':<13}")
    print(header)
    print("-" * len(header))
    for cat in cats:
        cells = " | ".join(fmt_cell(*mean_std(per_seed_cat_rates[cat][k])) for k in METRIC_KEYS)
        print(f"{cat:<15} | {cat_counts[cat]:<3} | {cells}")
    print("-" * len(header))
    cells = " | ".join(fmt_cell(*mean_std(per_seed_overall_rates[k])) for k in METRIC_KEYS)
    print(f"{'OVERALL':<15} | {n:<3} | {cells}")
    print("=" * len(header) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-predictions", default="predictions_agent.json",
                     help="source of per-run candidate_lines (the agent's deterministic candidate set)")
    ap.add_argument("--labels", default="dataset/labels.json")
    ap.add_argument("--out", default="predictions_random.json")
    ap.add_argument("--seeds", type=int, default=N_SEEDS)
    args = ap.parse_args()

    labels = {x["run_id"]: x for x in load(args.labels)}
    agent_preds = {x["run_id"]: x for x in load(args.agent_predictions)}

    missing = [rid for rid in labels if "candidate_lines" not in agent_preds.get(rid, {})]
    if missing:
        raise SystemExit(
            f"{args.agent_predictions} has no 'candidate_lines' for {len(missing)} run(s) "
            f"(e.g. {missing[0]}). Re-run run_agent_eval.py to regenerate it with the "
            f"current agent.py before running this baseline."
        )

    candidates = {rid: agent_preds[rid]["candidate_lines"] for rid in labels}

    print_diagnostics(labels, candidates)

    preds_seed0, _ = run_for_seed(labels, candidates, seed=0)
    with open(args.out, "w") as f:
        json.dump(list(preds_seed0.values()), f, indent=4)
    print(f"Wrote {args.out} (seed=0)\n")

    print_seed_averaged(labels, candidates, args.seeds)


if __name__ == "__main__":
    main()
