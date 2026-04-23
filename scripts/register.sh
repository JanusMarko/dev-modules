#!/usr/bin/env bash
# register.sh — atomically install a module manifest at .modules/<name>/module.toml
#
# Usage:
#   scripts/register.sh <name> < /path/to/module.toml
#   cat module.toml | scripts/register.sh <name>
#
# The repo root is the nearest ancestor of $PWD that already contains a
# .modules/ directory. If none is found, .modules/ is created in $PWD.

set -euo pipefail

name="${1:?usage: register.sh <name> < module.toml}"

# Find or decide on the repo root.
root="$PWD"
while [[ "$root" != "/" && ! -d "$root/.modules" ]]; do
  root="$(dirname "$root")"
done
if [[ "$root" == "/" ]]; then
  root="$PWD"
fi

dir="$root/.modules/$name"
mkdir -p "$dir"

# Atomic write: temp file in the same directory, then rename.
tmp="$(mktemp "$dir/.module.toml.XXXXXX")"
cat > "$tmp"
mv -f "$tmp" "$dir/module.toml"

echo "registered: $dir/module.toml"
