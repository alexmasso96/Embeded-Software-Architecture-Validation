# 1. Getting Started

[← Guide home](README.md) · **Getting Started** · [Next: The Workspace →](02-validation-workspace.md)

---

## Installing & running from source

You'll need **Python 3.10+** and **Node.js** (to build the frontend once).

```bash
# From the repository root
pip install -r requirements.txt

# Build the React frontend (the worker serves it inside the desktop shell)
( cd src/frontend && npm ci && npm run build )

# Launch the desktop app (native pywebview window over the FastAPI worker)
PYTHONPATH=src python -m desktop.main
```

A pre-built distributable is produced with PyInstaller from `ArchitectureValidatorDesktop.spec` — `scripts/build_desktop.sh` (macOS/Linux) or `scripts/build_desktop.ps1` (Windows). See the main [README](../../README.md#building-a-distributable) for details.

## The Start screen

When the app opens, the Start screen lets you create or open a project:

![Start screen](../../Media/images/startup_launcher.png)

| Action | What it does |
|--------|--------------|
| **＋ New Project** | Creates a fresh `.arch` project — you choose where to save it and set a master password. |
| **Open Project** | Browses for an existing `.arch` file. |
| **Recent projects** | Each recent entry can be opened **view-only** (safe to browse while a teammate edits) or **for editing** (which acquires the exclusive lock). |

Opening an encrypted project prompts once for its **master password**. The split between view-only and exclusive-edit is the heart of the collaboration model — only one person edits at a time, while everyone else can safely browse. There's more in [Collaboration & Safety](06-collaboration-and-safety.md).

## Projects are a single file

A project is one portable `.arch` file (a SQLite database under the hood). It holds everything: your architecture models, every software release and its ELF data, baselines, imported source, AI mind maps, test-case templates, test-injection projects, and the change history. Copy it, back it up, or hand it to a colleague as a single file.

## Finding your way around

Once a project is open, switch views from the **segmented control** in the title bar:

- **Workspace** — the architecture-validation matrix (where most work happens)
- **Test Design** · **AI Generation** · **AI Chat** · **Code Map** · **Test Injection** · **Change Log**

The title bar also has toolbar icons for **Import** and **Columns**, a **Save** button, and a ⚙ gear that opens **Preferences** (Appearance, AI Settings, Paths, **Tutorials**, Updates). The **Tutorials** section has an interactive walkthrough of every view — a good first stop.

## What you'll do next

A typical first session looks like this:

1. **Create a project** and import your first ELF release.
2. **Import your architecture** ports from Excel, CSV, or a Rhapsody export — see [Importing Architecture](03-importing-architecture.md).
3. **Review the matches** the tool proposes between ports and symbols in the [Workspace](02-validation-workspace.md).
4. **Design and generate test cases** from your reviewed data — see [Test Design](05-test-case-design.md).

---

[← Guide home](README.md) · [Next: The Workspace →](02-validation-workspace.md)
