from __future__ import annotations

from typing import Dict, Any, Optional
import os
import fitz  # PyMuPDF


def _apply_redactions_to_pdf(
    pdf_path: str,
    sensitive_items: list[dict[str, Any]],
    output_path: Optional[str] = None,
    redaction_color: tuple = (0, 0, 0),
) -> str:
    if not output_path:
        # Save AI redacted files in output/redacted/ directory
        base_name = os.path.basename(pdf_path).replace('.pdf', '')
        redacted_dir = os.path.join(os.getcwd(), "output", "redacted")
        os.makedirs(redacted_dir, exist_ok=True)
        output_path = os.path.join(redacted_dir, f"{base_name}_AI_REDACTED.pdf")

    doc = fitz.open(pdf_path)
    try:
        for item in sensitive_items:
            page_num = int(item.get("page_number", 1)) - 1
            bbox = item.get("bbox", {"x0": 0, "y0": 0, "x1": 0, "y1": 0})
            rect = fitz.Rect(bbox["x0"], bbox["y0"], bbox["x1"], bbox["y1"])
            page = doc[page_num]
            page.add_redact_annot(rect, text="[REDACTED]", fill=redaction_color)
        for i in range(len(doc)):
            doc[i].apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        doc.save(output_path)
    finally:
        doc.close()
    return output_path


def run_redactor(state: Dict[str, Any]) -> Dict[str, Any]:
    print(f"🔧 REDACTOR NODE:")
    print(f"   📊 Entering with state keys: {list(state.keys())}")
    print(f"   📄 PDF path: {state.get('pdf_path', 'None')}")
    print(f"   🤖 AI items to redact: {len(state.get('sensitive_data', []))}")
    print(f"   ✅ User approval status: {state.get('user_approval', 'None')}")
    
    pdf_path = str(state.get("pdf_path") or "").strip()
    items = state.get("sensitive_data") or []
    
    # Log each item that will be redacted
    for i, item in enumerate(items):
        print(f"   [{i+1}] Page {item.get('page_number')}: {item.get('content', '')[:50]}...")
    
    if not pdf_path or not items:
        print(f"   ❌ Skipping AI redaction: pdf_path={bool(pdf_path)}, items={len(items)}")
        return state
    
    print(f"   ▶️ Proceeding with AI redaction...")
    final_path = _apply_redactions_to_pdf(pdf_path, items)
    state["final_pdf_path"] = final_path
    print(f"   ✅ AI redaction complete: {final_path}")
    
    return state


