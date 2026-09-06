import os
import json
import requests

DATASET_DIR = "dataset"
VERILOG_FILE = "src/fifo_buggy.v"
OUTPUT_FILE = "predictions.json"

# Make sure this matches the model you have downloaded in Ollama!
OLLAMA_MODEL = "qwen2.5-coder:1.5b"
OLLAMA_URL = "http://localhost:11434/api/generate"

def get_llm_prediction(log_content, verilog_content):
    prompt = f"""
    You are an expert hardware verification engineer.
    A SystemVerilog simulation has failed. 
    
    Here is the Verilog source code:
    {verilog_content}
    
    Here is the failing simulation log:
    {log_content}
    
    Task: Identify the root cause of the failure.
    1. List the top 3 most likely line numbers in the Verilog code causing the bug.
    2. Classify the bug into one of these exact categories: operator_flip, off_by_one, stuck_at, wrong_reset.
    
    Output exactly in this JSON format and nothing else:
    {{
        "predicted_lines": [line1, line2, line3],
        "predicted_class": "category_name"
    }}
    """
    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload)
        response_text = response.json().get("response", "{}")
        return json.loads(response_text)
    except Exception as e:
        print(f"Error querying Ollama or parsing JSON: {e}")
        return {"predicted_lines": [], "predicted_class": "unknown"}

def main():
    print(f"Starting Single-Shot LLM baseline using {OLLAMA_MODEL}...")
    
    with open(VERILOG_FILE, "r") as f:
        verilog_content = f.read()

    predictions = []
    
    for file in os.listdir(DATASET_DIR):
        if file.endswith(".log"):
            run_id = file.replace(".log", "")
            log_path = os.path.join(DATASET_DIR, file)
            
            with open(log_path, "r") as f:
                log_content = f.read()
                
            print(f"Analyzing {run_id}...")
            result = get_llm_prediction(log_content, verilog_content)
            result["run_id"] = run_id
            predictions.append(result)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(predictions, f, indent=4)
    
    print(f"LLM predictions saved to {OUTPUT_FILE}.")

if __name__ == "__main__":
    main()
