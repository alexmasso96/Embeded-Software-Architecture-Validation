# 6. Collaboration & Safety

[← Test Case Design](05-test-case-design.md) · **Collaboration & Safety** · [Guide home](README.md)

---

Architecture data is often shared across a team and used for sign-off, so the tool has several features dedicated to not losing work and not stepping on each other.

## Edit modes & file locking

As covered in [Getting Started](01-getting-started.md), a project is opened either **View Only** or in **Exclusive Edit**:

- Entering **Exclusive Edit** acquires a lock on the project file.
- Anyone else who opens it sees that it's locked and **who holds the lock**, and can still open it View Only to browse safely.
- Releasing the lock (or closing) hands editing back to the team.

You can switch modes mid-session from the **Edit** menu (*Open in Exclusive Edit* / *Release Lock & Switch to View Only*), and there's a built-in *Help: Edit Modes* entry explaining the rules.

## Test Mode

**Test Mode** is a password-protected state for running through a project without risking accidental edits to your validated data. It requires a project **master password** to enter, and shows a clear red `TEST MODE` indicator in the status bar while active. Toggle it from **Options → Enter / Exit Test Mode**.

## Auto-save

So a crash or a forgotten *Save* never costs you work, auto-save runs on an interval you choose from the **Auto Save** menu:

- **Immediate**
- **1 / 5 / 15 minutes**
- **Do Not Auto Save**

## Change history (ASPICE-friendly)

Every modification to the architecture is recorded in a read-only **change log** — what changed, when, who did it, and in which model. Open it from the **History** menu:

![Change history log](../../Media/images/history.png)

Because the log is permanent and read-only, it gives you the traceability that process standards like ASPICE expect, without any extra bookkeeping on your part.

---

That's the full tour. 🎉

[← Test Case Design](05-test-case-design.md) · [Guide home](README.md)
