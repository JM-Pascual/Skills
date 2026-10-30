#!/usr/bin/env python3
"""Measure a rendered D2 SVG for overlaps and tight clearances.

Usage: check_layout.py diagram.svg [--node-gap 16] [--label-gap 16] [--edge-gap 8] [--json]

Exit 0 when every check passes, 1 when any fails, 2 when the SVG can't be read
(e.g. D2 changed its output structure). Tested against D2 v0.9.0 SVG output,
which tags every element group with a base64 ID and draws edge labels into a
mask as exact rectangles.

Defaults: ELK (as bundled in D2 0.9.0) always leaves 20px between nodes in the
same layer, whatever the spacing flags, so --node-gap 16 flags shapes that are
closer than ELK's own minimum (i.e. really touching), not normal stacking.

Checks:
  node-gap    two shapes that aren't nested closer than --node-gap px
  padding     a child closer than --node-gap px to its container's border
  container   a container's label or icon overlapping one of its children
  label       an edge label box touching a shape or another edge label
  label-edge  an edge label within --edge-gap of another edge's line
  edge        an edge segment passing through or within --edge-gap of a shape
              that isn't its source, target, or one of their containers
"""
import argparse
import base64
import html
import json
import re
import sys

TOL = 0.5  # sub-pixel rounding slack


def box(x0, y0, x1, y1):
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def gap(a, b):
    """Distance between two boxes; negative means they overlap."""
    dx = max(b[0] - a[2], a[0] - b[2])
    dy = max(b[1] - a[3], a[1] - b[3])
    if dx < 0 and dy < 0:
        return max(dx, dy)
    return max(dx, 0) if dy < 0 else (max(dy, 0) if dx < 0 else (dx * dx + dy * dy) ** 0.5)


def path_points(d):
    """Absolute M/L/H/V/C/S/Q/A path -> list of points (D2 only emits absolute)."""
    pts, x, y = [], 0.0, 0.0
    for cmd, args in re.findall(r"([MLHVCSQTAZ])([^MLHVCSQTAZ]*)", d):
        nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", args)]
        if cmd in "MLT":
            for i in range(0, len(nums) - 1, 2):
                x, y = nums[i], nums[i + 1]
                pts.append((x, y))
        elif cmd == "H":
            for n in nums:
                x = n
                pts.append((x, y))
        elif cmd == "V":
            for n in nums:
                y = n
                pts.append((x, y))
        elif cmd in "CSQ":
            for i in range(0, len(nums) - 1, 2):
                x, y = nums[i], nums[i + 1]
                pts.append((x, y))
        elif cmd == "A":
            for i in range(0, len(nums) - 6, 7):
                x, y = nums[i + 5], nums[i + 6]
                pts.append((x, y))
    return pts


def edge_segments(d):
    """Edge path -> straight segments, using the end point of each command."""
    pts, x, y = [], 0.0, 0.0
    for cmd, args in re.findall(r"([MLS])([^MLS]*)", d):
        nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", args)]
        if len(nums) >= 2:
            x, y = nums[-2], nums[-1]
            pts.append((x, y))
    return list(zip(pts, pts[1:]))


def seg_box_gap(p, q, b):
    """Distance from a segment to a box, sampled along the segment."""
    best = float("inf")
    n = max(2, int(max(abs(q[0] - p[0]), abs(q[1] - p[1])) / 4))
    for i in range(n + 1):
        t = i / n
        x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        best = min(best, gap((x, y, x, y), b))
    return best


def parse_edge_id(raw):
    """'vpc.(match -> data.ledger)[0]' -> ('vpc.match', 'vpc.data.ledger')."""
    m = re.match(r"^(?:(.*)\.)?\((.+?) (?:->|<-|<->|--) (.+)\)\[\d+\]$", raw)
    if not m:
        return None
    prefix = m.group(1) + "." if m.group(1) else ""
    return prefix + m.group(2), prefix + m.group(3)


