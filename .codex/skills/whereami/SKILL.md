---
name: whereami
description: >-
  Render a chat-friendly snapshot of project progress for a workshop-lite-managed repo. Detects the workshop-lite substrate — including the Shape-A SPLIT case where session-execution entities (sprints/handoffs/conversations) live in a parley dev-track substrate while product/design entities stay local — and composes one four-section picture (Macro / Where we've been / Where we're going / And then) from both roots. Parley-aware: discovers the dev-track substrate via parley whoami when split, routes the render via `parley say` so peers see the same picture; degrades cleanly to local-only when parley is absent. Use when the user wants a project snapshot, asks "where are we", "where am I", "what's the project status", "show me the map", "give me the big picture", or similar.
---

# /whereami — Workshop-lite project state

Produce a chat-friendly picture of where the project stands by reading the workshop-lite substrate (sprints + decisions + handoffs + issues + reviews + conversations indexes). Output is plain text with bullet lists + blank lines between sections — no ASCII bars or dense column layouts (those don't survive parley's chat formatter). When invoked inside a parley session, the render is also sent via `parley say` so peers see the same snapshot.

## Step 0 — Detect the substrate (split-substrate aware)

The workshop-lite substrate may be **split across two roots** (Shape-A
migration, decision `2026-05-15-02` / D67): a repo can keep its
product/design entities locally while its session-execution entities
(sprints, handoffs, conversations) live in a parley-managed **dev-track
substrate** at `~/.parley/sessions/<sid>/dev-track/`. Step 0 detects
both and computes the routing variables every later step uses.

### Step 0a — Local product substrate

```bash
LOCAL_HIT=0
[ -f docs/decisions/INDEX.md ] \
  && [ -f .claude/scripts/dev-mgmt/cli.py ] \
  && LOCAL_HIT=1
```

Note: `docs/sprints/INDEX.md` is **no longer required locally** — under
Shape-A it migrates out to the dev-track substrate (this is why the
pre-split signature regressed `/whereami` to the obsolescence note in a
post-migration product repo; that was the W3 correctness bug).

### Step 0b — Resolve `SPRINT_ROOT` (sprints/handoffs/conversations home)

