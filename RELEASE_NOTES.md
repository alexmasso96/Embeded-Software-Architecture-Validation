# v1.0.2

## 🔍 Fixed: imported & ELF-switched rows now fuzzy-match immediately

Previously, when you imported a Rhapsody/Excel architecture export and mapped
operations or ports into a **Search** column, the adjacent **(Match)** column did
not actually perform the fuzzy search — it only mirrored the raw text copied from
the search column. The match scoring was deferred to a *lazy* dropdown that only
ran when you manually opened each cell, so freshly imported rows showed no
suggestions or scores until you clicked through every one of them.

**Cause.** Imported and loaded rows were rendered through the lazy widget path,
which pre-fills the (Match) cell with the search text but never invokes the
matcher until the dropdown is opened. Typing into a cell by hand used the eager
path; importing did not.

**Fix.** Imports and ELF switches now run the **active (eager) matcher branch**,
so the (Match) columns are filled with real fuzzy results (with match percentages)
the moment the data lands:

- **Importing** an architecture export now eagerly matches every row against the
  loaded symbols. An *"Importing — matching symbols"* progress window is shown so
  it's clear work is happening on large imports.
- **Loading a different ELF** from the Release Selection window now re-runs the
  matcher against the new symbol set automatically. The redundant **Deep Search**
  checkbox (which had no effect) was removed.
- **Opening a saved project** intentionally keeps the lighter lazy path, and now
  always matches against the last loaded ELF for that project.

Baselines remain read-only snapshots — their stored matches are left untouched.

---

# v1.0.1 — Hotfix

## 🔒 Fixed: repeated master-password prompts ("integrity mismatch")

Opening a project frequently asked for the master password — claiming an
**integrity mismatch** — even on a normal save → close → reopen, and especially
after rebuilding or moving the app.

**Cause.** Project integrity was verified by hashing the **entire raw bytes of
the `.arch` SQLite file** and storing that hash in a separate `.integrity`
sidecar. SQLite files are not byte-stable for unchanged content: WAL
checkpoints on close, the file change counter, and version fields in the header
all rewrite bytes that have nothing to do with your data. The app also commits
to the database outside of an explicit save (UI state, history). So the bytes
changed on nearly every reopen and the check failed — a false alarm, not real
tampering.

**Fix.** Integrity is now an **HMAC over the project's canonical *logical*
content** (models, rows, layout, releases, test-case design, …), keyed by the
master-password hash, and stored **inside the database** so it travels with the
file. It ignores SQLite's internal bookkeeping and volatile/cosmetic tables, so
it is stable across reopen and across SQLite versions while remaining
tamper-evident. Existing projects open silently and are re-stamped on the next
save; the old `.integrity` sidecar is cleaned up automatically.

You should no longer be prompted for the master password unless a project's
content was genuinely modified outside the app (or you enter Test Mode, which is
password-gated by design).

## 📦 Build

- Stopped bundling the full PyQt6 package as data files, which was overriding
  PyInstaller's pruning and roughly doubling artifact size (macOS `.app`
  ~281 MB → ~138 MB). No functional change.

---

*No project file format change. No action required to upgrade.*
