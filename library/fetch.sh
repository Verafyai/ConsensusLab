#!/usr/bin/env bash
# Fetch the Season 0 papers into library/pdfs/ (gitignored) and verify their SHA-256 pins.
# Uses a local copy when CL_LIBRARY_SRC points at the Collective's private PDF folder,
# otherwise downloads the pinned arXiv versions.
set -euo pipefail
cd "$(dirname "$0")"; mkdir -p pdfs; fail=0
SRC="${CL_LIBRARY_SRC:-$HOME/Desktop/Collective/Collective/private/library/pdfs}"
sha() { (command -v sha256sum >/dev/null && sha256sum "$1" || shasum -a 256 "$1") | awk '{print $1}'; }
while read -r name url want; do
  [[ -z "$name" || "$name" == \#* ]] && continue
  if [ ! -f "pdfs/$name" ]; then
    if [ -f "$SRC/$name" ]; then cp "$SRC/$name" "pdfs/$name"
    else echo "fetching $name"; curl -sfL -A "consensus-lab" -o "pdfs/$name" "$url"; sleep 3; fi
  fi
  got="$(sha "pdfs/$name")"
  if [ "$got" = "$want" ]; then echo "ok   $name"; else echo "BAD  $name (hash mismatch)"; fail=1; fi
done < MANIFEST
exit $fail
