from __future__ import annotations

from typing import Dict, Any, List

from .model import AzureLLM


def run_evaluator(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluator Node: Compare expected vs detected sensitive data and provide feedback.
    
    NEW ARCHITECTURE:
    - Compare sensitive_data_description (what user wants) 
    - vs page_level_pdf_elements (what's in PDF)
    - vs sensitive_data (what detector found)
    - Generate feedback to improve detection quality
    """
    sensitive_data_description = state.get("sensitive_data_description") or []
    page_level_pdf_elements = state.get("page_level_pdf_elements") or []
    sensitive_data = state.get("sensitive_data") or []

    # Prevent infinite loops: limit evaluator feedback cycles  
    evaluator_cycles = state.get("evaluator_cycles", 0)
    max_cycles = state.get("max_evaluator_cycles", 3)  # Default 3 cycles as specified
    
    # Initialize cycle counter if not present
    if "evaluator_cycles" not in state:
        state["evaluator_cycles"] = 0
    if "max_evaluator_cycles" not in state:
        state["max_evaluator_cycles"] = 3
    
    if evaluator_cycles >= max_cycles:
        # Too many cycles, proceed to highlighter
        print(f"⚠️ Maximum evaluation cycles ({max_cycles}) reached. Proceeding to human-in-the-loop.")
        state["next_node"] = "HumanInLoop"
        return state

    print(f"🔍 Evaluator: Analyzing detection quality")
    print(f"📋 Guidance items: {len(sensitive_data_description)}")
    print(f"📄 Page elements: {len(page_level_pdf_elements)}")  
    print(f"🎯 Detected items: {len(sensitive_data)}")

    # Skip evaluation if no detection guidance or results
    if not sensitive_data_description:
        print("⚠️ No detection guidance available, proceeding to human-in-the-loop")
        state["next_node"] = "HumanInLoop"
        return state

    try:
        from pydantic import BaseModel
    except Exception:
        state["next_node"] = "HumanInLoop"
        return state

    class EvaluationResult(BaseModel):
        issues_found: bool
        missing_sensitive_data: List[str]  # Sensitive data that should be detected but wasn't
        incorrect_detections: List[str]    # Items that were flagged but shouldn't be
        feedback_message: str              # Specific feedback for detector improvement

    # Prepare PDF content for evaluation
    pdf_content_by_page = {}
    for element in page_level_pdf_elements:
        page_num = element.get("page_number", 1)
        content = element.get("content", "")
        if page_num not in pdf_content_by_page:
            pdf_content_by_page[page_num] = []
        pdf_content_by_page[page_num].append(content)

    # Build readable PDF content
    pdf_text = ""
    for page_num in sorted(pdf_content_by_page.keys()):
        page_content = "\n".join(pdf_content_by_page[page_num])
        pdf_text += f"\n\n--- Page {page_num} ---\n\n{page_content}"

    # Prepare detection guidance
    guidance_text = "\n".join([f"- {desc}" for desc in sensitive_data_description])

    # Prepare current detections
    detected_items = []
    for item in sensitive_data:
        detected_items.append(f"Page {item.get('page_number')}: '{item.get('content')}' (Reason: {item.get('reason')})")

    instruction = (
        "You are evaluating sensitive data detection quality. Your job is to find gaps and errors:\n\n"
        "EVALUATION CRITERIA:\n"
        "1. FALSE NEGATIVES: Find sensitive data in the PDF that matches the guidance but wasn't detected\n"
        "2. FALSE POSITIVES: Find detected items that aren't actually sensitive per the guidance\n"
        "3. QUALITY ASSESSMENT: Determine if the detection is acceptable or needs improvement\n\n"
        "EVALUATION PROCESS:\n"
        "- Read the detection guidance carefully\n"
        "- Scan the PDF content for sensitive information matching the guidance\n"
        "- Compare with what was actually detected\n"
        "- Identify missing items (false negatives) and incorrect items (false positives)\n\n"
        "Be CAREFUL and THOROUGH. The goal is to decrease both false negatives and false positives.\n"
        "If significant issues are found, provide specific feedback to improve detection."
    )
    
    evaluation_data = {
        "detection_guidance": guidance_text,
        "pdf_content": pdf_text,
        "detected_items": detected_items
    }
    
    try:
        llm = AzureLLM()
        res: EvaluationResult = llm.create_structured_response(EvaluationResult, instruction, str(evaluation_data))
        
        if res.issues_found and res.feedback_message:
            # Append feedback to sensitive_data_description for detector improvement
            state.setdefault("sensitive_data_description", [])
            state["sensitive_data_description"].append(res.feedback_message)
            state["evaluator_cycles"] = evaluator_cycles + 1
            
            # Route back to detector with feedback
            state["next_node"] = "Detector"
            print(f"📝 Evaluator: Issues found - {res.feedback_message}")
            print(f"🔄 Routing to Detector for improvement (cycle {state['evaluator_cycles']}/{max_cycles})")
            
            # Log specific issues for debugging
            if res.missing_sensitive_data:
                print(f"❌ Missing detections: {len(res.missing_sensitive_data)} items")
            if res.incorrect_detections:
                print(f"⚠️ Incorrect detections: {len(res.incorrect_detections)} items")
        else:
            # No issues found, proceed to human-in-the-loop
            state["next_node"] = "HumanInLoop"
            print("✅ Evaluator: Detection quality acceptable, proceeding to human-in-the-loop")
            
    except Exception as e:
        # If evaluation fails, proceed to human-in-the-loop
        print(f"❌ Evaluator error: {e}")
        state["next_node"] = "HumanInLoop"
    
    return state


