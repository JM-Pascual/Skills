#!/usr/bin/env python3
"""Fetch icons on demand, clean them for D2, and reuse what's already local.

Usage:
  icons.py ensure DIAGRAM.d2 [DIAGRAM.d2 ...]   make every icon class these diagrams use available
  icons.py check NAME [NAME ...]                 fetch/clean/validate specific classes (no diagram needed)

For each icon class a diagram uses (any class listed in assets/icon-registry.tsv),
looked up in this order:
  1. <diagram dir>/icons/<class>.svg|png      already in the repo: reuse it
  2. <skill>/assets/icons/<class>.svg|png     cleaned before, in another repo: copy it
  3. download the pinned URL, clean it, validate it with a real `d2` PNG render,
     store it in the skill cache, then copy it into the repo
Then <diagram dir>/_icons.d2 is regenerated from the icons present in <diagram dir>/icons/.

Cleaning fixes what D2's SVG importer (v0.9.0) rejects: <desc>/<title>/<metadata>,
editor namespaces, `isolation` and `enable-background`, radial gradients (turned into
linear ones), gradients outside <defs>, stops with no offset, gradients with no stops
(inherited via href), masks. Simple Icons get their brand colour as fill. An icon that
still fails validation is rasterised to PNG as a last resort.

Exit 0 when every icon is available, 1 when any couldn't be made to work.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(SKILL, "assets", "icon-registry.tsv")
# NEW_DIAGRAM_ICON_CACHE overrides the cache location (used for testing the whole registry).
CACHE = os.environ.get("NEW_DIAGRAM_ICON_CACHE") or os.path.join(SKILL, "assets", "icons")

SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", XLINK)
DROP_TAGS = {"desc", "title", "metadata", "mask", "filter"}
DROP_ATTRS = {"enable-background", "mask", "filter", "data-name", "overflow",
              "font-weight", "font-family", "font-size", "font-style"}
STYLE_OK = {"fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity",
            "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "stroke-dasharray",
            "stroke-dashoffset", "opacity", "stop-color", "stop-opacity", "clip-rule", "display",
            "visibility", "clip-path"}
MAX_BYTES = 65536  # D2 refuses icon SVGs larger than this


def local(tag):
    return tag.rsplit("}", 1)[-1]


def load_registry():
    reg = {}
    for line in open(REGISTRY, encoding="utf-8"):
        if line.startswith("#") or line.startswith("class\t") or not line.strip():
            continue
        name, _group, _source, url, color = (line.rstrip("\n").split("\t") + [""])[:5]
        reg[name] = {"url": url, "color": color}
    return reg


def used_classes(paths):
    names = set()
    for p in paths:
        text = open(p, encoding="utf-8").read()
        for m in re.finditer(r"class:\s*(\[[^\]]*\]|[\w-]+)", text):
            v = m.group(1).strip("[]")
            names.update(x.strip() for x in v.split(";") if x.strip())
    return names


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "new-diagram-skill"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def clean(text, color=""):
    text = re.sub(r"<!DOCTYPE[^>]*>", "", text)
    text = re.sub(r"<\?xml[^>]*\?>", "", text)
    root = ET.fromstring(text)

    # Drop editor/metadata elements and namespaced attributes D2 doesn't know.
    for parent in list(root.iter()):
        for child in list(parent):
            ns = child.tag[1:].split("}")[0] if child.tag.startswith("{") else SVG
            if local(child.tag) in DROP_TAGS or ns not in (SVG,):
                parent.remove(child)
    for el in root.iter():
        for a in list(el.attrib):
            ns = a[1:].split("}")[0] if a.startswith("{") else None
            if local(a) in DROP_ATTRS or (ns and ns not in (XLINK,)):
                del el.attrib[a]
        if "style" in el.attrib:
            parts = [p for p in el.attrib["style"].split(";")
                     if p.split(":")[0].strip() in STYLE_OK]
            if parts:
                el.attrib["style"] = ";".join(parts)
            else:
                del el.attrib["style"]

    # Collect every gradient wherever it sits.
    grads = {}
    for parent in list(root.iter()):
        for child in list(parent):
            if local(child.tag) in ("linearGradient", "radialGradient"):
                parent.remove(child)
                grads[child.get("id")] = child

    def stops(g, seen=()):
        own = [c for c in g if local(c.tag) == "stop"]
        if own:
            return own
        ref = (g.get("{%s}href" % XLINK) or g.get("href") or "").lstrip("#")
        if ref in grads and ref not in seen:
            return stops(grads[ref], seen + (ref,))
        return []

    fixed, solid = [], {}
    for gid, g in grads.items():
        st = stops(g)
        ref = (g.get("{%s}href" % XLINK) or g.get("href") or "").lstrip("#")
        base = grads.get(ref)
        lin = ET.Element("{%s}linearGradient" % SVG)
        lin.set("id", gid)
        src = g if base is None else base
        for a in ("gradientUnits", "gradientTransform"):
            v = g.get(a) or (base.get(a) if base is not None else None)
            if v:
                lin.set(a, v)

        if local(g.tag) == "radialGradient" or (base is not None and local(base.tag) == "radialGradient" and not g.get("x1")):
            # Approximate a radial gradient with a horizontal linear one across its circle.
            cx = float((g.get("cx") or src.get("cx") or "0.5").rstrip("%")) / (100 if "%" in (g.get("cx") or "") else 1)
            cy = float((g.get("cy") or src.get("cy") or "0.5").rstrip("%")) / (100 if "%" in (g.get("cy") or "") else 1)
            r = float((g.get("r") or src.get("r") or "0.5").rstrip("%")) / (100 if "%" in (g.get("r") or "") else 1)
            lin.set("x1", repr(cx - r)); lin.set("y1", repr(cy))
            lin.set("x2", repr(cx + r)); lin.set("y2", repr(cy))
        else:
            for a, default in (("x1", "0"), ("y1", "0"), ("x2", "1"), ("y2", "0")):
                v = g.get(a) or (base.get(a) if base is not None else None)
                if not v and not lin.get("gradientUnits") == "userSpaceOnUse":
                    v = default  # SVG's own defaults; D2 requires them spelled out
                if v:
                    lin.set(a, v)
        n = len(st)
        if n and lin.get("gradientUnits") != "userSpaceOnUse":
            # D2 only renders userSpaceOnUse gradients; use the first stop's colour instead.
            first = st[0]
            col = first.get("stop-color") or re.search(r"stop-color:\s*([^;]+)", first.get("style", "") or "")
            solid[gid] = col if isinstance(col, str) else (col.group(1).strip() if col else "#888888")
            continue
        for i, s in enumerate(st):
            ns = ET.SubElement(lin, "{%s}stop" % SVG)
            for k, v in s.attrib.items():
                ns.set(k, v)
            if not ns.get("offset"):
                ns.set("offset", "0" if n == 1 else repr(i / (n - 1)))
        if n == 0:
            continue  # unusable; references to it fall back below
        fixed.append(lin)

    if fixed:
        defs = root.find("{%s}defs" % SVG)
        if defs is None:
            defs = ET.Element("{%s}defs" % SVG)
            root.insert(0, defs)
        for g in fixed:
            defs.append(g)
    # Point references to dropped gradients at nothing D2 can't resolve.
    good = {g.get("id") for g in fixed}
    for el in root.iter():
        for a in ("fill", "stroke"):
            v = el.get(a) or ""
            m = re.match(r"url\(#([^)]+)\)", v)
            if m and m.group(1) not in good:
                el.set(a, solid.get(m.group(1), "#888888"))
        if "style" in el.attrib:
            el.attrib["style"] = re.sub(
                r"url\(#([^)]+)\)",
                lambda m: m.group(0) if m.group(1) in good else solid.get(m.group(1), "#888888"),
                el.attrib["style"])
    # Empty <defs> and <clipPath>s with overflow metadata confuse the importer.
    for parent in list(root.iter()):
        for child in list(parent):
            if local(child.tag) == "defs" and len(child) == 0:
                parent.remove(child)

    # "matrix(...)translate(...)" -> functions separated, as D2 requires.
    for el in root.iter():
        for a in ("transform", "gradientTransform", "patternTransform"):
            if a in el.attrib:
                el.attrib[a] = re.sub(r"\)\s*(?=[a-zA-Z])", ") ", el.attrib[a])

    # Keep only ids something references, and each id once.
    refs = set()
    for el in root.iter():
        for v in list(el.attrib.values()):
            refs.update(re.findall(r"url\(#([^)]+)\)", v))
            if v.startswith("#"):
                refs.add(v[1:])
    seen = set()
    for el in root.iter():
        i = el.get("id")
        if i is None:
            continue
        if local(el.tag) in ("linearGradient", "clipPath"):
            if i in seen:  # duplicate definition: give it a fresh id (nothing can reach it anyway)
                el.set("id", f"{i}-dup{len(seen)}")
        elif i not in refs or i in seen:
            del el.attrib["id"]
        seen.add(i)

    if color:
        root.set("fill", "#" + color)
    out = ET.tostring(root, encoding="unicode")
    if len(out.encode()) > MAX_BYTES:
        out = re.sub(r"(\d+\.\d{1})\d+", r"\1", out)  # one decimal is plenty at icon size
        out = re.sub(r">\s+<", "><", out)
    return out


def validate(icon_path):
    """Render a one-node diagram to PNG with D2; return None if fine, else the error."""
    with tempfile.TemporaryDirectory() as t:
        shutil.copy(icon_path, os.path.join(t, os.path.basename(icon_path)))
        with open(os.path.join(t, "v.d2"), "w") as f:
            f.write(f"x: X {{icon: {os.path.basename(icon_path)}}}\n")
        r = subprocess.run(["d2", "v.d2", "v.png"], cwd=t, capture_output=True, text=True)
        if r.returncode == 0:
            return None
        err = re.search(r"(d2svgimport.*|err: .*)", r.stderr)
        return err.group(1) if err else r.stderr.strip()[-200:]


def rasterise(svg_path, png_path):
    if shutil.which("rsvg-convert"):
        return subprocess.run(["rsvg-convert", "-w", "256", "-h", "256", "--keep-aspect-ratio",
                               svg_path, "-o", png_path]).returncode == 0
    if shutil.which("qlmanage"):
        with tempfile.TemporaryDirectory() as t:
            subprocess.run(["qlmanage", "-t", "-s", "256", "-o", t, svg_path], capture_output=True)
            out = os.path.join(t, os.path.basename(svg_path) + ".png")
            if os.path.exists(out):
                shutil.copy(out, png_path)
                return True
    return False


def find(dirpath, name):
    for ext in (".svg", ".png"):
        p = os.path.join(dirpath, name + ext)
        if os.path.exists(p):
            return p
    return None


def build(name, entry):
    """Download, clean, validate; return the cached file path or raise."""
    os.makedirs(CACHE, exist_ok=True)
    raw = fetch(entry["url"])
    svg_path = os.path.join(CACHE, name + ".svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(clean(raw, entry["color"]))
    err = validate(svg_path)
    if err is None:
        return svg_path, "downloaded"
    png_path = os.path.join(CACHE, name + ".png")
    if rasterise(svg_path, png_path) and validate(png_path) is None:
        os.remove(svg_path)
        return png_path, f"downloaded, rasterised to PNG ({err})"
    os.remove(svg_path)
    raise RuntimeError(err)


def ensure(names, reg, target):
    os.makedirs(os.path.join(target, "icons"), exist_ok=True)
    failed = 0
    for name in sorted(names):
        if name not in reg:
            continue
        here = find(os.path.join(target, "icons"), name)
        if here:
            print(f"  {name:28} reused   {os.path.relpath(here, target)}")
            continue
        try:
            cached = find(CACHE, name)
            how = "from skill cache"
            if not cached:
                cached, how = build(name, reg[name])
            dst = os.path.join(target, "icons", os.path.basename(cached))
            shutil.copy(cached, dst)
            print(f"  {name:28} {how}")
        except Exception as e:  # network, parse or render failure: report, keep going
            print(f"  {name:28} FAILED   {e}")
            failed += 1
    write_index(target)
    return failed


def write_index(target):
    icons = sorted(f for f in os.listdir(os.path.join(target, "icons")) if f.endswith((".svg", ".png")))
    lines = ["# _icons.d2: generated by new-diagram/scripts/icons.py from the icons in ./icons/. Do not edit.",
             "# Partial: imported by diagrams, never rendered on its own.", "classes: {"]
    lines += [f'  {os.path.splitext(f)[0]}.icon: "icons/{f}"' for f in icons]
    lines += ["}"]
    with open(os.path.join(target, "_icons.d2"), "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("ensure", "check"):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        sys.exit(2)
    reg = load_registry()
    if sys.argv[1] == "ensure":
        failed = 0
        by_dir = {}
        for p in sys.argv[2:]:
            by_dir.setdefault(os.path.dirname(os.path.abspath(p)), []).append(p)
        for d, files in by_dir.items():
            names = used_classes(files) & set(reg)
            rel = os.path.relpath(d)
            print(f"icons for {d if rel.startswith('..') else rel}: {len(names)} used")
            failed += ensure(names, reg, d)
    else:
        unknown = [n for n in sys.argv[2:] if n not in reg]
        if unknown:
            print("not in registry: " + ", ".join(unknown), file=sys.stderr)
        with tempfile.TemporaryDirectory() as t:
            failed = ensure(set(sys.argv[2:]) & set(reg), reg, t) + len(unknown)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
