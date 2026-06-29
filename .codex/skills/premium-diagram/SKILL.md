---
name: premium-diagram
description: Generate premium, modern, enterprise-grade engineering diagrams and visual architecture assets. Use when the user asks Codex to create, redesign, audit, or export architecture diagrams, workflow diagrams, state machine diagrams, Artifact flow diagrams, README overview visuals, technical sharing infographics, SVG/HTML/CSS diagram boards, Mermaid drafts, or PNG exports for project documentation. Always prefer code-backed, editable, high-end visuals over traditional flowcharts.
---

# Premium Diagram

Use this skill to create high-end engineering visual assets that are accurate to the current project code and suitable for README, documentation, product pages, and technical talks.

## When To Use

Use this skill for:

- System architecture diagrams.
- Runtime or business workflow diagrams.
- State machine diagrams.
- Artifact / data flow diagrams.
- README homepage overview graphics.
- Technical sharing or whitepaper infographics.
- Redesigning existing diagrams that feel crowded, traditional, or visually weak.
- Exporting editable SVG/HTML diagrams and PNG screenshots from those sources.

## Output Priority

Prefer outputs in this order:

1. **HTML + CSS** for premium board-style visuals, product-page architecture sections, dense but polished overview graphics, or PNG screenshot export.
2. **Hand-written SVG** for precise, editable, documentation-ready architecture diagrams.
3. **Mermaid** only as a draft, content scaffold, or quick discussion artifact.

Rules:

- Do not use Mermaid default styling as the final output.
- Do not screenshot a default Mermaid graph as a finished diagram.
- If PNG is needed, export it from the finished SVG or HTML/CSS source.
- Preserve the editable source file next to exported images.
- Keep final artifacts under the user-requested docs path when provided.

## Visual Principles

Aim for a premium engineering product visual language:

- High-end, modern, enterprise-grade, clean, structured.
- Looks like a mature SaaS infrastructure product or technical whitepaper, not a classroom flowchart.
- Clear sections and hierarchy.
- Strong main story line.
- Few, meaningful connector lines.
- Short labels and spacious cards.
- Grid-based layout with consistent alignment.
- Balanced whitespace; avoid both empty deserts and crowded clusters.
- Consistent color palette and card component system.
- Consistent simple icon style, using geometry or inline SVG when useful.
- Clean Chinese typography with explicit fallback:

```css
font-family: "Inter", "SF Pro Display", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
```

Recommended palette:

- Navy / blue-slate for titles and primary emphasis: `#172033`, `#1E2A44`, `#334155`.
- White and light blue-gray backgrounds: `#FFFFFF`, `#F8FAFC`, `#EEF4FA`.
- Cool gray-blue borders: `#CBD5E1`, `#D8E0EA`.
- Soft green for orchestration, success, ready states.
- Soft amber for approval, waiting, human-required states.
- Soft red only for failure, blocking, repair paths.
- Soft violet for Artifact / data contract cards.
- Pale cyan for storage / SQLite.
- Gray dashed style for Planned or placeholder capabilities.

## Content Discipline

Before drawing, decide what belongs in the image and what belongs in text below it.

Put in the diagram:

- The main narrative.
- 5 to 8 major areas or stages.
- Important boundaries and source-of-truth relationships.
- Only the essential modules or states the viewer must remember.

Move to documentation:

- Full CLI command lists.
- Full YAML schema fields.
- SQLite table field details.
- Every Python class, function, or file dependency.
- Gate runner subprocess details.
- Long explanations, caveats, and edge cases.

Use short labels:

- One title line.
- One subtitle line.
- At most 2 or 3 keywords per card.

## Planned Capabilities

Never mix planned capabilities with implemented capabilities.

- Show planned or placeholder features only when they help explain the boundary.
- Use dashed borders, lower contrast, and a clear `Planned` or `placeholder` label.
- Keep planned items off the main path.
- Do not invent future features that the code or docs do not mention.

## Prohibitions

Do not:

