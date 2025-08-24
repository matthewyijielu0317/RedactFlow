from __future__ import annotations

from typing import Dict, Any
from langgraph.graph import StateGraph, END

from .model import AzureLLM
from .searcher_node import run_searcher
from .detector_node import run_detector
from .highlighter_node import run_highlighter
from .evaluator_node import run_evaluator
from .hitl_node import run_hitl
from .redactor_node import run_redactor


def orchestrator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    print(f"🔧 ORCHESTRATOR NODE:")
    print(f"   📊 Entering with state keys: {list(state.keys())}")
    print(f"   📋 User prompt: {state.get('user_prompt', 'None')[:100]}...")
    print(f"   📄 PDF path: {state.get('pdf_path', 'None')}")
    
    # Ensure essential keys exist
    state.setdefault("user_prompt", "")
    state.setdefault("pdf_path", "")
    state.setdefault("sensitive_data_description", [])

    prompt = str(state.get("user_prompt") or "").strip()
    if not prompt:
        print(f"   ➡️ No prompt, routing to Detector")
        state["next_node"] = "Detector"
        return state

    # Use LLM to summarize and route
    from pydantic import BaseModel

    class OrchestratorDecision(BaseModel):
        next_node: str  # "Searcher" or "Detector"
        sensitive_descriptions: list[str]
        search_query: str | None = None

    instruction = (
        "You route a PDF sanitization pipeline. Summarize the user's request into 1-3 brief"
        " sensitive data descriptions. If external regulation lookup is needed (industry,"
        " jurisdiction, or specific regulation implied), set next_node to Searcher and"
        " propose a concise search_query; otherwise set next_node to Detector."
    )
    text = f"User prompt:\n{prompt}"

    try:
        llm = AzureLLM()
        res: OrchestratorDecision = llm.create_structured_response(OrchestratorDecision, instruction, text)
        desc = [d.strip() for d in (res.sensitive_descriptions or []) if d and d.strip()]
        if desc:
            # Functionality 1 & 2: Always append new descriptions to existing list
            existing_descriptions = state.get("sensitive_data_description") or []
            state["sensitive_data_description"] = existing_descriptions + desc
        if (res.search_query or "").strip() and res.next_node == "Searcher":
            print(f"   ➡️ Routing to Searcher with query: {res.search_query}")
            state["search_query"] = res.search_query.strip()  # type: ignore[union-attr]
            state["next_node"] = "Searcher"
        else:
            print(f"   ➡️ Routing to Detector")
            state["next_node"] = "Detector"
    except Exception as e:
        # Fallback: no LLM -> go directly to Detector
        print(f"   ❌ LLM error: {str(e)}, routing to Detector")
        state["next_node"] = "Detector"
    
    print(f"   ✅ Orchestrator complete, next_node: {state.get('next_node')}")
    return state


def build_sanitizer_graph() -> StateGraph:
    graph = StateGraph(dict)
    graph.add_node("Orchestrator", orchestrator_node)
    graph.add_node("Searcher", run_searcher)
    graph.add_node("Detector", run_detector)
    graph.add_node("Highlighter", run_highlighter)
    graph.add_node("Evaluator", run_evaluator)
    graph.add_node("HumanInLoop", run_hitl)
    graph.add_node("Redactor", run_redactor)

    graph.set_entry_point("Orchestrator")

    def route_from_orchestrator(state: Dict[str, Any]) -> str:
        nxt = str(state.get("next_node") or "").strip()
        return nxt if nxt in {"Searcher", "Detector"} else "Detector"

    graph.add_conditional_edges("Orchestrator", route_from_orchestrator, {"Searcher": "Searcher", "Detector": "Detector"})
    graph.add_edge("Searcher", "Detector")
    graph.add_edge("Detector", "Evaluator")  # New simplified workflow: Detector -> Evaluator

    def route_from_evaluator(state: Dict[str, Any]) -> str:
        nxt = str(state.get("next_node") or "").strip()
        return nxt if nxt in {"Detector", "Highlighter"} else "Highlighter"

    graph.add_conditional_edges("Evaluator", route_from_evaluator, {
        "Detector": "Detector",  # Feedback loop to detector
        "Highlighter": "Highlighter"
    })
    graph.add_edge("Highlighter", "HumanInLoop")

    def route_from_hitl(state: Dict[str, Any]) -> str:
        nxt = str(state.get("next_node") or "").strip()
        print(f"🔧 HITL ROUTING: next_node='{nxt}', user_approval='{state.get('user_approval')}'")
        if nxt == "Redactor":
            print(f"   ➡️ Routing to Redactor")
            return "Redactor"
        elif nxt == "Orchestrator":
            print(f"   ➡️ Routing to Orchestrator")
            return "Orchestrator"
        else:
            print(f"   ⏸️ Staying in HumanInLoop")
            return "HumanInLoop"  # Stay in loop if no decision made yet

    graph.add_conditional_edges("HumanInLoop", route_from_hitl, {
        "Redactor": "Redactor", 
        "Orchestrator": "Orchestrator",
        "HumanInLoop": "HumanInLoop"
    })
    graph.add_edge("Redactor", END)
    
    # Interrupt before HumanInLoop to allow UI to collect user input
    return graph


