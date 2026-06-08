# Architecture Validator Pro — User Guide

Welcome! This guide walks through everything Architecture Validator Pro can do, one feature area at a time, with screenshots from the app.

If you're new, read it top to bottom. If you're looking for one thing, jump straight to the section you need from the list below.

> 📷 _Screenshot coming soon._

---

## Contents

| # | Section | What's inside |
|---|---------|---------------|
| 1 | [Getting Started](01-getting-started.md) | Installing, launching, and the New / Open / Edit-mode choices |
| 2 | [The Validation Workspace](02-validation-workspace.md) | The architecture table, models, columns, fuzzy symbol matching, and the column customizer |
| 3 | [Importing Architecture](03-importing-architecture.md) | Bringing ports in from Excel, CSV, and Rhapsody exports |
| 4 | [Releases & Baselines](04-releases-and-baselines.md) | Managing software releases, baselines, and change detection across releases |
| 5 | [Test Case Design](05-test-case-design.md) | The Markdown scripting language, live preview, grouping, and exports |
| 6 | [Collaboration & Safety](06-collaboration-and-safety.md) | Edit locking, Test Mode, auto-save, and the change-history log |
| 7 | [AI Test Case Generation](07-ai-test-generation.md) | Connecting Copilot / Claude / OpenAI / Gemini and generating low-level test cases |
| 8 | [Advanced AI Chat](08-advanced-ai-chat.md) | Source mind maps, agentic source-grounded chat, requirements import, and release diffs |
| 9 | [Code Map](09-code-map.md) | The visual call-graph + source explorer joining the ELF to your C source |
| 10 | [Change Log](10-change-log.md) | Side-by-side release diffs and the AI change-log summary |

---

## What is this tool, in one paragraph?

Embedded teams maintain an architecture — ports, interfaces, operations — that's supposed to reflect what's actually compiled into the ECU. Keeping those two in sync is normally slow and manual. Architecture Validator Pro parses the compiled `.elf` binary, fuzzy-matches your architecture ports to the real symbols in the firmware, and gives you an editable table to review and sign off on everything. From there you can track changes between software releases, keep a reviewable history, and generate low-level test case designs straight from your data.

## A quick tour of the demo project

The screenshots throughout this guide come from a sample project ([`Resources/Demo/Demo_Project.arch`](../../Resources/Demo/Demo_Project.arch)) with two architecture models — `DoorControl_ECU` and `BatteryMgmt_ECU` — and two releases. Open it yourself to follow along.

---

➡️ Start with **[1. Getting Started](01-getting-started.md)**
