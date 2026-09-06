# Drop this in your project root as debug_probe.py and run: python debug_probe.py
import json, re
import agent
from agent import _stage_signals, _src_lines, _ollama, _coerce
from agent_tools import parse_log, ast_trace_signal, read_span

rid = "bug_004"
labels = {x["run_id"]: x for x in json.load(open("dataset/labels.json"))}
vpath = labels[rid]["file"]
log = f"dataset/{rid}.log"

print("MODEL_NAME =", agent.MODEL_NAME)
summary = parse_log(log)
print("\n--- log_summary ---\n", summary)

sigs = _stage_signals(summary)
print("\n--- stage signals ---", sigs)

ast_lines = []
for s in sigs:
    t = ast_trace_signal(vpath, s, "fifo")
    nums = [int(n) for n in re.findall(r"Line (\d+):", t)]
    print(f"  trace {s:9s} -> {nums}   raw={t!r}")
    ast_lines.extend(nums)
print("\n--- collected ast_lines ---", ast_lines)

# Now see what the model returns for the hypothesize call
src = _src_lines(vpath)
full_code = read_span(vpath, 1, len(src))
context = f"""--- Full Verilog Source (line numbers are authoritative) ---
{full_code}

--- Deterministic dataflow for the failing signals {sigs} ---
"""
prompt = f"""You are a hardware verification triage agent.

{summary}

{context}

RULES:
1. predicted_lines = top 3 LINE NUMBERS of the WRONG STATEMENT. Never structural lines.
Output ONLY JSON: {{"predicted_class":"...","predicted_lines":[l1,l2,l3],"rationale":"...","suggested_fix":"..."}}"""
raw = _ollama(prompt, as_json=True)
print("\n--- raw model output ---\n", raw)

print("\n--- _coerce result ---\n", _coerce(raw, src, ast_lines))
print("\n--- true line ---", labels[rid]["line"])
