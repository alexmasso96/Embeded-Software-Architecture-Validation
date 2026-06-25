# 9. Code Map

[← AI Chat](08-advanced-ai-chat.md) · **Code Map** · [Next: Change Log →](10-change-log.md)

---

![Code Map](../../Media/images/code_map.png)

The **Code Map** is a visual explorer of your firmware's call graph plus a read-only IDE, joining what the compiled ELF knows (addresses, sizes, parameters, structs, globals) to your C source (which file defines each function, the call relationships, the body).

> 💡 **Preferences → Tutorials → Code Map & call graph** is an interactive tour.

## Where the data comes from

The map is built by joining two sources **by function name**:

- the **ELF / DWARF** facts from the loaded binary (verified addresses, sizes, parameter and return types, struct layouts, global types), and
- the **C source index** (which `.c` file defines each function, the caller/callee graph, and the body for the viewer).

The call-graph *edges* come from the source (DWARF has no call edges); the ELF side annotates each node with verified low-level facts. C++ names are demangled before matching. When a binary carries no call tree (stripped or relocatable objects often don't), the map falls back to the **source-derived** call graph automatically.

## Building / refreshing it

A Code Map is produced when you build the mind map in [AI Generation](07-ai-test-generation.md) with source imported for the release — it re-indexes the source and rebuilds the map **offline, with no AI tokens**. If no map exists yet for the selected model/release, the view points you to generate one.

## Using the view

- **Sidebar** — status badges for whether **Source** and a **Mind Map** are loaded, a function **search**, and the function list. Click a function to **focus** it.
- **Call graph (centre)** — the focused function sits in the middle; **Callers** are on the left, **Callees** on the right, colour-coded. Click any node to **re-center** on it and walk the tree node by node.
- **IDE panel** — the focused function's source, read-only and syntax-highlighted. Hover a symbol for its signature or `#define` value; **Ctrl-click** (Cmd-click on macOS) a symbol to focus it. A details card summarizes its callers and callees.

Source is read through the same sandboxed reader as the AI tools, so the viewer can only read files under the project's source root.

---

[← AI Chat](08-advanced-ai-chat.md) · [Guide home](README.md) · [Next: Change Log →](10-change-log.md)
