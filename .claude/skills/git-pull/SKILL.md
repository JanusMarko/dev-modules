---
name: git-pull
description: Pull from origin, handling the WSL → Windows → GitHub chain topology when present. Fast-forward only; never merges or rebases. Falls back to plain `git pull --ff-only` on any repo whose origin is a normal URL.
---

# Git Pull

Pull from the remote, handling a WSL → Windows → GitHub chain topology when
present. Falls back to a plain `git pull --ff-only` on any repo whose origin
is a normal URL. Always fast-forward only — never merges, never rebases,
never stashes. Aborts loudly instead of silently resolving.

Follow these steps exactly.

1. In a SINGLE Bash tool invocation, probe the repo topology and state.
   This must run inside the current git repo (cwd). The script prints
   key=value lines that drive every subsequent decision. Use `set -e` so
   an unexpected failure surfaces immediately. (Bash variables set in one
   tool call do NOT carry over to another — combining into one call is
   required.)

     set -e
     local_origin="$(git remote get-url origin 2>/dev/null || true)"
     local_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
     local_status="$(git status --porcelain 2>/dev/null || true)"

     # Chain mode requires origin to be a local path that is itself a git
     # repo AND whose own origin is a URL. Anything else (origin is a URL,
     # origin path missing, origin path not a repo, origin path's origin
     # is also a local path) is "no chain" and falls through to a plain
     # pull.
     chain=0
     chain_remote=""
     chain_branch=""
     chain_status=""
     if [ -n "$local_origin" ] \
        && { [ -d "$local_origin/.git" ] || [ -f "$local_origin/.git" ]; }; then
       chain_remote="$(git -C "$local_origin" remote get-url origin 2>/dev/null || true)"
       case "$chain_remote" in
         http://*|https://*|git@*|ssh://*|git://*)
           chain=1
           chain_branch="$(git -C "$local_origin" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
           chain_status="$(git -C "$local_origin" status --porcelain 2>/dev/null || true)"
           ;;
       esac
     fi

     echo "CHAIN=$chain"
     echo "LOCAL_ORIGIN=$local_origin"
     echo "LOCAL_BRANCH=$local_branch"
     echo "LOCAL_DIRTY=$([ -n "$local_status" ] && echo 1 || echo 0)"
     if [ "$chain" = "1" ]; then
       echo "CHAIN_PATH=$local_origin"
       echo "CHAIN_REMOTE=$chain_remote"
       echo "CHAIN_BRANCH=$chain_branch"
       echo "CHAIN_DIRTY=$([ -n "$chain_status" ] && echo 1 || echo 0)"
     fi
     if [ -n "$local_status" ]; then
       echo "---LOCAL_STATUS---"
       echo "$local_status"
     fi
     if [ "$chain" = "1" ] && [ -n "$chain_status" ]; then
       echo "---CHAIN_STATUS---"
       echo "$chain_status"
     fi

2. Parse the output and pick a path:

   - **No chain** (`CHAIN=0`): run `git pull --ff-only` in a single Bash
     invocation and report the result. Stop.
   - **Chain + either side dirty** (`LOCAL_DIRTY=1` or `CHAIN_DIRTY=1`):
     ABORT. Tell the user which side is dirty, echo the corresponding
     `---..._STATUS---` block from step 1, and instruct them to commit or
     stash on that side before retrying. Do NOT pull.
   - **Chain + branch mismatch** (`LOCAL_BRANCH` != `CHAIN_BRANCH`):
     ABORT. Print both branches and tell the user to run
     `git checkout <branch>` on the lagging side before retrying. Do NOT
     pull. The skill never modifies the Windows worktree to bridge the
     drift — alignment is the user's call.
   - **Chain + both clean + branches match**: proceed to step 3.

3. In a SINGLE Bash invocation, execute the chain pull in the correct
   order. Interpolate `<CHAIN_PATH>` with the value from step 1.

     set -e
     git -C "<CHAIN_PATH>" pull --ff-only
     git pull --ff-only

   If the first pull fails (non-fast-forward, network error, auth, etc.),
   `set -e` stops the second pull. Report exactly what failed; do NOT
   retry and do NOT pull the WSL side alone — it would just resync to
   the stale Windows HEAD, silently hiding the upstream error.

4. Report one summary: final `git rev-parse --short HEAD`, and whether
   this was a "chain pull (GitHub → Windows → WSL)" or "plain pull (origin
   direct)". If no new commits came down, say so explicitly ("already up
   to date") — don't leave the user guessing.

Constraints:
- NEVER use --force, --rebase, --no-ff, or stash. Diverged history is
  surfaced to the user as a non-fast-forward error, not papered over.
- NEVER modify the Windows worktree beyond running `pull --ff-only`.
- If the user explicitly asks for a merge or rebase flow, tell them this
  skill is intentionally fast-forward-only and ask them to run
  `git pull` (or `git pull --rebase`) themselves outside the skill.
