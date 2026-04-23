#!/usr/bin/env bash
# unregister.sh — remove a module manifest from .modules/<name>/
#
# Usage: scripts/unregister.sh <name>

set -euo pipefail

name="${1:?usage: unregister.sh <name>}"

root="$PWD"
while [[ "$root" != "/" && ! -d "$root/.modules" ]]; do
  root="$(dirname "$root")"
done
if [[ "$root" == "/" ]]; then
  echo "no .modules/ directory found above $PWD" >&2
  exit 1
fi

dir="$root/.modules/$name"
if [[ -d "$dir" ]]; then
  rm -rf "$dir"
  echo "unregistered: $dir"
else
  echo "not installed: $name"
fi
