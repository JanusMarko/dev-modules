#!/usr/bin/env bash
# Advisory kit-lint check for Gate 4.3.
# Uses the documentation-expert steward-home checker via the versioned contract.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="kit-lint-checker-v2.1.1"
STEWARD_HOME="${KIT_LINT_STEWARD_HOME:-../documentation-expert}"
CONTRACT="$STEWARD_HOME/docs/specs/2026-07-06-kit-lint-versioned-checker-contract.md"
CHECKER="$STEWARD_HOME/tools/kit-lint"

if [[ ! -f "$CONTRACT" ]]; then
  echo "missing steward contract: $CONTRACT" >&2
  exit 2
fi
if [[ ! -x "$CHECKER" ]]; then
  echo "missing steward checker: $CHECKER" >&2
  exit 2
fi
if ! grep -q "checker_source_version: ${VERSION}" "$CONTRACT"; then
  echo "steward contract is not ${VERSION}: $CONTRACT" >&2
  exit 2
fi

exec "$CHECKER" check --config kit-lint.yaml --mode advisory --format "${KIT_LINT_FORMAT:-json}"
