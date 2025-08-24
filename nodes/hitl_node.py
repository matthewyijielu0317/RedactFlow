from __future__ import annotations

from typing import Dict, Any


def run_hitl(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Human-in-the-loop node: 
    - If user approves (Yes): route to Redactor (sensitive_data may have been edited by user)
    - If user doesn't approve (No): expect hints to be added to user_prompt, then route to Orchestrator
    """
    approval = str(state.get("user_approval") or "").strip()
    
    if approval == "Yes":
        # User is satisfied with current sensitive_data (may have been edited), proceed to redaction
        current_items = state.get("sensitive_data", [])
        print(f"🔧 HITL: User approved with {len(current_items)} AI items (including any user edits)")
        
        # Log the items that will be redacted
        for i, item in enumerate(current_items):
            print(f"   [{i+1}] Page {item.get('page_number')}: {item.get('content', '')[:50]}...")
        
        state["next_node"] = "Redactor"
        # Clear user_approval for next iteration
        state.pop("user_approval", None)
        return state
    
    elif approval == "No":
        # User is not satisfied, expect hints to be appended to user_prompt by external UI
        # The external UI should append hints to user_prompt before calling this node again
        # Route back to Orchestrator to re-process with new hints
        print(f"🔧 HITL: User rejected, routing back to Orchestrator")
        state["next_node"] = "Orchestrator"
        # Clear user_approval for next iteration
        state.pop("user_approval", None)
        return state
    
    else:
        # No approval set yet, stay in HumanInLoop (waiting for user input)
        # This allows the external UI to display preview and wait for user decision
        state["next_node"] = "HumanInLoop"
        return state


