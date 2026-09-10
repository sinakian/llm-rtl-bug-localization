import json
import argparse

RATE_KEYS = ["top1", "top3", "top3_tol", "recall5", "class"]


def load(path):
    with open(path) as f:
        return json.load(f)


def score(predictions_path, labels_path="dataset/labels.json", tol=2):
    """Score a predictions file against labels. Returns (cats, tot, rows, confusion):
    - cats: bug_type -> raw hit counts (+ "total" and "mrr_sum")
    - tot: same shape as a cats entry, summed over all categories
    - rows: per-run detail tuples for the console table
    - confusion: true bug_type -> {predicted_class: count}
    Single source of truth for scoring, used by both this script's CLI and
    compare_all.py so the two never drift apart.
    """
    truth = {x["run_id"]: x for x in load(labels_path)}
    preds = {x["run_id"]: x for x in load(predictions_path)}

    cats = {}
    rows = []
    confusion = {}

    for run_id, t in truth.items():
        cat = t["bug_type"]
        true_line = t["line"]
        c = cats.setdefault(cat, {"total": 0, "top1": 0, "top3": 0, "top3_tol": 0,
                                   "recall5": 0, "class": 0, "mrr_sum": 0.0})
        c["total"] += 1
        conf_row = confusion.setdefault(cat, {})

        p = preds.get(run_id)
        if not p:
            rows.append((run_id, cat, true_line, [], "-", "MISSING"))
            conf_row["MISSING"] = conf_row.get("MISSING", 0) + 1
            continue

        pls = p.get("predicted_lines", []) or []
        pcls = p.get("predicted_class", "-")

        top1 = len(pls) > 0 and pls[0] == true_line
        top3 = true_line in pls[:3]
        top3_tol = any(abs(x - true_line) <= tol for x in pls[:3])
        recall5 = true_line in pls[:5]
        cls_hit = (pcls == cat)
        mrr = (1.0 / (pls.index(true_line) + 1)) if true_line in pls else 0.0

        c["top1"] += top1
        c["top3"] += top3
        c["top3_tol"] += top3_tol
        c["recall5"] += recall5
        c["class"] += cls_hit
        c["mrr_sum"] += mrr
        conf_row[pcls] = conf_row.get(pcls, 0) + 1

        verdict = "top1" if top1 else ("top3" if top3 else ("~tol" if top3_tol else ("r@5" if recall5 else "miss")))
        rows.append((run_id, cat, true_line, pls[:5], pcls, verdict))

    tot = {"total": 0, "top1": 0, "top3": 0, "top3_tol": 0, "recall5": 0, "class": 0, "mrr_sum": 0.0}
    for s in cats.values():
        for k in tot:
            tot[k] += s[k]

    return cats, tot, rows, confusion


def rates(stats):
    """Raw hit-count dict (a cats[...] entry or tot) -> percentage/MRR rates."""
    n = stats["total"] or 1
    return {
        "n": stats["total"],
        "top1": stats["top1"] / n * 100,
        "top3": stats["top3"] / n * 100,
        "top3_tol": stats["top3_tol"] / n * 100,
        "mrr": stats["mrr_sum"] / n,
        "recall5": stats["recall5"] / n * 100,
        "class": stats["class"] / n * 100,
    }


def print_run_table(rows):
    print(f"{'run_id':<10} {'bug_type':<14} {'true':>4} {'predicted':<20} {'class':<14} verdict")
    print("-" * 82)
    for run_id, cat, tl, pls, pcls, verdict in rows:
        print(f"{run_id:<10} {cat:<14} {tl:>4} {str(pls):<20} {str(pcls):<14} {verdict}")


def print_summary_table(cats, tot):
    print("\n===================== EVALUATION RESULTS =====================")
    print(f"{'Bug Category':<15} | {'N':<3} | {'Top-1':<6} | {'Top-3':<6} | {'MRR':<5} | "
          f"{'Top-3±':<6} | {'Rec@5':<6} | {'Class':<6}")
    print("-" * 82)
    for cat, s in cats.items():
        r = rates(s)
        print(f"{cat:<15} | {r['n']:<3} | {r['top1']:>4.0f}% | {r['top3']:>4.0f}% | {r['mrr']:>5.2f} | "
              f"{r['top3_tol']:>4.0f}% | {r['recall5']:>4.0f}% | {r['class']:>4.0f}%")
    print("-" * 82)
    r = rates(tot)
    print(f"{'OVERALL':<15} | {r['n']:<3} | {r['top1']:>4.0f}% | {r['top3']:>4.0f}% | {r['mrr']:>5.2f} | "
          f"{r['top3_tol']:>4.0f}% | {r['recall5']:>4.0f}% | {r['class']:>4.0f}%")
    print("================================================================\n")


def print_confusion(cats, confusion):
    true_labels = list(cats.keys())
    col_labels = list(true_labels)
    for cat in true_labels:
        for pcls in confusion.get(cat, {}):
            if pcls not in col_labels:
                col_labels.append(pcls)

    row_w = max([len("true \\ pred")] + [len(c) for c in true_labels]) + 2
    col_w = max([12] + [len(c) for c in col_labels]) + 2

    print("================ CONFUSION MATRIX (rows=true, cols=predicted) ================")
    header = f"{'true \\ pred':<{row_w}}" + "".join(f"{c:>{col_w}}" for c in col_labels)
    print(header)
    print("-" * len(header))
    for cat in true_labels:
        row = confusion.get(cat, {})
        print(f"{cat:<{row_w}}" + "".join(f"{row.get(c, 0):>{col_w}}" for c in col_labels))
    print("=" * len(header) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("predictions", nargs="?", default="predictions_agent.json",
                    help="predictions file to score (default: predictions_agent.json)")
    ap.add_argument("--labels", default="dataset/labels.json")
    ap.add_argument("--tol", type=int, default=2, help="line tolerance for the tolerant metric")
    ap.add_argument("--confusion", action="store_true",
                     help="print a predicted-vs-true bug-class confusion matrix")
    ap.add_argument("--json", nargs="?", const="metrics.json", default=None, metavar="PATH",
                     help="dump all metrics to this JSON file (default: metrics.json)")
    args = ap.parse_args()

    cats, tot, rows, confusion = score(args.predictions, args.labels, args.tol)

    print(f"\nScoring: {args.predictions}  (tolerance = +/-{args.tol} lines)\n")
    print_run_table(rows)
    print_summary_table(cats, tot)

    if args.confusion:
        print_confusion(cats, confusion)

    if args.json:
        metrics_out = {
            "predictions": args.predictions,
            "labels": args.labels,
            "tol": args.tol,
            "categories": {cat: rates(s) for cat, s in cats.items()},
            "overall": rates(tot),
            "confusion": confusion,
        }
        with open(args.json, "w") as f:
            json.dump(metrics_out, f, indent=2)
        print(f"Wrote metrics -> {args.json}")


if __name__ == "__main__":
    main()
