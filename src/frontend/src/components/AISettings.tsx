import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AIProvider, ProvidersResponse } from "../api/types";

// Providers that authenticate with a pasted API key (vs. Copilot's device flow).
const KEY_PROVIDERS = new Set(["anthropic", "openai", "gemini"]);

// In-flight GitHub Copilot device-flow sign-in.
interface CopilotFlow {
  user_code: string;
  verification_uri: string;
}
interface CopilotLoginStatus {
  status: "idle" | "pending" | "done" | "error";
  user_code?: string;
  verification_uri?: string;
  error?: string | null;
}

// AI provider linkage — manage the credential for each provider and see which
// models it exposes. Lives in Preferences → AI Settings. Backs onto the
// machine-global credential store via /api/ai/providers (PUT/DELETE key).
export function AISettings() {
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [copilotFlow, setCopilotFlow] = useState<CopilotFlow | null>(null);
  const pollTimer = useRef<number | null>(null);

  // Stop polling the device-flow status on unmount.
  useEffect(() => {
    return () => {
      if (pollTimer.current) window.clearInterval(pollTimer.current);
    };
  }, []);

  async function startCopilotLogin() {
    setBusy("copilot");
    setNote(null);
    try {
      const r = await api.post<CopilotFlow & { interval: number }>(
        "/ai/providers/copilot/login",
      );
      setCopilotFlow({ user_code: r.user_code, verification_uri: r.verification_uri });
      window.open(r.verification_uri, "_blank", "noopener");
      // Poll until the user approves (or it errors out).
      if (pollTimer.current) window.clearInterval(pollTimer.current);
      pollTimer.current = window.setInterval(async () => {
        try {
          const s = await api.get<CopilotLoginStatus>("/ai/providers/copilot/login");
          if (s.status === "done") {
            stopCopilotPoll();
            setCopilotFlow(null);
            setNote("Signed in to GitHub Copilot.");
            await load();
          } else if (s.status === "error") {
            stopCopilotPoll();
            setCopilotFlow(null);
            setNote(`Sign-in failed: ${s.error ?? "unknown error"}`);
          }
        } catch {
          /* transient — keep polling */
        }
      }, 2500);
    } catch (e) {
      setNote(`Sign-in failed: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  function stopCopilotPoll() {
    if (pollTimer.current) window.clearInterval(pollTimer.current);
    pollTimer.current = null;
  }

  async function cancelCopilotLogin() {
    stopCopilotPoll();
    setCopilotFlow(null);
    try {
      await api.del("/ai/providers/copilot/login");
    } catch {
      /* best effort */
    }
  }

  async function signOutCopilot() {
    setBusy("copilot");
    setNote(null);
    try {
      await api.del("/ai/providers/copilot");
      setNote("Signed out of GitHub Copilot.");
      await load();
    } catch (e) {
      setNote(`Sign-out failed: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  async function load() {
    setLoading(true);
    try {
      const r = await api.get<ProvidersResponse>("/ai/providers");
      setProviders(r.providers);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function saveKey(id: string) {
    const key = (drafts[id] ?? "").trim();
    if (!key) return;
    setBusy(id);
    setNote(null);
    try {
      await api.put(`/ai/providers/${id}`, { api_key: key });
      setDrafts((d) => ({ ...d, [id]: "" }));
      setNote(`Saved key for ${id}.`);
      await load();
    } catch (e) {
      setNote(`Save failed: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  async function clearKey(id: string) {
    setBusy(id);
    setNote(null);
    try {
      await api.del(`/ai/providers/${id}`);
      setNote(`Cleared key for ${id}.`);
      await load();
    } catch (e) {
      setNote(`Clear failed: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return (
      <div className="prefs-body">
        <div className="center-msg">
          <span className="spin" /> Loading providers…
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="prefs-body">
        <div className="prefs-placeholder" style={{ color: "var(--red)" }}>
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="prefs-body">
      <div className="prefs-field">
        <div className="prefs-label">AI Providers</div>
        <p className="prefs-hint">
          Link an AI account by storing its API key. Credentials are kept in the
          machine-global encrypted store, independent of the open project.
        </p>
      </div>

      <div className="ai-prov-list">
        {providers.map((p) => {
          const keyed = KEY_PROVIDERS.has(p.id);
          return (
            <div key={p.id} className="ai-prov-card">
              <div className="ai-prov-head">
                <span className="ai-prov-name">{p.label}</span>
                <span
                  className={
                    "ai-prov-badge " + (p.configured ? "ok" : "off")
                  }
                >
                  {p.configured ? "● Linked" : "○ Not linked"}
                </span>
                <span className="ai-prov-models">{p.models.length} models</span>
              </div>

              {keyed ? (
                <div className="ai-prov-keyrow">
                  <input
                    type="password"
                    className="ai-prov-key"
                    placeholder={p.configured ? "Replace API key…" : "Paste API key…"}
                    autoComplete="off"
                    spellCheck={false}
                    value={drafts[p.id] ?? ""}
                    onChange={(e) =>
                      setDrafts((d) => ({ ...d, [p.id]: e.target.value }))
                    }
                    onKeyDown={(e) => e.key === "Enter" && saveKey(p.id)}
                  />
                  <button
                    className="save-btn"
                    disabled={busy === p.id || !(drafts[p.id] ?? "").trim()}
                    onClick={() => saveKey(p.id)}
                  >
                    {busy === p.id ? "…" : "Save"}
                  </button>
                  {p.configured && (
                    <button
                      className="scope-btn"
                      disabled={busy === p.id}
                      onClick={() => clearKey(p.id)}
                    >
                      Clear
                    </button>
                  )}
                </div>
              ) : p.id === "copilot" ? (
                <div className="ai-copilot">
                  {copilotFlow ? (
                    <div className="ai-copilot-flow">
                      <p className="ai-prov-note">
                        Open{" "}
                        <a
                          href={copilotFlow.verification_uri}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {copilotFlow.verification_uri}
                        </a>{" "}
                        and enter this code to authorise:
                      </p>
                      <div className="ai-copilot-code">{copilotFlow.user_code}</div>
                      <div className="ai-copilot-actions">
                        <span className="ai-copilot-wait">
                          <span className="spin" /> Waiting for approval…
                        </span>
                        <button className="scope-btn" onClick={cancelCopilotLogin}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : p.configured ? (
                    <div className="ai-copilot-actions">
                      <span className="ai-prov-note">Signed in with GitHub.</span>
                      <button
                        className="scope-btn"
                        disabled={busy === "copilot"}
                        onClick={signOutCopilot}
                      >
                        Sign out
                      </button>
                    </div>
                  ) : (
                    <div className="ai-copilot-actions">
                      <span className="ai-prov-note">
                        Authorise with your GitHub account — no API key needed.
                      </span>
                      <button
                        className="save-btn ai-copilot-signin"
                        disabled={busy === "copilot"}
                        onClick={startCopilotLogin}
                      >
                        {busy === "copilot" ? "…" : "Sign in with GitHub"}
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="ai-prov-note">
                  This provider is configured outside the key store.
                </div>
              )}
            </div>
          );
        })}
      </div>

      {note && <div className="ai-prov-toast">{note}</div>}
    </div>
  );
}
