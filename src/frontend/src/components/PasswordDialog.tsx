import { useState } from "react";

// Passwords reserved as test/demo bypasses (mirror of Logic_Crypto's set) —
// blocked in production setup so a user can't pick the plaintext bypass.
const BLACKLIST = new Set(["master123"]);
const MIN_LEN = 6;

// Master-password dialog. Two modes:
//   setup  → new project: enter + confirm, mandatory, blacklist + length checks.
//   unlock → opening an encrypted project: single field, shows a retry error.
export function PasswordDialog({
  mode,
  busy,
  error,
  onSubmit,
  onCancel,
}: {
  mode: "setup" | "unlock";
  busy?: boolean;
  error?: string | null;
  onSubmit: (password: string) => void;
  onCancel: () => void;
}) {
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");

  let localErr: string | null = null;
  if (mode === "setup") {
    if (pw && BLACKLIST.has(pw)) localErr = "That password is reserved — choose another.";
    else if (pw && pw.length < MIN_LEN) localErr = `Use at least ${MIN_LEN} characters.`;
    else if (confirm && pw !== confirm) localErr = "Passwords don't match.";
  }
  const valid =
    mode === "unlock"
      ? pw.length > 0
      : pw.length >= MIN_LEN && pw === confirm && !BLACKLIST.has(pw);

  function submit() {
    if (valid && !busy) onSubmit(pw);
  }

  return (
    <div className="modal-overlay" onMouseDown={onCancel}>
      <div className="modal pwdialog" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">
          {mode === "setup" ? "Set Master Password" : "Enter Master Password"}
        </div>
        <div className="pw-body">
          <p className="pw-sub">
            {mode === "setup"
              ? "This password encrypts the project at rest (database + source). It cannot be recovered — store it safely."
              : "This project is encrypted. Enter its master password to open it."}
          </p>

          <label>Password</label>
          <input
            autoFocus
            type="password"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (mode === "unlock" ? submit() : undefined)}
          />

          {mode === "setup" && (
            <>
              <label>Confirm password</label>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
              />
            </>
          )}

          {(localErr || error) && <div className="pw-err">{localErr || error}</div>}
        </div>
        <div className="picker-foot">
          <div className="spacer" />
          <button className="scope-btn" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button className="save-btn" onClick={submit} disabled={!valid || busy}>
            {busy ? "Working…" : mode === "setup" ? "Create" : "Unlock"}
          </button>
        </div>
      </div>
    </div>
  );
}
