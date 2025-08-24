from __future__ import annotations

from typing import Dict, Any
import os
import fitz  # PyMuPDF


HIGHLIGHT_COLOR = (1, 1, 0)


def run_highlighter(state: Dict[str, Any]) -> Dict[str, Any]:
    print(f"🔧 HIGHLIGHTER NODE:")
    print(f"   📊 Entering with state keys: {list(state.keys())}")
    print(f"   📄 PDF path: {state.get('pdf_path', 'None')}")
    print(f"   🤖 Sensitive items to highlight: {len(state.get('sensitive_data', []))}")
    
    pdf_path = str(state.get("pdf_path") or "").strip()
    items = state.get("sensitive_data") or []
    if not pdf_path or not items:
        print("❌ Highlighter: Missing PDF path or sensitive data")
        return state

    # Save preview in output/preview/ folder
    filename = os.path.basename(pdf_path)
    preview_dir = os.path.join(os.getcwd(), "output", "preview")
    os.makedirs(preview_dir, exist_ok=True)
    base_name = os.path.splitext(filename)[0]
    preview_path = os.path.join(preview_dir, f"{base_name}_PREVIEW.pdf")

    doc = fitz.open(pdf_path)
    try:
        for it in items:
            page_idx = int(it.get("page_number", 1)) - 1
            bbox = it.get("bbox", {})
            rect = fitz.Rect(bbox.get("x0", 0), bbox.get("y0", 0), bbox.get("x1", 0), bbox.get("y1", 0))
            if 0 <= page_idx < len(doc):
                page = doc[page_idx]
                hl = page.add_highlight_annot(rect)
                hl.set_colors(stroke=HIGHLIGHT_COLOR, fill=HIGHLIGHT_COLOR)
                hl.update()
        doc.save(preview_path)
    finally:
        doc.close()

    state["preview_pdf_path"] = preview_path
    print(f"   ✅ Highlighter complete, preview saved: {preview_path}")
    return state


