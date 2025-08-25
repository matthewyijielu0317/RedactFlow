"""
Agentic PDF Sanitizer - Streamlit UI
Human-in-the-Loop Interface for PDF Sanitization with Agentic Workflow
"""

import streamlit as st
import os
import tempfile
from typing import Dict, Any, List, Optional
import fitz  # PyMuPDF
from PIL import Image
import io
import json
from streamlit_drawable_canvas import st_canvas
import pandas as pd

# Import backend components
from nodes.orchestrator import build_sanitizer_graph
from nodes.state import SanitizerState
from nodes.manual_redactor_node import apply_manual_redactions, combine_ai_and_manual_redactions


# Configuration
CANVAS_WIDTH = 700
CANVAS_HEIGHT = 1000
HIGHLIGHT_COLOR = "#FFFF00"  # Yellow for AI detections
MANUAL_COLOR = "#00FF00"    # Green for manual selections
REDACTION_COLOR = "#FF0000" # Red for final redactions


def init_session_state():
    """Initialize Streamlit session state variables."""
    if "initialized" not in st.session_state:
        st.session_state.workflow_state = {}
        st.session_state.current_page = 0
        st.session_state.pdf_doc = None
        st.session_state.canvas_key = 0
        st.session_state.manual_rectangles = []
        st.session_state.workflow_running = False
        st.session_state.preview_approved = False
        st.session_state.show_approval_buttons = False
        st.session_state.current_file_key = None
        st.session_state.detection_prompt = ""
        st.session_state.initialized = True
        st.session_state.rejection_message = None


def load_pdf_page_as_image(pdf_doc: fitz.Document, page_num: int, width: int = CANVAS_WIDTH) -> Image.Image:
    """Convert PDF page to PIL Image for canvas display."""
    page = pdf_doc[page_num]
    
    # Calculate scale to fit canvas width
    page_rect = page.rect
    scale = width / page_rect.width
    
    # Render page as image
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    img_data = pix.tobytes("png")
    
    return Image.open(io.BytesIO(img_data))


def canvas_to_pdf_coordinates(canvas_coords: Dict, page_rect: fitz.Rect, canvas_width: int, canvas_height: int) -> Dict[str, float]:
    """Convert canvas coordinates to PDF coordinates (PyMuPDF points)."""
    scale_x = page_rect.width / canvas_width
    scale_y = page_rect.height / canvas_height
    
    return {
        "x0": canvas_coords["left"] * scale_x,
        "y0": canvas_coords["top"] * scale_y,
        "x1": (canvas_coords["left"] + canvas_coords["width"]) * scale_x,
        "y1": (canvas_coords["top"] + canvas_coords["height"]) * scale_y
    }


def pdf_to_canvas_coordinates(pdf_coords: Dict[str, float], page_rect: fitz.Rect, canvas_width: int, canvas_height: int) -> Dict:
    """Convert PDF coordinates to canvas coordinates."""
    scale_x = canvas_width / page_rect.width
    scale_y = canvas_height / page_rect.height
    
    return {
        "left": pdf_coords["x0"] * scale_x,
        "top": pdf_coords["y0"] * scale_y,
        "width": (pdf_coords["x1"] - pdf_coords["x0"]) * scale_x,
        "height": (pdf_coords["y1"] - pdf_coords["y0"]) * scale_y
    }


def create_canvas_objects(sensitive_items: List[Dict], manual_items: List[Dict], page_num: int, page_rect: fitz.Rect) -> List[Dict]:
    """Create canvas objects for AI detections and manual selections."""
    objects = []
    
    # Add AI detected items (yellow)
    for item in sensitive_items:
        if item.get("page_number") == page_num + 1:  # Convert to 1-based
            canvas_coords = pdf_to_canvas_coordinates(item["bbox"], page_rect, CANVAS_WIDTH, CANVAS_HEIGHT)
            objects.append({
                "type": "rect",
                "left": canvas_coords["left"],
                "top": canvas_coords["top"],
                "width": canvas_coords["width"],
                "height": canvas_coords["height"],
                "fill": HIGHLIGHT_COLOR,
                "stroke": HIGHLIGHT_COLOR,
                "strokeWidth": 2,
                "opacity": 0.5
            })
    
    # Add manual selections (green)
    for item in manual_items:
        if item.get("page_number") == page_num + 1:  # Convert to 1-based
            canvas_coords = pdf_to_canvas_coordinates(item["bbox"], page_rect, CANVAS_WIDTH, CANVAS_HEIGHT)
            objects.append({
                "type": "rect",
                "left": canvas_coords["left"],
                "top": canvas_coords["top"],
                "width": canvas_coords["width"],
                "height": canvas_coords["height"],
                "fill": MANUAL_COLOR,
                "stroke": MANUAL_COLOR,
                "strokeWidth": 2,
                "opacity": 0.5
            })
    
    return objects


