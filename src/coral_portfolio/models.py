"""Model clients. Coral uses models; it does not depend on any one of them."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Protocol


class ModelClient(Protocol):
    def complete(self, model_id: str, prompt: str) -> str: ...


class ModelUnavailable(RuntimeError):
    """The model could not be reached or returned something unusable."""


class MockModel:
    """Deterministic stand-in so tests and CI never need a real model."""

    def complete(self, model_id: str, prompt: str) -> str:
        memories = [
            line.removeprefix("Relevant memory: ")
            for line in prompt.splitlines()
            if line.startswith("Relevant memory: ")
        ]
        if not memories:
            return "I don't have a stored memory that answers that."
        return f"Based on what I have stored: {memories[0]}"


class OllamaModel:
    """Calls a local Ollama server. Nothing leaves the machine."""

    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(self, model_id: str, prompt: str) -> str:
        body = json.dumps({"model": model_id, "prompt": prompt, "stream": False}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ModelUnavailable(f"local model at {self.base_url} is unavailable: {exc}") from exc
        text = payload.get("response")
        if not isinstance(text, str) or not text.strip():
            raise ModelUnavailable("local model returned an empty response")
        return text.strip()
