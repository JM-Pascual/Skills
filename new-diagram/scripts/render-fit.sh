#!/usr/bin/env bash
# Render one diagram with the tightest spacing tier that passes check_layout.py.
#
# Usage: render-fit.sh diagram.d2 [out-dir]
#
# Tries compact -> medium -> roomy. Stops at the first tier with no issues and
# writes <name>.svg + <name>.png to out-dir (default: next to the .d2 file).
# Exit 0 = clean render; 1 = still failing at roomy (the issues printed need a
# structural fix, see references/layout.md); 2 = render or tooling error.
set -euo pipefail

src=${1:?usage: render-fit.sh diagram.d2 [out-dir]}
out=${2:-$(dirname "$src")}
name=$(basename "$src" .d2)
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# tier | nodeNodeBetweenLayers | edgeNodeBetweenLayers | container padding
tiers=(
  "compact|70|40|[top=50,left=50,bottom=50,right=50]"
  "medium|85|50|[top=60,left=55,bottom=55,right=55]"
  "roomy|100|60|[top=70,left=60,bottom=60,right=60]"
)

# PNG for visual review. D2's own rasterizer rejects some icon SVGs (gradients,
# masks, <desc>...), so fall back to converting the finished SVG.
png() {
  local svg=$1 dst=$2
  if d2 "${flags[@]}" "$src" "$dst" >"$tmp/png.log" 2>&1; then return 0; fi
  echo "warn: d2 PNG export failed: $(grep -o 'd2svgimport.*' "$tmp/png.log" | head -1); converting the SVG instead" >&2
  if command -v rsvg-convert >/dev/null; then
    rsvg-convert -z 2 "$svg" -o "$dst"
  elif command -v qlmanage >/dev/null && command -v sips >/dev/null; then
    # Quick Look renders into a square canvas; crop back to the SVG's aspect ratio.
    local wh w h
    wh=$(grep -o 'viewBox="[^"]*"' "$svg" | head -1 | awk -F'[ "]' '{print $4, $5}')
    read -r w h <<<"$wh"
    qlmanage -t -s 3000 -o "$tmp" "$svg" >/dev/null 2>&1
    if (( ${w%.*} >= ${h%.*} )); then
    # offset "0 0" means "unset" to sips (it then crops from the centre); 1px off is harmless
      sips -c "$(( 3000 * ${h%.*} / ${w%.*} ))" 3000 --cropOffset 1 1 "$tmp/$(basename "$svg").png" --out "$dst" >/dev/null
    else
      sips -c 3000 "$(( 3000 * ${w%.*} / ${h%.*} ))" --cropOffset 1 1 "$tmp/$(basename "$svg").png" --out "$dst" >/dev/null
    fi
  else
    echo "error: no PNG fallback available (install librsvg for rsvg-convert)" >&2
    return 2
  fi
}

# Make every icon class the diagram uses available locally (reuse, else fetch + clean).
if ! python3 "$here/icons.py" ensure "$src"; then
  echo "error: some icons could not be prepared (see above)" >&2
  exit 2
fi

for t in "${tiers[@]}"; do
  IFS='|' read -r tier nn en pad <<<"$t"
  flags=(--layout elk --elk-nodeNodeBetweenLayers "$nn" --elk-edgeNodeBetweenLayers "$en" --elk-padding "$pad")
  echo "== $tier (layers $nn, edges $en, padding $pad)"
  if ! d2 "${flags[@]}" "$src" "$tmp/$name.svg" >"$tmp/log" 2>&1; then
    cat "$tmp/log" >&2
    exit 2
  fi
  set +e
  python3 "$here/check_layout.py" "$tmp/$name.svg"
  rc=$?
  set -e
  [[ $rc -eq 2 ]] && exit 2
  if [[ $rc -eq 0 ]]; then
    mkdir -p "$out"
    cp "$tmp/$name.svg" "$out/$name.svg"
    png "$out/$name.svg" "$out/$name.png"
    echo "PASS at $tier -> $out/$name.svg, $out/$name.png"
    exit 0
  fi
  last=$tier
  cp "$tmp/$name.svg" "$tmp/$name.$tier.svg"
done

mkdir -p "$out"
cp "$tmp/$name.$last.svg" "$out/$name.svg"
png "$out/$name.svg" "$out/$name.png"
echo "FAIL at $last: spacing alone can't clear these. Apply the crowding ladder (references/layout.md)."
exit 1
