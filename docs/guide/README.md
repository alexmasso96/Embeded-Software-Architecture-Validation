# Architecture Validator Pro — User Guide

Welcome! This guide walks through everything Architecture Validator Pro can do, one view at a time, with screenshots from the app.

If you're new, read it top to bottom. If you're looking for one thing, jump straight to the section you need from the list below.

> 💡 **Prefer to learn by doing?** Every view also has an **interactive in-app walkthrough**. Open **Preferences → Tutorials** (the ⚙ gear) for a safe, click-through demo of each one — nothing in your real projects is touched.

---

## Contents

| # | Section | What's inside |
|---|---------|---------------|
| 1 | [Getting Started](01-getting-started.md) | Installing, launching, the Start screen, and how the app is laid out |
| 2 | [The Workspace](02-validation-workspace.md) | The architecture matrix, models, columns, fuzzy symbol matching, and the column customizer |
| 3 | [Importing Architecture](03-importing-architecture.md) | Bringing ports in from Excel, CSV, and Rhapsody exports |
| 4 | [Releases & Baselines](04-releases-and-baselines.md) | Managing software releases, baselines, and change detection across releases |
| 5 | [Test Design](05-test-case-design.md) | The Markdown template language, live preview, grouping, and exports |
| 6 | [Collaboration & Safety](06-collaboration-and-safety.md) | Exclusive-edit locking, view-only mode, master-password encryption, and change history |
| 7 | [AI Test Generation](07-ai-test-generation.md) | Connecting Copilot / Claude / OpenAI / Gemini and generating low-level tests |
| 8 | [AI Chat](08-advanced-ai-chat.md) | Source mind maps and agentic, source-grounded chat |
| 9 | [Code Map](09-code-map.md) | The visual call-graph + read-only IDE joining the ELF to your C source |
| 10 | [Change Log](10-change-log.md) | Side-by-side release diffs and the AI change-log summary |
| 11 | [Test Injection](11-test-injection.md) | Splicing test code into production source without editing the originals |

---

## What is this tool, in one paragraph?

Embedded teams maintain an architecture — ports, interfaces, operations — that's supposed to reflect what's actually compiled into the ECU. Keeping those two in sync is normally slow and manual. Architecture Validator Pro parses the compiled `.elf` binary, fuzzy-matches your architecture ports to the real symbols in the firmware, and gives you an editable matrix to review and sign off on everything. From there you can track changes between software releases, keep a reviewable history, generate test-case designs straight from your data, and even splice test code into the source without touching the originals.

## How the app is laid out

The window has a **title bar** along the top with the document name, a **segmented control** to switch between the seven views, toolbar icons for **Import** and **Columns**, a **Save** button, and a ⚙ gear for **Preferences**. The seven views are: **Workspace**, **Test Design**, **AI Generation**, **AI Chat**, **Code Map**, **Test Injection**, and **Change Log**.

---

➡️ Start with **[1. Getting Started](01-getting-started.md)**
