# -*- coding: utf-8 -*-
"""Transport abstraction so the module is not coupled to a single AI vendor.

Each transport speaks the provider's native tool-use protocol but returns a
normalized result to the orchestrator:

    {
      "text": "<assistant natural language, if any>",
      "tool_calls": [{"id": ..., "name": ..., "input": {...}}, ...],
      "raw_assistant": <provider-native assistant turn to echo back>,
      "stop": True/False,   # True when the model produced a final answer
    }
"""
import copy
import json
import logging

from .exceptions import ProviderError

_logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


DEFAULT_ENDPOINTS = {
    "anthropic": "https://api.anthropic.com/v1/messages",
    "openai": "https://api.openai.com/v1/chat/completions",
}


def get_transport(provider):
    """provider is an ai.provider record."""
    if requests is None:
        raise ProviderError("The 'requests' Python library is required.")
    if provider.provider_type == "anthropic":
        return AnthropicTransport(provider)
    if provider.provider_type == "openai":
        return OpenAiTransport(provider)
    if provider.provider_type == "gemini":
        return GeminiTransport(provider)
    raise ProviderError("Unsupported provider type: %s" % provider.provider_type)


class BaseTransport:
    def __init__(self, provider):
        self.provider = provider
        self.endpoint = provider.api_base_url or DEFAULT_ENDPOINTS.get(
            provider.provider_type, ""
        )
        self.timeout = provider.request_timeout or 60

    def send(self, system, messages, tools):
        raise NotImplementedError


