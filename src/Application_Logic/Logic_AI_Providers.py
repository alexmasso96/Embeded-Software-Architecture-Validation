"""
AI Provider Adapters
====================
A small, uniform interface over several AI backends so the rest of the app can
ask for a completion without caring which provider/model is behind it.

Providers (see AI_INTEGRATION_PLAN.md, Phase 2):
  * CopilotProvider  — GitHub Copilot via OAuth device-flow + the (undocumented)
                       copilot_internal token exchange. Ported faithfully from a
                       known-working reference implementation. Masquerades as the
                       VS Code Copilot Chat client (required to pass the
                       "approved clients" check).
  * AnthropicProvider — Claude direct, by API key (api.anthropic.com).
  * OpenAIProvider    — GPT direct, by API key (api.openai.com).
  * GeminiProvider    — Google Gemini, by API key (generativelanguage.googleapis).

Secrets come from Logic_AI_Credentials (encrypted per-user store) — never from
the project DB.

Phase 2 scope: NON-streaming generate (stream=False). SSE streaming is added in
Phase 5. The request-building and response-parsing are split into pure methods
so they can be unit-tested without any network access.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import requests

from . import Logic_AI_Credentials as creds

# ---------------------------------------------------------------------------
# Endpoints / constants
# ---------------------------------------------------------------------------

DEVICE_CODE_URL = "https://github.com/login/device/code"
OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"
COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
COPILOT_API_BASE_DEFAULT = "https://api.githubcopilot.com"

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
ANTHROPIC_VERSION = "2023-06-01"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Substrings identifying non-chat models to hide from the picker.
_NON_CHAT = ("embedding", "whisper", "tts", "dall", "audio", "image",
             "moderation", "realtime", "transcribe", "search",
             "trajectory", "compaction")

# Per-model context windows (Phase 12, locked decision #5: conservative default).
DEFAULT_CONTEXT_WINDOW = 128_000
MODEL_CONTEXT_WINDOWS = {
    "gpt-4o": 128_000, "gpt-4o-mini": 128_000, "gpt-4.1": 1_000_000,
    "o3-mini": 200_000, "o1": 200_000,
    "claude-opus-4": 200_000, "claude-sonnet-4": 200_000,
    "claude-3-5-sonnet-latest": 200_000, "claude-3-5-haiku-latest": 200_000,
    "gemini-1.5-pro": 2_000_000, "gemini-1.5-flash": 1_000_000,
    "gemini-2.0-flash": 1_000_000,
}


def context_window_for(model: str) -> int:
    """Best-effort context window (tokens) for a model id; conservative default
    for unknown ids. Substring match tolerates dated/snapshot suffixes."""
    if model in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model]
    low = model.lower()
    for key, win in MODEL_CONTEXT_WINDOWS.items():
        if low.startswith(key.lower()):
            return win
    return DEFAULT_CONTEXT_WINDOW


# ---------------------------------------------------------------------------
# Tool / function-calling model (Phase 9)
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict = field(default_factory=lambda: {"type": "object", "properties": {}})


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict = field(default_factory=dict)


# Well-known VS Code / Copilot-Chat OAuth app client id (same one editor plugins
# and community tools use; not org-specific).
GITHUB_CLIENT_ID = "Iv1.b507a08c87ecfe98"

# Editor masquerade headers required by the copilot_internal endpoint.
_VSCODE_HEADERS = {
    "Editor-Version": "vscode/1.100.0",
    "Editor-Plugin-Version": "copilot-chat/0.25.0",
    "User-Agent": "GitHubCopilotChat/0.25.0",
}

_DEFAULT_MAX_TOKENS = 16384
_DEFAULT_TEMPERATURE = 0.2
_HTTP_TIMEOUT = 120


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class AIError(Exception):
    """Base class for provider errors."""


class AIAuthError(AIError):
    """Authentication / authorization failure (not signed in, bad key, 401/403)."""


class AIGenerationError(AIError):
    """The model request failed or returned no usable content."""


class AIStopped(AIError):
    """Generation aborted by the caller's stop_check."""


# A unified message is {"role": "system"|"user"|"assistant", "content": str}.
Message = Dict[str, str]
StreamCb = Optional[Callable[[str], None]]
StopCheck = Optional[Callable[[], bool]]


