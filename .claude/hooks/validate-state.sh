#!/usr/bin/env bash
# Stop hook for dev-mgmt sessions (D34 + D36 + D33).
#
# - Invokes `dev-mgmt validate` with the Sprint-6 fast-subset:
#     * D35.1 sprint folder coherence (always)
#     * D35.2 INDEX coherence (always)
#     * D35.3 frontmatter parse / per-type validate (mtime-filtered, 300s)
# - Cohort W (wl:2026-06-03-06): cadence-gated handoff aging trigger.
#   When `[handoffs].collapse_cadence_stub_writes > 0` AND the count of
#   eligible stubs (older than `empty_stub_age_hours`, beyond the
#   `keep_recent_n_stubs` retention window) is at-or-above the cadence
#   threshold, fires `cli.py aging` with the configured strategy. Cadence
#   defaults to 0 (manual-only) — opt-in per consumer; hook is a no-op
#   for repos that haven't enabled it.
# - Warnings stream to stderr; CC surfaces them in turn-end output.
# - D33: always exits 0; never blocks CC turn-end behavior.

set +e

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PY="$REPO/.venv/bin/python3"
[ -x "$PY" ] || PY="python3"
CLI="$REPO/.claude/scripts/dev-mgmt/cli.py"

"$PY" "$CLI" validate --mtime-cutoff 300 --repo-root "$REPO" || true

# Cohort W cadence-gated aging trigger. Lives behind a python --check
# probe so the shell stays simple + parley-agnostic + non-blocking.
# stderr leak surfaces the run summary; exit always 0 (D33).
"$PY" - "$REPO" <<'PYEOF' 2>&1 || true
import sys
from pathlib import Path

repo = Path(sys.argv[1])
scripts = repo / ".claude" / "scripts" / "dev-mgmt"
if not scripts.is_dir():
    sys.exit(0)
sys.path.insert(0, str(scripts))
try:
    import index as _index_mod
    import handoff_aging as _aging_mod
except Exception:
    sys.exit(0)

try:
    cfg = _index_mod._handoffs_config(repo)
    cadence = cfg.get("collapse_cadence_stub_writes", 0)
    if not isinstance(cadence, int) or cadence <= 0:
        sys.exit(0)
    eligible = _aging_mod.detect_stubs(
        repo / "docs" / "handoffs",
        empty_stub_age_hours=cfg["empty_stub_age_hours"],
        keep_recent_n=cfg["keep_recent_n_stubs"],
    )
    if len(eligible) < cadence:
        sys.exit(0)
    summary = _aging_mod.run_aging_policy(repo, config=cfg)
    sys.stderr.write(
        f"[handoff-aging] strategy={summary['strategy']} "
        f"detected={summary['detected']} "
        f"archived={summary['archived']} "
        f"merged={summary['merged']} "
        f"deleted={summary['deleted']}\n"
    )
except Exception as exc:
    # D33: hooks never block. Surface to stderr; exit 0 below.
    sys.stderr.write(f"[handoff-aging] skipped: {exc}\n")

sys.exit(0)
PYEOF

exit 0
