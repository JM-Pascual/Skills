---
name: new-diagram
description: Creates a D2 diagram of part of a codebase from a brief description of what to document, in a fixed house style, with automatic overlap checking. Use with /new-diagram <what to document>, or when asked to diagram, document or visualize something in the repo.
argument-hint: <brief description of what to document>
---

# new-diagram

Produce one diagram, or a small related set, written in D2, documenting what the user describes: `$ARGUMENTS`.

The description is the scope. Investigate only the parts of the repo relevant to it.

`<skill>` below means the folder this file is in (globally: `~/.claude/skills/new-diagram`).

## Principles

- **The look is fixed.** Every diagram uses the house style in `<skill>/assets/_style.d2`. Don't ask about colors, themes, fonts or sketch mode, and don't invent new styles.
- **Content is the user's call.** Scope, diagram type, level of detail, and anything that adds or removes information are agreed with the user.
- **Ground truth is code.** Never invent components or connections. Anything not evidenced in the code is drawn with the `inferred` / `inferred-edge` classes and a `?` in its label.
- **No overlaps.** Every render goes through `render-fit.sh`, which measures it. A diagram isn't done until the check passes *and* you have looked at the PNG.
- **D2 places everything.** Write semantic D2 (structure, containers, `direction`). Never use `top`/`left`, spacer nodes, or fixed sizes to push things apart.

## Workflow

### 1. Scope
- If `$ARGUMENTS` is empty, ask "What should this diagram document?" in one line, offering 2–3 examples from a quick look at the repo.
- If it's too broad ("everything", "the backend"), ask 1–2 narrowing questions: which flow, which level of abstraction, who the audience is.
- Restate the scope in one sentence and get a yes before investigating.

### 2. Preflight
- Run `d2 --version`. If d2 is missing, tell the user how to install it (macOS: `brew install d2`; elsewhere: `curl -fsSL https://d2lang.com/install.sh | sh -s --`) and stop. `python3` is also required.
- The diagram folder is `docs/diagrams/` unless the repo already keeps diagrams elsewhere; confirm it.
- If `<dir>/_style.d2` is missing, copy `<skill>/assets/_style.d2` there. If it exists and differs from the skill's copy, show the diff and ask which to keep. Never overwrite silently.

### 3. Investigate
- From the description, find the entrypoints, routes and handlers, modules, schemas, queues, configs, IaC and external SDK calls. Follow code paths only as far as the scope needs.
- Build an inventory of components, datastores, external systems, actors and connections (direction, protocol, sync/async), each with its source file.
- Mark anything you can't point to in code as inferred.
- If the scope turns out bigger or different than expected, say so and ask how to proceed.

### 4. Agree on the form
Propose 1–3 diagram types that fit, and say what each one emphasizes:
- context
- containers / deployment
- components
- data flow
- sequence
- ERD (`sql_table`)
- state machine
- agent / LLM orchestration
- CI/CD

The user picks the type, the level of detail, and whether it's one diagram or a set. For a set, finish the first diagram before starting the next.

### 5. Write the D2
- The file starts with `...@_style` and `...@_icons`, then a `# comment` saying what the diagram answers.
- Add a title, `title: … {class: title}`, and pick a `direction` (`right` for flows, `down` for hierarchies).
- **Node classes:** `svc`, `store`, `queue`, `actor`, `external`, `boundary` (containers), `critical` (the focus; use sparingly), `inferred`.
- **Edge classes:** sync is the default (no class), `async`, `critical-path`, `inferred-edge`.
- **Icons:** add a class from `<skill>/assets/icon-registry.tsv`, stacked after the style class, e.g. `class: [svc; aws-lambda]`. Only use an icon when the code names that technology. Rules: `references/icons.md`.
- **Syntax:**
  - Multiple classes are separated with `;`, never `,`.
  - Quote labels that contain brackets: `"publishes [SQS]"`.
  - Labels are verb phrases of at most 4 words.
  - Use stable kebab-case IDs that match the code, and add comments so people can edit the file.
- **Sequence diagrams:** `name: "" {shape: sequence_diagram}`, and every participant uses `svc` or `external` (no `actor`/`store` shapes).
- **Legend:** if the diagram uses more than the basic classes, add one horizontal strip with `class: legend`, swatches stacked with `legend-item`, and no title (see `examples/01-…`).
- **No inline `style.*`.** All styling comes from classes. If one is truly needed, ask first and note it in a comment.

### 6. Render and check
```bash
<skill>/scripts/render-fit.sh <dir>/<name>.d2
```
This script:
1. prepares the icons the diagram uses, on demand (from the repo, then the skill cache, then download, clean and validate)
2. renders at the tightest spacing tier that passes the overlap check
3. writes `<name>.svg` and `<name>.png`

- **On `FAIL`:** spacing can't fix it. Go down the crowding ladder in `references/layout.md`:
  1. group siblings
  2. merge or remove edges
  3. shorten labels
  4. change direction
  5. split the diagram

  Do structural fixes yourself. Ask before anything that changes content (removing detail, splitting, changing emphasis).
- **Always** open the PNG with Read and look at it, even after a `PASS`. The checker measures boxes and segments, not readability.

### 7. Review with the user
- Show the PNG. Collect feedback on content.
- Propose a file name derived from the description (e.g. `bank-statement-reconciliation.d2`). Never overwrite an existing diagram without asking; offer to update it instead.

### 8. Integrate
Ask where the diagrams should appear (README, docs site, wiki) and in which format (SVG or PNG). Commit `docs/diagrams/icons/`: the repo keeps its own icons. Offer a render script or CI check only if wanted, and do only what's agreed.

## References

- `references/layout.md`: spacing tiers, what the checker measures, the crowding ladder, patterns learned from the examples. Read it before your first render.
- `references/icons.md`: icon rules, sources, the code signals that justify an icon, how icons are cached and cleaned, how to add one.
- `examples/`: seven worked diagrams (data flow, containers, sequence, ERD, agent, CI/CD, state machine) that pass the checker. Copy their patterns.
