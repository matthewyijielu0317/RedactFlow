from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple
import os

from .model import AzureLLM

class Searcher:
    """Regulation searcher that can leverage Tavily and LLM summarization."""

    def __init__(self, use_ai: bool = True) -> None:
        self.use_ai = use_ai
        self._tavily_key: Optional[str] = os.getenv("TAVILY_KEY")

        self._authorities: Dict[str, List[Tuple[str, str]]] = {
            "US": [
                ("NIST (PII Guidance)", "https://www.nist.gov/"),
                ("FTC", "https://www.ftc.gov/"),
                ("HHS (HIPAA)", "https://www.hhs.gov/hipaa/index.html"),
            ],
            "EU": [
                ("EU GDPR", "https://gdpr.eu/"),
                ("EDPB", "https://edpb.europa.eu/"),
            ],
            "CA": [
                ("Office of the Privacy Commissioner of Canada", "https://www.priv.gc.ca/"),
            ],
            "CN": [
                ("National People's Congress", "https://www.npc.gov.cn/"),
                ("Cyberspace Administration of China", "https://www.cac.gov.cn/"),
                ("People's Bank of China", "https://www.pbc.gov.cn/"),
                ("CBIRC", "https://www.cbirc.gov.cn/"),
                ("CSRC", "https://www.csrc.gov.cn/"),
            ],
        }

        self._allow_domains: Dict[str, List[str]] = {
            "US": ["hhs.gov", "ftc.gov", "nist.gov"],
            "EU": ["gdpr.eu", "edpb.europa.eu", "europa.eu"],
            "CA": ["priv.gc.ca"],
            "CN": ["npc.gov.cn", "cac.gov.cn", "pbc.gov.cn", "cbirc.gov.cn", "csrc.gov.cn"],
        }

    def search(self, query: str, industry: Optional[str], jurisdiction: Optional[str]) -> Dict[str, Any]:
        sources = self._find_sources(query, industry, jurisdiction)
        additions = self._summarize_with_llm(query, industry, jurisdiction, sources) if self.use_ai else []
        return {"sources": [{"name": n, "url": u} for n, u in sources], "descriptions": additions}

    def _find_sources(self, query: str, industry: Optional[str], jurisdiction: Optional[str]) -> List[Tuple[str, str]]:
        juris = (jurisdiction or "").upper()
        if self.use_ai and self._tavily_key:
            try:
                from tavily import TavilyClient  # type: ignore

                client = TavilyClient(api_key=self._tavily_key)
                include_domains = self._allow_domains.get(juris, [])
                res = client.search(query, search_depth="advanced", include_domains=include_domains or None, max_results=5)
                results = res.get("results", []) if isinstance(res, dict) else []
                out: List[Tuple[str, str]] = []
                seen = set()
                for r in results:
                    url = str(r.get("url") or "").strip()
                    title = str(r.get("title") or url or "Source").strip()
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    out.append((title, url))
                if out:
                    return out
            except Exception:
                pass
        # fallback to authorities list
        base = self._authorities.get(juris, [])
        seen = set()
        out: List[Tuple[str, str]] = []
        for name, url in base:
            if url not in seen:
                seen.add(url)
                out.append((name, url))
        return out[:5]

    def _summarize_with_llm(
        self, query: str, industry: Optional[str], jurisdiction: Optional[str], sources: List[Tuple[str, str]]
    ) -> List[str]:
        try:
            from pydantic import BaseModel
        except Exception:
            return []

        citations_text = "\n".join([f"- {name}: {url}" for name, url in sources])

        class OutSchema(BaseModel):
            sensitive_descriptions: List[str]

        instruction = (
            "You are a compliance analyst. Given a search query, optional industry/jurisdiction, and sources,"
            " produce a concise list of sensitive data descriptions (categories or rules) to guide detection."
        )
        user_prompt = (
            f"Query: {query}\nIndustry: {industry or ''}\nJurisdiction: {jurisdiction or ''}\nSources:\n{citations_text}"
        )
        try:
            llm = AzureLLM()
            res: OutSchema = llm.create_structured_response(OutSchema, instruction, user_prompt)
            return [s.strip() for s in (res.sensitive_descriptions or []) if s and s.strip()]
        except Exception:
            return []


def run_searcher(state: Dict[str, Any]) -> Dict[str, Any]:
    query = str(state.get("search_query") or "").strip()
    if not query:
        return state
    industry = state.get("industry")
    jurisdiction = state.get("jurisdiction")
    try:
        searcher = Searcher(use_ai=True)
        result = searcher.search(query=query, industry=industry, jurisdiction=jurisdiction)
        desc = result.get("descriptions", [])
        if desc:
            state.setdefault("sensitive_data_description", [])
            state["sensitive_data_description"] = list(
                dict.fromkeys((state.get("sensitive_data_description") or []) + desc)
            )
    except Exception:
        pass
    # Clear the query after processing
    state.pop("search_query", None)
    return state


