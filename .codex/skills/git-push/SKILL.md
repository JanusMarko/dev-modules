---
name: git-push
description: Push to origin, handling the WSL → Windows → GitHub chain topology when present (WSL → Windows → GitHub in that order). Never force-pushes. Falls back to plain `git push` on any repo whose origin is a normal URL.
---

# Git Push

Push to the remote, handling a WSL → Windows → GitHub chain topology when
present (WSL → Windows → GitHub in that order). Falls back to a plain
`git push` on any repo whose origin is a normal URL. Never force-pushes.

Follow these steps exactly.

**Before you start.** If the caller has pending work in the working tree
that they expect to land on the remote, make sure it's committed first —
this skill will not commit for you. `git push` only transmits committed
refs; uncommitted edits stay local regardless of whether the push
succeeds. A dirty WSL worktree is still not a blocker for the push
itself (see step 2), but it's the most common reason for a "why didn't
my changes show up on GitHub?" surprise after a successful run.

1. In a SINGLE Bash tool invocation, probe the repo topology and state.
   Use `set -e`. (Bash variables set in one tool call do NOT carry over
   to another — combining into one call is required.)

     set -e
     local_origin="$(git remote get-url origin 2>/dev/null || true)"
     local_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"

     # Chain mode requires origin to be a local path that is itself a git
     # repo AND whose own origin is a URL.
     chain=0
     chain_remote=""
     chain_branch=""
     chain_status=""
     chain_deny=""
     if [ -n "$local_origin" ] \
        && { [ -d "$local_origin/.git" ] || [ -f "$local_origin/.git" ]; }; then
       chain_remote="$(git -C "$local_origin" remote get-url origin 2>/dev/null || true)"
       case "$chain_remote" in
         http://*|https://*|git@*|ssh://*|git://*)
           chain=1
           chain_branch="$(git -C "$local_origin" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
           chain_status="$(git -C "$local_origin" status --porcelain 2>/dev/null || true)"
           chain_deny="$(git -C "$local_origin" config --get receive.denyCurrentBranch 2>/dev/null || true)"
           ;;
       esac
     fi

     echo "CHAIN=$chain"
     echo "LOCAL_ORIGIN=$local_origin"
     echo "LOCAL_BRANCH=$local_branch"
     if [ "$chain" = "1" ]; then
       echo "CHAIN_PATH=$local_origin"
       echo "CHAIN_REMOTE=$chain_remote"
       echo "CHAIN_BRANCH=$chain_branch"
       echo "CHAIN_DIRTY=$([ -n "$chain_status" ] && echo 1 || echo 0)"
       echo "CHAIN_DENY=$chain_deny"
     fi
     if [ "$chain" = "1" ] && [ -n "$chain_status" ]; then
       echo "---CHAIN_STATUS---"
       echo "$chain_status"
     fi

2. Parse the output and pick a path:

   - **No chain** (`CHAIN=0`): run `git push` in a single Bash invocation
     and report the result. Stop.
   - **Chain + `CHAIN_DENY` != `updateInstead`**: ABORT. The Windows repo
     doesn't have the one-time config needed to accept pushes into its
     checked-out branch. Tell the user to run:

         git -C "<CHAIN_PATH>" config receive.denyCurrentBranch updateInstead

     (substituting the actual CHAIN_PATH value). Link them to
     `docs/getting-started/installation.md#wsl--windows--github-sync-optional`
     for the full topology context. Do NOT push.
   - **Chain + `CHAIN_DIRTY=1`**: ABORT. `updateInstead` refuses to
     fast-forward a dirty target. Echo the `---CHAIN_STATUS---` block and
     tell the user to commit or stash on the Windows side first.
   - **Chain + `LOCAL_BRANCH` != `CHAIN_BRANCH`**: ABORT. Pushing a ref
     that Windows isn't checked out on leaves the Windows worktree stale
     (the ref updates but the worktree doesn't), and the subsequent
     `git -C <windows> push` would push whatever branch Windows is on —
     not the one the user just pushed from WSL. Print both branches and
     tell the user to run `git checkout <branch>` on the Windows side
     before retrying.
   - **Chain + `updateInstead` set + clean + branches match**: proceed.

   NOTE: a dirty WSL worktree is intentionally NOT a blocker. `git push`
   only sends committed refs — what's in the WSL working tree is
   irrelevant to the push. Whether to commit those edits before pushing
   is the user's call, not this skill's.

3. In a SINGLE Bash invocation, execute the chain push in the correct
   order. Interpolate `<CHAIN_PATH>` with the value from step 1.

     set -e
     git push
     git -C "<CHAIN_PATH>" push

   If the first push fails (non-fast-forward upstream, auth, hook
   rejection, etc.), `set -e` stops the second push. Report what failed;
   do NOT retry and do NOT run the Windows → GitHub push alone — the
   whole point of the chain is that Windows mirrors WSL, so pushing
   Windows without WSL going through first would publish a state the
   user didn't ask for.

4. Report one summary: what was pushed (ref names, commit count, final
   remote HEADs). If there was nothing to push on either hop, say so
   explicitly ("everything up-to-date") — don't leave the user guessing.

Constraints:
- NEVER use --force, --force-with-lease, or any push flag that rewrites
  remote history. Non-fast-forward upstreams surface as errors the user
  resolves themselves.
- NEVER modify the Windows worktree beyond letting `updateInstead`
  fast-forward it. No `checkout`, no `reset`, no branch creation on
  the Windows side.
- If the user explicitly asks for a force-push, tell them this skill is
  intentionally fast-forward-only and ask them to run
  `git push --force-with-lease` themselves outside the skill, after
  confirming they understand which commits get orphaned.
