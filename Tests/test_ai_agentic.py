"""
Phase 9 — agentic tool-calling backend: provider tool shapes (mocked, no
network), the native + text-fallback agent loops, circuit breakers, and the
sandboxed read-only ToolExecutor (path-jail).
"""
import os
import sys

sys.path.append(os.path.abspath("src"))

import pytest
from Application_Logic import Logic_AI_Providers as P
from Application_Logic import Logic_AI_Tools as T


# ---------------------------------------------------------------------------
# _post_and_json error handling (shared by generate + the loop)
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._p = payload if payload is not None else {}
        self.text = text
    def json(self):
        if isinstance(self._p, Exception):
            raise self._p
        return self._p


def test_post_and_json_errors(monkeypatch):
    prov = P.get_provider("openai")
    monkeypatch.setattr(P.requests, "post", lambda *a, **k: _Resp(401))
    with pytest.raises(P.AIAuthError):
        prov._post_and_json("u", {}, {})
    monkeypatch.setattr(P.requests, "post", lambda *a, **k: _Resp(500, text="boom"))
    with pytest.raises(P.AIGenerationError):
        prov._post_and_json("u", {}, {})
    monkeypatch.setattr(P.requests, "post", lambda *a, **k: _Resp(200, ValueError("x")))
    with pytest.raises(P.AIGenerationError):
        prov._post_and_json("u", {}, {})


# ---------------------------------------------------------------------------
# Per-provider tool shapes
# ---------------------------------------------------------------------------

TOOLS = [P.Tool("read_file", "read a file", {"type": "object", "properties": {"path": {"type": "string"}}})]


def test_openai_tool_shapes():
    o = P.OpenAIProvider()
    tp = o.build_tools_param(TOOLS)
    assert tp[0]["type"] == "function" and tp[0]["function"]["name"] == "read_file"
    data = {"choices": [{"message": {"content": None, "tool_calls": [
        {"id": "c1", "function": {"name": "read_file", "arguments": '{"path": "a.c"}'}}]}}]}
    calls = o.parse_tool_calls(data)
    assert calls == [P.ToolCall(id="c1", name="read_file", input={"path": "a.c"})]
    assert o.capture_assistant_turn(data)["tool_calls"][0]["id"] == "c1"
    fr = o.format_tool_results({"c1": ("read_file", "FILE BODY")})
    assert fr == [{"role": "tool", "tool_call_id": "c1", "content": "FILE BODY"}]


def test_anthropic_tool_shapes():
    a = P.AnthropicProvider()
    tp = a.build_tools_param(TOOLS)
    assert tp[0]["name"] == "read_file" and "input_schema" in tp[0]
    data = {"content": [{"type": "text", "text": "let me look"},
                        {"type": "tool_use", "id": "u1", "name": "read_file", "input": {"path": "a.c"}}]}
    calls = a.parse_tool_calls(data)
    assert calls == [P.ToolCall(id="u1", name="read_file", input={"path": "a.c"})]
    # assistant turn MUST be replayed verbatim (full block array, text+tool_use)
    cap = a.capture_assistant_turn(data)
    assert cap["role"] == "assistant" and cap["content"] == data["content"]
    fr = a.format_tool_results({"u1": ("read_file", "BODY")})
    assert fr[0]["role"] == "user"
    assert fr[0]["content"][0] == {"type": "tool_result", "tool_use_id": "u1", "content": "BODY"}


def test_gemini_tool_shapes():
    g = P.GeminiProvider()
    tp = g.build_tools_param(TOOLS)
    assert tp[0]["functionDeclarations"][0]["name"] == "read_file"
    data = {"candidates": [{"content": {"parts": [
        {"functionCall": {"name": "read_file", "args": {"path": "a.c"}}}]}}]}
    calls = g.parse_tool_calls(data)
    assert calls == [P.ToolCall(id="read_file", name="read_file", input={"path": "a.c"})]
    fr = g.format_tool_results({"read_file": ("read_file", "BODY")})
    # functionResponse must echo the function name
    assert fr[0]["parts"][0]["functionResponse"]["name"] == "read_file"


# ---------------------------------------------------------------------------
# Agent loop — native + fallback
# ---------------------------------------------------------------------------

class _StubProvider(P.AIProvider):
    """Scripted provider: no network. `script` is a list of dicts consumed per turn."""
    id = "stub"
    label = "Stub"

    def __init__(self, script, supports_tools=True):
        self.script = list(script)
        self.SUPPORTS_TOOLS = supports_tools
        self.posts = []

    def is_configured(self):
        return True

    def build_request(self, messages, model, system_prompt, tools_param=None):
        return ("http://stub", {}, {"messages": list(messages),
                                    "system": system_prompt, "tools": tools_param})

    def _post_and_json(self, url, headers, body, stop_check=None):
        self.posts.append(body)
        return self.script.pop(0)

    def parse_response(self, data):
        return data.get("text", "")

    def parse_tool_calls(self, data):
        return [P.ToolCall(**c) for c in data.get("calls", [])]

    def capture_assistant_turn(self, data):
        return {"role": "assistant", "content": data.get("text", "")}

    def format_tool_results(self, results):
        return [{"role": "tool", "content": out} for _cid, (_n, out) in results.items()]


@pytest.fixture()
def stub(monkeypatch):
    def _install(script, supports_tools=True):
        sp = _StubProvider(script, supports_tools)
        monkeypatch.setitem(P._REGISTRY, "stub", sp)
        return sp
    return _install


