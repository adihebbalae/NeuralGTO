"""
test_llm_client.py — Offline tests for the LLMClient abstraction.

Tests routing logic, error handling, and fallback behavior for both
Gemini and Ollama code paths. No real API calls are made.

Created: 2026-02-28
Task: T4.2b
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from poker_gpt.llm_client import LLMClient, LLMClientError


# ──────────────────────────────────────────────────────────
# Construction & Routing
# ──────────────────────────────────────────────────────────

class TestLLMClientConstruction:
    """Test that LLMClient initializes and routes correctly."""

    def test_default_provider_is_gemini(self):
        """Default provider should come from config (gemini)."""
        with patch("poker_gpt.llm_client.config") as mock_cfg:
            mock_cfg.LLM_PROVIDER = "gemini"
            mock_cfg.GEMINI_MODEL = "gemini-2.5-flash"
            mock_cfg.LOCAL_LLM_ENDPOINT = "http://localhost:11434/api/generate"
            mock_cfg.LOCAL_LLM_MODEL = "qwen2.5:14b"
            client = LLMClient()
            assert client.provider == "gemini"
            assert client.model == "gemini-2.5-flash"

    def test_explicit_local_provider(self):
        """Explicit provider='local' should use local config."""
        with patch("poker_gpt.llm_client.config") as mock_cfg:
            mock_cfg.LLM_PROVIDER = "gemini"  # default is gemini
            mock_cfg.LOCAL_LLM_MODEL = "qwen2.5:14b"
            mock_cfg.LOCAL_LLM_ENDPOINT = "http://localhost:11434/api/generate"
            client = LLMClient(provider="local")
            assert client.provider == "local"
            assert client.model == "qwen2.5:14b"

    def test_model_override(self):
        """Explicit model= should override config defaults."""
        with patch("poker_gpt.llm_client.config") as mock_cfg:
            mock_cfg.LLM_PROVIDER = "local"
            mock_cfg.LOCAL_LLM_MODEL = "qwen2.5:14b"
            mock_cfg.LOCAL_LLM_ENDPOINT = "http://localhost:11434/api/generate"
            client = LLMClient(model="phi4:latest")
            assert client.model == "phi4:latest"

    def test_endpoint_override(self):
        """Explicit endpoint= should override config default."""
        with patch("poker_gpt.llm_client.config") as mock_cfg:
            mock_cfg.LLM_PROVIDER = "local"
            mock_cfg.LOCAL_LLM_MODEL = "qwen2.5:14b"
            mock_cfg.LOCAL_LLM_ENDPOINT = "http://localhost:11434/api/generate"
            client = LLMClient(endpoint="http://custom:8080/api/generate")
            assert client.endpoint == "http://custom:8080/api/generate"

    def test_invalid_provider_raises(self):
        """Unknown provider should raise LLMClientError immediately."""
        with patch("poker_gpt.llm_client.config") as mock_cfg:
            mock_cfg.LLM_PROVIDER = "gemini"
            with pytest.raises(LLMClientError, match="Unknown LLM provider"):
                LLMClient(provider="openai")

    def test_repr_gemini(self):
        with patch("poker_gpt.llm_client.config") as mock_cfg:
            mock_cfg.LLM_PROVIDER = "gemini"
            mock_cfg.GEMINI_MODEL = "gemini-2.5-flash"
            client = LLMClient()
            r = repr(client)
            assert "gemini" in r
            assert "gemini-2.5-flash" in r

    def test_repr_local(self):
        with patch("poker_gpt.llm_client.config") as mock_cfg:
            mock_cfg.LLM_PROVIDER = "local"
            mock_cfg.LOCAL_LLM_MODEL = "qwen2.5:14b"
            mock_cfg.LOCAL_LLM_ENDPOINT = "http://localhost:11434/api/generate"
            client = LLMClient()
            r = repr(client)
            assert "local" in r
            assert "qwen2.5:14b" in r


# ──────────────────────────────────────────────────────────
# Gemini Path
# ──────────────────────────────────────────────────────────

class TestGeminiPath:
    """Test the Gemini code path with mocked SDK."""

    def _make_client(self, mock_cfg):
        mock_cfg.LLM_PROVIDER = "gemini"
        mock_cfg.GEMINI_MODEL = "gemini-2.5-flash"
        mock_cfg.GEMINI_API_KEY = "AIzaFAKEKEY123"
        return LLMClient()

    @patch("poker_gpt.llm_client.config")
    def test_gemini_success(self, mock_cfg):
        """Gemini path returns text on successful call."""
        client = self._make_client(mock_cfg)

        mock_response = MagicMock()
        mock_response.text = "Raise 75% pot with AKs on Kc-Qc-2h."

        mock_genai_client = MagicMock()
        mock_genai_client.models.generate_content.return_value = mock_response

        with patch.dict("sys.modules", {
            "google": MagicMock(),
            "google.genai": MagicMock(),
        }):
            with patch("poker_gpt.llm_client.LLMClient._generate_gemini") as mock_gen:
                mock_gen.return_value = "Raise 75% pot with AKs on Kc-Qc-2h."
                result = client.generate(
                    system_prompt="You are a poker advisor.",
                    user_prompt="What should I do with AKs?",
                )
                assert "Raise" in result

    @patch("poker_gpt.llm_client.config")
    def test_gemini_missing_key_raises(self, mock_cfg):
        """Missing GEMINI_API_KEY should raise LLMClientError."""
        mock_cfg.LLM_PROVIDER = "gemini"
        mock_cfg.GEMINI_MODEL = "gemini-2.5-flash"
        mock_cfg.GEMINI_API_KEY = ""
        client = LLMClient()

        with pytest.raises(LLMClientError, match="GEMINI_API_KEY not set"):
            client.generate(
                system_prompt="test",
                user_prompt="test",
            )

    @patch("poker_gpt.llm_client.config")
    def test_gemini_empty_response_raises(self, mock_cfg):
        """Empty Gemini response should raise LLMClientError."""
        client = self._make_client(mock_cfg)

        mock_response = MagicMock()
        mock_response.text = ""
        mock_response.__bool__ = lambda self: True  # response is truthy but text is empty

        mock_genai_client_inst = MagicMock()
        mock_genai_client_inst.models.generate_content.return_value = mock_response

        with patch("google.genai.Client", return_value=mock_genai_client_inst):
            with pytest.raises(LLMClientError, match="empty response"):
                client._generate_gemini("sys", "user", 0.1, 4096)

    @patch("poker_gpt.llm_client.config")
    def test_gemini_quota_error(self, mock_cfg):
        """Gemini 429 / quota error should produce clear error message."""
        client = self._make_client(mock_cfg)

        mock_genai_client_inst = MagicMock()
        mock_genai_client_inst.models.generate_content.side_effect = Exception(
            "429 Resource exhausted: quota exceeded"
        )

        with patch("google.genai.Client", return_value=mock_genai_client_inst):
            with pytest.raises(LLMClientError, match="quota"):
                client._generate_gemini("sys", "user", 0.1, 4096)


# ──────────────────────────────────────────────────────────
# Local (Ollama) Path
# ──────────────────────────────────────────────────────────

class TestLocalOllamaPath:
    """Test the Ollama HTTP code path with mocked httpx."""

    def _make_client(self, mock_cfg):
        mock_cfg.LLM_PROVIDER = "local"
        mock_cfg.LOCAL_LLM_MODEL = "qwen2.5:14b"
        mock_cfg.LOCAL_LLM_ENDPOINT = "http://localhost:11434/api/generate"
        return LLMClient()

    @patch("poker_gpt.llm_client.config")
    @patch("poker_gpt.llm_client.httpx.post")
    def test_ollama_success(self, mock_post, mock_cfg):
        """Successful Ollama call returns the 'response' field."""
        client = self._make_client(mock_cfg)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "model": "qwen2.5:14b",
            "response": "BET 75% pot. AKs has strong equity.",
            "done": True,
        }
        mock_post.return_value = mock_resp

        result = client.generate(
            system_prompt="You are a poker advisor.",
            user_prompt="AKs on Kc-Qc-2h, what to do?",
        )
        assert "BET" in result

        # Verify the POST payload
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["model"] == "qwen2.5:14b"
        assert payload["stream"] is False
        assert "system" in payload
        assert payload["system"] == "You are a poker advisor."

    @patch("poker_gpt.llm_client.config")
    @patch("poker_gpt.llm_client.httpx.post")
    def test_ollama_connection_error(self, mock_post, mock_cfg):
        """Connection refused should raise clear LLMClientError."""
        client = self._make_client(mock_cfg)
        mock_post.side_effect = __import__("httpx").ConnectError("Connection refused")

        with pytest.raises(LLMClientError, match="Cannot connect"):
            client.generate(system_prompt="test", user_prompt="test")

    @patch("poker_gpt.llm_client.config")
    @patch("poker_gpt.llm_client.httpx.post")
    def test_ollama_timeout(self, mock_post, mock_cfg):
        """Timeout should raise LLMClientError with helpful message."""
        client = self._make_client(mock_cfg)
        mock_post.side_effect = __import__("httpx").ReadTimeout("timed out")

        with pytest.raises(LLMClientError, match="timed out"):
            client.generate(system_prompt="test", user_prompt="test")

    @patch("poker_gpt.llm_client.config")
    @patch("poker_gpt.llm_client.httpx.post")
    def test_ollama_http_error_status(self, mock_post, mock_cfg):
        """Non-200 status from Ollama should raise with detail."""
        client = self._make_client(mock_cfg)
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"error": "model 'nonexistent' not found"}
        mock_post.return_value = mock_resp

        with pytest.raises(LLMClientError, match="HTTP 404"):
            client.generate(system_prompt="test", user_prompt="test")

    @patch("poker_gpt.llm_client.config")
    @patch("poker_gpt.llm_client.httpx.post")
    def test_ollama_empty_response(self, mock_post, mock_cfg):
        """Empty response field from Ollama should raise LLMClientError."""
        client = self._make_client(mock_cfg)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "model": "qwen2.5:14b",
            "response": "",
            "done": True,
        }
        mock_post.return_value = mock_resp

        with pytest.raises(LLMClientError, match="empty response"):
            client.generate(system_prompt="test", user_prompt="test")

    @patch("poker_gpt.llm_client.config")
    @patch("poker_gpt.llm_client.httpx.post")
    def test_ollama_non_json_response(self, mock_post, mock_cfg):
        """Non-JSON response from Ollama should raise LLMClientError."""
        client = self._make_client(mock_cfg)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("not JSON")
        mock_resp.text = "<html>Server Error</html>"
        mock_post.return_value = mock_resp

        with pytest.raises(LLMClientError, match="non-JSON"):
            client.generate(system_prompt="test", user_prompt="test")

    @patch("poker_gpt.llm_client.config")
    @patch("poker_gpt.llm_client.httpx.post")
    def test_ollama_payload_structure(self, mock_post, mock_cfg):
        """Verify the exact payload structure sent to Ollama."""
        client = self._make_client(mock_cfg)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "ok", "done": True}
        mock_post.return_value = mock_resp

        client.generate(
            system_prompt="System instructions here",
            user_prompt="User query here",
            temperature=0.5,
            max_tokens=2048,
        )

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload == {
            "model": "qwen2.5:14b",
            "prompt": "User query here",
            "system": "System instructions here",
            "stream": False,
            "options": {
                "temperature": 0.5,
                "num_predict": 2048,
            },
        }


# ──────────────────────────────────────────────────────────
# Routing Integration
# ──────────────────────────────────────────────────────────

class TestRouting:
    """Test that generate() dispatches to the correct backend."""

    @patch("poker_gpt.llm_client.config")
    def test_gemini_routing(self, mock_cfg):
        """Provider=gemini routes to _generate_gemini."""
        mock_cfg.LLM_PROVIDER = "gemini"
        mock_cfg.GEMINI_MODEL = "gemini-2.5-flash"
        mock_cfg.GEMINI_API_KEY = "AIzaFAKE"
        client = LLMClient()

        with patch.object(client, "_generate_gemini", return_value="gemini response") as mock_g:
            result = client.generate("sys", "user")
            mock_g.assert_called_once()
            assert result == "gemini response"

    @patch("poker_gpt.llm_client.config")
    def test_local_routing(self, mock_cfg):
        """Provider=local routes to _generate_local."""
        mock_cfg.LLM_PROVIDER = "local"
        mock_cfg.LOCAL_LLM_MODEL = "qwen2.5:14b"
        mock_cfg.LOCAL_LLM_ENDPOINT = "http://localhost:11434/api/generate"
        client = LLMClient()

        with patch.object(client, "_generate_local", return_value="local response") as mock_l:
            result = client.generate("sys", "user")
            mock_l.assert_called_once()
            assert result == "local response"