def load(svg_path):
    s = open(svg_path, encoding="utf-8").read()
    s = re.sub(r'href="data:[^"]+"', 'href=""', s)
    # D2's built-in vars.d2-legend draws scaled copies of nodes; drop that block.
    t = s.find(">Legend<")
    if t != -1:
        start = s.rfind("<rect", 0, s.rfind("drop-shadow", 0, t))
        end = s.find('<mask id="d2-', t)
        if 0 <= start < t < end:
            s = s[:start] + s[end:]
    shapes, edges, labels = {}, [], []

    # Element groups carry a base64 ID; inner groups like <g class="shape"> don't decode.
    groups = []
    for m in re.finditer(r'<g class="([A-Za-z0-9+/=]+)(?: [^"]*)?"', s):
        try:
            groups.append((m, html.unescape(base64.b64decode(m.group(1), validate=True).decode())))
        except Exception:
            continue
    # Sequence diagrams draw lifelines as "(seq.actor -- )[0]"; their actors sit on the frame by design.
    sequences = {m.group(1).rsplit(".", 1)[0] for _, raw in groups
                 for m in [re.match(r"^\((.+?) -- \)\[\d+\]$", raw)] if m and "." in m.group(1)}
    for i, (m, raw) in enumerate(groups):
        end = groups[i + 1][0].start() if i + 1 < len(groups) else len(s)
        body = s[m.end():end]
        ends = parse_edge_id(raw)
        if ends:
            pm = re.search(r'<path d="([^"]+)"[^>]*class="connection', body)
            tm = re.search(r'<text x="([\d.\-]+)" y="([\d.\-]+)"[^>]*>([^<]*)</text>', body)
            if pm:
                edges.append({
                    "id": raw, "src": ends[0], "dst": ends[1],
                    "segs": edge_segments(pm.group(1)),
                    "label": html.unescape(tm.group(3)) if tm else None,
                    "lx": float(tm.group(1)) if tm else None,
                })
            continue
        sm = re.search(r'<g class="shape" >(.*?)</g>', body, re.S)
        if not sm:
            continue
        el = sm.group(1)
        r = re.search(r'<rect x="([\d.\-]+)" y="([\d.\-]+)" width="([\d.]+)" height="([\d.]+)"', el)
        if r:
            x, y, w, h = map(float, r.groups())
            b = (x, y, x + w, y + h)
        else:
            pts = []
            for d in re.findall(r' d="([^"]+)"', el):
                pts += path_points(d)
            if not pts:
                continue
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            b = (min(xs), min(ys), max(xs), max(ys))
        # Text and icon drawn outside the shape box (person labels, container labels/icons)
        extras = []
        for im in re.finditer(r'<image href="" x="([\d.\-]+)" y="([\d.\-]+)" width="([\d.]+)" height="([\d.]+)"', body):
            x, y, w, h = map(float, im.groups())
            extras.append(("icon", (x, y, x + w, y + h)))
        tm = re.search(r'<text x="([\d.\-]+)" y="([\d.\-]+)"[^>]*font-size:(\d+)px[^>]*>([^<]*)</text>', body)
        if tm:
            tx, ty, fs = float(tm.group(1)), float(tm.group(2)), float(tm.group(3))
            tw = len(html.unescape(tm.group(4))) * fs * 0.55
            extras.append(("label", (tx - tw / 2, ty - fs, tx + tw / 2, ty + fs * 0.3)))
        shapes[raw] = {"box": b, "extras": extras, "name": html.unescape(tm.group(4)) if tm else raw}

    mask = re.search(r'<mask id="d2-\d+"[^>]*>(.*?)</mask>', s, re.S)
    if mask:
        for r in re.finditer(r'<rect x="([\d.\-]+)" y="([\d.\-]+)" width="([\d.]+)" height="([\d.]+)" fill="black"', mask.group(1)):
            x, y, w, h = map(float, r.groups())
            labels.append((x, y, x + w, y + h))
    for e in edges:  # attach exact label boxes by centre x
        if e["lx"] is None:
            continue
        cands = [l for l in labels if abs((l[0] + l[2]) / 2 - e["lx"]) < 1.0]
        e["lbox"] = cands.pop(0) if cands else None
        if e["lbox"]:
            labels.remove(e["lbox"])
    if not shapes:
        raise ValueError("no shapes found; D2 SVG structure may have changed")
    for i in sequences & set(shapes):
        shapes[i]["sequence"] = True
    return shapes, edges


def nested(a, b):
    return a.startswith(b + ".") or b.startswith(a + ".")


def ancestors(i):
    parts = i.split(".")
    return {".".join(parts[:k]) for k in range(1, len(parts))}


