#!/usr/bin/env bash
# Gate 4.4 LR-3/LR-6 teeth check for dev-modules.
# Proves green -> injected red for both rules -> restored green deterministically.
set -euo pipefail
cd "$(dirname "$0")/../.."

FIXTURE="docs/reviews/fixtures/2026-07-06-kit-lint-lr3-lr6-teeth.md"
CHECK="./scripts/check-kit-lint.sh"
TMPDIR="$(mktemp -d)"
BACKUP="$TMPDIR/fixture.md"
GREEN1="$TMPDIR/green-1.json"
GREEN2="$TMPDIR/green-2.json"
RED="$TMPDIR/red.json"
RESTORED="$TMPDIR/restored.json"

cleanup() {
  if [[ -f "$BACKUP" ]]; then
    cp "$BACKUP" "$FIXTURE"
  fi
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

cp "$FIXTURE" "$BACKUP"

"$CHECK" > "$GREEN1"
"$CHECK" > "$GREEN2"
cmp -s "$GREEN1" "$GREEN2"

python3 - "$GREEN1" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1]))
summary = payload["summary"]
if summary["exit"] != 0 or summary["counts_by_class"] != {} or payload["findings"] != []:
    raise SystemExit(f"expected green at rest, got {summary!r}")
PY

cat >> "$FIXTURE" <<'EOF'

Injected red reference: [missing target](missing-target.md).
Injected red scaffolding token: TODO.
EOF

"$CHECK" > "$RED"

python3 - "$RED" "$FIXTURE" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1]))
fixture = sys.argv[2]
summary = payload["summary"]
counts = summary["counts_by_class"]
if counts.get("dead-path") != 1 or counts.get("scaffolding-token") != 1:
    raise SystemExit(f"expected LR-3 dead-path=1 and LR-6 scaffolding-token=1, got {counts!r}")
hits = {(item["class"], item["path"]) for item in payload["findings"]}
expected = {("dead-path", fixture), ("scaffolding-token", fixture)}
if hits != expected:
    raise SystemExit(f"expected only fixture findings {expected!r}, got {hits!r}")
PY

cp "$BACKUP" "$FIXTURE"
"$CHECK" > "$RESTORED"
cmp -s "$GREEN1" "$RESTORED"

python3 - "$GREEN1" "$RED" "$RESTORED" <<'PY'
import hashlib
import json
import sys

green, red, restored = sys.argv[1:]
def digest(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()
payload = {
    "green_hash": digest(green),
    "red_hash": digest(red),
    "restored_hash": digest(restored),
    "green_summary": json.load(open(green))["summary"],
    "red_summary": json.load(open(red))["summary"],
}
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
PY