```bash
SPRINT_ROOT="."   # default: local (un-migrated / legacy single-root repo)
if [ -f docs/sprints/INDEX.md ]; then
  SPRINT_ROOT="."                       # local sprints present → not split
else
  # parley-aware discovery (SKILL layer only, D27; the dev-mgmt lib
  # never shells parley — Hard Rule 1/5). Routing is delegated to the
  # pure-Python helper at `.claude/scripts/dev-mgmt/
  # whereami_substrate_router.py` (Sprint workshop-lite.25, closes
  # issue 2026-05-16-02 D3). The helper consumes parsed whoami JSON +
  # an optional --substrate selector and applies a 5-level precedence
  # (peer selector → path selector → session-substrate-path → wl.12
  # D1 sid-derivation → unresolved). Graceful degradation: when
  # @Par hasn't yet wired peer-level substrate_path (current state),
  # the helper falls through to the wl.12 sid-derivation; the
  # mechanism activates seamlessly when @Par lands the peer field.
  #
  # The bash invocation pipes parley whoami output to a small python
  # one-liner that imports the helper and prints just the chosen
  # path. NEVER `eval` the result (W12-F2 / P4-MF2 unsanitized-sid
  # injection class).
  SID=$(parley whoami 2>/dev/null | python3 -c "
import json, sys, os
try: d = json.loads(sys.stdin.read() or '{}')
except Exception: d = {}
sel = os.environ.get('WHEREAMI_SUBSTRATE_SELECTOR') or None
# Helper-first path (Sprint workshop-lite.25 D3 mechanism). When the
# helper is bundled (workshop-lite cwd OR any consumer repo with the
# wl.11 install), use it for full per-peer routing + selector support.
# Fallback: inline precedence #3 (substrate_path) + #4 (sid-derived)
# — preserves wl.12 D1 behavior when helper isn't on sys.path.
try:
    sys.path.insert(0, os.path.join(os.getcwd(), '.claude', 'scripts', 'dev-mgmt'))
    from whereami_substrate_router import resolve_sprint_root
    r = resolve_sprint_root(d, selector=sel)
    if r.sprint_root is not None:
        print(str(r.sprint_root))
except Exception:
    sp = d.get('substrate_path') or ''
    sess = d.get('session') or {}
    print(sp or ('~/.parley/sessions/'+sess.get('sid','')+'/dev-track' if sess.get('sid') else ''))
" 2>/dev/null)
  SID="${SID/#\~/$HOME}"                # ~-expand via bash param-expansion
                                        # — NEVER `eval` (see comment above).
  if [ -n "$SID" ] && [ -f "$SID/docs/sprints/INDEX.md" ]; then
    SPRINT_ROOT="$SID"
  fi
fi
```

**Per-peer substrate enumeration (D3 wl.25, gated on @Par):** when an
operator wants to render a DIFFERENT pane's substrate from this pane
(the "any-pane → any-substrate" generalization), set the
`WHEREAMI_SUBSTRATE_SELECTOR` env to either `@<peer-id>` (routes to
that peer's substrate IF `peers[].substrate_path` is populated) or an
absolute path (routes there directly). In the current gated state
(@Par hasn't wired peer-level substrate_path yet), the @-form is a
no-op and the path-form falls through to direct selection.

### Step 0c — Routing convention (used by ALL later steps)

Once Step 0 has run, every later step resolves entity paths through
these two roots — **this is the canonical routing; later steps name
bare `docs/...` paths for brevity but MUST apply this mapping**:

- **`$SPRINT_ROOT/docs/sprints/`, `$SPRINT_ROOT/docs/handoffs/`,
  `$SPRINT_ROOT/docs/conversations/`** — session-execution entities
  (Steps 1, 2, 3, 4-retro-scrape, 5-handoffs/conversations sidebar).
- **`./docs/decisions/`, `./docs/issues/`, `./docs/reviews/`,
  `./docs/design/`** — local product/design entities, ALWAYS the
  invoking cwd (Step 5 decisions/issues/reviews sidebar; Step 4
  Bucket-A anchor `./docs/design/workshop-side-blockers-anchor.md`).
- If an entity's home is ever genuinely ambiguous (should not occur —
  Shape-A pre-partitions every entity by type+scope), **local
  `./docs/` wins** (the product repo is the operator's primary view)
  and the render notes the split.

### Step 0d — Decision

- `LOCAL_HIT=1` → proceed to Step 1. If `SPRINT_ROOT != "."` the
  substrate is **split**; the render (Step 6) notes
  `substrate split: sprints ← parley dev-track (<SPRINT_ROOT>)`.
- `LOCAL_HIT=1` but `SPRINT_ROOT="."` AND `docs/sprints/INDEX.md`
  absent (split repo, parley unavailable so dev-track unresolved) →
  render the product-only picture from local decisions/issues/reviews
  + emit a one-line note: `sprint history unavailable (lives in the
  parley dev-track substrate; parley not on PATH here) — product
  entities shown`. Do NOT emit the full obsolescence note (the
  substrate IS workshop-lite, just split).
- `LOCAL_HIT=0` → emit the one-line obsolescence note:
  `No workshop-lite substrate detected (looked for: docs/decisions/INDEX.md + .claude/scripts/dev-mgmt/cli.py). Use the corresponding system's where-am-i skill, or /load-context, or git log instead.` — then stop. Do NOT render an empty picture.

## Step 1 — Read sprint groupings (Macro)

> **Routing (Step 0c):** every `docs/sprints/…`, `docs/handoffs/…`,
> `docs/conversations/…` path in Steps 1–5 is **`$SPRINT_ROOT/docs/…`**
> (dev-track when split, `.` when local/legacy). `docs/decisions/…`,
> `docs/issues/…`, `docs/reviews/…`, `docs/design/…` are always local
> `./docs/…`. Executable snippets below use `$SPRINT_ROOT` explicitly;
> prose `docs/sprints/…` mentions mean the same.

Parse `$SPRINT_ROOT/docs/sprints/INDEX.md`. Rows are `| ID | Title | Status | Stage | Created | Shipped |` (header + separator rows skipped).

### Step 1a — Try GROUPS.md (semantic-label override)

If `$SPRINT_ROOT/docs/sprints/GROUPS.md` exists, parse its mapping table and use semantic group labels instead of bare id-prefix grouping. Shape (per the workshop-lite convention introduced in Sprint workshop-lite.11 deliverable A):

```
| Group | Sprint IDs | Spans |
|-------|-----------|-------|
| <Group label 1> | <comma-separated sprint-ids>      | <prose describing the span> |
| <Group label 2> | <comma-separated sprint-ids>      | <prose describing the span> |
```

For each group row:
- Take the `Group` column value as the macro-row label.
- Parse the `Sprint IDs` column (comma-separated). For each sprint-id in the list, find its corresponding INDEX row.
- Count: `archived_count` (sprints with `Status=archived`), `active_count` (sprints with `Status=active`). Total = archived + active. Sprints listed in GROUPS.md but missing from INDEX are silently skipped (forward-pointer placeholders).

Group ordering: by first-sprint Created date ascending across the group's listed sprint-ids (earliest group first). This matches the chronological narrative.

For sprint-ids in INDEX but NOT listed in any GROUPS.md group: fall through to Step 1b id-prefix grouping for that orphan set (renders as a separate macro row labeled by id-prefix).

### Step 1b — Fallback: id-prefix grouping (no GROUPS.md, or orphan sprints)

If `$SPRINT_ROOT/docs/sprints/GROUPS.md` is absent entirely, OR for sprints not covered by GROUPS.md (orphan rows): group by **id-prefix** — everything left of the final `.N` segment. Examples:

- `dev-mgmt.1` … `dev-mgmt.9` → group `dev-mgmt`
- `dev-mgmt.9.5` → group `dev-mgmt` (multi-segment sprint ids stay under their prefix; treat the final `.NN` or `.NN.M` as the sprint-counter)
- `workshop-lite.10` → group `workshop-lite`
- `foo.bar.7` → group `foo.bar`

For each group, count: `archived_count` (rows with `Status=archived`), `active_count` (rows with `Status=active`). Total = archived + active.

The group ordering for render: by first-sprint Created date ascending (earliest group first).

### Precedence summary

GROUPS.md wins where it covers a sprint-id; id-prefix is the fallback for everything else. The render is honest either way (counts come from INDEX, labels come from whichever source covers the sprint), and never invents groups.

## Step 2 — Active sprint + stage pin

```bash
ls "$SPRINT_ROOT"/docs/sprints/active/sprint-*/ 2>/dev/null | head -1
```

If an active sprint folder exists, read `plan.md`'s YAML frontmatter for `sprint_id`, `status`, and `stage` (`plan` / `execute` / `retro`). If multiple active sprints exist (rare; convention is one at a time), pick the most recently created. Active sprint becomes the "you are here" pin.

If `$SPRINT_ROOT/docs/sprints/active/` is empty: no active sprint; the substrate is in **idle state between sprints**. The "you are here" pin sits at the boundary after the most recently-archived sprint.

## Step 3 — Just-shipped + recent arc

Last-shipped sprint:

```bash
ls -t "$SPRINT_ROOT"/docs/sprints/archive/sprint-*/retro.md 2>/dev/null | head -1
```

Pull the sprint id (parent dir name) + retro title (first `# ` heading).

Last 5–6 sprint completions: take INDEX archived rows, sort by Shipped date descending, keep top 5–6. For each, pull `ID` + first sentence of `Title`. Format each as a single bullet line.

## Step 4 — Recommended next + outstanding follow-ons + downstream-bucket

**Recommended next**: derive from one of these (first hit wins):

1. If an active sprint exists, read `$SPRINT_ROOT/docs/sprints/active/sprint-<id>/plan.md` for the `## What's next` section (if present) or the last bullet of `## Scope`.
2. Else read `$SPRINT_ROOT/docs/sprints/archive/sprint-<latest>/retro.md` `## What's next` section.

**Outstanding follow-ons (workshop-lite-side)**: read the latest archived retro's `## Out of scope` section. Filter to bullets that are NOT already shipped (per the retro's own ✅ / shipped annotations). These become **Bucket B** entries in the AND THEN… section.

