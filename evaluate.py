import json
import argparse

def load(path):
    with open(path) as f:
        return json.load(f)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("predictions", nargs="?", default="predictions_agent.json",
                    help="predictions file to score (default: predictions_agent.json)")
    ap.add_argument("--labels", default="dataset/labels.json")
    ap.add_argument("--tol", type=int, default=2, help="line tolerance for the tolerant metric")
    args = ap.parse_args()

    truth = {x["run_id"]: x for x in load(args.labels)}
    preds = {x["run_id"]: x for x in load(args.predictions)}

    cats = {}
    rows = []
    for run_id, t in truth.items():
        cat = t["bug_type"]
        true_line = t["line"]
        c = cats.setdefault(cat, {"total": 0, "top1": 0, "top3": 0, "top3_tol": 0, "recall5": 0, "class": 0})
        c["total"] += 1

        p = preds.get(run_id)
        if not p:
            rows.append((run_id, cat, true_line, [], "-", "MISSING"))
            continue

        pls = p.get("predicted_lines", []) or []
        pcls = p.get("predicted_class", "-")

        top1 = len(pls) > 0 and pls[0] == true_line
        top3 = true_line in pls[:3]
        top3_tol = any(abs(x - true_line) <= args.tol for x in pls[:3])
        recall5 = true_line in pls[:5]
        cls_hit = (pcls == cat)

        c["top1"] += top1
        c["top3"] += top3
        c["top3_tol"] += top3_tol
        c["recall5"] += recall5
        c["class"] += cls_hit

        verdict = "top1" if top1 else ("top3" if top3 else ("~tol" if top3_tol else ("r@5" if recall5 else "miss")))
        rows.append((run_id, cat, true_line, pls[:5], pcls, verdict))

    print(f"\nScoring: {args.predictions}  (tolerance = +/-{args.tol} lines)\n")
    print(f"{'run_id':<10} {'bug_type':<14} {'true':>4} {'predicted':<20} {'class':<14} verdict")
    print("-" * 82)
    for run_id, cat, tl, pls, pcls, verdict in rows:
        print(f"{run_id:<10} {cat:<14} {tl:>4} {str(pls):<20} {str(pcls):<14} {verdict}")

    print("\n===================== EVALUATION RESULTS =====================")
    print(f"{'Bug Category':<15} | {'N':<3} | {'Top-1':<6} | {'Top-3':<6} | {'Top-3±':<6} | {'Rec@5':<6} | {'Class':<6}")
    print("-" * 74)
    tot = {"total": 0, "top1": 0, "top3": 0, "top3_tol": 0, "recall5": 0, "class": 0}
    for cat, s in cats.items():
        for k in tot:
            tot[k] += s[k]
        n = s["total"]
        print(f"{cat:<15} | {n:<3} | {s['top1']/n*100:>4.0f}% | {s['top3']/n*100:>4.0f}% | "
              f"{s['top3_tol']/n*100:>4.0f}% | {s['recall5']/n*100:>4.0f}% | {s['class']/n*100:>4.0f}%")
    n = tot["total"] or 1
    print("-" * 74)
    print(f"{'OVERALL':<15} | {tot['total']:<3} | {tot['top1']/n*100:>4.0f}% | {tot['top3']/n*100:>4.0f}% | "
          f"{tot['top3_tol']/n*100:>4.0f}% | {tot['recall5']/n*100:>4.0f}% | {tot['class']/n*100:>4.0f}%")
    print("==============================================================\n")

if __name__ == "__main__":
    main()