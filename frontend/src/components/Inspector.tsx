// Inspector strip: the selected row's actions are always visible here, so
// nothing is right-click-only (plan §4.2). Mirrors the row kebab menu.
export function Inspector({
  label,
  canEdit,
  onPickMatch,
  onShowInCodeMap,
  onHistory,
  onDuplicate,
  onRetire,
}: {
  label: string | null;
  canEdit: boolean;
  onPickMatch: () => void;
  onShowInCodeMap: () => void;
  onHistory: () => void;
  onDuplicate: () => void;
  onRetire: () => void;
}) {
  return (
    <div className="inspector">
      <span className="sel">{label ?? "No row selected"}</span>
      <button disabled={!label || !canEdit} onClick={onPickMatch}>
        Pick match candidate…
      </button>
      <button disabled={!label} onClick={onShowInCodeMap}>
        Show in Code Map
      </button>
      <button disabled={!label} onClick={onHistory}>
        Port history…
      </button>
      <button disabled={!label || !canEdit} onClick={onDuplicate}>
        Duplicate
      </button>
      <button className="danger" disabled={!label || !canEdit} onClick={onRetire}>
        Retire…
      </button>
    </div>
  );
}
