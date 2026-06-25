# 5. Test Design

[← Releases & Baselines](04-releases-and-baselines.md) · **Test Design** · [Next: Collaboration & Safety →](06-collaboration-and-safety.md)

---

Writing test cases by hand, one port at a time, is exactly the kind of repetitive work this tool exists to remove. The **Test Design** view lets you author a template once and generate consistent test-case documents across every port in your architecture.

![Test Design with live preview](../../Media/images/testcase_design_tab.png)

> 💡 **Preferences → Tutorials → Test Design templates** walks through this interactively.

The screen is split in two: you write your **Design Template** on the left (with a **Project Title** field above it), and a **live preview** on the right shows exactly how it renders for a real row from your matrix — paged row by row, updating as you type.

## The template language

Templates are plain **Markdown** with two small additions, so there's almost nothing new to learn. Everything you already know — headings, bold/italic, lists, checkboxes, blockquotes, code spans — just works.

### 1. Column tokens

Wrap any column name in square brackets and it's replaced with that row's value:

```markdown
## Verify `[Input Port]` in *[Model]*
- [ ] Set a breakpoint in `[Mapped Symbol]`
```

The special token `[Model]` resolves to the current architecture model's name. Type `[` in the editor and an **autocomplete** list of your columns pops up.

### 2. Conditional blocks (`#if`)

Show or hide content per row depending on its data:

```markdown
#if [Init] is equal 'Yes' {
- [ ] Confirm the symbol is reached once during initialisation
}
```

Supported operators are `contains`, `does not contain`, `is equal`, and `is not equal` (all case-insensitive). Combine conditions with `AND` / `OR`, and nest blocks as deeply as you like. There's also a `multiple` count predicate for reacting to how many operations a grouped test case represents.

Autocomplete helps here too — after a column token, a space offers operators; after an operator, a space offers values seen in that column.

## Operation grouping

The **Operation grouping** selector controls how rows become test cases:

- **Per port** — one test case per port, with that port's operations collapsed together.
- **Per operation** — one test case per operation.

The live preview respects whichever mode you pick, so what you see is what you'll get, and the pager count updates to match.

## Generating & exporting

When you're happy, export the result:

- **Export Test Cases** — just the current architecture model, or
- **Export All Models** — every model in the project at once.

Output is written as Markdown (`.md`), ready to drop into your documentation or version control. Retired and Deleted ports are skipped automatically, so generated output only ever covers live ports. These high-level design files are also what the [AI Generation](07-ai-test-generation.md) view reads to produce low-level tests.

---

[← Releases & Baselines](04-releases-and-baselines.md) · [Guide home](README.md) · [Next: Collaboration & Safety →](06-collaboration-and-safety.md)