def run_agentic_workflow(state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the agentic workflow using LangGraph."""
    try:
        # Build the workflow graph
        graph = build_sanitizer_graph()
        
        # Compile with interrupt before HumanInLoop to pause workflow for UI input
        app = graph.compile(interrupt_before=["HumanInLoop"])
        
        # Execute workflow (will pause before HumanInLoop)
        sensitive_items = state.get('sensitive_data', [])
        print(f"🔄 AI WORKFLOW DEBUG:")
        print(f"   📊 Starting workflow with state keys: {list(state.keys())}")
        print(f"   📋 User approval: {state.get('user_approval')}")
        print(f"   📄 PDF path: {state.get('pdf_path')}")
        print(f"   🤖 AI items for workflow: {len(sensitive_items)}")
        
        result = app.invoke(state)
        
        print(f"   ⏸️ Workflow paused at HumanInLoop with state keys: {list(result.keys())}")
        print(f"   📁 Preview PDF path: {result.get('preview_pdf_path')}")
        
        return result
        
    except Exception as e:
        print(f"❌ Workflow execution error: {str(e)}")
        st.error(f"Workflow execution error: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return state


def display_workflow_progress(state: Dict[str, Any]):
    """Display workflow progress indicators."""
    st.subheader("🔄 Workflow Progress")
    
    # Determine current stage
    stages = [
        ("🎯 Orchestrator", "orchestrator"),
        ("🔍 Searcher", "searcher"),
        ("🤖 Detector", "detector"),
        ("📊 Evaluator", "evaluator"),
        ("👤 Human Review", "hitl"),
        ("✂️ Redactor", "redactor")
    ]
    
    cols = st.columns(len(stages))
    
    for i, (stage_name, stage_key) in enumerate(stages):
        with cols[i]:
            # Determine stage status
            if stage_key == "orchestrator" and state.get("sensitive_data_description"):
                st.success(stage_name)
            elif stage_key == "searcher" and state.get("search_query"):
                st.success(stage_name)
            elif stage_key == "detector" and state.get("sensitive_data"):
                st.success(stage_name)
            elif stage_key == "evaluator" and state.get("evaluator_cycles", 0) > 0:
                st.success(stage_name)
            elif stage_key == "hitl" and st.session_state.show_approval_buttons:
                st.warning(stage_name)
            elif stage_key == "redactor" and state.get("final_pdf_path"):
                st.success(stage_name)
            else:
                st.info(stage_name)


def main():
    st.set_page_config(
        page_title="Agentic PDF Sanitizer",
        page_icon="✂️🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    init_session_state()
    
    # Debug info (remove in production)
    if st.sidebar.checkbox("🔧 Debug Mode", value=False):
        st.sidebar.write("**Session State Debug:**")
        st.sidebar.write(f"File Key: {st.session_state.get('current_file_key', 'None')}")
        st.sidebar.write(f"Workflow Running: {st.session_state.workflow_running}")
        st.sidebar.write(f"Canvas Key: {st.session_state.canvas_key}")
        st.sidebar.write(f"Manual Rectangles: {len(st.session_state.manual_rectangles)}")
        st.sidebar.write(f"Preview Approved: {st.session_state.preview_approved}")
        st.sidebar.write(f"Show Approval Buttons: {st.session_state.show_approval_buttons}")
        if st.session_state.workflow_state:
            st.sidebar.write("**Workflow State Keys:**")
            for key in st.session_state.workflow_state.keys():
                st.sidebar.write(f"- {key}")
            if "final_pdf_path" in st.session_state.workflow_state:
                st.sidebar.write(f"Final PDF: {st.session_state.workflow_state['final_pdf_path']}")
    
    st.title("✂️🤖 Agentic PDF Sanitizer")
    st.markdown("*Human-in-the-Loop PDF Sanitization with AI Workflow*")

    if st.session_state.rejection_message:
        st.info(st.session_state.rejection_message)
        st.session_state.rejection_message = None
    
    # Sidebar for controls
    with st.sidebar:
        st.header("📋 Control Panel")
        
        # PDF Upload
        st.subheader("📄 Upload PDF")
        uploaded_file = st.file_uploader(
            "Upload PDF Document",
            type=["pdf"],
            key="pdf_uploader"
        )
        
        if uploaded_file is not None:
            # Create a unique key for this file to detect changes
            file_key = f"{uploaded_file.name}_{uploaded_file.size}"
            
            # Only process if it's a new file
            if st.session_state.get("current_file_key") != file_key:
                # Save uploaded file to output/original/ folder
                original_dir = os.path.join(os.getcwd(), "output", "original")
                os.makedirs(original_dir, exist_ok=True)
                pdf_path = os.path.join(original_dir, uploaded_file.name)
                
                with open(pdf_path, "wb") as f:
                    f.write(uploaded_file.getvalue())
                
                # Load PDF
                if st.session_state.pdf_doc is not None:
                    st.session_state.pdf_doc.close()
                
                st.session_state.pdf_doc = fitz.open(pdf_path)
                st.session_state.workflow_state = {"pdf_path": pdf_path}
                st.session_state.current_page = 0
                st.session_state.manual_rectangles = []
                st.session_state.preview_approved = False
                st.session_state.show_approval_buttons = False
                st.session_state.workflow_running = False
                st.session_state.current_file_key = file_key
                st.rerun()
            
            # Get the current PDF path for use below
            pdf_path = st.session_state.workflow_state.get("pdf_path")
        
        # Detection Prompt
        st.subheader("🎯 Detection Prompt")
        
        # Quick action buttons
        st.markdown("**Quick Actions:**")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("👤 Names & IDs", use_container_width=True):
                st.session_state.detection_prompt = "Detect and redact all personal names, ID numbers, and identification information in this PDF"
        
        with col2:
            if st.button("📞 Contact Info", use_container_width=True):
                st.session_state.detection_prompt = "Detect and redact all contact information including emails, phone numbers, and addresses in this PDF"
        
        if st.button("💰 Financial Data", use_container_width=True):
            st.session_state.detection_prompt = "Detect and redact all financial information including account numbers, amounts, and payment details in this PDF"
        
        # Main prompt input
        detection_prompt = st.text_area(
            "Describe what to detect and redact:",
            value=st.session_state.get("detection_prompt", ""),
            height=100,
            placeholder="Example: Detect and redact all personal names, SSNs, addresses, and phone numbers in this PDF"
        )
        
        # Run Detection Button
        run_detection = st.button(
            "🚀 Run Detection",
            type="primary",
            disabled=st.session_state.workflow_running or uploaded_file is None,
            use_container_width=True
        )
        
        if run_detection and detection_prompt and not st.session_state.workflow_running:
            st.session_state.workflow_running = True
            st.session_state.workflow_state.update({
                "user_prompt": detection_prompt,
                "pdf_path": pdf_path
            })
            # Reset previous results
            st.session_state.show_approval_buttons = False
            st.session_state.preview_approved = False
            
            # Clear the prompt from the UI
            st.session_state.detection_prompt = ""
            
            st.rerun()
    
    # Main content area
    if uploaded_file is None:
        st.info("👆 Please upload a PDF document to get started")
        return

    
    
    # Ensure we have a valid PDF path
    pdf_path = st.session_state.workflow_state.get("pdf_path")
    if not pdf_path:
        st.error("❌ PDF path not found. Please re-upload the PDF.")
        return
    
    # Display workflow progress
    if st.session_state.workflow_state.get("user_prompt"):
        display_workflow_progress(st.session_state.workflow_state)
    
    # Run workflow if needed
    if st.session_state.workflow_running:
        with st.spinner("🤖 Running agentic workflow..."):
            st.session_state.workflow_state = run_agentic_workflow(st.session_state.workflow_state)
            st.session_state.workflow_running = False
            
            # Preserve original AI detections for reset functionality
            if st.session_state.workflow_state.get("sensitive_data"):
                st.session_state.original_ai_detections = st.session_state.workflow_state["sensitive_data"].copy()
            
            # Check if we need to show approval buttons
            if st.session_state.workflow_state.get("sensitive_data"):
                st.session_state.show_approval_buttons = True
            
            st.rerun()
    
    # PDF Display and Canvas
    if st.session_state.pdf_doc is not None:
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.subheader("📄 PDF Canvas")
            
            # Page navigation
            total_pages = len(st.session_state.pdf_doc)
            if total_pages > 1:
                nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
                
                with nav_col1:
                    if st.button("⬅️ Previous", disabled=st.session_state.current_page == 0):
                        st.session_state.current_page = max(0, st.session_state.current_page - 1)
                        st.session_state.canvas_key += 1
                        st.rerun()
                
                with nav_col2:
                    st.markdown(f"**Page {st.session_state.current_page + 1} of {total_pages}**")
                
                with nav_col3:
                    if st.button("Next ➡️", disabled=st.session_state.current_page >= total_pages - 1):
                        st.session_state.current_page = min(total_pages - 1, st.session_state.current_page + 1)
                        st.session_state.canvas_key += 1
                        st.rerun()
            
            # Load current page - use preview PDF if available, otherwise original
            current_page = st.session_state.current_page
            
            # Use original PDF for canvas
            page_image = load_pdf_page_as_image(st.session_state.pdf_doc, current_page, CANVAS_WIDTH)
            page_rect = st.session_state.pdf_doc[current_page].rect
            
            # Create canvas objects for existing detections
            sensitive_items = st.session_state.workflow_state.get("sensitive_data", [])
            canvas_objects = create_canvas_objects(sensitive_items, st.session_state.manual_rectangles, current_page, page_rect)
            
            # Canvas for PDF display and manual drawing
            canvas_result = st_canvas(
                fill_color="rgba(0, 255, 0, 0.3)",  # Green with transparency
                stroke_width=2,
                stroke_color="#00FF00",
                background_image=page_image,
                update_streamlit=True,
                width=CANVAS_WIDTH,
                height=CANVAS_HEIGHT,
                drawing_mode="rect",
                point_display_radius=0,
                key=f"canvas_{st.session_state.canvas_key}",
                initial_drawing={
                    "version": "4.4.0",
                    "objects": canvas_objects
                }
            )
            
            # Process canvas drawings IMMEDIATELY after canvas render
            # This ensures manual rectangles are captured before button logic runs
            if canvas_result.json_data is not None:
                objects = canvas_result.json_data["objects"]
                print(f"🔧 CANVAS DEBUG:")
                print(f"   📊 Canvas objects found: {len(objects)}")
                
                # Debug: Show all objects
                for i, obj in enumerate(objects):
                    print(f"   [{i+1}] Object type: {obj.get('type')}, stroke: {obj.get('stroke')}, fill: {obj.get('fill')}")
                
                new_rectangles = [obj for obj in objects if obj["type"] == "rect" and obj.get("stroke") == "#00FF00"]
                print(f"   🟢 Green rectangles (manual): {len(new_rectangles)}")
                
                # Only process if we have new rectangles and they're not already processed
                current_manual_count = len(st.session_state.manual_rectangles)
                print(f"   📋 Current manual_rectangles in state: {current_manual_count}")
                
                # Convert new rectangles to PDF coordinates
                for i, rect in enumerate(new_rectangles):
                    print(f"   ✏️ Processing rectangle {i+1}: {rect}")
                    
                    pdf_coords = canvas_to_pdf_coordinates(rect, page_rect, CANVAS_WIDTH, CANVAS_HEIGHT)
                    print(f"   📍 Converted coordinates: {pdf_coords}")
                    
                    manual_item = {
                        "page_number": current_page + 1,
                        "content": "[Manual Selection]",
                        "reason": "Manually selected sensitive area",
                        "bbox": pdf_coords
                    }
                    
                    # Check if this rectangle is already in manual_rectangles
                    is_duplicate = False
                    for existing in st.session_state.manual_rectangles:
                        if (existing["page_number"] == manual_item["page_number"] and
                            abs(existing["bbox"]["x0"] - manual_item["bbox"]["x0"]) < 5 and
                            abs(existing["bbox"]["y0"] - manual_item["bbox"]["y0"]) < 5):
                            is_duplicate = True
                            print(f"   ⚠️ Duplicate detected, skipping")
                            break
                    
                    if not is_duplicate:
                        st.session_state.manual_rectangles.append(manual_item)
                        print(f"   ✅ Added manual item to state: {manual_item}")
                        # Force immediate state update
                        st.session_state.manual_rectangles = st.session_state.manual_rectangles
                    
                print(f"   📋 Final manual_rectangles count: {len(st.session_state.manual_rectangles)}")
            else:
                print(f"🔧 CANVAS DEBUG: No canvas data available")
            
            # Manual drawing controls
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Confirm Manual Selections", use_container_width=True):
                    # Just refresh to ensure manual rectangles are captured
                    manual_count = len(st.session_state.manual_rectangles)
                    
                    print(f"🔧 MANUAL SELECTIONS DEBUG:")
                    print(f"   📊 Manual rectangles found: {manual_count}")
                    print(f"   📋 Full manual_rectangles data: {st.session_state.manual_rectangles}")
                    
                    if manual_count > 0:
                        st.success(f"✅ Found {manual_count} manual selection(s)")
                        for i, rect in enumerate(st.session_state.manual_rectangles):
                            print(f"   [{i+1}] Page {rect.get('page_number')}: {rect.get('bbox')}")
                            print(f"       Content: {rect.get('content')}")
                            print(f"       Reason: {rect.get('reason')}")
                    else:
                        st.info("ℹ️ No manual selections found. Draw rectangles on sensitive areas.")
                        print(f"   🔍 Session state keys: {list(st.session_state.keys())}")
                        print(f"   🔍 Canvas key: {st.session_state.canvas_key}")
                    
                    st.rerun()
            
            with col2:
                if st.button("🔄 Reset Drawings", use_container_width=True):
                    # Reset manual rectangles and restore original AI detections
                    st.session_state.manual_rectangles = []
                    st.session_state.canvas_key += 1
                    
                    # Restore workflow state to only AI items
                    if "original_ai_detections" in st.session_state:
                        st.session_state.workflow_state["sensitive_data"] = st.session_state.original_ai_detections
                    
                    st.rerun()
        
        with col2:
            st.subheader("📊 Detection Results")
            
            # AI detected items
            ai_items = st.session_state.workflow_state.get("sensitive_data", [])
            manual_items = st.session_state.manual_rectangles
            
            print(f"🔧 DISPLAY DEBUG:")
            print(f"   🤖 AI items: {len(ai_items)}")
            print(f"   ✋ Manual items: {len(manual_items)}")
            
            # Editable AI items with expanders
            if ai_items:
                st.markdown("**🤖 AI Detected Items:**")
                for idx, item in enumerate(ai_items):
                    with st.expander(f"AI Item {idx+1}: {item.get('content', '')[:40]} (Page {item.get('page_number', 1)})"):
                        new_content = st.text_input("Content", value=item.get("content", ""), key=f"ai_content_{idx}")
                        new_reason = st.text_input("Reason", value=item.get("reason", ""), key=f"ai_reason_{idx}")
                        page = st.number_input("Page", value=int(item.get("page_number", 1)), min_value=1, key=f"ai_page_{idx}")
                       
                        bbox = item.get("bbox", {"x0": 0, "y0": 0, "x1": 0, "y1": 0})
                        st.markdown("**Coordinates (PDF points):**")
                        x0 = st.number_input("x0", value=float(bbox.get("x0", 0)), key=f"ai_x0_{idx}")
                        y0 = st.number_input("y0", value=float(bbox.get("y0", 0)), key=f"ai_y0_{idx}")
                        x1 = st.number_input("x1", value=float(bbox.get("x1", 0)), key=f"ai_x1_{idx}")
                        y1 = st.number_input("y1", value=float(bbox.get("y1", 0)), key=f"ai_y1_{idx}")
                        
                        if st.button("✅ Apply Changes", key=f"ai_apply_{idx}"):
                            # Update the AI item in workflow state's sensitive_data
                            if "sensitive_data" not in st.session_state.workflow_state:
                                st.session_state.workflow_state["sensitive_data"] = []
                            
                            st.session_state.workflow_state["sensitive_data"][idx] = {
                                "page_number": int(page),
                                "content": new_content,
                                "reason": new_reason,
                                "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
                            }
                            st.success("✅ AI item updated in workflow state!")
                            st.rerun()
                        
                        if st.button("🗑️ Delete Item", key=f"ai_delete_{idx}"):
                            if "sensitive_data" in st.session_state.workflow_state and idx < len(st.session_state.workflow_state["sensitive_data"]):
                                del st.session_state.workflow_state["sensitive_data"][idx]
                                st.success("🗑️ AI item deleted from workflow state!")
                                st.rerun()
                
                st.markdown(f"**AI Items: {len(ai_items)}**")
            else:
                st.info("No AI detections yet")
            
            # Editable manual items with expanders
            if manual_items:
                st.markdown("**✋ Manual Selections:**")
                for idx, item in enumerate(manual_items):
                    with st.expander(f"Manual Item {idx+1}: Page {item.get('page_number', 1)}"):
                        new_content = st.text_input("Content", value=item.get("content", "[Manual Selection]"), key=f"manual_content_{idx}")
                        new_reason = st.text_input("Reason", value=item.get("reason", "Manually selected sensitive area"), key=f"manual_reason_{idx}")
                        page = st.number_input("Page", value=int(item.get("page_number", 1)), min_value=1, key=f"manual_page_{idx}")
                        
                        bbox = item.get("bbox", {"x0": 0, "y0": 0, "x1": 0, "y1": 0})
                        st.markdown("**Coordinates (PDF points):**")
                        x0 = st.number_input("x0", value=float(bbox.get("x0", 0)), key=f"manual_x0_{idx}")
                        y0 = st.number_input("y0", value=float(bbox.get("y0", 0)), key=f"manual_y0_{idx}")
                        x1 = st.number_input("x1", value=float(bbox.get("x1", 0)), key=f"manual_x1_{idx}")
                        y1 = st.number_input("y1", value=float(bbox.get("y1", 0)), key=f"manual_y1_{idx}")
                        
                        if st.button("✅ Apply Changes", key=f"manual_apply_{idx}"):
                            # Update the manual item
                            st.session_state.manual_rectangles[idx] = {
                                "page_number": int(page),
                                "content": new_content,
                                "reason": new_reason,
                                "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
                            }
                            st.success("✅ Manual item updated successfully!")
                            st.rerun()
                        
                        if st.button("🗑️ Delete Item", key=f"manual_delete_{idx}"):
                            del st.session_state.manual_rectangles[idx]
                            st.success("🗑️ Manual item deleted successfully!")
                            st.rerun()
                
                st.markdown(f"**Manual Items: {len(manual_items)}**")
            else:
                st.info("No manual selections yet")
            
            # Summary
            total_items = len(ai_items) + len(manual_items)
            if total_items > 0:
                st.markdown(f"**📊 Total for Redaction: {total_items} items ({len(ai_items)} AI + {len(manual_items)} Manual)**")
    
    # Human-in-the-Loop Approval Section
    if st.session_state.show_approval_buttons and not st.session_state.preview_approved:
        st.divider()
        st.subheader("👤 Human Review")
        
        st.info("📋 Please review the highlighted sensitive items above. You can:")
        st.markdown("- ✅ **Approve Preview** → AI redaction first, then manual redactions applied on top")
        st.markdown("- ❌ **Reject Preview** → Provide more hints and re-run detection")
        
        manual_count = len(st.session_state.manual_rectangles)
        if manual_count > 0:
            st.markdown(f"- ✂️ **Manual Only** → Skip AI, redact only your {manual_count} manual selection(s)")
        
        st.markdown("**🔄 Process Flow:**")
        st.markdown("1. **AI Workflow** → Detects and redacts sensitive data")
        st.markdown("2. **Manual Redactor** → Applies your manual selections on top of AI result")
        st.markdown("3. **Final PDF** → Combined AI + Manual redactions")
        
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if st.button("✅ Approve Preview", type="primary", use_container_width=True):
                # Only process AI workflow - manual redactions will be applied separately
                ai_items = st.session_state.workflow_state.get("sensitive_data", [])
                manual_count = len(st.session_state.manual_rectangles)
                
                print(f"🔧 APPROVE PREVIEW DEBUG:")
                print(f"   🤖 AI items for workflow: {len(ai_items)}")
                print(f"   ✋ Manual rectangles (separate): {manual_count}")
                print(f"   📋 Manual rectangles data: {st.session_state.manual_rectangles}")
                
                # Debug: Check if manual rectangles exist
                if manual_count > 0:
                    print(f"   ✅ Manual count > 0, will proceed with combined redaction")
                    for i, rect in enumerate(st.session_state.manual_rectangles):
                        print(f"   📍 Manual rectangle {i+1}: Page {rect.get('page_number')}, BBox: {rect.get('bbox')}")
                else:
                    print(f"   ❌ Manual count is 0, will skip manual redaction step")
                
                st.session_state.workflow_state["user_approval"] = "Yes"
                st.session_state.preview_approved = True
                st.session_state.show_approval_buttons = False
                
                # Step 1: Resume workflow from HumanInLoop to continue to Redactor
                with st.spinner("🔄 Generating AI redacted PDF..."):
                    try:
                        # Build the workflow graph and compile without interrupt for redaction
                        from nodes.orchestrator import build_sanitizer_graph
                        graph = build_sanitizer_graph()
                        app = graph.compile()  # No interrupt for redaction phase
                        
                        # Continue directly from HITL to Redactor
                        print(f"🔧 CONTINUING FROM HITL TO REDACTOR:")
                        print(f"   📊 Current state keys: {list(st.session_state.workflow_state.keys())}")
                        print(f"   🤖 AI items (user-edited): {len(st.session_state.workflow_state.get('sensitive_data', []))}")
                        print(f"   ✅ User approval: {st.session_state.workflow_state.get('user_approval')}")
                        
                        # Force workflow to start from HumanInLoop and continue to Redactor
                        from nodes.hitl_node import run_hitl
                        from nodes.redactor_node import run_redactor
                        
                        print(f"   🔄 Step 1: Running HITL node directly")
                        hitl_result = run_hitl(st.session_state.workflow_state)
                        print(f"   📋 HITL result next_node: {hitl_result.get('next_node')}")
                        
                        if hitl_result.get('next_node') == 'Redactor':
                            print(f"   🔄 Step 2: Running Redactor node directly")
                            redactor_result = run_redactor(hitl_result)
                            st.session_state.workflow_state = redactor_result
                            ai_redacted_path = redactor_result.get('final_pdf_path')
                            print(f"   📁 Final PDF path from redactor: {ai_redacted_path}")
                        else:
                            print(f"   ❌ HITL did not route to Redactor, got: {hitl_result.get('next_node')}")
                            ai_redacted_path = None
                        
                        if not ai_redacted_path:
                            st.error("❌ AI workflow failed to produce redacted PDF")
                            return
                        
                        print(f"🔧 WORKFLOW SEQUENCE:")
                        print(f"   ✅ Step 1: AI workflow completed → {ai_redacted_path}")
                        st.success(f"✅ Step 1: AI redaction completed! {len(ai_items)} items redacted")
                        st.info(f"📁 AI-redacted file saved: `{ai_redacted_path}`")
                        
                        # Step 2: Apply manual redactions on top of AI-redacted PDF
                        if manual_count > 0:
                            with st.spinner("🔄 Step 2: Applying manual redactions on AI-redacted PDF..."):
                                print(f"   🔄 Step 2: Applying {manual_count} manual redactions on AI result")
                                final_path = combine_ai_and_manual_redactions(ai_redacted_path, st.session_state.manual_rectangles)
                                
                                # Update the final path in workflow state
                                st.session_state.workflow_state["final_pdf_path"] = final_path
                                print(f"   ✅ Step 2: Combined redaction completed → {final_path}")
                                st.success(f"✅ Step 2: Manual redactions applied! Final PDF ready for download.")
                                st.info(f"📁 Combined file saved: `{final_path}`")
                                
                                # Show file structure
                                output_base = os.path.join(os.getcwd(), "output")
                                if os.path.exists(output_base):
                                    st.markdown("**📂 Files created in `output/` directory:**")
                                    
                                    # Show original files
                                    original_dir = os.path.join(output_base, "original")
                                    if os.path.exists(original_dir):
                                        original_files = [f for f in os.listdir(original_dir) if f.endswith('.pdf')]
                                        if original_files:
                                            st.markdown("**📁 original/**")
                                            for file in sorted(original_files):
                                                st.markdown(f"  - `{file}`")
                                    
                                    # Show preview files
                                    preview_dir = os.path.join(output_base, "preview")
                                    if os.path.exists(preview_dir):
                                        preview_files = [f for f in os.listdir(preview_dir) if f.endswith('.pdf')]
                                        if preview_files:
                                            st.markdown("**📁 preview/**")
                                            for file in sorted(preview_files):
                                                st.markdown(f"  - `{file}`")
                                    
                                    # Show redacted files
                                    redacted_dir = os.path.join(output_base, "redacted")
                                    if os.path.exists(redacted_dir):
                                        redacted_files = [f for f in os.listdir(redacted_dir) if f.endswith('.pdf')]
                                        if redacted_files:
                                            st.markdown("**📁 redacted/**")
                                            for file in sorted(redacted_files):
                                                st.markdown(f"  - `{file}`")
                        else:
                            st.info("ℹ️ No manual selections to apply. AI redaction is final.")
                        
                        # Force immediate UI refresh to show download button
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Workflow error: {str(e)}")
                        st.write("Debug info:", st.session_state.workflow_state.keys())
                        st.rerun()
        
        with col2:
            if st.button("❌ Reject Preview", use_container_width=True):
                st.session_state.show_approval_buttons = False
                st.session_state.workflow_state["user_approval"] = "No"
                st.session_state.rejection_message = "🤖 **To improve the results, please provide more specific instructions in the 'Detection Prompt' on the left sidebar and click 'Run Detection' again.**"
                st.rerun()

        with col3:
            # Manual-only redaction option
            manual_count = len(st.session_state.manual_rectangles)
            if manual_count > 0:
                if st.button(f"✂️ Redact Manual Only ({manual_count})", use_container_width=True):
                    pdf_path = st.session_state.workflow_state.get("pdf_path")
                    if pdf_path:
                        with st.spinner("🔄 Applying manual redactions only..."):
                            try:
                                final_path = apply_manual_redactions(pdf_path, st.session_state.manual_rectangles)
                                st.session_state.workflow_state["final_pdf_path"] = final_path
                                st.session_state.preview_approved = True
                                st.session_state.show_approval_buttons = False
                                st.success(f"✅ Manual redaction completed! {manual_count} selections redacted")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Manual redaction error: {str(e)}")
                    else:
                        st.error("❌ PDF path not found")
            else:
                st.info("Draw rectangles on sensitive areas to enable manual-only redaction")
    
    # Final Redaction Section
    if st.session_state.workflow_state.get("final_pdf_path"):
        st.divider()
        st.subheader("🎉 Final Redacted PDF")
        
        final_path = st.session_state.workflow_state["final_pdf_path"]
        
        if os.path.exists(final_path):
            with open(final_path, "rb") as file:
                st.download_button(
                    label="📥 Download Redacted PDF",
                    data=file.read(),
                    file_name=f"redacted_{uploaded_file.name}",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
            
            st.success("✅ PDF successfully redacted! All sensitive information has been replaced with black boxes.")
            
            # Add button to start over with a new document
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                if st.button("🔄 Process New Document", type="secondary", use_container_width=True):
                    # Clear all session state to start fresh
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.rerun()
                    
        else:
            st.error("❌ Final PDF file not found. Please try again.")


if __name__ == "__main__":
    main()
