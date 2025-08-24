from __future__ import annotations

from typing import TypedDict, Literal, List, Dict, Optional
from pydantic import Field


# Coordinate system: PyMuPDF points (72 points = 1 inch)
class BBox(TypedDict):
    x0: float
    y0: float
    x1: float
    y1: float


class PdfElement(TypedDict):
    element_id: int
    page_number: int
    content: str
    bbox: BBox


class SensitiveItem(TypedDict):
    """Output from detector node with content and coordinates"""
    page_number: int
    content: str
    reason: str
    bbox: BBox


class SanitizerState(TypedDict, total=False):
    # Core inputs
    user_prompt: str
    pdf_path: str

    # Conceptual guidance (cumulative from orchestrator and evaluator feedback)
    sensitive_data_description: List[str]
    search_query: Optional[str]

    # Dual OCR outputs (NEW architecture)
    page_level_pdf_elements: List[PdfElement]  # Page-level content for LLM analysis
    word_level_pdf_elements: List[PdfElement]  # Word-level coordinates for mapping

    # Final detection output (from detector node dual LLM)
    sensitive_data: List[SensitiveItem]

    # Loop control for evaluator
    evaluator_cycles: int
    max_evaluator_cycles: int  # Default 3

    # Artifacts
    preview_pdf_path: str
    final_pdf_path: str

    # Routing / control
    next_node: Optional[str]
    user_approval: Optional[Literal["Yes", "No"]]

    # Optional context for search
    industry: Optional[str]
    jurisdiction: Optional[str]
    regulations: List[str]