**Downstream-bucket — anchor-doc first (Bucket-A source-of-record)**: if `docs/design/workshop-side-blockers-anchor.md` exists, it is the **canonical Bucket-A source**. Read its `## The four Workshop-side blockers` section (one `### B-A.N` heading per blocker) plus the `## Umbrella arc` section, and seed Bucket A from those entries (one bullet per `B-A.N` title + its one-line "What it blocks", plus the `Sprint D-Workshop-side` umbrella). This anchor does NOT roll up across sprints, so it is preferred over latest-retro scraping for completeness; entries whose **Status** line reads closed/shipped are still listed but tagged as resolved. The latest-retro scrape below is then a **supplement** (catches newly-surfaced arcs not yet anchored) and the **fallback** (used alone if the anchor doc is absent — degraded: detail rolls up, which is the failure mode the anchor exists to prevent).

**Downstream-bucket (post-Sprint workshop-lite.11 substrate-coherence convention)**: also read forward-pointer sections from the latest archived retro that describe out-of-cwd or planned arcs. Section name patterns to match (case-sensitive headings):

- `## Out of scope` (already covered above for Bucket B; sub-bullets that explicitly reference downstream/Workshop-internal arcs go into Bucket A instead)
- `## Near-term future arcs`
- `## Out of scope (post-Sprint-N; Workshop-internal / future arcs)` and similar parenthesized variants

