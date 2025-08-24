from __future__ import annotations

import os
from typing import Any, Type

# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class AzureLLM:
    """Azure OpenAI client for chat and structured outputs.

    Environment:
    - AZURE_ENDPOINT: Azure OpenAI endpoint
    - OPENAI_API_KEY: Azure OpenAI API key (same secret as server/agent `GPT_4_1_SECRET_KEY`)
    - AZURE_API_VERSION (optional): defaults to 2025-03-01-preview
    - OPENAI_DEPLOYMENT (optional): Azure deployment name; defaults to gpt-4o
    """

    def __init__(self, model: str | None = None) -> None:
        # Prefer a dedicated Azure OpenAI endpoint if provided
        self.azure_endpoint = (
            os.getenv("AZURE_OPENAI_ENDPOINT")
            or os.getenv("OPENAI_API_BASE")
            or os.getenv("AZURE_ENDPOINT")
        )
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.azure_api_version = os.getenv("AZURE_API_VERSION", "2025-03-01-preview")
        self.model = model or os.getenv("OPENAI_DEPLOYMENT", "gpt-4o")
        if not self.azure_endpoint or not self.openai_api_key:
            raise RuntimeError(
                "Azure OpenAI not configured. Set OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT (or OPENAI_API_BASE)."
            )

        # Azure OpenAI SDK client (for free-form chat)
        from openai import AzureOpenAI

        self.client = AzureOpenAI(
            api_version=self.azure_api_version,
            azure_endpoint=self.azure_endpoint,
            api_key=self.openai_api_key,
        )

    def create_instructed_response(self, instruction: str, text: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": instruction},
                {"role": "user", "content": text},
            ],
            temperature=0,
        )
        return response.choices[0].message.content or ""

    def create_structured_response(self, schema_cls: Type[Any], instruction: str, text: str) -> Any:
        """Return a Pydantic model instance using LangChain structured output (Azure)."""
        try:
            from langchain_openai import AzureChatOpenAI  # type: ignore
        except Exception as exc:
            raise ImportError("langchain-openai is required for structured output") from exc

        llm = AzureChatOpenAI(
            azure_endpoint=self.azure_endpoint,
            api_key=self.openai_api_key,
            api_version=self.azure_api_version,
            azure_deployment=self.model,
            temperature=0,
        )
        structured_llm = llm.with_structured_output(schema_cls)  # type: ignore[attr-defined]
        prompt = f"{instruction}\n\n{text}"
        return structured_llm.invoke(prompt)
