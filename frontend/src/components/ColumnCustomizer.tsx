import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";

const SEARCH_TYPES = ["Port Search", "Function Search", "Variable Search"];
const DEP_SUFFIXES = [" (Match)", " (Init)", " (Cyclic)"];

function isDepName(name: string): boolean {
  return name === "Port State" || DEP_SUFFIXES.some((s) => name.endsWith(s));
}

interface Col {
  id: string; // stable: original name for existing cols, "__newN" for added ones
  name: string;
  type: string;
  visible: boolean | null; // null = Auto (Init/Cyclic only)
  width: number;
}
interface Group {
  leader: Col;
  deps: Col[];
}
interface EditorResponse {
  columns: { name: string; type: string; visible: boolean | null; width: number }[];
  locked: string[];
  addable_types: string[];
}

const isInitCyclic = (type: string) => type === "InitColumn" || type === "CyclicColumn";

// Group a flat ordered column list into leader+dependents blocks (Search col +
// its Match/Init/Cyclic; Review Status + Port State; everything else standalone).
// Real layouts keep dependents contiguous after their leader (Qt enforced it).
function group(cols: Col[]): Group[] {
  const groups: Group[] = [];
  let i = 0;
  while (i < cols.length) {
    const c = cols[i];
    const deps: Col[] = [];
    if (SEARCH_TYPES.includes(c.type)) {
      let j = i + 1;
      while (j < cols.length && isDepName(cols[j].name) && cols[j].name.startsWith(`${c.name} (`)) {
        deps.push(cols[j]);
        j++;
      }
      groups.push({ leader: c, deps });
      i = j;
    } else if (c.type === "Review Status") {
      if (i + 1 < cols.length && cols[i + 1].name === "Port State") deps.push(cols[i + 1]);
      groups.push({ leader: c, deps });
      i += 1 + deps.length;
    } else {
      groups.push({ leader: c, deps });
      i++;
    }
  }
  return groups;
}

const flatten = (groups: Group[]): Col[] => groups.flatMap((g) => [g.leader, ...g.deps]);