For each bullet under those headings:
- If the bullet text contains `Workshop-internal`, `Workshop-side`, `downstream`, `Workshop product`, or references a `D5N` / `D6N` decision known to be a Workshop-side schema-add: route to **Bucket A** (Workshop-internal arcs).
- Otherwise: route to **Bucket B** (workshop-lite-side opportunistic items).

If the substrate has a sprint with `scope: downstream` frontmatter (per the workshop-lite schema-v0.2 amendment decision `2026-05-15-01-workshop-lite-schema-v0-2-amendment-*`), that sprint's title also seeds a Bucket A entry — even if no retro mentions it, the planned-status sprint itself counts as a known downstream arc.

The render bucket assignment in Step 6 reads these collected entries and renders them under the AND THEN… section (Bucket A first, Bucket B second).

## Step 5 — Entity sidebar counts

Count records in each entity INDEX (one row per record after the header + separator rows):

The sidebar is **split-routed** (Step 0c): product entities count from
local `./docs/`, session-execution entities from `$SPRINT_ROOT/docs/`.

```bash
# product entities — ALWAYS local cwd
for kind in decisions issues reviews; do
  n=$(awk 'NR>2 && /^\| /' "./docs/$kind/INDEX.md" 2>/dev/null | wc -l)
  echo "$kind: $n"
done
# session-execution entities — SPRINT_ROOT (dev-track when split)
for kind in handoffs conversations; do
  n=$(awk 'NR>2 && /^\| /' "$SPRINT_ROOT/docs/$kind/INDEX.md" 2>/dev/null | wc -l)
  echo "$kind: $n"
done
```

Skip kinds whose INDEX.md is absent. Workshop-lite tasks live INLINE in `$SPRINT_ROOT/docs/sprints/active/sprint-<id>/tasks.md` (per D19+D20), not as files at `docs/tasks/<id>.md` — to count tasks, scan the active sprint's tasks.md and group by state (`pending` / `in_progress` / `completed` / `blocked`).

## Step 6 — Render (ASCII bars + plain section headers)

Output four sections + headline. Use 12-char `█░` ASCII bars (12 = full width when divided into 12ths of progress), plain ALLCAPS section headers, glyph + state-label suffix for macro rows. Sections separated by exactly two blank lines (so they breathe in monospace contexts AND survive parley delivery wrapped in a code-fence per Step 7).