def _split_system(messages: List[Message], system_prompt: Optional[str]) -> Tuple[str, List[Message]]:
    """Separate a leading/explicit system prompt from the conversational turns.

    Non-system messages are passed through VERBATIM (not reconstructed) so that
    provider-native keys added during a tool loop — OpenAI `tool_calls`/
    `tool_call_id`, Anthropic content-block arrays, Gemini `parts` — survive into
    build_request on later turns.
    """
    sys_parts: List[str] = []
    if system_prompt:
        sys_parts.append(system_prompt)
    convo: List[Message] = []
    for m in messages:
        if m.get("role") == "system":
            if m.get("content"):
                sys_parts.append(m["content"])
        else:
            convo.append(m)
    return "\n\n".join(sys_parts), convo


# ---------------------------------------------------------------------------
# Base provider
# ---------------------------------------------------------------------------

class AIProvider:
    id: str = ""
    label: str = ""
    # Static fallback model catalogue; providers may override list_models() to
    # discover dynamically.
    _models: List[Dict] = []

    def is_configured(self) -> bool:
        raise NotImplementedError

    def list_models(self) -> List[Dict]:
        """Static fallback catalogue (instant, no network)."""
        return list(self._models)

    def discover_models(self) -> List[Dict]:
        """Query the provider for the models actually available to this account.

        Returns a list of {id, name, context_tokens}. Returns [] on any failure
        so callers can fall back to list_models(). Overridden per provider.
        """
        return []

    # --- tool / function calling (Phase 9) ---
    # True only for providers verified to accept native function-calling. Copilot
    # stays False and is driven via the text-fallback grammar (locked decision #2).
    SUPPORTS_TOOLS: bool = False

    def build_tools_param(self, tools: "List[Tool]"):
        """Provider-native representation of the tool list (or None)."""
        return None

    def parse_tool_calls(self, data: Dict) -> "List[ToolCall]":
        """Extract tool calls from a raw response dict (default: none)."""
        return []

    def format_tool_results(self, results: "Dict[str, tuple]") -> List[Dict]:
        """Turn {tool_call_id: (name, output)} into the provider's follow-up
        message(s) (default: none)."""
        return []

    def capture_assistant_turn(self, data: Dict) -> Dict:
        """The assistant message to replay before tool results. Default flattens
        to text; providers needing verbatim content blocks (Anthropic) override."""
        return {"role": "assistant", "content": self.parse_response(data)}

    # --- pure, unit-testable ---
    def build_request(self, messages: List[Message], model: str,
                      system_prompt: Optional[str], tools_param=None) -> Tuple[str, Dict, Dict]:
        """Return (url, headers, json_body). No network."""
        raise NotImplementedError

    def parse_response(self, data: Dict) -> str:
        """Extract assistant text from a decoded JSON response. No network."""
        raise NotImplementedError

    # --- network ---
    def _post_and_json(self, url: str, headers: Dict, body: Dict,
                       stop_check: StopCheck = None) -> Dict:
        """Shared POST + error-handling, returning the raw decoded dict. Used by
        both generate() and the agentic loop (which needs the raw response that
        generate() discards)."""
        if stop_check and stop_check():
            raise AIStopped("Stopped before request.")
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=_HTTP_TIMEOUT)
        except requests.RequestException as e:
            raise AIGenerationError(f"Network error contacting {self.label}: {e}")
        self._raise_for_status(resp)
        try:
            return resp.json()
        except ValueError:
            raise AIGenerationError(f"{self.label} returned a non-JSON response.")

    def generate(self, messages: List[Message], model: str,
                 system_prompt: Optional[str] = None,
                 stream_cb: StreamCb = None, stop_check: StopCheck = None) -> str:
        url, headers, body = self.build_request(messages, model, system_prompt)
        data = self._post_and_json(url, headers, body, stop_check=stop_check)
        text = self.parse_response(data)
        if not text:
            raise AIGenerationError(f"{self.label} returned no content.")
        if stream_cb:
            stream_cb(text)
        return text

    def _raise_for_status(self, resp) -> None:
        if resp.status_code in (401, 403):
            raise AIAuthError(
                f"{self.label}: authentication failed (HTTP {resp.status_code}). "
                f"Check your credentials / subscription."
            )
        if resp.status_code >= 400:
            snippet = (resp.text or "")[:300]
            raise AIGenerationError(f"{self.label}: HTTP {resp.status_code}. {snippet}")


# ---------------------------------------------------------------------------
# Copilot
# ---------------------------------------------------------------------------

