# Layout & spacing

Overlaps are the failure we care about most. Nodes touching, labels sitting on borders, and edges grazing boxes make a diagram unusable, however good it looks otherwise. The house layout trades compactness for room.

The model never positions anything. Spacing comes from two places only:
1. the engine settings below (always on)
2. structure (the "crowding ladder" below, used when a render is still crowded)

## Adaptive spacing: as tight as possible, as roomy as needed

Layout engine: **ELK**. Never pick spacing by eye. Render with `scripts/render-fit.sh diagram.d2`, which:

1. renders at the **compact** tier
2. measures the SVG with `scripts/check_layout.py`
3. stops at the first tier with zero issues; otherwise moves up a tier and repeats
4. if **roomy** still fails, exits 1 with the issues listed. Spacing can't fix those, so go to the crowding ladder below, change the structure, and run `render-fit.sh` again

| Tier | `--elk-nodeNodeBetweenLayers` | `--elk-edgeNodeBetweenLayers` | `--elk-padding` |
|---|---|---|---|
| compact (D2 defaults) | 70 | 40 | `[top=50,left=50,bottom=50,right=50]` |
| medium | 85 | 50 | `[top=60,left=55,bottom=55,right=55]` |
| roomy | 100 | 60 | `[top=70,left=60,bottom=60,right=60]` |

These are CLI-only flags; D2 rejects them in `vars.d2-config`.

What `check_layout.py` measures, with its thresholds:

| Check | Fails when |
|---|---|
| `node-gap` | two shapes that aren't nested are < 16px apart. ELK always leaves exactly 20px between nodes in the same layer, so this catches real touching only |
| `padding` | a child is < 16px from its container's border |
| `container` | a container's label or icon is < 16px from a child |
| `label` | an edge label is < 16px from a shape, or touching another label |
| `label-edge` | an edge label is < 8px from *another* edge's line |
| `edge` | an edge passes < 8px from a shape it doesn't connect |

Exit codes: 0 means clean, 1 means issues, 2 means it couldn't parse the SVG (D2 changed its output; tested against 0.9.0). The script ignores D2's built-in legend block.

Results on the test diagrams:
- 2 actors → 1 service: passed at compact
- bank reconciliation, left-to-right, 8 edges: passed at compact
- dense 13-edge diagram: needed roomy ("writes matches" sat inside Redis cache at compact, and 10px from it at medium)
- the same diagram top-down: failed at every tier, because of labels inside nodes. Switching to `direction: right` (ladder step 4) made it pass at compact

In `_style.d2`: `vars.d2-config.pad: 60` (space around the whole diagram).

What was tested (D2 0.9.0, a 13-edge diagram with nested containers):
- Raising the between-layer spacing further (200 / 120) only made the diagram wider. It did **not** separate nodes stacked in the same column.
- dagre with wide `nodesep` / `edgesep` spaced columns better but produced curved, crossing edges and lost the left-to-right reading order. Don't switch to dagre to get more space.

## What the engine can't fix: crowding inside a column

D2's ELK exposes no setting for the gap between nodes in the *same* layer (ELK's `spacing.nodeNode`). When several nodes share a column, especially many sinks that one node fans out to, they stack tightly and edge labels land on borders. Fix it with structure. Work down this ladder and stop at the first step that clears it:

1. **Group siblings that share a real role** into a `boundary` container, e.g. "Data stores", "Third-party APIs" or "Notifications". Container padding then forces a gap around and between them. This fixed the test diagram on its own. Group only when the grouping is true in the code.
2. **Remove redundant edges.** Merge parallel edges between the same pair, and drop edges the diagram's question doesn't need. Removing detail is a content change, so ask first.
3. **Shorten edge labels** to at most 4 words. Long labels widen the gaps edges must pass through.
4. **Change `direction`** (`right` ↔ `down`) so the long chain runs along the long axis.
5. **Split the diagram** (separate files, or `layers`). This is a content change, so ask first.

Never:
- add invisible spacer nodes or edges
- use `top` / `left` / absolute positions
- set fixed `width`/`height` to push things apart. The one fixed size in the house style is the `actor` class (56×72). It exists only because D2 stretches `shape: person` to the label's width, not to create spacing
- switch the engine only to get spacing

## Patterns learned from the examples (`examples/`)

- **Merge fan-outs into a group.** An agent calling three tools as three edges routed one edge through a datastore. A single `agent -> tools: calls` edge into the Tools container fixed it, and it says the same thing.
- **Draw edges the way data flows.** "Argo CD watches the manifests repo" drawn `argocd -> repo` became a backward edge that looped around the whole diagram. `repo -> argocd: "pulled by Argo CD"` lays out left to right. Genuine replies (webhooks back to the caller) will still loop; that's acceptable as long as nothing collides.
- **Dropping a label can make things worse.** Removing a label re-runs the layout from scratch, so always re-check.
- **Sequence diagrams:** give the container an empty label (`flow: "" {shape: sequence_diagram}`) and use box classes (`svc`, `external`) for every participant. `actor` (person) and `store` (cylinder) render oversized there.
- **Legend:** one horizontal strip (`near: bottom-center`, `grid-rows: 1`, no title) with swatches at `legend-item` size. A vertical legend made the bank example twice as tall.

## Checking a render for overlaps

`check_layout.py` is the gate. After it passes, still open the PNG and look. The script measures boxes and straight segments; it can't judge readability. Look for:
- two node borders closer than about one label height, or touching
- an edge label overlapping a node border, an icon or another label
- an edge running along a node border, or through a node
- a container label or icon colliding with a child node
- an arrowhead hidden inside a node

Any hit means: go down the crowding ladder, re-render, look again. Report what was changed.