```
═══ Where-am-i — <repo-basename> (workshop-lite) ═══
<substrate split: sprints ← parley dev-track (<SPRINT_ROOT>)   — include this line ONLY when SPRINT_ROOT != "." (split substrate); omit entirely when local/legacy single-root>


MACRO (where we are)

<group-or-phase-label-1>        <bar>  <done>/<total>   <pct>%  <glyph> <state-label>
<group-or-phase-label-2>        <bar>  <done>/<total>   <pct>%  <glyph> <state-label>
…

Overall (workshop-lite internal): <X>/<Y> sprint-units ≈ <pct>%
Overall (incl. downstream):       <X>/<Y+>            ≈ ~<pct>%


WHERE WE'VE BEEN (last <N> sprint-units, newest first)

<sprint-id-1>        <one-line goal>
<sprint-id-2>        <one-line goal>
…
<sprint-id-latest>   <one-line goal>     ◄── JUST SHIPPED
  (one-line take from retro headline / 'what shipped' first sentence — wrap-indented under the JUST SHIPPED bullet)


WHERE WE'RE GOING (active focus)

Active sprint:  <id> at stage <stage>   OR   None — between sprints (post-<latest>)
Active group:   <group> (<pct>% archived; <reason-tag-if-notable>)

Substrate state:
  Decisions       <bar>  <N> records  (<id-range-if-useful>)
  Sprints         <bar>  <N> archived (<N> active)
  Issues          <bar>  <N> records
  Reviews         <bar>  <N> records             [omit if absent or 0]
  Handoffs        <bar>  <N> records             [omit if absent or 0]
  Conversations   <bar>  <N> records             [omit if absent or 0]

Test baselines:
  workshop-lite-cwd     <P>/<P>  passing
  parley-side           <P>/<P>  passing   [include if recently relevant; omit if N/A]

Pending @user push approvals (no time pressure):     [include if any unpushed commit chain exists]
  <repo>    →   <sha>     (<one-line>)
  …


AND THEN…

<short-prose-line-or-bullets-per-bucket>

Bucket A (e.g., Workshop-internal arcs; Hard Rule 2 = not workshop-lite-cwd):
  • <item-1>     <one-line>
  • <item-2>     <one-line>
  …

Bucket B (e.g., Workshop-lite-side opportunistic items):
  • <item-1>     <one-line>
  • <item-2>     <one-line>


HEADLINE

<2–3 sentence summary covering (a) overall %, (b) where the active pin is,
(c) the very next move, (d) what major thing still sits behind a milestone>.
```

### Overall lines (B2 — unconditional dual-%)

Both `Overall` lines render **unconditionally** — this is the
"total-vision" view (workshop-lite-internal % AND global-incl-downstream
%) that the Sprint workshop-lite.11 Step-4 refactor regressed by gating
the second line behind a downstream-detection condition (backlog item
B2; folded into this sprint per @plan W3 signoff).

- **`Overall (workshop-lite internal)`**: `X` = archived sprint-units,
  `Y` = total local+dev-track sprint-units (the count Step 1 built
  from `$SPRINT_ROOT/docs/sprints/INDEX.md`). Always rendered.
- **`Overall (incl. downstream)`**: `Y+` = `Y` plus the distinct
  downstream/Workshop-internal arcs collected for **Bucket A** in
  Step 4 (the `docs/design/workshop-side-blockers-anchor.md` entries +
  any `scope: downstream` sprint stubs). Always rendered — even when
  there are zero downstream arcs, in which case `Y+ == Y` and the two
  percentages coincide (render both anyway; the point of the
  total-vision view is that the reader never has to wonder whether the
  downstream line was suppressed or genuinely empty). The `~` prefix on
  the incl-downstream pct signals it spans an estimated/forward scope.

### Bar construction

The 12-char bar is `<done>` full-blocks `█` followed by `<todo>` light-shade `░`, where `done = round(12 * archived / total)` and `todo = 12 - done`. Examples:

```
12/12   ████████████
 9/12   █████████░░░
 1/12   █░░░░░░░░░░░
 0/12   ░░░░░░░░░░░░
```

For substrate-state bars (Decisions / Sprints / etc. in Section 3), the bar visualizes "how full is the index" rather than a done/total ratio — use `████████████` (full) when records exist, `░░░░░░░░░░░░` when the INDEX is empty. The bar is decorative in these rows; the N count carries the signal.

### State-label rules (Macro section)