class CopilotProvider(AIProvider):
    id = "copilot"
    label = "GitHub Copilot"
    _models = [
        {"id": "claude-opus-4", "name": "Claude Opus 4 (Copilot)", "context_tokens": 32000},
        {"id": "claude-sonnet-4", "name": "Claude Sonnet 4 (Copilot)", "context_tokens": 32000},
        {"id": "gpt-4.1", "name": "GPT-4.1 (Copilot)", "context_tokens": 32000},
        {"id": "gpt-4o", "name": "GPT-4o (Copilot)", "context_tokens": 32000},
        {"id": "gpt-4o-mini", "name": "GPT-4o mini (Copilot)", "context_tokens": 16000},
        {"id": "o3-mini", "name": "o3-mini (Copilot)", "context_tokens": 16000},
    ]

    # cached short-lived copilot token
    _cp_token: str = ""
    _cp_expires: float = 0
    _cp_api_base: str = COPILOT_API_BASE_DEFAULT

    def is_configured(self) -> bool:
        return bool(creds.get_copilot_oauth_token())

    # --- device flow ---
    @staticmethod
    def start_device_flow() -> Dict:
        resp = requests.post(
            DEVICE_CODE_URL,
            headers={"Accept": "application/json"},
            data={"client_id": GITHUB_CLIENT_ID, "scope": "copilot"},
            timeout=15,
        )
        if resp.status_code != 200:
            raise AIAuthError(f"Failed to start device flow (HTTP {resp.status_code}).")
        data = resp.json()
        if "device_code" not in data:
            raise AIAuthError("Unexpected device-flow response.")
        return data

    @staticmethod
    def poll_for_token(device_code: str, interval: int = 5, expires_in: int = 900,
                       stop_check: StopCheck = None) -> str:
        deadline = time.time() + expires_in
        while time.time() < deadline:
            if stop_check and stop_check():
                raise AIStopped("Sign-in cancelled.")
            time.sleep(interval)
            resp = requests.post(
                OAUTH_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            err = data.get("error")
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval += 5
                continue
            if err == "expired_token":
                raise AIAuthError("Sign-in expired. Please try again.")
            if err == "access_denied":
                raise AIAuthError("Access denied by user.")
            if err:
                raise AIAuthError(f"OAuth error: {err}")
            token = data.get("access_token", "")
            if token:
                creds.set_copilot_oauth_token(token)
                return token
        raise AIAuthError("Sign-in timed out.")

    def sign_out(self) -> None:
        creds.clear_copilot_oauth_token()
        type(self)._cp_token = ""
        type(self)._cp_expires = 0

    # --- copilot token exchange ---
    def _fresh_copilot_token(self) -> str:
        cls = type(self)
        if cls._cp_token and cls._cp_expires > time.time() + 60:
            return cls._cp_token
        oauth = creds.get_copilot_oauth_token()
        if not oauth:
            raise AIAuthError("Not signed in to GitHub Copilot.")
        headers = {"Authorization": f"token {oauth}", "Accept": "application/json", **_VSCODE_HEADERS}
        resp = requests.get(COPILOT_TOKEN_URL, headers=headers, timeout=15)
        if resp.status_code == 401:
            raise AIAuthError("Copilot OAuth token expired — sign in again.")
        if resp.status_code == 403:
            raise AIAuthError("This GitHub account has no Copilot subscription/access.")
        if resp.status_code != 200:
            raise AIAuthError(f"Copilot token exchange failed (HTTP {resp.status_code}).")
        data = resp.json()
        cls._cp_token = data.get("token", "")
        cls._cp_expires = data.get("expires_at", 0)
        cls._cp_api_base = data.get("endpoints", {}).get("api", COPILOT_API_BASE_DEFAULT)
        if not cls._cp_token:
            raise AIAuthError("Copilot token exchange returned no token.")
        return cls._cp_token

    def build_request(self, messages, model, system_prompt, tools_param=None):
        api_token = self._fresh_copilot_token()
        system, convo = _split_system(messages, system_prompt)
        msgs = ([{"role": "system", "content": system}] if system else []) + list(convo)
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "Openai-Intent": "conversation-panel",
            "Copilot-Integration-Id": "vscode-chat",
            **_VSCODE_HEADERS,
        }
        body = {"model": model, "messages": msgs, "stream": False}
        if tools_param:
            body["tools"] = tools_param
        # Reasoning models (o-series) reject temperature/max_tokens.
        if model.startswith("o"):
            body["max_completion_tokens"] = _DEFAULT_MAX_TOKENS
        else:
            body["temperature"] = _DEFAULT_TEMPERATURE
            body["max_tokens"] = _DEFAULT_MAX_TOKENS
        return f"{type(self)._cp_api_base}/chat/completions", headers, body

    def parse_response(self, data):
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return ""

    def discover_models(self):
        try:
            token = self._fresh_copilot_token()
            base = type(self)._cp_api_base
            resp = requests.get(
                f"{base}/models",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json",
                         "Copilot-Integration-Id": "vscode-chat", **_VSCODE_HEADERS},
                timeout=15)
            if resp.status_code != 200:
                return []
            data = resp.json()
            items = data.get("data", data) if isinstance(data, dict) else data
            return _models_from_openai_list(items)
        except (requests.RequestException, ValueError, AIError):
            return []


