---
name: detached-index-protective-snapshot
tier: 1
applies_when:
  - single-copy work (uncommitted mods / untracked files) must be protected on
    a SHARED working tree without disturbing live seats
  - a dev server, test run, or other seat is using the same tree right now
when_not_to_apply:
  - the tree is yours alone and quiescent — a plain branch + commit is simpler
  - the files are secrets-bearing (do not push; protect to $HOME instead)
origin:
  date: 2026-06-10
  context: 'Crash lessons-learned pass (Kris directive msg-15dae5951227, review-lead
    wsl-plan collation msg-e25880822edd, CTO ratify msg-889211d8fe09). ma-plan
    executed this recipe to protect the maxai 30-file unowned delta
    (wip/substrate-sync-2026-06-08, commits 12f549e + 53945ef) with zero
    disturbance to shared HEAD/index/working tree while live seats and a dev
    server ran on the same tree. Ratified for canonization as THE way to
    protect single-copy work in shared trees (ma-plan lesson 4).'
see_also:
  - lead-seat-sweep-duty
  - push-early-unconditional
---

# Detached-index protective snapshot: protect single-copy work on a live shared tree

## Rule

To protect uncommitted single-copy work on a shared tree **without
touching the shared HEAD, index, or working tree**, build the commit
through a detached index:

```bash
export GIT_INDEX_FILE=$(mktemp)        # private index, not .git/index
git read-tree HEAD                     # seed from current HEAD
git add <paths-to-protect>             # stage into the private index
TREE=$(git write-tree)
COMMIT=$(git commit-tree "$TREE" -p HEAD -m "protective snapshot: <what/why>")
unset GIT_INDEX_FILE
git branch wip/<name> "$COMMIT"
git push origin wip/<name>             # per push-early-unconditional
```

The working tree is never checked out, the shared index is never
written, HEAD never moves — safe with live seats, dev servers, and
in-flight test runs on the same tree.

## Why

A plain `git add` + `commit` mutates the shared index and HEAD that
other seats and processes depend on mid-flight. The detached-index
form was proven in anger during the 2026-06-10 crash recovery: a
30-file delta protected and pushed off-host with zero disturbance to
the tree's live users.

## When to apply

Sweep-duty protective commits ([[lead-seat-sweep-duty]]) and any
"protect this now, owner unknown, tree busy" situation.

## When NOT to apply

Quiescent single-occupant trees (plain commit is simpler); secrets.

## See also

[[lead-seat-sweep-duty]], [[push-early-unconditional]].