- `archived == total > 0` → `✓ DONE`
- `archived > 0 AND archived < total` → `◐ IN PROGRESS` (append `← you are here` if any sprint in this group is the active one)
- `archived == 0 AND total > 0 AND any sprint in this group is active` → `◐ NEXT ← you are here`
- `archived == 0 AND total > 0 AND no active sprint in this group` → `◯ Not started` (or `blocked on <prior-group>` if a sequencing dependency exists; only flag if explicitly noted somewhere in the substrate)
- `archived == 0 AND total == ?` (unknown future scope; e.g., a downstream-Workshop arc whose sprint count isn't determined yet) → `◯ Not started (Workshop-side)` or similar one-line context tag in the state-label slot
- Group is empty (0 sprints): omit row (don't render hypothetical groups)

### Style guarantees

- **Read, don't infer.** Counts come from actual INDEX rows; the active pin comes from `$SPRINT_ROOT/docs/sprints/active/` (Step 0c routing — NOT cwd-relative; in a Shape-A split repo the local sprints dir is migrated out, which is exactly why this routes through `$SPRINT_ROOT`); the next pick comes from the substrate's designated next-pick anchor (active plan.md or latest archive retro.md under `$SPRINT_ROOT`). Never narrate from in-context memory — the substrate changes between sessions.
- **ASCII bars + plain section headers.** Section labels are plain ALLCAPS (e.g., `MACRO`, `WHERE WE'VE BEEN`); no markdown headers (`#`, `##`). Bars are 12-char `█░`. Per @user msg-16b61b9d4827 + @plan msg-df51e9a4de09 the boxed-frame-with-`┌─┐` style is OUT; the simpler unframed-with-`═══` divider style is the canonical render shape.
- **Glyphs `✓ ◐ ◯` carry the macro-state signal**; pair with the word (`DONE` / `IN PROGRESS` / `Not started`) so narrow renderers still parse the meaning.
- **Don't pad with hypothetical features.** If a group has 0 sprints, it doesn't appear. If an entity INDEX is missing, omit its sidebar line. The picture is honest.
- **Don't compute ETAs or "weeks remaining."** Sprint count is the only honest velocity unit.
- **The just-shipped pin is at sprint granularity, not commit granularity.** If multiple sprints landed since the last `/whereami`, list them in the recent-arc bullet chain; don't enumerate every commit.

## Step 7 — Parley-aware tail

After the render is computed, check if the calling pane is a parley member:

```bash
WHOAMI_JSON="$(parley whoami 2>/dev/null)"
IS_MEMBER=0
if [ -n "$WHOAMI_JSON" ]; then
  KIND=$(printf '%s' "$WHOAMI_JSON" | python3 -c "import json,sys
try: d=json.loads(sys.stdin.read() or '{}')
except Exception: d={}
print(d.get('kind') or '')" 2>/dev/null)
  [ "$KIND" = "member" ] && IS_MEMBER=1
fi
```

Routing:

- **Always print to stdout** (the canonical local-render path; user sees the picture in their CLI regardless of parley state).
- **If `IS_MEMBER=1`**: ALSO send the render via `parley say`, **wrapped in a `` ```text ... ``` `` code-fence**. The fence is load-bearing for the chat surface (Telegram bridge): per @Par msg-d10f539817d8 + the planned Sprint dev-mgmt.9.6 parley patch, fenced content routes to `<pre>` which preserves monospace + whitespace alignment so the bars + columns don't squish. Today (pre-9.6) markdown clients still parse the fence as preformatted text empirically (msg-16b61b9d4827 "test was perfect"); post-9.6 the routing is contract-guaranteed.
  - Concretely: `parley say "$(printf '```text\n%s\n```' "$RENDER")"` — the literal triple-backticks + the `text` language tag wrap the render body.
- **If `IS_MEMBER=0` (parley absent OR pane is not a member)**: stdout only, NO fence wrap (stdout is already monospace). Silent — no error message about parley being missing (per workshop-lite Hard Rule 5: parley-agnostic at base; the skill is parley-AWARE at the SKILL layer per D27, but never requires parley).

## When NOT to use

- The user wants doc-content drilling into a specific sprint (read the relevant `$SPRINT_ROOT/docs/sprints/{active,archive}/sprint-<id>/{plan,tasks,retro}.md` directly — Step 0c routing; in a split repo this resolves to the parley dev-track substrate, NOT cwd-relative).
- The user wants to know "what just shipped" specifically (read the latest archived retro.md — faster than the whole picture).
- The user wants to verify claims match code (use `dev-mgmt validate` for INDEX-vs-filesystem coherence + frontmatter validation).
- The workshop-lite substrate isn't present (Step 0 fell through) — already handled by printing the obsolescence note.

## Notes

- The skill is parley-AWARE at the SKILL layer (D27 pattern from `/capture-conversation`). The workshop-lite **library** (`.claude/scripts/dev-mgmt/`) never imports or shells out to parley — that coupling lives only here in SKILL.md and in the parley-aware tail (Step 7).
- This is the workshop-lite-specific whereami. Other repos with their own management substrate (workshop v2-build, maxai project-checklist, etc.) have their own where-am-i skills with their own detection + render logic. If a single repo somehow had multiple substrates installed, the operator can invoke the substrate-specific skill they want — there's no global cross-substrate dispatcher.
- Future workshop-lite versions can extend the macro grouping (e.g., support an explicit `docs/project/CHECKLIST.md` for semantic-phase grouping like maxai does) without changing the data sources read here. The sprint-id-prefix grouping is the minimum-viable mechanical default.
