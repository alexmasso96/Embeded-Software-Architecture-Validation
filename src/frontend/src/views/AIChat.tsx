import { useCallback, useEffect, useRef, useState } from "react";
import { api, getToken } from "../api/client";
import type { AIProvider, ProvidersResponse } from "../api/types";
import { renderMarkdown } from "../markdown";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

function modelLabel(m: { id: string; name?: string }): string {
  return m.name || m.id;
}

const DEFAULT_SYSTEM_PROMPT =
  "You are an embedded-software test engineer assisting with architecture " +
  "validation. Answer concisely and reference the code mind map when relevant.";

// Stream a POST /api/ai/chat SSE response. EventSource can't POST, so we read
// the response body manually and parse the `event:`/`data:` frames ourselves,
// invoking the callbacks as token / done / error frames arrive.
async function streamChat(
  body: unknown,
  cbs: {
    onToken: (t: string) => void;
    onDone: (full: string) => void;
    onError: (msg: string) => void;
  },
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/ai/chat", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${getToken()}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON */
    }
    cbs.onError(String(detail));
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  const dispatch = (ev: string, data: string) => {
    let payload: string = data;
    try {
      payload = JSON.parse(data);
    } catch {
      /* keep raw */
    }
    if (ev === "token") cbs.onToken(String(payload));
    else if (ev === "done") cbs.onDone(String(payload));
    else if (ev === "error") cbs.onError(String(payload));
  };

  // SSE frames are separated by a blank line; sse-starlette uses CRLF, so split
  // on either \r\n\r\n or \n\n and strip the optional \r from each line.
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const frames = buf.split(/\r?\n\r?\n/);
    buf = frames.pop() ?? ""; // last (possibly partial) frame stays buffered
    for (const frame of frames) {
      let event = "message";
      let data = "";
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) dispatch(event, data);
    }
  }
}

// ---------------------------------------------------------------------------
// AI Chat view — provider/model + system prompt + mind-map grounding on the
// left, a streamed conversation on the right.
// ---------------------------------------------------------------------------
export function AIChat({ toast }: { toast: (msg: string) => void }) {
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [providerId, setProviderId] = useState("");
  const [model, setModel] = useState("");
  const [systemPrompt, setSystemPrompt] = useState(DEFAULT_SYSTEM_PROMPT);
  const [ground, setGround] = useState(true);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const threadEndRef = useRef<HTMLDivElement>(null);

  const provider = providers.find((p) => p.id === providerId) ?? null;

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await api.get<ProvidersResponse>("/ai/providers");
        if (!alive) return;
        setProviders(r.providers);
        const def =
          r.providers.find((p) => p.configured) ?? r.providers[0] ?? null;
        if (def) {
          setProviderId(def.id);
          setModel(def.models[0]?.id ?? "");
        }
      } catch (e) {
        if (alive) toast(`AI providers: ${(e as Error).message}`);
      }
    })();
    return () => {
      alive = false;
    };
  }, [toast]);

  useEffect(() => {
    if (!provider) return;
    if (!provider.models.some((m) => m.id === model)) {
      setModel(provider.models[0]?.id ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providerId]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || !providerId || !model || streaming) return;

    const history = [...messages, { role: "user" as const, content: text }];
    // Add the user turn + an empty assistant turn we'll fill as tokens stream.
    setMessages([...history, { role: "assistant", content: "" }]);
    setInput("");
    setStreaming(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const appendAssistant = (chunk: string) =>
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === "assistant") {
          next[next.length - 1] = { ...last, content: last.content + chunk };
        }
        return next;
      });

    try {
      await streamChat(
        {
          provider_id: providerId,
          model,
          messages: history,
          system_prompt: systemPrompt,
          ground_in_mindmap: ground,
        },
        {
          onToken: appendAssistant,
          onDone: (full) => {
            // Replace with the authoritative full text if streaming produced
            // nothing (some providers only deliver the final blob).
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last && last.role === "assistant" && !last.content && full) {
                next[next.length - 1] = { ...last, content: full };
              }
              return next;
            });
          },
          onError: (msg) => {
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last && last.role === "assistant") {
                next[next.length - 1] = {
                  ...last,
                  content: last.content || `⚠ ${msg}`,
                };
              }
              return next;
            });
            toast(`Chat error: ${msg}`);
          },
        },
        ctrl.signal,
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        toast(`Chat failed: ${(e as Error).message}`);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [input, providerId, model, streaming, messages, systemPrompt, ground, toast]);

  function stop() {
    abortRef.current?.abort();
    setStreaming(false);
  }

  function clearThread() {
    if (streaming) stop();
    setMessages([]);
  }

  return (
    <div className="chat-view">
      {/* Left: config */}
      <aside className="chat-config">
        <div className="chat-config-h">Chat Configuration</div>
        <label className="aig-field">
          <span>Provider</span>
          <select
            value={providerId}
            onChange={(e) => setProviderId(e.target.value)}
          >
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
                {p.configured ? "" : " (not configured)"}
              </option>
            ))}
          </select>
        </label>
        <label className="aig-field">
          <span>Model</span>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={!provider || provider.models.length === 0}
          >
            {provider?.models.length ? (
              provider.models.map((m) => (
                <option key={m.id} value={m.id}>
                  {modelLabel(m)}
                </option>
              ))
            ) : (
              <option value="">No models</option>
            )}
          </select>
        </label>
        <label className="aig-field chat-sysprompt">
          <span>System Prompt</span>
          <textarea
            value={systemPrompt}
            spellCheck={false}
            onChange={(e) => setSystemPrompt(e.target.value)}
            rows={8}
          />
        </label>
        <label className="chat-ground">
          <input
            type="checkbox"
            checked={ground}
            onChange={(e) => setGround(e.target.checked)}
          />
          Ground in Code Mind Map
        </label>
        <div className="spacer" />
        <button
          className="scope-btn"
          disabled={messages.length === 0}
          onClick={clearThread}
        >
          Clear Conversation
        </button>
      </aside>

      {/* Right: console */}
      <div className="chat-console">
        <div className="chat-thread">
          {messages.length === 0 ? (
            <div className="chat-empty">
              Ask a question about the architecture, the code, or the validation
              results.
            </div>
          ) : (
            messages.map((m, i) => (
              <div key={i} className={"chat-msg " + m.role}>
                <div className="chat-role">
                  {m.role === "user" ? "You" : "Assistant"}
                </div>
                {m.role === "assistant" ? (
                  <div
                    className="chat-bubble md"
                    dangerouslySetInnerHTML={{
                      __html: m.content
                        ? renderMarkdown(m.content)
                        : "<span class='chat-typing'>▍</span>",
                    }}
                  />
                ) : (
                  <div className="chat-bubble">{m.content}</div>
                )}
              </div>
            ))
          )}
          <div ref={threadEndRef} />
        </div>

        <div className="chat-composer">
          <textarea
            className="chat-input"
            placeholder="Send a message…  (Enter to send, Shift+Enter for newline)"
            spellCheck={false}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            rows={2}
          />
          {streaming ? (
            <button className="scope-btn" onClick={stop}>
              Stop
            </button>
          ) : (
            <button
              className="save-btn"
              disabled={!input.trim() || !providerId || !model}
              onClick={send}
            >
              Send
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