def _models_from_openai_list(items) -> List[Dict]:
    """Parse an OpenAI-style model list ({data:[{id,...}]}) into our shape,
    dropping non-chat models and de-duplicating by id."""
    out, seen = [], set()
    if not isinstance(items, list):
        return []
    for m in items:
        if not isinstance(m, dict):
            continue
        mid = m.get("id", "")
        if not mid or mid in seen:
            continue
        low = mid.lower()
        if any(tok in low for tok in _NON_CHAT):
            continue
        seen.add(mid)
        ctx = 0
        cap = m.get("capabilities") or {}
        limits = cap.get("limits") or {}
        if isinstance(limits, dict):
            ctx = limits.get("max_context_window_tokens", 0) or 0
        out.append({"id": mid, "name": m.get("name", mid), "context_tokens": ctx})
    return out


# ---------------------------------------------------------------------------
# Anthropic (direct)
# ---------------------------------------------------------------------------

class AnthropicProvider(AIProvider):
    id = "anthropic"
    label = "Anthropic Claude"
    SUPPORTS_TOOLS = True
    _models = [
        {"id": "claude-opus-4-20250514", "name": "Claude Opus 4", "context_tokens": 200000},
        {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "context_tokens": 200000},
        {"id": "claude-3-5-sonnet-latest", "name": "Claude 3.5 Sonnet", "context_tokens": 200000},
        {"id": "claude-3-5-haiku-latest", "name": "Claude 3.5 Haiku", "context_tokens": 200000},
    ]

    def is_configured(self) -> bool:
        return bool(creds.get_key(self.id))

    def build_request(self, messages, model, system_prompt, tools_param=None):
        key = creds.get_key(self.id)
        if not key:
            raise AIAuthError("No Anthropic API key configured.")
        system, convo = _split_system(messages, system_prompt)
        headers = {
            "x-api-key": key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        body = {
            "model": model,
            "max_tokens": 8192,
            # content may be a string OR a content-block array (tool_use / tool_result).
            "messages": [{"role": m["role"], "content": m.get("content", "")} for m in convo],
        }
        if system:
            body["system"] = system
        if tools_param:
            body["tools"] = tools_param
        return ANTHROPIC_URL, headers, body

    def parse_response(self, data):
        try:
            blocks = data.get("content", [])
            texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
            return "".join(texts)
        except (KeyError, IndexError, TypeError, AttributeError):
            return ""

    # --- tool calling (Anthropic 'tools' / tool_use blocks) ---
    def build_tools_param(self, tools):
        return [{"name": t.name, "description": t.description,
                 "input_schema": t.input_schema} for t in tools]

    def parse_tool_calls(self, data):
        out = []
        for b in (data.get("content", []) or []):
            if isinstance(b, dict) and b.get("type") == "tool_use":
                out.append(ToolCall(id=b.get("id", ""), name=b.get("name", ""),
                                    input=b.get("input", {}) or {}))
        return out

    def capture_assistant_turn(self, data):
        # MUST replay the assistant's full content-block array verbatim (text +
        # tool_use, in order) or the API 400s on the following tool_result turn.
        return {"role": "assistant", "content": data.get("content", [])}

    def format_tool_results(self, results):
        return [{"role": "user",
                 "content": [{"type": "tool_result", "tool_use_id": cid, "content": out}
                             for cid, (_name, out) in results.items()]}]

    def discover_models(self):
        key = creds.get_key(self.id)
        if not key:
            return []
        try:
            resp = requests.get(
                ANTHROPIC_MODELS_URL,
                headers={"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION},
                timeout=15)
            if resp.status_code != 200:
                return []
            out = []
            for m in resp.json().get("data", []):
                mid = m.get("id", "")
                if mid:
                    out.append({"id": mid, "name": m.get("display_name", mid),
                                "context_tokens": 200000})
            return out
        except (requests.RequestException, ValueError):
            return []


# ---------------------------------------------------------------------------
# OpenAI (direct)
# ---------------------------------------------------------------------------

class OpenAIProvider(AIProvider):
    id = "openai"
    label = "OpenAI"
    SUPPORTS_TOOLS = True
    _models = [
        {"id": "gpt-4.1", "name": "GPT-4.1", "context_tokens": 128000},
        {"id": "gpt-4o", "name": "GPT-4o", "context_tokens": 128000},
        {"id": "gpt-4o-mini", "name": "GPT-4o mini", "context_tokens": 128000},
        {"id": "o3-mini", "name": "o3-mini (reasoning)", "context_tokens": 200000},
    ]

    def is_configured(self) -> bool:
        return bool(creds.get_key(self.id))

    def build_request(self, messages, model, system_prompt, tools_param=None):
        key = creds.get_key(self.id)
        if not key:
            raise AIAuthError("No OpenAI API key configured.")
        system, convo = _split_system(messages, system_prompt)
        msgs = ([{"role": "system", "content": system}] if system else []) + list(convo)
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        body = {"model": model, "messages": msgs}
        if tools_param:
            body["tools"] = tools_param
        # o-series reasoning models reject temperature/max_tokens.
        if model.startswith("o"):
            body["max_completion_tokens"] = _DEFAULT_MAX_TOKENS
        else:
            body["temperature"] = _DEFAULT_TEMPERATURE
            body["max_tokens"] = _DEFAULT_MAX_TOKENS
        return OPENAI_URL, headers, body

    def parse_response(self, data):
        try:
            return data["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError, AttributeError):
            return ""

    # --- tool calling (OpenAI 'tools' / 'tool_calls') ---
    def build_tools_param(self, tools):
        return [{"type": "function",
                 "function": {"name": t.name, "description": t.description,
                              "parameters": t.input_schema}} for t in tools]

    def parse_tool_calls(self, data):
        out = []
        try:
            for tc in (data["choices"][0]["message"].get("tool_calls") or []):
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except (ValueError, TypeError):
                    args = {}
                out.append(ToolCall(id=tc.get("id", ""), name=tc["function"]["name"], input=args))
        except (KeyError, IndexError, TypeError):
            pass
        return out

    def capture_assistant_turn(self, data):
        # Replay the assistant message verbatim (carries tool_calls).
        try:
            return dict(data["choices"][0]["message"])
        except (KeyError, IndexError, TypeError):
            return {"role": "assistant", "content": ""}

    def format_tool_results(self, results):
        return [{"role": "tool", "tool_call_id": cid, "content": out}
                for cid, (_name, out) in results.items()]

    def discover_models(self):
        key = creds.get_key(self.id)
        if not key:
            return []
        try:
            resp = requests.get(
                OPENAI_MODELS_URL,
                headers={"Authorization": f"Bearer {key}"}, timeout=15)
            if resp.status_code != 200:
                return []
            items = resp.json().get("data", [])
            # Keep only chat-capable families (gpt*, o*-reasoning, chatgpt*).
            chat = [m for m in items if isinstance(m, dict)
                    and str(m.get("id", "")).lower().startswith(("gpt", "o1", "o3", "o4", "chatgpt"))]
            return _models_from_openai_list(chat)
        except (requests.RequestException, ValueError):
            return []


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

class GeminiProvider(AIProvider):
    id = "gemini"
    label = "Google Gemini"
    SUPPORTS_TOOLS = True
    _models = [
        {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "context_tokens": 1000000},
        {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "context_tokens": 2000000},
        {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "context_tokens": 1000000},
    ]

    def is_configured(self) -> bool:
        return bool(creds.get_key(self.id))

    def build_request(self, messages, model, system_prompt, tools_param=None):
        key = creds.get_key(self.id)
        if not key:
            raise AIAuthError("No Gemini API key configured.")
        system, convo = _split_system(messages, system_prompt)
        # Gemini uses contents/parts and roles 'user'/'model'. Messages that
        # already carry 'parts' (assistant turn / functionResponse) pass through.
        contents = []
        for m in convo:
            if "parts" in m:
                contents.append({"role": m["role"], "parts": m["parts"]})
            else:
                role = "model" if m.get("role") == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
        body: Dict = {"contents": contents}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools_param:
            body["tools"] = tools_param
        url = f"{GEMINI_BASE}/{model}:generateContent?key={key}"
        headers = {"Content-Type": "application/json"}
        return url, headers, body

    def parse_response(self, data):
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts if "text" in p)
        except (KeyError, IndexError, TypeError):
            return ""

    # --- tool calling (Gemini functionDeclarations / functionCall) ---
    def build_tools_param(self, tools):
        return [{"functionDeclarations": [
            {"name": t.name, "description": t.description, "parameters": t.input_schema}
            for t in tools]}]

    def parse_tool_calls(self, data):
        out = []
        try:
            for p in data["candidates"][0]["content"]["parts"]:
                fc = p.get("functionCall") if isinstance(p, dict) else None
                if fc:
                    # Gemini has no per-call id; use the function name as the id.
                    out.append(ToolCall(id=fc.get("name", ""), name=fc.get("name", ""),
                                        input=fc.get("args", {}) or {}))
        except (KeyError, IndexError, TypeError):
            pass
        return out

    def capture_assistant_turn(self, data):
        try:
            return {"role": "model", "parts": data["candidates"][0]["content"]["parts"]}
        except (KeyError, IndexError, TypeError):
            return {"role": "model", "parts": [{"text": ""}]}

    def format_tool_results(self, results):
        # functionResponse must echo the function name.
        return [{"role": "user", "parts": [
            {"functionResponse": {"name": name, "response": {"result": out}}}
            for _cid, (name, out) in results.items()]}]

    def discover_models(self):
        key = creds.get_key(self.id)
        if not key:
            return []
        try:
            resp = requests.get(f"{GEMINI_MODELS_URL}?key={key}", timeout=15)
            if resp.status_code != 200:
                return []
            out = []
            for m in resp.json().get("models", []):
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" not in methods:
                    continue
                name = str(m.get("name", "")).replace("models/", "")
                if not name:
                    continue
                out.append({"id": name,
                            "name": m.get("displayName", name),
                            "context_tokens": m.get("inputTokenLimit", 0)})
            return out
        except (requests.RequestException, ValueError):
            return []


# ---------------------------------------------------------------------------
# Registry / dispatch
# ---------------------------------------------------------------------------

_REGISTRY: Dict[str, AIProvider] = {
    p.id: p for p in (
        CopilotProvider(),
        AnthropicProvider(),
        OpenAIProvider(),
        GeminiProvider(),
    )
}


def list_providers() -> List[AIProvider]:
    return list(_REGISTRY.values())


def get_provider(provider_id: str) -> AIProvider:
    p = _REGISTRY.get(provider_id)
    if p is None:
        raise AIError(f"Unknown AI provider: {provider_id!r}")
    return p


def generate(provider_id: str, model: str, messages: List[Message],
             system_prompt: Optional[str] = None,
             stream_cb: StreamCb = None, stop_check: StopCheck = None) -> str:
    """Top-level convenience dispatch."""
    return get_provider(provider_id).generate(
        messages, model, system_prompt, stream_cb=stream_cb, stop_check=stop_check
    )


# ===========================================================================
# Agentic tool-calling loop (Phase 9)
# ===========================================================================

# Bracket-tag grammar for the text-fallback path (locked decision #2 — Copilot).
# The model emits e.g. [READ: path/to/file.c] when it wants to inspect code.
_FALLBACK_TAG_RE = re.compile(r"\[(READ|LIST|SEARCH|MINDMAP|REQUIREMENTS|DIFF)(?::\s*([^\]]*))?\]",
                              re.IGNORECASE)
_FALLBACK_TAG_TOOL = {
    "READ": "read_file", "LIST": "list_files", "SEARCH": "search_code",
    "MINDMAP": "get_mind_map", "REQUIREMENTS": "get_requirements", "DIFF": "get_diff",
}
_FALLBACK_ARG_KEY = {
    "read_file": "path", "list_files": "pattern", "search_code": "query",
    "get_diff": "file_path",
}


def _fallback_tool_catalogue(tools: "List[Tool]") -> str:
    lines = ["You can inspect the codebase by emitting ONE bracket tag on its own "
             "line when you need information; I will reply with the result and you "
             "continue. Available tags:"]
    tag_for = {v: k for k, v in _FALLBACK_TAG_TOOL.items()}
    for t in tools:
        tag = tag_for.get(t.name, t.name.upper())
        arg = _FALLBACK_ARG_KEY.get(t.name)
        sample = f"[{tag}: <{arg}>]" if arg else f"[{tag}]"
        lines.append(f"  {sample} — {t.description}")
    lines.append("Emit a tag only when you need it; otherwise give your final answer.")
    return "\n".join(lines)


def _parse_fallback_calls(text: str) -> "List[ToolCall]":
    calls = []
    for i, m in enumerate(_FALLBACK_TAG_RE.finditer(text or "")):
        tag = m.group(1).upper()
        arg = (m.group(2) or "").strip()
        name = _FALLBACK_TAG_TOOL[tag]
        key = _FALLBACK_ARG_KEY.get(name)
        calls.append(ToolCall(id=f"fb{i}", name=name, input=({key: arg} if key and arg else {})))
    return calls


def generate_with_tools(provider_id: str, model: str, messages: List[Message],
                        tools: "List[Tool]", tool_executor,
                        system_prompt: Optional[str] = None,
                        max_turns: int = 10, max_tool_calls: int = 40,
                        max_tool_output_chars: int = 4_000_000,
                        on_tool_call=None, on_text=None,
                        stop_check: StopCheck = None) -> str:
    """Run an agentic loop: the model may request read-only tools; we execute
    them locally and feed results back until it returns a final answer.

    Native tool-calling for SUPPORTS_TOOLS providers (OpenAI/Anthropic/Gemini);
    a bracket-tag text fallback for the rest (Copilot). `tool_executor(name, input)
    -> str` runs a tool (and should itself enforce the per-tool byte cap). Circuit
    breakers raise AIGenerationError: > max_turns, > max_tool_calls, or cumulative
    tool output > max_tool_output_chars (a runaway backstop — the model's context
    window is the real limit, locked decision #3).
    """
    provider = get_provider(provider_id)
    convo: List[Message] = list(messages)
    total_calls = 0
    total_chars = 0

    def _run_calls(calls: "List[ToolCall]") -> Dict[str, tuple]:
        nonlocal total_calls, total_chars
        results: Dict[str, tuple] = {}
        for call in calls:
            if stop_check and stop_check():
                raise AIStopped("Stopped during tool execution.")
            total_calls += 1
            if total_calls > max_tool_calls:
                raise AIGenerationError(f"Tool-call budget exceeded ({max_tool_calls}).")
            if on_tool_call:
                on_tool_call(call.name, call.input)
            try:
                out = tool_executor(call.name, call.input)
            except Exception as e:  # tool errors are returned to the model, not fatal
                out = f"ERROR: {e}"
            out = "" if out is None else str(out)
            total_chars += len(out)
            if total_chars > max_tool_output_chars:
                raise AIGenerationError(
                    f"Cumulative tool output exceeded {max_tool_output_chars} chars.")
            results[call.id] = (call.name, out)
        return results

    native = provider.SUPPORTS_TOOLS
    tools_param = provider.build_tools_param(tools) if native else None
    effective_system = system_prompt
    if not native:
        cat = _fallback_tool_catalogue(tools)
        effective_system = (system_prompt + "\n\n" + cat) if system_prompt else cat

    for _turn in range(max_turns):
        if stop_check and stop_check():
            raise AIStopped("Stopped before turn.")
        url, headers, body = provider.build_request(convo, model, effective_system, tools_param)
        data = provider._post_and_json(url, headers, body, stop_check=stop_check)
        text = provider.parse_response(data)

        if native:
            calls = provider.parse_tool_calls(data)
            if not calls:
                if on_text and text:
                    on_text(text)
                return text
            convo.append(provider.capture_assistant_turn(data))
            results = _run_calls(calls)
            convo.extend(provider.format_tool_results(results))
        else:
            calls = _parse_fallback_calls(text)
            if not calls:
                if on_text and text:
                    on_text(text)
                return text
            # Record the assistant's tagged message, then feed tool results back.
            convo.append({"role": "assistant", "content": text})
            results = _run_calls(calls)
            blob = "\n\n".join(f"[{name} result]\n{out}" for _cid, (name, out) in results.items())
            convo.append({"role": "user", "content": "TOOL RESULTS:\n" + blob})

    raise AIGenerationError(f"Agent did not finish within {max_turns} turns.")