class AnthropicTransport(BaseTransport):
    def send(self, system, messages, tools):
        headers = {
            "x-api-key": self.provider.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self.provider.model,
            "max_tokens": self.provider.max_tokens or 1024,
            "temperature": self.provider.temperature or 0.0,
            "system": system,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools
        data = self._post(headers, body)

        text_parts, tool_calls = [], []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input") or {},
                })
        return {
            "text": "\n".join(p for p in text_parts if p).strip(),
            "tool_calls": tool_calls,
            "raw_assistant": {"role": "assistant", "content": data.get("content", [])},
            "stop": data.get("stop_reason") != "tool_use",
        }

    @staticmethod
    def format_tool_results(results):
        """results: list of (tool_use_id, content_dict)."""
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tid,
                    "content": json.dumps(content, default=str),
                }
                for tid, content in results
            ],
        }

    def _post(self, headers, body):
        try:
            resp = requests.post(
                self.endpoint, headers=headers, json=body, timeout=self.timeout
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Anthropic transport error: %s", exc)
            raise ProviderError("The AI service is unreachable.")
        if resp.status_code >= 400:
            _logger.warning("Anthropic API %s: %s", resp.status_code, resp.text[:500])
            raise ProviderError("The AI service returned an error.")
        return resp.json()


class OpenAiTransport(BaseTransport):
    """OpenAI-compatible Chat Completions (also covers many self-hosted gateways)."""

    def send(self, system, messages, tools):
        headers = {
            "Authorization": "Bearer %s" % self.provider.api_key,
            "Content-Type": "application/json",
        }
        oai_messages = [{"role": "system", "content": system}] + messages
        body = {
            "model": self.provider.model,
            "temperature": self.provider.temperature or 0.0,
            "max_tokens": self.provider.max_tokens or 1024,
            "messages": oai_messages,
        }
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"],
                    },
                }
                for t in tools
            ]
        data = self._post(headers, body)
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        tool_calls = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            tool_calls.append({"id": tc.get("id"), "name": fn.get("name"), "input": args})
        return {
            "text": (message.get("content") or "").strip(),
            "tool_calls": tool_calls,
            "raw_assistant": message,
            "stop": choice.get("finish_reason") != "tool_calls",
        }

    @staticmethod
    def format_tool_results(results):
        # OpenAI expects one message per tool result.
        return [
            {
                "role": "tool",
                "tool_call_id": tid,
                "content": json.dumps(content, default=str),
            }
            for tid, content in results
        ]

    def _post(self, headers, body):
        try:
            resp = requests.post(
                self.endpoint, headers=headers, json=body, timeout=self.timeout
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("OpenAI transport error: %s", exc)
            raise ProviderError("The AI service is unreachable.")
        if resp.status_code >= 400:
            _logger.warning("OpenAI API %s: %s", resp.status_code, resp.text[:500])
            raise ProviderError("The AI service returned an error.")
        return resp.json()


GEMINI_DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiTransport(BaseTransport):
    """Google Gemini (generateContent) with native function calling.

    Gemini uses roles 'user' / 'model' and returns tool requests as
    `functionCall` parts; tool results are sent back as `functionResponse`
    parts. Gemini's schema validation is strict, so heterogeneous arrays (the
    Odoo `domain`) are declared as a JSON-encoded string and parsed back here.
    """

    def __init__(self, provider):
        super().__init__(provider)
        self.base_url = (provider.api_base_url or GEMINI_DEFAULT_BASE).rstrip("/")

    def send(self, system, messages, tools):
        url = "%s/models/%s:generateContent?key=%s" % (
            self.base_url, self.provider.model, self.provider.api_key
        )
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": self._to_contents(messages),
            "generationConfig": {
                "temperature": self.provider.temperature or 0.0,
                "maxOutputTokens": self.provider.max_tokens or 1024,
            },
        }
        decls = self._function_declarations(tools)
        if decls:
            body["tools"] = [{"functionDeclarations": decls}]

        data = self._post(url, body)
        candidates = data.get("candidates") or [{}]
        content = candidates[0].get("content", {}) or {}
        parts = content.get("parts", []) or []

        text_parts, tool_calls = [], []
        for p in parts:
            if "text" in p:
                text_parts.append(p.get("text", ""))
            elif "functionCall" in p:
                fc = p["functionCall"]
                tool_calls.append({
                    "id": fc.get("name"),          # Gemini matches results by name
                    "name": fc.get("name"),
                    "input": self._normalize_args(fc.get("args") or {}),
                })
        return {
            "text": "\n".join(t for t in text_parts if t).strip(),
            "tool_calls": tool_calls,
            "raw_assistant": {"role": "model", "parts": parts},
            "stop": not tool_calls,
        }

    @staticmethod
    def format_tool_results(results):
        return {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": name,
                        "response": content if isinstance(content, dict)
                        else {"result": content},
                    }
                }
                for name, content in results
            ],
        }

    # -- helpers --------------------------------------------------------
    def _to_contents(self, messages):
        """Translate the orchestrator's message list into Gemini `contents`.
        Native turns (dicts already carrying `parts`) pass through unchanged;
        plain {role, content} turns are converted."""
        contents = []
        for m in messages:
            if isinstance(m, dict) and "parts" in m:
                contents.append(m)
                continue
            role = m.get("role")
            g_role = "model" if role == "assistant" else "user"
            contents.append({"role": g_role, "parts": [{"text": m.get("content") or ""}]})
        return contents

    def _function_declarations(self, tools):
        decls = []
        for t in tools:
            schema = self._sanitize_schema(t.get("input_schema") or {})
            decl = {"name": t["name"], "description": t["description"]}
            if schema.get("properties"):
                decl["parameters"] = schema
            decls.append(decl)
        return decls

    @staticmethod
    def _sanitize_schema(schema):
        """Gemini rejects untyped arrays; declare those as JSON-string params."""
        schema = copy.deepcopy(schema)
        props = schema.get("properties") or {}
        for key, spec in list(props.items()):
            if spec.get("type") == "array" and not (spec.get("items") or {}).get("type"):
                desc = (spec.get("description", "") +
                        " (pass as a JSON-encoded array string)").strip()
                props[key] = {"type": "string", "description": desc}
        return schema

    @staticmethod
    def _normalize_args(args):
        """Parse the JSON-string `domain` back into a list for the engine."""
        if isinstance(args, dict) and isinstance(args.get("domain"), str):
            try:
                args["domain"] = json.loads(args["domain"])
            except ValueError:
                args["domain"] = []
        return args

    def _post(self, url, body):
        try:
            resp = requests.post(
                url, headers={"Content-Type": "application/json"},
                json=body, timeout=self.timeout,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Gemini transport error: %s", exc)
            raise ProviderError("The AI service is unreachable.")
        if resp.status_code >= 400:
            # Never log the URL (it carries the API key); log status + body only.
            _logger.warning("Gemini API %s: %s", resp.status_code, resp.text[:500])
            raise ProviderError("The AI service returned an error.")
        return resp.json()
