import json
import os
import re
from typing import TypedDict, List
from pydantic import BaseModel, Field
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END
from agent_tools import parse_log, read_span

class AgentState(TypedDict):
    run_id: str
    log_path: str
    verilog_path: str
    log_summary: str
    failure_class: str
    code_context: str
    predicted_lines: List[int]
    rationale: str
    suggested_fix: str

class AgentOutput(BaseModel):
    predicted_lines: List[int] = Field(description="List of the top 3 most likely line numbers causing the bug.")
    rationale: str = Field(description="A short explanation of the root cause.")
    suggested_fix: str = Field(description="A short suggested fix for the Verilog code.")

llm = ChatOllama(model="llama3", temperature=0.5)
structured_llm = llm.with_structured_output(AgentOutput)


def classify_node(state: AgentState) -> dict:
    parsed = parse_log(state["log_path"])
    prompt = f"""Analyze this simulation error snippet:
{parsed}
Classify the root cause into EXACTLY one of these categories: operator_flip, off_by_one, stuck_at, wrong_reset.
Reply with strictly the category name and nothing else."""
    res = llm.invoke(prompt).content.strip().lower()
    for cat in ["operator_flip", "off_by_one", "stuck_at", "wrong_reset"]:
        if cat in res:
            return {"log_summary": parsed, "failure_class": cat}
    return {"log_summary": parsed, "failure_class": "unknown"}

def gather_context_node(state: AgentState) -> dict:
    code_snippet = read_span(state["verilog_path"], 20, 50)
    return {"code_context": code_snippet}

def hypothesize_and_emit_node(state: AgentState) -> dict:
    prompt = f"""You are a hardware verification triage agent.
Design file: {state['verilog_path']}

Failing Log Summary:
{state['log_summary']}

Verilog Code Context:
{state['code_context']}

Identified Failure Class: {state['failure_class']}

Task: Hypothesize the root cause line numbers and suggest a fix. 
CRITICAL RULE: Base your answer STRICTLY on the provided Verilog Code Context. Do not invent signal names."""

    try:
        # We use structured_llm here instead of the raw llm!
        res = structured_llm.invoke(prompt)
        
        return {
            "predicted_lines": res.predicted_lines[:3],
            "rationale": res.rationale,
            "suggested_fix": res.suggested_fix
        }
    except Exception as e:
        return {"predicted_lines": [], "rationale": f"Structured parsing failed: {e}", "suggested_fix": ""}

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
    initial_state = {"run_id": run_id, "log_path": log_path, "verilog_path": verilog_path, "log_summary": "", "failure_class": "", "code_context": "", "predicted_lines": [], "rationale": "", "suggested_fix": ""}
    final_state = app.invoke(initial_state)
    return {"run_id": run_id, "predicted_lines": final_state["predicted_lines"], "predicted_class": final_state["failure_class"], "rationale": final_state["rationale"], "suggested_fix": final_state["suggested_fix"]}
