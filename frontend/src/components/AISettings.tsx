import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AIProvider, ProvidersResponse } from "../api/types";

// Providers that authenticate with a pasted API key (vs. Copilot's device flow).
const KEY_PROVIDERS = new Set(["anthropic", "openai", "gemini"]);

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
              ) : (
                <div className="ai-prov-note">
                  {p.id === "copilot"
                    ? "GitHub Copilot signs in with the OAuth device flow (run the desktop sign-in); no API key is stored here."
                    : "This provider is configured outside the key store."}
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
