import { useEffect } from "react";
import { renderMarkdown } from "../markdown";

// Scrollable release-notes viewer. Renders the GitHub release `body` (markdown)
// through the app's own renderer so it matches the rest of the chrome.
export function ChangelogModal({
  version,
  body,
  onClose,
}: {
  version?: string;
  body: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div className="modal changelog" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">
          What's New{version ? ` — v${version}` : ""}
          <button className="prefs-close" onClick={onClose} title="Close">
            ✕
          </button>
        </div>
        <div
          className="changelog-body md"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(body) }}
        />
      </div>
    </div>
  );
}
