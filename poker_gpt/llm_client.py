"""
llm_client.py — Thin LLM abstraction layer for research experiments.

Routes LLM calls to either Google Gemini (via google-genai SDK) or a local
model (via Ollama-compatible HTTP endpoint). Used by research modules
(llm_pruner.py, experiment harnesses) — NOT by the main product pipeline
(nl_parser.py, nl_advisor.py). Those will migrate in T3.4.

Created: 2026-02-28
Task: T4.2b — Ollama local LLM integration for ablation experiments

DOCUMENTATION:
- Set LLM_PROVIDER="gemini" (default) or LLM_PROVIDER="local" in .env
- For local: install Ollama (https://ollama.com), run `ollama pull qwen2.5:14b`
- Config: LOCAL_LLM_ENDPOINT, LOCAL_LLM_MODEL in config.py / .env
- Usage:
    client = LLMClient()                    # uses config.LLM_PROVIDER
    client = LLMClient(provider="local")    # explicit override
    result = client.generate(system_prompt="...", user_prompt="...")
"""

from __future__ import annotations

from typing import Optional

import httpx

from poker_gpt import config


class LLMClientError(Exception):
    """Raised when an LLM call fails (network, API, or response parsing error)."""
    pass


class LLMClient:
    """Unified LLM client that routes to Gemini or a local Ollama-compatible endpoint.

    Args:
        provider: "gemini" or "local". Defaults to config.LLM_PROVIDER.
        model: Model name override. Defaults to config value for the chosen provider.
        endpoint: Local endpoint override. Only used when provider="local".
        timeout: Request timeout in seconds. Default 120s (local models can be slow).
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        endpoint: Optional[str] = None,
        timeout: float = 120.0,
    ) -> None:
        self.provider = provider or config.LLM_PROVIDER
        if self.provider not in ("gemini", "local"):
            raise LLMClientError(
                f"Unknown LLM provider: {self.provider!r}. "
                "Expected 'gemini' or 'local'."
            )

        if self.provider == "gemini":
            self.model = model or config.GEMINI_MODEL
        else:
            self.model = model or config.LOCAL_LLM_MODEL

        self.endpoint = endpoint or config.LOCAL_LLM_ENDPOINT
        self.timeout = timeout

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a completion from the configured LLM.

        Args:
            system_prompt: System-level instruction text.
            user_prompt: User message / query text.
            temperature: Sampling temperature (0.0–1.0).
            max_tokens: Maximum output tokens.

        Returns:
            The generated text response.

        Raises:
            LLMClientError: On any failure (network, API, empty response).
        """
        if self.provider == "gemini":
            return self._generate_gemini(
                system_prompt, user_prompt, temperature, max_tokens
            )
        else:
            return self._generate_local(
                system_prompt, user_prompt, temperature, max_tokens
            )

    def _generate_gemini(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call Google Gemini via the google-genai SDK.

        Mirrors the call pattern from nl_advisor.py but does not modify that module.
        """
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise LLMClientError(
                "google-genai package not installed. "
                "Install with: pip install google-genai"
            ) from e

        if not config.GEMINI_API_KEY:
            raise LLMClientError(
                "GEMINI_API_KEY not set. Add it to your .env file."
            )

        try:
            client = genai.Client(api_key=config.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )
        except Exception as e:
            error_msg = str(e)
            if "quota" in error_msg.lower() or "429" in error_msg:
                raise LLMClientError(
                    "Gemini API quota exceeded. Check your billing at "
                    "https://console.cloud.google.com/billing"
                ) from e
            raise LLMClientError(f"Gemini API call failed: {e}") from e

        if not response or not response.text:
            raise LLMClientError("Gemini returned an empty response.")

        return response.text

    def _generate_local(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call a local Ollama-compatible endpoint via HTTP POST.

        Ollama API docs: https://github.com/ollama/ollama/blob/main/docs/api.md
        """
        # Ollama's /api/generate accepts a single "prompt" field.
        # Prepend system prompt as a system block for models that support it.
        payload = {
            "model": self.model,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            resp = httpx.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout,
            )
        except httpx.ConnectError as e:
            raise LLMClientError(
                f"Cannot connect to local LLM at {self.endpoint}. "
                "Is Ollama running? Start with: ollama serve"
            ) from e
        except httpx.TimeoutException as e:
            raise LLMClientError(
                f"Local LLM request timed out after {self.timeout}s. "
                "The model may be loading or the prompt may be too large."
            ) from e
        except httpx.HTTPError as e:
            raise LLMClientError(
                f"HTTP error calling local LLM: {e}"
            ) from e

        if resp.status_code != 200:
            # Ollama returns JSON error bodies
            try:
                error_detail = resp.json().get("error", resp.text)
            except Exception:
                error_detail = resp.text
            raise LLMClientError(
                f"Local LLM returned HTTP {resp.status_code}: {error_detail}"
            )

        try:
            data = resp.json()
        except Exception as e:
            raise LLMClientError(
                f"Local LLM returned non-JSON response: {resp.text[:200]}"
            ) from e

        text = data.get("response", "")
        if not text:
            raise LLMClientError(
                "Local LLM returned an empty response. "
                f"Full response body: {data}"
            )

        return text

    def __repr__(self) -> str:
        if self.provider == "local":
            return f"LLMClient(provider='local', model='{self.model}', endpoint='{self.endpoint}')"
        return f"LLMClient(provider='gemini', model='{self.model}')"
