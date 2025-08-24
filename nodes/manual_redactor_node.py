"""
Manual Redactor Node
Handles manual redactions independently from the AI workflow using PyMuPDF
"""

import fitz  # PyMuPDF
import tempfile
import os
from typing import List, Dict, Any


def apply_manual_redactions(pdf_path: str, manual_rectangles: List[Dict[str, Any]]) -> str:
    """
    Apply manual redactions to PDF using black boxes.
    
    Args:
        pdf_path: Path to the source PDF
        manual_rectangles: List of manual selection dictionaries with bbox and page_number
        
    Returns:
        Path to the manually redacted PDF
    """
    if not manual_rectangles:
        print("🔧 MANUAL REDACTOR: No manual rectangles to redact")
        return pdf_path
    
    print(f"🔧 MANUAL REDACTOR DEBUG:")
    print(f"   📄 Source PDF: {pdf_path}")
    print(f"   📋 Manual rectangles to redact: {len(manual_rectangles)}")
    
    # Open the PDF
    doc = fitz.open(pdf_path)
    
    # Apply manual redactions
    redacted_count = 0
    for i, rect_item in enumerate(manual_rectangles):
        page_number = rect_item.get("page_number", 1)
        bbox = rect_item.get("bbox", {})
        
        print(f"   [{i+1}] Manual redaction: Page {page_number}, BBox: ({bbox.get('x0', 0):.1f}, {bbox.get('y0', 0):.1f}, {bbox.get('x1', 0):.1f}, {bbox.get('y1', 0):.1f})")
        
        # Convert to 0-based page index
        page_idx = page_number - 1
        
        if 0 <= page_idx < len(doc):
            page = doc[page_idx]
            
            # Create rectangle for redaction
            rect = fitz.Rect(
                bbox.get("x0", 0),
                bbox.get("y0", 0), 
                bbox.get("x1", 0),
                bbox.get("y1", 0)
            )
            
            # Add black redaction annotation
            redact_annot = page.add_redact_annot(rect)
            redact_annot.set_colors(fill=[0, 0, 0])  # Black fill
            redact_annot.update()
            
            redacted_count += 1
            print(f"   ✅ Applied redaction {i+1} on page {page_number}")
        else:
            print(f"   ❌ Invalid page number: {page_number}")
    
    # Apply all redactions per page (correct PyMuPDF API)
    try:
        # Apply redactions on each page that has them
        for page_num in range(len(doc)):
            page = doc[page_num]
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        
        print(f"   🎯 Applied {redacted_count} manual redactions")
        
        # Save manual redacted files in output/redacted/ directory
        base_name = os.path.basename(pdf_path).replace('.pdf', '')
        redacted_dir = os.path.join(os.getcwd(), "output", "redacted")
        os.makedirs(redacted_dir, exist_ok=True)
        manual_redacted_path = os.path.join(redacted_dir, f"{base_name}_MANUAL_REDACTED.pdf")
        
        print(f"   💾 Saving manual redacted file to: {manual_redacted_path}")
        doc.save(manual_redacted_path)
        doc.close()
        
        # Verify file was created
        if os.path.exists(manual_redacted_path):
            file_size = os.path.getsize(manual_redacted_path)
            print(f"   ✅ Manual redaction complete: {manual_redacted_path} ({file_size} bytes)")
        else:
            print(f"   ❌ ERROR: Manual redacted file was not created!")
        
        return manual_redacted_path
        
    except Exception as e:
        print(f"   ❌ ERROR in manual redaction: {str(e)}")
        doc.close()
        return pdf_path


def combine_ai_and_manual_redactions(ai_redacted_path: str, manual_rectangles: List[Dict[str, Any]]) -> str:
    """
    Apply manual redactions on top of AI-redacted PDF.
    This function takes the AI-redacted PDF as input and applies additional manual redactions.
    
    Args:
        ai_redacted_path: Path to the AI-redacted PDF (already has AI redactions applied)
        manual_rectangles: List of manual selection dictionaries with bbox and page_number
        
    Returns:
        Path to the final combined redacted PDF
    """
    if not manual_rectangles:
        print("🔧 COMBINING REDACTIONS: No manual rectangles, returning AI-redacted PDF as-is")
        return ai_redacted_path
    
    if not os.path.exists(ai_redacted_path):
        print(f"❌ ERROR: AI-redacted PDF not found: {ai_redacted_path}")
        return ai_redacted_path
    
    print(f"🔧 COMBINING REDACTIONS:")
    print(f"   📄 Input: AI-redacted PDF → {ai_redacted_path}")
    print(f"   📋 Applying {len(manual_rectangles)} additional manual redactions")
    print(f"   📍 Manual rectangles received:")
    for i, rect in enumerate(manual_rectangles):
        print(f"      [{i+1}] Page: {rect.get('page_number')}, Content: {rect.get('content')}, BBox: {rect.get('bbox')}")
    
    # Apply manual redactions on top of the already AI-redacted PDF
    temp_path = apply_manual_redactions(ai_redacted_path, manual_rectangles)
    
    # Create final filename in output directory indicating combined redactions
    ai_base_name = os.path.basename(ai_redacted_path).replace('.pdf', '')
    # Remove AI_REDACTED suffix if present
    if "_AI_REDACTED" in ai_base_name:
        clean_base = ai_base_name.replace("_AI_REDACTED", "")
    else:
        clean_base = ai_base_name.replace("_REDACTED", "").replace("_MANUAL_REDACTED", "")
    
    redacted_dir = os.path.join(os.getcwd(), "output", "redacted")
    os.makedirs(redacted_dir, exist_ok=True)
    combined_path = os.path.join(redacted_dir, f"{clean_base}_COMBINED_REDACTED.pdf")
    
    # Rename the temporary file to final name
    if os.path.exists(temp_path) and temp_path != combined_path:
        os.rename(temp_path, combined_path)
        print(f"   ✅ Output: Combined redacted PDF → {combined_path}")
        return combined_path
    
    print(f"   ✅ Output: Combined redacted PDF → {temp_path}")
    return temp_path