def check(shapes, edges, node_gap, label_gap, edge_gap):
    issues = []
    ids = list(shapes)
    containers = {i for i in ids if any(j.startswith(i + ".") for j in ids)}
    name = lambda i: shapes[i]["name"]

    for k, a in enumerate(ids):
        for b in ids[k + 1:]:
            A, B = shapes[a]["box"], shapes[b]["box"]
            if nested(a, b):
                parent, child = (a, b) if b.startswith(a + ".") else (b, a)
                P, C = shapes[parent]["box"], shapes[child]["box"]
                inner = min(C[0] - P[0], C[1] - P[1], P[2] - C[2], P[3] - C[3])
                if (inner < node_gap - TOL and child.count(".") == parent.count(".") + 1
                        and not shapes[parent].get("sequence")):
                    issues.append(("padding", f"{name(child)} is {inner:.0f}px from the border of {name(parent)}", inner))
                if parent in containers:
                    for kind, X in shapes[parent]["extras"]:
                        g = gap(X, C)
                        if g < label_gap - TOL:
                            issues.append(("container", f"{name(parent)} {kind} is {g:.0f}px from {name(child)}", g))
                continue
            g = gap(A, B)
            if g < node_gap - TOL:
                issues.append(("node-gap", f"{name(a)} <-> {name(b)}: {g:.0f}px", g))

    leaves = [i for i in ids if i not in containers]
    for e in edges:
        if not e.get("lbox"):
            continue
        L = e["lbox"]
        for i in ids:
            if i in containers:
                # a label may sit inside its container, but not on its label/icon
                for kind, X in shapes[i]["extras"]:
                    g = gap(L, X)
                    if g < label_gap - TOL:
                        issues.append(("label", f'"{e["label"]}" is {g:.0f}px from the {kind} of {name(i)}', g))
                continue
            for B in [shapes[i]["box"]] + [X for _, X in shapes[i]["extras"] if _ == "label"]:
                g = gap(L, B)
                if g < label_gap - TOL:
                    issues.append(("label", f'"{e["label"]}" is {g:.0f}px from {name(i)}', g))
                    break
    lab = [e for e in edges if e.get("lbox")]
    for k, e in enumerate(lab):
        for f in lab[k + 1:]:
            g = gap(e["lbox"], f["lbox"])
            if g < label_gap - TOL:
                issues.append(("label", f'"{e["label"]}" <-> "{f["label"]}": {g:.0f}px', g))

    for e in lab:  # a label sitting on someone else's line
        for f in edges:
            if f is e:
                continue
            g = min((seg_box_gap(p, q, e["lbox"]) for p, q in f["segs"]), default=float("inf"))
            if g < edge_gap - TOL:
                other = f'"{f["label"]}"' if f["label"] else f'{f["src"]} -> {f["dst"]}'
                issues.append(("label-edge", f'"{e["label"]}" is {g:.0f}px from edge {other}', g))

    for e in edges:
        skip = {e["src"], e["dst"]} | ancestors(e["src"]) | ancestors(e["dst"])
        for i in leaves:
            if i in skip:
                continue
            g = min((seg_box_gap(p, q, shapes[i]["box"]) for p, q in e["segs"]), default=float("inf"))
            if g < edge_gap - TOL:
                what = f'"{e["label"]}"' if e["label"] else f'{e["src"]} -> {e["dst"]}'
                issues.append(("edge", f"edge {what} passes {g:.0f}px from {name(i)}", g))

    issues.sort(key=lambda x: x[2])
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("svg")
    ap.add_argument("--node-gap", type=float, default=16)
    ap.add_argument("--label-gap", type=float, default=16)
    ap.add_argument("--edge-gap", type=float, default=8)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        shapes, edges = load(a.svg)
    except (OSError, ValueError) as err:
        print(f"check_layout: cannot read {a.svg}: {err}", file=sys.stderr)
        sys.exit(2)
    issues = check(shapes, edges, a.node_gap, a.label_gap, a.edge_gap)
    if a.json:
        print(json.dumps([{"check": c, "detail": d, "px": round(p, 1)} for c, d, p in issues], indent=2))
    else:
        print(f"{len(shapes)} shapes, {len(edges)} edges, {len(issues)} issue(s)")
        for c, d, _ in issues:
            print(f"  [{c}] {d}")
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