def test_native_loop_executes_tool_then_returns(stub):
    sp = stub([
        {"calls": [{"id": "c1", "name": "read_file", "input": {"path": "a.c"}}]},
        {"text": "final answer"},
    ])
    seen = []
    out = P.generate_with_tools(
        "stub", "m", [{"role": "user", "content": "go"}], T.default_tools(),
        tool_executor=lambda n, a: seen.append((n, a)) or "FILE BODY")
    assert out == "final answer"
    assert seen == [("read_file", {"path": "a.c"})]
    assert len(sp.posts) == 2          # two model turns


def test_fallback_loop_parses_bracket_tags(stub):
    sp = stub([{"text": "I need to look. [READ: door_control.c]"},
               {"text": "done"}], supports_tools=False)
    seen = []
    out = P.generate_with_tools(
        "stub", "m", [{"role": "user", "content": "go"}], T.default_tools(),
        tool_executor=lambda n, a: seen.append((n, a)) or "CODE")
    assert out == "done"
    assert seen == [("read_file", {"path": "door_control.c"})]
    # fallback injects the tag catalogue into the system prompt
    assert "[READ:" in sp.posts[0]["system"]


def test_loop_circuit_breaker_max_tool_calls(stub):
    stub([{"calls": [{"id": "c", "name": "read_file", "input": {}}]}] * 50)
    with pytest.raises(P.AIGenerationError):
        P.generate_with_tools("stub", "m", [{"role": "user", "content": "go"}],
                              T.default_tools(), tool_executor=lambda n, a: "x",
                              max_tool_calls=3)


def test_loop_circuit_breaker_cumulative_output(stub):
    stub([{"calls": [{"id": "c", "name": "read_file", "input": {}}]}] * 50)
    with pytest.raises(P.AIGenerationError):
        P.generate_with_tools("stub", "m", [{"role": "user", "content": "go"}],
                              T.default_tools(),
                              tool_executor=lambda n, a: "x" * 1000,
                              max_tool_output_chars=2000)


def test_loop_returns_plain_text_when_no_tool(stub):
    stub([{"text": "just an answer"}])
    out = P.generate_with_tools("stub", "m", [{"role": "user", "content": "hi"}],
                               T.default_tools(), tool_executor=lambda n, a: "x")
    assert out == "just an answer"


# ---------------------------------------------------------------------------
# Sandboxed tool executor — path jail
# ---------------------------------------------------------------------------

@pytest.fixture()
def sandbox(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "door.c").write_text("void f(void){ lock(); }\n")
    sub = root / "sub"; sub.mkdir()
    (sub / "g.c").write_text("int g;\n")
    # sibling dir that must NOT be reachable (the '/root-evil' vs '/root' case)
    evil = tmp_path / "root-evil"; evil.mkdir()
    (evil / "secret.c").write_text("SECRET\n")
    return T.ToolExecutor(str(root))


def test_read_file_ok(sandbox):
    assert "lock()" in sandbox.read_file("door.c")
    assert "int g;" in sandbox.read_file("sub/g.c")


def test_read_file_escapes_rejected(sandbox):
    for bad in ("../root-evil/secret.c", "../../etc/passwd", "/etc/passwd"):
        with pytest.raises(T.ToolError):
            sandbox.read_file(bad)


def test_sibling_prefix_not_escapable(sandbox):
    # '/root-evil' shares the '/root' prefix but must be rejected (os.sep guard).
    with pytest.raises(T.ToolError):
        sandbox.read_file("../root-evil")


def test_no_sandbox_refuses(tmp_path):
    ex = T.ToolExecutor(None)
    with pytest.raises(T.ToolError):
        ex.read_file("anything")          # never falls back to CWD


def test_list_and_search(sandbox):
    listing = sandbox.list_files("*.c")
    assert "door.c" in listing and "sub/g.c" in listing
    assert "secret.c" not in listing       # sibling never listed
    found = sandbox.search_code("lock")
    assert "door.c:1:" in found


def test_read_cap_truncates(sandbox, monkeypatch):
    monkeypatch.setattr(T, "READ_CAP", 10)
    big = "x" * 50
    import os as _os
    with open(_os.path.join(sandbox.source_root, "big.c"), "w") as f:
        f.write(big)
    out = sandbox.read_file("big.c")
    assert "truncated" in out and len(out) < 50


def test_execute_dispatch_and_unknown(sandbox):
    assert "lock()" in sandbox.execute("read_file", {"path": "door.c"})
    with pytest.raises(T.ToolError):
        sandbox.execute("rm_rf", {})


def test_get_mind_map_and_requirements_with_db(sandbox):
    import json
    from Application_Logic import Logic_AI_Context as ctx

    class FakeDB:
        is_open = True
        def __init__(self):
            self._m = {ctx.META_REQUIREMENTS: json.dumps([{"id": "R1", "text": "lock"}])}
        def get_model_mindmap(self, mid, release_id=None):
            return {"builder_version": ctx.MINDMAP_BUILDER_VERSION, "model_name": "M",
                    "files": {}, "ports": {}, "requirements": {},
                    "functions": {"f": {"file": "x.c", "signature": "void f(void)",
                                        "calls": [], "reads": [], "writes": []}}}
        def get_meta(self, k, default=None):
            return self._m.get(k, default)
    ex = T.ToolExecutor(sandbox.source_root, db=FakeDB(), model_id=1)
    assert "void f(void)" in ex.get_mind_map()
    assert "R1" in ex.get_requirements()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
