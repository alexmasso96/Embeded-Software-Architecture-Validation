# 3. Importing Architecture

[← The Workspace](02-validation-workspace.md) · **Importing Architecture** · [Next: Releases & Baselines →](04-releases-and-baselines.md)

---

Rather than type ports in by hand, you can import them from a spreadsheet or an architecture-tool export. The importer auto-detects the format and routes it to the right flow.

Open the **Import** toolbar icon in the title bar and pick your file. The import wizard analyses it, shows you a preview, and creates the models and ports.

## Supported formats

### Excel / CSV
Standard spreadsheets are supported (`.xlsx`, `.xls`, `.csv`). In the classic **sheet-per-model** layout, each worksheet becomes its own architecture model and its rows become ports — handy when you maintain your architecture in Excel.

### Rhapsody path-based exports
Exports from IBM Rhapsody, where the architecture is encoded as hierarchical paths, are **detected automatically**. The tool reads the path structure, works out which model each port belongs to, and pulls out the operations associated with each interface. The wizard then lets you:

- **Preview** the models and ports that will be created before committing.
- **Choose which models** to import.
- **Map the relevant columns** (such as the required-interface and operations columns) when they can't be inferred.

A large Rhapsody export becomes a populated, model-organised project in a couple of clicks instead of a manual re-keying exercise. Because a Rhapsody export embeds many packages in one path column, the split into per-model row sets happens server-side in a single step.

## After importing

Imported ports land as rows in the [Workspace](02-validation-workspace.md). From there the fuzzy matcher proposes symbol mappings against the loaded ELF release, and you review them as normal.

> **Tip:** Import is additive and model-aware — re-importing an updated export tops up the right models rather than flattening everything into one.

---

[← The Workspace](02-validation-workspace.md) · [Guide home](README.md) · [Next: Releases & Baselines →](04-releases-and-baselines.md)