- Generate traditional low-quality flowcharts.
- Generate crowded node-link diagrams.
- Generate spiderweb architecture maps.
- Generate garbled Chinese text.
- Put large Chinese paragraphs inside the graphic.
- Put all information into one giant diagram.
- Draw current-code capabilities that do not exist.
- Present SQLAlchemy storage, automatic PR creation, remote push, automatic merge, or notification approval as implemented unless the current code proves it.
- Use external images or network assets unless explicitly requested.
- Let lines run through cards or cross heavily.
- Use high-saturation rainbow palettes, decorative blobs, or gratuitous gradients.

## Workflow

Follow this workflow for substantial diagram work:

1. **Audit current code and docs**
   - Read the relevant architecture inventory, README, workflow docs, source modules, configs, and tests.
   - Verify unstable or implementation-specific facts from current code.
   - Identify implemented, partial, and Planned capabilities.

2. **Content noise reduction**
   - List what must be visible.
   - List what belongs in captions or Markdown.
   - Merge low-level modules into higher-level areas.
   - Split the diagram if one canvas would become crowded.

3. **Information architecture**
   - Define the role of each diagram:
     - Overview: product positioning and module boundaries.
     - Runtime flow: user goal to deliverable evidence.
     - Artifact/state: source-of-truth files, persistence, and status transitions.
   - Choose a layout pattern:
     - Layered architecture cards.
     - Horizontal stage flow.
     - Swimlanes.
     - Card matrix.
     - Center main line with side notes.

4. **Generate editable visual source**
   - Prefer HTML/CSS or hand-written SVG.
   - Use one consistent component system.
   - Use explicit Chinese font fallback.
   - Use short, natural Chinese labels with essential English technical terms.

5. **Export PNG when requested**
   - Use browser screenshot, `rsvg-convert`, or `inkscape`.
   - Export from the final SVG/HTML source, not from a rough Mermaid draft.

6. **Verify before completion**
   - Parse SVG as XML when SVG is produced.
   - Render HTML/SVG in a browser when visual fidelity matters.
   - Check text bounds and screenshots when possible.
   - Report any limitations honestly.

## Self-Check Checklist

Before saying the diagram is complete, check:

- Chinese text is readable and not garbled.
- Font fallback is specified.
- Cards do not overlap.
- Text does not overflow its card.
- Margins and whitespace are balanced.
- The main path is visually obvious.
- There are no severe crossing lines.
- Connector lines are few and meaningful.
- The diagram is not overloaded with text.
- The diagram reflects current real project capabilities.
- Planned or placeholder abilities are clearly labeled and visually weaker.
- No non-existent capabilities are shown as implemented.
- The editable source file exists.
- PNG exports, if requested, were generated from the editable source.

## Recommended Diagram Set

For an engineering project, prefer this set over one giant diagram:

1. **System Overview**
   - Purpose: explain what the project is and its main architecture boundaries.
   - Include: entry points, orchestration, core services, execution, quality loop, artifacts, storage, repository.
   - Exclude: full command lists, schema fields, every class.

2. **Runtime Flow**
   - Purpose: explain how a user goal becomes a verified deliverable.
   - Include: main stages, key branches, repair loop, human control points, delivery states.
   - Exclude: storage internals, backend factory details, schema fields.

3. **Artifact / State Flow**
   - Purpose: explain deterministic handoff, persistence, and recovery.
   - Include: fixed Artifact chain, repair artifacts, RunStatus, checkpoint, storage tables by name.
   - Exclude: YAML field details, service methods, low-level Git internals.

## Example Invocation Prompts

Use prompts like:

```text
Use the premium-diagram skill. Based on the current code and docs/architecture/architecture_inventory.md, generate a high-end SVG system overview for this project. Do not use Mermaid as final output. Keep labels short, mark Planned capabilities clearly, and export PNG if possible.
```

```text
Use premium-diagram to redesign the current architecture diagrams. First audit what is overcrowded, then rebuild the information architecture, then generate editable SVG or HTML/CSS assets with browser-verified PNG exports.
```

```text
Use the premium-diagram skill to create a README hero architecture board as HTML + CSS. It should look like a modern SaaS infrastructure product visual, with clean Chinese typography and no traditional flowchart styling.
```
