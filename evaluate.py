import json

LABELS_FILE = "dataset/labels.json"
PREDICTIONS_FILE = "predictions.json"

def main():
    # 1. Load data
    with open(LABELS_FILE, "r") as f:
        ground_truth = {item["run_id"]: item for item in json.load(f)}

    with open(PREDICTIONS_FILE, "r") as f:
        predictions = {item["run_id"]: item for item in json.load(f)}

    categories = {}
    
    # 2. Score predictions
    for run_id, truth in ground_truth.items():
        cat = truth["bug_type"]
        if cat not in categories:
            categories[cat] = {"total": 0, "top1": 0, "top3": 0, "class_hit": 0}
            
        categories[cat]["total"] += 1
        pred = predictions.get(run_id)
        if not pred: continue
        
        true_line = truth["line"]
        pred_lines = pred.get("predicted_lines", [])
        
        # Top-1: The true line is exactly the first guess
        if len(pred_lines) > 0 and pred_lines[0] == true_line:
            categories[cat]["top1"] += 1
            
        # Top-3: The true line is anywhere in the top 3 guesses
        if true_line in pred_lines[:3]:
            categories[cat]["top3"] += 1
            
        # Classification Accuracy
        if pred.get("predicted_class") == cat:
            categories[cat]["class_hit"] += 1

    # 3. Print Results Table
    print("\n================ EVALUATION RESULTS ================")
    print(f"{'Bug Category':<15} | {'Total':<5} | {'Top-1 Loc':<10} | {'Top-3 Loc':<10} | {'Class Acc':<10}")
    print("-" * 62)
    
    for cat, stats in categories.items():
        t = stats["total"]
        t1 = (stats["top1"] / t) * 100
        t3 = (stats["top3"] / t) * 100
        ca = (stats["class_hit"] / t) * 100
        print(f"{cat:<15} | {t:<5} | {t1:>8.1f}% | {t3:>8.1f}% | {ca:>8.1f}%")
    print("====================================================\n")

if __name__ == "__main__":
    main()
