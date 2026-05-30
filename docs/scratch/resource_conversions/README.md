# Prismata Click-Conversion Graph

Visualises all 14 units whose click consumes one resource and produces another.

## Files

- `graph.dot` — Graphviz source. Prettier auto-layout; recommended for SVG output.
- `graph.mmd` — Mermaid source. Renders in more places without install.

## Rendering

### Graphviz (DOT)

**Online (zero install):**
- Paste `graph.dot` into <https://edotor.net> or <https://dreampuf.github.io/GraphvizOnline/>
- Download as SVG / PNG

**Local:**
```bash
winget install graphviz   # or: choco install graphviz
dot -Tsvg graph.dot -o graph.svg
dot -Tpng graph.dot -o graph.png
```

### Mermaid

**Online:** Paste `graph.mmd` into <https://mermaid.live> and export.

**VS Code:** install the *Markdown Preview Mermaid Support* extension, embed in a `.md` file inside a ` ```mermaid ` fenced block.

**GitHub:** any `.md` with a ` ```mermaid ` block renders natively.

## Graph notes

- **Blue is a pure sink** — no unit clicks Blue to produce another resource.
- **Zemora** is the only conversion with multiple output resources (Green → Gold + Attack), so its arrow is split into two in the diagram. The Green → Attack edge is dashed to flag the "shared with the Green → Gold edge" relationship.
- **No backward arrows** — the canonical partial order `Energy → Green → Blue ◇ Red → Attack → Gold` is respected by every unit.
