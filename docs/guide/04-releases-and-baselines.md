# 4. Releases & Baselines

[← Importing Architecture](03-importing-architecture.md) · **Releases & Baselines** · [Next: Test Case Design →](05-test-case-design.md)

---

Firmware evolves, and so does the architecture that maps onto it. Releases and baselines are how Architecture Validator Pro keeps validation honest across that change.

## Software releases

A **release** represents one software build, and carries its own ELF binary data. A project can hold many releases at once. Open the release dialog from **Select Software Release** in the workspace:

![Release selection dialog](../../Media/images/release_selection.png)

From here you can:

| Action | What it does |
|--------|--------------|
| **Select / Load** | Make a release active — the table re-matches against that build's symbols |
| **Add New Release** | Bring in another ELF as a new release |
| **Rename / Delete** | Manage the release list |
| **Create Result Column** | Add a per-release validation-result column to the table |
| **Link Last Result** | Track the most recent result across releases in one column |
| **Create Baseline** | Snapshot the current release (see below) |

Only the active release is held in memory, so projects with many large ELF builds stay responsive.

## Baselines

A **baseline** is an immutable snapshot of a release at a point in time — your reference of record. Once created, it can't be edited, which is exactly what you want for a signed-off state. You can keep several baselines and browse them all from **Options → View All Baselines**.

## Change detection

This is the payoff. Ask the tool to compare the current data against a baseline, and it highlights what's changed with **colour-coded cells**. You then **approve or reject** each difference, so a new software release can't quietly drift away from your reviewed architecture without someone signing off on the change.

The per-release result columns build on this: each release gets its own column recording whether that port validated, and the *Last Result* column rolls the latest outcome up so you can see the current status without hunting through history.

---

[← Importing Architecture](03-importing-architecture.md) · [Guide home](README.md) · [Next: Test Case Design →](05-test-case-design.md)
