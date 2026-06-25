import { useCallback, useEffect, useState, type ReactNode } from "react";

// Themed replacement for window.confirm / window.alert. The native dialogs look
// out of place against the macOS-style chrome (and on macOS the system sheet can
// steal focus oddly), so all in-app confirmations route through this instead.

export interface ConfirmOptions {
  title?: string;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean; // red confirm button (destructive actions)
  hideCancel?: boolean; // alert mode — single OK button
}

function ConfirmDialog({
  title,
  message,
  confirmLabel = "OK",
  cancelLabel = "Cancel",
  danger = false,
  hideCancel = false,
  onConfirm,
  onCancel,
}: ConfirmOptions & { onConfirm: () => void; onCancel: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      else if (e.key === "Enter") onConfirm();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onConfirm, onCancel]);

  return (
    <div className="modal-overlay confirm-overlay" onMouseDown={onCancel}>
      <div className="modal confirm-modal" onMouseDown={(e) => e.stopPropagation()}>
        {title && <div className="modal-head">{title}</div>}
        <div className="confirm-body">{message}</div>
        <div className="confirm-foot">
          {!hideCancel && (
            <button className="confirm-cancel" onClick={onCancel} autoFocus>
              {cancelLabel}
            </button>
          )}
          <button
            className={"confirm-ok" + (danger ? " danger" : " primary")}
            onClick={onConfirm}
            autoFocus={hideCancel}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// Hook form: returns an async `confirm(opts) → Promise<boolean>` plus the node to
// render. Mirrors window.confirm so call sites read naturally:
//
//   const { confirm, confirmNode } = useConfirm();
//   if (await confirm({ message: "Delete?" , danger: true })) { … }
//   return <>{…}{confirmNode}</>;
export function useConfirm() {
  const [state, setState] = useState<{
    opts: ConfirmOptions;
    resolve: (ok: boolean) => void;
  } | null>(null);

  const confirm = useCallback(
    (opts: ConfirmOptions) =>
      new Promise<boolean>((resolve) => setState({ opts, resolve })),
    [],
  );

  const finish = (ok: boolean) => {
    state?.resolve(ok);
    setState(null);
  };

  const confirmNode = state ? (
    <ConfirmDialog
      {...state.opts}
      onConfirm={() => finish(true)}
      onCancel={() => finish(false)}
    />
  ) : null;

  return { confirm, confirmNode };
}
