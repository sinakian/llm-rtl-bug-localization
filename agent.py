import re
import json
import requests
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from agent_tools import parse_log, read_span, ast_trace_signal

# ":3b" for a fast dev loop; "qwen2.5-coder:latest" (7B) or "llama3" for final numbers.
MODEL_NAME = "llama3:latest"
OLLAMA_URL = "http://localhost:11434/api/generate"
TIMEOUT = 120

VALID_CLASSES = ["operator_flip", "off_by_one", "stuck_at", "wrong_reset"]
_STRUCT_KW = re.compile(r"^\s*(always|begin|end|endmodule|module|else|if)\b")
N_PRED = 5  # emit up to 5 ranked candidate lines so we can score recall@5


def _is_structural(text: str) -> bool:
    t = text.strip()
    return (not t) or t.startswith(("`", "//")) or bool(_STRUCT_KW.match(text))


class AgentState(TypedDict):
    run_id: str
    log_path: str
    verilog_path: str
    log_summary: str
    failure_class: str
    code_context: str
    ast_lines: List[int]
    predicted_lines: List[int]
    rationale: str
    suggested_fix: str


def _ollama(prompt: str, as_json: bool) -> str:
    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": False}
    if as_json:
        payload["format"] = "json"
    r = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT)
    return r.json().get("response", "")


def _src_lines(path: str) -> List[str]:
    with open(path, "r") as f:
        return f.read().splitlines()


def _stage_signals(log_summary: str) -> list:
    """Several distinct root causes on this design surface through the SAME assertion, so
    each stage traces the UNION of signals that can plausibly cause it. The MODEL then
    ranks within this candidate set (recall@5 measures whether the true line is in it)."""
    s = log_summary.upper()
    if "RESET STAGE" in s:
        return ["empty", "full", "count"]
    if "FILL STAGE" in s:
        return ["full", "count", "wr_ptr", "rd_ptr", "data_out"]
    if "READBACK STAGE" in s:
        return ["data_out", "rd_ptr", "wr_ptr", "count", "full"]
    return ["count", "full", "data_out", "wr_ptr", "rd_ptr"]


def classify_node(state: AgentState) -> dict:
    print("  [classify]", flush=True)
    return {"log_summary": parse_log(state["log_path"])}


def gather_context_node(state: AgentState) -> dict:
    print("  [gather_context]", flush=True)
    signals = _stage_signals(state["log_summary"])

    traces, ast_lines = [], []
    for sig in signals:
        t = ast_trace_signal(state["verilog_path"], sig, top_module="fifo")
        nums = [int(n) for n in re.findall(r"Line (\d+):", t)]
        if nums:
            traces.append(t)
            ast_lines.extend(nums)

    src = _src_lines(state["verilog_path"])
    full_code = read_span(state["verilog_path"], 1, len(src))

    context = f"""--- Full Verilog Source (line numbers are authoritative) ---
{full_code}

--- Deterministic dataflow for the failing signals {signals} ---
{chr(10).join(traces)}"""
    return {"code_context": context, "ast_lines": ast_lines}


def _coerce(raw: str, src: List[str], ast_lines: List[int]) -> dict:
    data = {}
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = {}

    lines = data.get("predicted_lines", [])
    if isinstance(lines, (int, str)):
        lines = [lines]
    model_lines = []
    for x in lines:
        try:
            model_lines.append(int(x))
        except Exception:
            pass

    def keep(n):
        return 1 <= n <= len(src) and not _is_structural(src[n - 1])

    # Candidate set = deterministic assignment lines for the stage's signals.
    cand = [n for n in ast_lines if keep(n)]
    cand_set = set(cand)

    # The MODEL RANKS first (its judgement of which candidates are wrong), but restricted
    # to real candidate lines so a weak model can't inject hallucinated line numbers.
    # Remaining candidates are appended as a deterministic backstop for recall.
    ranked = [n for n in model_lines if n in cand_set]
    merged, seen = [], set()
    for n in ranked + cand:
        if n in seen:
            continue
        seen.add(n)
        merged.append(n)
    if not merged:                      # last resort, never emit garbage
        merged = [n for n in model_lines if keep(n)]

    cls = str(data.get("predicted_class", "")).strip().lower()
    cls = next((c for c in VALID_CLASSES if c in cls), "unknown")

    return {
        "failure_class": cls,
        "predicted_lines": merged[:N_PRED],
        "rationale": str(data.get("rationale", ""))[:500],
        "suggested_fix": str(data.get("suggested_fix", ""))[:300],
    }


def hypothesize_and_emit_node(state: AgentState) -> dict:
    print("  [hypothesize]", flush=True)
    cand = sorted(set(state.get("ast_lines", [])))
    prompt = f"""You are a hardware verification triage agent.

{state['log_summary']}

{state['code_context']}

CANDIDATE LINES (the bug is on ONE of these; choose and RANK only from this list):
{cand}

RULES:
1. predicted_lines = the candidate lines above, RANKED most-likely-first (up to 5). Use
   ONLY numbers from the candidate list. Never a structural line.
2. predicted_class uses the FAILURE STAGE prior, refined with the code and dataflow:
   - RESET stage    -> wrong_reset (a register resets to the wrong constant).
   - FILL stage     -> off_by_one if the full-flag compare is off; operator_flip if a
                       write pointer/counter uses the wrong operator; stuck_at if a signal
                       is driven by a constant.
   - READBACK stage -> stuck_at if data_out is a CONSTANT; operator_flip if a pointer uses
                       the wrong operator.

Output ONLY this JSON:
{{"predicted_class":"<operator_flip|off_by_one|stuck_at|wrong_reset>",
  "predicted_lines":[most_likely, ...up to 5],
  "rationale":"...","suggested_fix":"..."}}"""
    try:
        raw = _ollama(prompt, as_json=True)
        return _coerce(raw, _src_lines(state["verilog_path"]), state.get("ast_lines", []))
    except Exception as e:
        cand = [n for n in sorted(set(state.get("ast_lines", [])))][:N_PRED]
        return {"failure_class": "unknown", "predicted_lines": cand,
                "rationale": f"call failed: {e}", "suggested_fix": ""}


workflow = StateGraph(AgentState)
workflow.add_node("classify", classify_node)
workflow.add_node("gather_context", gather_context_node)
workflow.add_node("hypothesize_emit", hypothesize_and_emit_node)
workflow.set_entry_point("classify")
workflow.add_edge("classify", "gather_context")
workflow.add_edge("gather_context", "hypothesize_emit")
workflow.add_edge("hypothesize_emit", END)
app = workflow.compile()


def triage_run(run_id: str, log_path: str, verilog_path: str) -> dict:
    initial_state = {
        "run_id": run_id, "log_path": log_path, "verilog_path": verilog_path,
        "log_summary": "", "failure_class": "", "code_context": "", "ast_lines": [],
        "predicted_lines": [], "rationale": "", "suggested_fix": "",
    }
    final = app.invoke(initial_state)
    return {
        "run_id": run_id,
        "predicted_lines": final["predicted_lines"],
        "predicted_class": final["failure_class"],
        "rationale": final["rationale"],
        "suggested_fix": final["suggested_fix"],
    }