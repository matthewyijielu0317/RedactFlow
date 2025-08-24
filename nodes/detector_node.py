from __future__ import annotations

"""
Detector Node: Dual OCR + Dual LLM Architecture

Case 1 (First detection):
1. Run dual OCR in parallel (page-level + word-level)
2. Convert coordinates to PyMuPDF format
3. First LLM: Analyze page-level content for sensitive data
4. Second LLM: Map sensitive content to word-level coordinates

Case 2 (Feedback loop):
1. Skip OCR (already done)
2. First LLM: Re-analyze with feedback
3. Second LLM: Re-map with updated sensitive content
"""

import os
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Azure Document Intelligence for dual OCR
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult

from .model import AzureLLM


def run_detector(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main detector node entry point.
    
    Implements dual OCR + dual LLM architecture:
    - Case 1: First detection (with OCR)
    - Case 2: Feedback loop (OCR already cached)
    """
    print(f"🔧 DETECTOR NODE:")
    print(f"   📊 Entering with state keys: {list(state.keys())}")
    print(f"   📄 PDF path: {state.get('pdf_path', 'None')}")
    print(f"   📋 Descriptions: {state.get('sensitive_data_description', [])}")
    print(f"   🤖 Existing sensitive_data: {len(state.get('sensitive_data', []))} items")
    
    pdf_path = state.get("pdf_path", "")
    descriptions = state.get("sensitive_data_description", [])
    
    if not pdf_path:
        print("❌ Detector: No PDF path provided")
        return state
    
    # Determine case based on OCR cache
    if not state.get("word_level_pdf_elements") or not state.get("page_level_pdf_elements"):
        # Case 1: First detection - run dual OCR + dual LLM
        print("🔄 Detector Case 1: First detection with dual OCR")
        result = _first_detection(state, pdf_path, descriptions)
        print(f"   ✅ Detector Case 1 complete, sensitive_data: {len(result.get('sensitive_data', []))} items")
        return result
    else:
        # Case 2: Feedback loop - rerun dual LLM with feedback
        print("🔄 Detector Case 2: Feedback loop with cached OCR")
        result = _feedback_detection(state, descriptions)
        print(f"   ✅ Detector Case 2 complete, sensitive_data: {len(result.get('sensitive_data', []))} items")
        return result


def _first_detection(state: Dict[str, Any], pdf_path: str, descriptions: List[str]) -> Dict[str, Any]:
    """
    Case 1: First detection with dual OCR + dual LLM.
    """
    try:
        # Step 1: Run dual OCR in parallel
        print("📊 Running dual OCR (page-level + word-level)...")
        page_elements, word_elements = _run_dual_ocr_parallel(pdf_path)
        
        if not page_elements or not word_elements:
            print("❌ Dual OCR failed")
            return state
            
        print(f"✅ Page-level OCR: {len(page_elements)} elements")
        print(f"✅ Word-level OCR: {len(word_elements)} elements")
        
        # Step 2: Store OCR results in state
        state["page_level_pdf_elements"] = page_elements
        state["word_level_pdf_elements"] = word_elements
        
        # Step 3: Run dual LLM analysis
        sensitive_data = _run_dual_llm_analysis(page_elements, word_elements, descriptions)
        state["sensitive_data"] = sensitive_data
        
        print(f"✅ Detector: Found {len(sensitive_data)} sensitive items")
        return state
        
    except Exception as e:
        print(f"❌ Detector Case 1 error: {e}")
        return state


def _feedback_detection(state: Dict[str, Any], descriptions: List[str]) -> Dict[str, Any]:
    """
    Case 2: Feedback loop with cached OCR + dual LLM.
    """
    try:
        page_elements = state.get("page_level_pdf_elements", [])
        word_elements = state.get("word_level_pdf_elements", [])
        
        if not page_elements or not word_elements:
            print("❌ Detector Case 2: OCR cache missing")
            return state
        
        print(f"📊 Using cached OCR: {len(page_elements)} page + {len(word_elements)} word elements")
        
        # Run dual LLM with feedback
        sensitive_data = _run_dual_llm_analysis(page_elements, word_elements, descriptions)
        state["sensitive_data"] = sensitive_data
        
        print(f"✅ Detector feedback: Updated to {len(sensitive_data)} sensitive items")
        return state
        
    except Exception as e:
        print(f"❌ Detector Case 2 error: {e}")
        return state


def _run_dual_ocr_parallel(pdf_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Run dual OCR in parallel:
    1. Page-level OCR (prebuilt-read) for content analysis
    2. Word-level OCR (prebuilt-layout) for coordinate mapping
    """
    client = _init_di_client()
    
    # Run both OCR operations in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        # Submit both OCR tasks
        page_future = executor.submit(_run_page_level_ocr, client, pdf_path)
        word_future = executor.submit(_run_word_level_ocr, client, pdf_path)
        
        # Collect results
        page_elements = []
        word_elements = []
        
        try:
            for future in as_completed([page_future, word_future]):
                result = future.result()
                if future == page_future:
                    page_elements = result
                elif future == word_future:
                    word_elements = result
        except Exception as e:
            print(f"❌ OCR parallel execution error: {e}")
            return [], []
    
    return page_elements, word_elements


def _run_page_level_ocr(client: DocumentIntelligenceClient, pdf_path: str) -> List[Dict[str, Any]]:
    """
    Page-level OCR using prebuilt-read for content analysis.
    Returns elements optimized for LLM reading.
    """
    try:
        with open(pdf_path, "rb") as f:
            file_content = f.read()
        
        # Use prebuilt-read for page-level content
        poller = client.begin_analyze_document("prebuilt-read", file_content, content_type="application/pdf")
        result = poller.result()
        
        elements = []
        element_id = 0
        
        for page in result.pages:
            page_num = page.page_number
            
            # Extract paragraphs/lines for better content structure
            if hasattr(page, 'paragraphs') and page.paragraphs:
                for paragraph in page.paragraphs:
                    if paragraph.content:
                        element_id += 1
                        elements.append({
                            "element_id": element_id,
                            "page_number": page_num,
                            "content": paragraph.content,
                            "bbox": _extract_paragraph_bbox(paragraph),
                            "type": "paragraph"
                        })
            else:
                # Fallback to lines if no paragraphs
                if hasattr(page, 'lines') and page.lines:
                    for line in page.lines:
                        if line.content:
                            element_id += 1
                            elements.append({
                                "element_id": element_id,
                                "page_number": page_num,
                                "content": line.content,
                                "bbox": _polygon_to_bbox(line.polygon or []),
                                "type": "line"
                            })
        
        return elements
        
    except Exception as e:
        print(f"❌ Page-level OCR error: {e}")
        return []


def _run_word_level_ocr(client: DocumentIntelligenceClient, pdf_path: str) -> List[Dict[str, Any]]:
    """
    Word-level OCR using prebuilt-layout for coordinate mapping.
    Returns individual words with precise coordinates.
    """
    try:
        with open(pdf_path, "rb") as f:
            file_content = f.read()
        
        # Use prebuilt-layout for word-level coordinates
        poller = client.begin_analyze_document("prebuilt-layout", file_content, content_type="application/pdf")
        result = poller.result()
        
        return _extract_word_elements(result, pdf_path)
        
    except Exception as e:
        print(f"❌ Word-level OCR error: {e}")
        return []


def _extract_word_elements(azure_result: AnalyzeResult, pdf_path: str) -> List[Dict[str, Any]]:
    """Extract word-level elements and convert coordinates to PyMuPDF points."""
    import fitz  # PyMuPDF
    
    elements = []
    doc = fitz.open(pdf_path)
    
    try:
        for page in azure_result.pages:
            page_index = int(page.page_number) - 1
            if not (0 <= page_index < len(doc)):
                continue
                
            pdf_pt_w = float(doc[page_index].rect.width)
            pdf_pt_h = float(doc[page_index].rect.height)
            di_w = float(getattr(page, "width", 0.0) or 0.0)
            di_h = float(getattr(page, "height", 0.0) or 0.0)
            unit = getattr(page, "unit", None)
            
            element_id = 0
            for word in page.words:
                polygon = list(getattr(word, "polygon", []) or [])
                bbox = _polygon_to_bbox_points(polygon, unit, di_w, di_h, pdf_pt_w, pdf_pt_h)
                element_id += 1
                
                elements.append({
                    "element_id": element_id,
                    "page_number": page.page_number,
                    "content": word.content,
                    "bbox": bbox,
                })
    finally:
        doc.close()
        
    return elements


def _run_dual_llm_analysis(page_elements: List[Dict[str, Any]], word_elements: List[Dict[str, Any]], descriptions: List[str]) -> List[Dict[str, Any]]:
    """
    Run dual LLM analysis:
    1. First LLM: Analyze page-level content for sensitive data
    2. Second LLM: Map sensitive content to word-level coordinates
    """
    # Step 1: First LLM - Content analysis
    sensitive_content_items = _first_llm_content_analysis(page_elements, descriptions)
    
    if not sensitive_content_items:
        print("⚠️ First LLM found no sensitive content")
        return []

    print(f"📝 First LLM found {len(sensitive_content_items)} sensitive content items")
    
    # Step 2: Second LLM - Coordinate mapping  
    sensitive_data = _second_llm_coordinate_mapping(sensitive_content_items, word_elements)
    
    print(f"📍 Second LLM mapped {len(sensitive_data)} items to coordinates")
    
    return sensitive_data


def _first_llm_content_analysis(page_elements: List[Dict[str, Any]], descriptions: List[str]) -> List[Dict[str, Any]]:
    """
    First LLM: Analyze page-level content to identify sensitive information.
    """
    try:
        from pydantic import BaseModel
    except Exception:
        return []
    
    class SensitiveContentItem(BaseModel):
        sensitive_content: str
        page_num: int
        reason: str
    
    class ContentAnalysisOutput(BaseModel):
        items: List[SensitiveContentItem]
    
    # Build guidance
    guidance = "\n".join([f"- {d}" for d in descriptions]) if descriptions else (
        "Detect all sensitive information including names, IDs, addresses, phone numbers, "
        "financial amounts, dates, birth dates, signatures, student IDs, social security numbers."
    )
    
    # Prepare page content for analysis
    content_by_page = {}
    for element in page_elements:
        page_num = element.get("page_number", 1)
        content = element.get("content", "")
        if page_num not in content_by_page:
            content_by_page[page_num] = []
        content_by_page[page_num].append(content)
    
    # Build readable text for LLM
    page_text = ""
    for page_num in sorted(content_by_page.keys()):
        page_content = "\n".join(content_by_page[page_num])
        page_text += f"\n\n--- Page {page_num} ---\n\n{page_content}"
    
    instruction = (
        "You are a specialized LLM for identifying sensitive information in PDF documents. "
        "You must be SKEPTICAL and follow the sensitive data description to increase recall. "
        "Add as much sensitive information as you think should be sensitive based on the guidance.\n\n"
        f"Guidance for sensitive data detection:\n{guidance}\n\n"
        "Extract the EXACT sensitive VALUES only, specify the page number, and provide a clear reason. "
                "Be thorough - it's better to flag more values than to miss sensitive data."
    )
    
    try:
        llm = AzureLLM()
        res: ContentAnalysisOutput = llm.create_structured_response(ContentAnalysisOutput, instruction, page_text)
        
        items = []
        for item in res.items or []:
            items.append({
                "sensitive_content": item.sensitive_content,
                "page_num": item.page_num,
                "reason": item.reason
            })
        
        return items

    except Exception as e:
        print(f"❌ First LLM error: {e}")
        return []


def _second_llm_coordinate_mapping(sensitive_content_items: List[Dict[str, Any]], word_elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Second LLM: Map sensitive content to word-level coordinates.
    """
    try:
        from pydantic import BaseModel
    except Exception:
        return []
    
    class CoordinateMappedItem(BaseModel):
        page_number: int
        content: str
        reason: str
        element_ids: List[int]  # Word element IDs that contain this sensitive data
    
    class CoordinateMappingOutput(BaseModel):
        items: List[CoordinateMappedItem]
    
    # Prepare word elements by page
    words_by_page = {}
    for element in word_elements:
        page_num = element.get("page_number", 1)
        if page_num not in words_by_page:
            words_by_page[page_num] = []
        words_by_page[page_num].append({
            "element_id": element.get("element_id"),
            "content": element.get("content", ""),
            "bbox": element.get("bbox", {})
        })
    
    # Prepare sensitive content for matching
    sensitive_items_str = []
    for item in sensitive_content_items:
        sensitive_items_str.append(f"Page {item.get('page_num', 1)}: '{item.get('sensitive_content', '')}' (Reason: {item.get('reason', '')})")
    
    instruction = (
        "You are a specialized LLM for mapping sensitive content to precise word coordinates. "
        "For each sensitive content item, find the matching word element IDs that contain that information.\n\n"
        "CRITICAL MAPPING RULES:\n"
        "- Map ONLY the sensitive VALUES, NOT field labels\n"
        "- Example: For 'N0004705512' → find element IDs for 'N0004705512' words only\n"
        "- Example: For 'John Smith' → find element IDs for 'John' and 'Smith' words only\n"
        "- DO NOT map field labels like 'SEVIS ID:', 'NAME:', 'ADDRESS:'\n"
        "- For multi-word values (like 'John Doe Smith'), include ALL element IDs for the complete value\n"
        "- For single word values, select the specific element_id for that word\n"
        "- Be PRECISE - only select elements that contain the actual sensitive values\n"
        "- Group related value words together (avoid over-segmentation)\n\n"
        "Extract the word-level coordinates for each sensitive VALUE and provide the exact value content, "
        "reason, and list of element_ids that cover only the sensitive value (not labels)."
    )
    
    payload = {
        "sensitive_items_to_map": sensitive_items_str,
        "word_elements_by_page": words_by_page
    }
    
    try:
        llm = AzureLLM()
        res: CoordinateMappingOutput = llm.create_structured_response(CoordinateMappingOutput, instruction, str(payload))
        
        # Convert to final format with actual coordinates
        final_items = []
        for item in res.items or []:
            # Get actual coordinates from word elements
            page_num = item.page_number
            element_ids = item.element_ids or []
            
            if not element_ids:
                continue
            
            # Find matching word elements
            page_words = words_by_page.get(page_num, [])
            matching_words = [w for w in page_words if w["element_id"] in element_ids]
            
            if not matching_words:
                continue
            
            # Compute merged bounding box
            if len(matching_words) == 1:
                bbox = matching_words[0]["bbox"]
            else:
                bboxes = [w["bbox"] for w in matching_words]
                bbox = {
                    "x0": min(b["x0"] for b in bboxes),
                    "y0": min(b["y0"] for b in bboxes),
                    "x1": max(b["x1"] for b in bboxes),
                    "y1": max(b["y1"] for b in bboxes)
                }
            
            final_items.append({
                "page_number": page_num,
                "content": item.content,
                "reason": item.reason,
                "bbox": bbox
            })
        
        return final_items
        
    except Exception as e:
        print(f"❌ Second LLM error: {e}")
        return []


# Helper functions

def _init_di_client() -> DocumentIntelligenceClient:
    """Initialize Azure Document Intelligence client."""
    endpoint = os.getenv("AZURE_DI_ENDPOINT") or os.getenv("AZURE_ENDPOINT")
    key = os.getenv("AZURE_KEY")
    if not endpoint or not key:
        raise RuntimeError("AZURE_DI_ENDPOINT (or AZURE_ENDPOINT) and AZURE_KEY must be set")
    return DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))


def _extract_paragraph_bbox(paragraph) -> Dict[str, float]:
    """Extract bounding box from paragraph."""
    if hasattr(paragraph, 'polygon') and paragraph.polygon:
        return _polygon_to_bbox(paragraph.polygon)
    return {"x0": 0, "y0": 0, "x1": 0, "y1": 0}


def _polygon_to_bbox(polygon: List[float]) -> Dict[str, float]:
    """Convert polygon to bounding box."""
    if not polygon or len(polygon) < 4:
        return {"x0": 0, "y0": 0, "x1": 0, "y1": 0}
    
    xs = [polygon[i] for i in range(0, len(polygon), 2)]
    ys = [polygon[i + 1] for i in range(0, len(polygon), 2)]
    
    return {
        "x0": float(min(xs)),
        "y0": float(min(ys)),
        "x1": float(max(xs)),
        "y1": float(max(ys))
    }


def _polygon_to_bbox_points(polygon: List[float], unit: str, di_w: float, di_h: float, pdf_pt_w: float, pdf_pt_h: float) -> Dict[str, float]:
    """Convert Azure DI polygon coordinates to PyMuPDF points."""
    # Compute axis-aligned bbox from polygon
    xs = [polygon[i] for i in range(0, len(polygon), 2)] if polygon else [0.0]
    ys = [polygon[i + 1] for i in range(0, len(polygon), 2)] if polygon else [0.0]
    min_x, max_x = float(min(xs)), float(max(xs))
    min_y, max_y = float(min(ys)), float(max(ys))

    u = (unit or "").lower()
    if u == "inch":
        # Convert inches to points
        return {"x0": min_x * 72.0, "y0": min_y * 72.0, "x1": max_x * 72.0, "y1": max_y * 72.0}
    if u in ("pixel", "pixelperinch", "pixelperinch2", "pixel/unknown") or (di_w and di_h):
        # Scale pixels to PDF points using page sizes
        sx = (pdf_pt_w / di_w) if di_w else 1.0
        sy = (pdf_pt_h / di_h) if di_h else 1.0
        return {"x0": min_x * sx, "y0": min_y * sy, "x1": max_x * sx, "y1": max_y * sy}
    if u in ("cm", "centimeter"):
        k = 72.0 / 2.54
        return {"x0": min_x * k, "y0": min_y * k, "x1": max_x * k, "y1": max_y * k}
    # Fallback: assume already points
    return {"x0": min_x, "y0": min_y, "x1": max_x, "y1": max_y}
