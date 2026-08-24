"""Ollama chat transport. The only network in the stack.

Kept behind the ChatFn signature so core/agent.py never imports requests and
the whole conversation engine stays testable with a scripted model.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

DEFAULT_URL = "http://127.0.0.1:11434/api/chat"


class OllamaChat:
    def __init__(self, model: str, url: str = DEFAULT_URL, timeout: float = 120.0,
                 options: Optional[Dict[str, Any]] = None):
        self.model, self.url, self.timeout = model, url, timeout
        self.options = options or {"temperature": 0.4}

    def __call__(self, messages: List[Dict[str, Any]],
                 tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"model": self.model, "messages": messages,
                                "stream": False, "options": self.options}
        if tools:
            body["tools"] = tools
        r = requests.post(self.url, json=body, timeout=self.timeout)
        r.raise_for_status()
        return r.json().get("message", {}) or {}
