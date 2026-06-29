# v3.0.2 — Hotfix: Windows blank/white window

A follow-up Windows fix. On some machines the app opened to a **blank white
window** (and only worked when "Run as administrator" was used). macOS and Linux
are unaffected.

## 🐛 Fixed
- **No more blank white window on Windows.** The embedded WebView2 control stores
  its browser profile in a "user data folder"; left unset it lands next to the
  `.exe`, which fails to initialise when the app runs from a read-only or
  permission-restricted location (Program Files, a VM shared folder, a locked-down
  extract) — leaving the window white unless launched as administrator. The app
  now puts that folder in a guaranteed per-user-writable location
  (`%LOCALAPPDATA%\ArchitectureValidator\WebView2`), so it works as a normal user.

---

# v3.0.1 — Hotfix: Windows launch crash

A maintenance release that fixes the Windows desktop build failing to start. No
functional changes to the app itself — **macOS and Linux behave exactly as in
3.0.0**; if 3.0.0 already runs for you, 3.0.1 only adds the Windows fix and better
diagnostics.

## 🐛 Fixed
- **Windows app no longer crashes on launch.** The native window backend
  (pywebview → winforms → pythonnet/.NET) failed to initialise on several
  machines — symptoms ranged from a silent exit, to a blank white window, to
  `Failed to resolve Python.Runtime.Loader.Initialize`. The build now ships
  pythonnet and its `clr_loader` .NET bootstrap shims with a pinned, matched
  version so the runtime loads correctly.
- **Crashes are no longer silent.** If the app fails to start, a full traceback is
  now written to `%LOCALAPPDATA%\ArchitectureValidator\crash.log`.
- **Missing-prerequisite check.** On Windows the app now verifies the WebView2
  Runtime and .NET Framework are present at launch, and — if either is missing —
  shows a dialog linking straight to Microsoft's download page instead of
  failing cryptically.

## 📦 Linux packaging
- Linux now ships proper distribution packages — **`.deb`, `.rpm`, and
  `.flatpak`** — instead of a portable `.tar.gz` archive.

## ℹ️ Windows prerequisites
The native window needs two Microsoft runtimes on the target machine:
- **Microsoft Edge WebView2 Evergreen Runtime** (match the CPU architecture — a
  missing/wrong-arch runtime shows a blank white window; install the ARM64
  runtime on Windows-on-ARM devices).
- **.NET Framework 4.7.2 or newer.**

---

# v3.0.0 — Desktop Rewrite: React + pywebview, Test Injection & Single-File Projects

The biggest release yet: the entire desktop app has been **rewritten**. The PyQt6
UI is gone, replaced by a **React single-page app running in a native pywebview
window** over a **local FastAPI worker**. The Qt-free Python logic core and the
native Rust ELF parser carry straight over, so every validation, release, AI, and
code-map capability is intact — now behind a faster, more responsive interface
that physically cannot freeze (the heavy work runs in a separate process and
streams progress over Server-Sent Events).

## 🏗 New architecture (no behaviour you relied on was dropped)
- **React SPA + pywebview shell + FastAPI worker.** The UI talks to the worker
  over `127.0.0.1` with a per-session bearer token; the worker owns all project
  state and drives the existing `Application_Logic` layer directly.
- **Every heavy operation is a cancellable background job** with uniform progress,
  cancellation, and error reporting streamed over a single `/api/events` SSE.
- **View-only is enforced server-side** (`PRAGMA query_only=ON`) — read-only
  sessions physically cannot write, not just a greyed-out button.

## 💉 New: Source-level Test Injection
A new view to **splice test code into production C source without editing the
originals**. Hooks anchor to the *text* of the surrounding lines (not brittle line
numbers), so they re-find their spot when upstream source shifts. Import helper
`.c/.h` files alongside, then export build-ready code — *Modified files only* or a
full *Reconstructed* tree — leaving your originals untouched.

## 🎓 New: Interactive in-app tutorials
Every view now has a **click-through interactive walkthrough** on a simulated
screen (nothing in your real projects is touched). Open **Preferences → Tutorials**
for Workspace, Code Map, Change Log, Test Design, AI Generation, AI Chat, and Test
Injection.

## 💾 Single-file projects + per-block encryption
- A project is now **one portable `.arch` SQLite file** — no per-project folder
  required.
- Encryption moved from whole-file to **per-block (per-category) content
  encryption**: the `.arch` is a plaintext SQLite container and only sensitive
  content columns are encrypted, each under its own key. Open and save are fast
  (no decrypt-to-temp / re-encrypt-the-whole-file). **Legacy whole-file
  (`ARCHENC1`) projects auto-migrate on first open.**

## ⚙️ Packaging
- Packaged as a **PyInstaller onedir desktop bundle** (Windows/macOS/Linux) from
  `ArchitectureValidatorDesktop.spec`, which builds the React SPA and the Rust
  parser wheel first. CI gained the Node.js setup + frontend build steps.

> **Upgrade note:** opening a project from v2.x re-stamps it into the v3 storage
> format on first open. Keep a backup of important projects before upgrading.
