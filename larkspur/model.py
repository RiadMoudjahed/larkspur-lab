"""Model backends: any OpenAI-compatible chat endpoint, or a scripted model for tests."""

import json
import os
import urllib.request

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "qwen2.5:7b-instruct"


class OpenAICompatibleModel:
    def __init__(self, base_url, model, api_key=None, timeout=120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_env(cls):
        return cls(
            os.environ.get("LARKSPUR_BASE_URL", DEFAULT_BASE_URL),
            os.environ.get("LARKSPUR_MODEL", DEFAULT_MODEL),
            os.environ.get("LARKSPUR_API_KEY"),
        )

    def complete(self, messages, tools):
        body = {
            "model": self.model,
            "messages": messages,
            "tools": [{"type": "function", "function": tool} for tool in tools],
            "temperature": 0.2,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.load(response)
        message = data["choices"][0]["message"]
        out = {"role": "assistant", "content": message.get("content")}
        if message.get("tool_calls"):
            out["tool_calls"] = message["tool_calls"]
        return out


class ScriptedModel:
    """Returns a fixed sequence of replies. A step is a string (final answer)
    or a list of (tool_name, args) pairs. Records every context it was shown."""

    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    def complete(self, messages, tools):
        self.seen.append([dict(message) for message in messages])
        step = self.script.pop(0) if self.script else "Done."
        if isinstance(step, str):
            return {"role": "assistant", "content": step}
        calls = [
            {
                "id": f"call_{len(self.seen)}_{i}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
            for i, (name, args) in enumerate(step)
        ]
        return {"role": "assistant", "content": None, "tool_calls": calls}