// The ▦ column customizer (parity §7): add / remove / reorder / rename / hide,
// TC. ID pinned first, dependents follow their leader, reviewed/locked columns
// protected. Renames migrate cell data server-side via PUT /columns {renames}.
export function ColumnCustomizer({
  canEdit,
  onClose,
  onChanged,
  toast,
}: {
  canEdit: boolean;
  onClose: () => void;
  onChanged: () => void;
  toast: (msg: string) => void;
}) {
  const [cols, setCols] = useState<Col[]>([]);
  const [locked, setLocked] = useState<Set<string>>(new Set());
  const [types, setTypes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState("Static Text");
  const [renaming, setRenaming] = useState<string | null>(null); // col id
  const [draft, setDraft] = useState("");
  const [dragIdx, setDragIdx] = useState<number | null>(null); // group being dragged
  const [dropIdx, setDropIdx] = useState<number | null>(null); // hovered drop target
  const newId = useRef(0);
  const renameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get<EditorResponse>("/columns/editor");
        setCols(r.columns.map((c) => ({ id: c.name, ...c })));
        setLocked(new Set(r.locked));
        setTypes(r.addable_types);
        if (r.addable_types.length) setNewType(r.addable_types[0]);
      } catch (e) {
        toast(`Load columns failed: ${(e as Error).message}`);
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && renaming === null) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, renaming]);

  useEffect(() => {
    if (renaming !== null) {
      renameRef.current?.focus();
      renameRef.current?.select();
    }
  }, [renaming]);

  const groups = group(cols);
  const nameTaken = (name: string, exceptId?: string) =>
    cols.some((c) => c.name === name && c.id !== exceptId);

  function uniqueName(base: string): string {
    if (!nameTaken(base)) return base;
    let n = 1;
    while (nameTaken(`${base} (${n})`)) n++;
    return `${base} (${n})`;
  }

  // Binary columns toggle Show/Hide. Init/Cyclic cycle Auto → Show → Hide → Auto.
  function toggleVisible(id: string) {
    setCols((cs) =>
      cs.map((c) => {
        if (c.id !== id) return c;
        if (isInitCyclic(c.type)) {
          const next = c.visible === null ? true : c.visible === true ? false : null;
          return { ...c, visible: next };
        }
        return { ...c, visible: !c.visible };
      }),
    );
  }

  // Drag-and-drop reorder of whole groups (TC. ID stays pinned at index 0).
  function moveGroupTo(from: number, to: number) {
    if (from <= 0 || to <= 0 || from === to) return;
    const g = [...groups];
    const [moved] = g.splice(from, 1);
    const insertAt = Math.max(1, Math.min(from < to ? to - 1 : to, g.length));
    g.splice(insertAt, 0, moved);
    setCols(flatten(g));
  }

  function commitRename() {
    const id = renaming;
    const next = draft.trim();
    setRenaming(null);
    if (id === null || !next) return;
    const target = cols.find((c) => c.id === id);
    if (!target || next === target.name) return;
    if (next.includes("|")) return toast("Column names cannot contain '|'.");
    const unique = uniqueName(next);
    const old = target.name;
    setCols((cs) =>
      cs.map((c) => {
        if (c.id === id) return { ...c, name: unique };
        // rename dependents that belong to this leader
        if (c.name.startsWith(`${old} (`) && isDepName(c.name)) {
          return { ...c, name: `${unique}${c.name.slice(old.length)}` };
        }
        return c;
      }),
    );
  }

  function deleteGroup(g: Group) {
    const all = [g.leader, ...g.deps];
    if (all.some((c) => locked.has(c.name))) {
      toast("This column is locked (reviewed data) and can't be deleted.");
      return;
    }
    const ids = new Set(all.map((c) => c.id));
    setCols((cs) => cs.filter((c) => !ids.has(c.id)));
  }

  function addColumn() {
    const base = newName.trim();
    if (!base) return;
    if (base.includes("|")) return toast("Column names cannot contain '|'.");
    if (types.includes(newType) === false) return;
    const name = uniqueName(base);
    const mk = (n: string, t: string): Col => ({
      id: `__new${newId.current++}`,
      name: n,
      type: t,
      visible: isInitCyclic(t) ? null : true, // Init/Cyclic default to Auto
      width: 120,
    });
    const added: Col[] = [mk(name, newType)];
    if (SEARCH_TYPES.includes(newType)) {
      added.push(mk(`${name} (Match)`, "Static Text"));
      if (newType === "Port Search" || newType === "Function Search") {
        added.push(mk(`${name} (Init)`, "InitColumn"));
        added.push(mk(`${name} (Cyclic)`, "CyclicColumn"));
      }
    }
    setCols((cs) => [...cs, ...added]);
    setNewName("");
  }

  async function apply() {
    setSaving(true);
    try {
      const renames: Record<string, string> = {};
      for (const c of cols) {
        // existing columns have id === original name; a changed name is a rename
        if (!c.id.startsWith("__new") && c.id !== c.name) renames[c.id] = c.name;
      }
      await api.put("/columns", {
        columns: cols.map((c) => ({
          name: c.name,
          type: c.type,
          visible: c.visible,
          width: c.width,
        })),
        renames,
      });
      onChanged();
      onClose();
    } catch (e) {
      toast(`Save columns failed: ${(e as Error).message}`);
      setSaving(false);
    }
  }

  function renderCol(c: Col, isLeader: boolean, g: Group | null) {
    const dep = isDepName(c.name);
    const isLocked = locked.has(c.name);
    const isTcid = c.name === "TC. ID";
    const canRename = canEdit && isLeader && !dep && !isLocked && !isTcid && c.type !== "Review Status";
    const triState = isInitCyclic(c.type);
    return (
      <div className={"cc-col" + (dep ? " dep" : "")} key={c.id}>
        {triState ? (
          <button
            className={
              "cc-tri " +
              (c.visible === null ? "auto" : c.visible ? "show" : "hide")
            }
            disabled={!canEdit}
            title="Auto = shown only when a row has a value"
            onClick={() => toggleVisible(c.id)}
          >
            {c.visible === null ? "Auto" : c.visible ? "Show" : "Hide"}
          </button>
        ) : (
          <label className="cc-vis">
            <input
              type="checkbox"
              checked={c.visible === true}
              disabled={!canEdit || isTcid}
              onChange={() => toggleVisible(c.id)}
            />
          </label>
        )}
        {renaming === c.id ? (
          <input
            ref={renameRef}
            className="cc-rename"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitRename();
              if (e.key === "Escape") setRenaming(null);
            }}
          />
        ) : (
          <span className="cc-name" onDoubleClick={() => canRename && (setRenaming(c.id), setDraft(c.name))}>
            {c.name}
          </span>
        )}
        <span className="cc-type">{c.type}</span>
        {isLocked && <span className="cc-lock" title="Locked — reviewed data">🔒</span>}
        {isLeader && g && !isTcid && (
          <span className="cc-actions">
            {canRename && (
              <button className="cc-act" title="Rename" onClick={() => (setRenaming(c.id), setDraft(c.name))}>
                ✎
              </button>
            )}
            {canEdit && (
              <button className="cc-act danger" title="Delete column" onClick={() => deleteGroup(g)}>
                ✕
              </button>
            )}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div className="modal colcust" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">Customize Columns</div>

        <div className="cc-body">
          {loading ? (
            <div className="cc-empty">
              <span className="spin" />
              &nbsp;Loading…
            </div>
          ) : (
            groups.map((g, gi) => {
              const pinned = gi === 0; // TC. ID
              return (
                <div
                  className={
                    "cc-group" +
                    (dragIdx === gi ? " dragging" : "") +
                    (dropIdx === gi && dragIdx !== null && dragIdx !== gi ? " dropbefore" : "")
                  }
                  key={g.leader.id}
                  onDragOver={(e) => {
                    if (dragIdx === null || pinned) return;
                    e.preventDefault();
                    if (dropIdx !== gi) setDropIdx(gi);
                  }}
                  onDrop={(e) => {
                    e.preventDefault();
                    if (dragIdx !== null) moveGroupTo(dragIdx, gi);
                    setDragIdx(null);
                    setDropIdx(null);
                  }}
                >
                  <div className="cc-move">
                    {!pinned && canEdit && (
                      <span
                        className="cc-grip"
                        title="Drag to reorder"
                        draggable
                        onDragStart={(e) => {
                          setDragIdx(gi);
                          e.dataTransfer.effectAllowed = "move";
                        }}
                        onDragEnd={() => {
                          setDragIdx(null);
                          setDropIdx(null);
                        }}
                      >
                        ⠿
                      </span>
                    )}
                  </div>
                  <div className="cc-cols">
                    {renderCol(g.leader, true, g)}
                    {g.deps.map((d) => renderCol(d, false, null))}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {canEdit && (
          <div className="cc-add">
            <input
              placeholder="New column name…"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addColumn()}
            />
            <select value={newType} onChange={(e) => setNewType(e.target.value)}>
              {types.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <button className="cc-addbtn" onClick={addColumn} disabled={!newName.trim()}>
              ＋ Add
            </button>
          </div>
        )}

        <div className="cc-foot">
          {!canEdit && <span className="cc-vo">View-only — open for editing to change columns.</span>}
          <div className="spacer" />
          <button className="scope-btn" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="save-btn" onClick={apply} disabled={!canEdit || saving || loading}>
            {saving ? "Saving…" : "Apply"}
          </button>
        </div>
      </div>
    </div>
  );
}
