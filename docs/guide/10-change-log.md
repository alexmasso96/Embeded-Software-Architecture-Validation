# 10. Change Log

[← Code Map](09-code-map.md) · **Change Log** · [Next: Test Injection →](11-test-injection.md)

---

![Change Log](../../Media/images/change_log.png)

The **Change Log** shows what changed in the source between two releases — both as a precise side-by-side diff and, optionally, as an AI-written summary.

> 💡 **Preferences → Tutorials → Change Log & release diff** walks through it interactively.

## The layout

- **File list (left)** — every changed C/H file with a badge: **A** added, **M** modified, **D** deleted. Click one to open its diff.
- **Diff pane (centre)** — the old release on the left and the new one on the right, reconstructed from the stored release diff, with **synchronized scrolling** and git-style highlighting (removed lines red, added lines green, aligned so changes line up).
- **AI Summary (collapsible)** — a plain-language summary of the selected file's changes, generated on request (requires a connected provider and uses tokens).

## Computing the diff

Pick a **previous** release to compare against the active one, then **Compute Release Diff**. The app runs a file-by-file comparison and stores the per-file diffs in the project. The comparison is **stat-gated** — files whose size and timestamp match in both trees are skipped without being read — so it stays fast and friendly to the heavy-I/O constraints of locked-down build machines. Once computed, the result is cached, so re-opening it later is instant.

The stored diffs are reused here and are also available to the [AI Chat](08-advanced-ai-chat.md) agent via its `get_diff` tool, so you can ask "what changed in this file and why?" and get a grounded answer.

## Typical workflow

1. Make sure both releases have their **source imported** (see [Releases & Baselines](04-releases-and-baselines.md)).
2. Choose the previous release and **Compute Release Diff**.
3. Browse the changed files and review the side-by-side diff.
4. Optionally expand **AI Summary** for a human-readable description to attach to your release record.

---

[← Code Map](09-code-map.md) · [Guide home](README.md) · [Next: Test Injection →](11-test-injection.md)
