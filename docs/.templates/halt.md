---
id: null
type: halt
halt_id: null              # UUID4 written at HALT-create time (uuid.uuid4())
halt_ts: null              # ISO-8601 timestamp; canonical (replaces legacy halted_at)
agent: null                # '@<id>' or descriptive agent identifier
reason: null               # operator-readable cause
gate_ref: null             # docs/gates/<gate-id>.md or null when not gate-induced
what_i_tried: []
what_i_need: null          # explicit ask to operator/CTO
contact: null              # '@<id>' override; null defaults to substrate routing
ttl_until: null            # default: halt_ts + 4h on write
content_hash: null         # sha256 of body; OPTIONAL, parley side may compute
---

# AGENT HALTED — operator action required

(free-form body describing the stuck state — what you were doing, what
broke, why you can't proceed, what kind of help unblocks you)

When you write this file, ALSO print to stdout:

```
🚨 HALT.md WRITTEN — AGENT HALTED, NEEDS OPERATOR 🚨
<reason summary>
<path to this HALT.md>
```

The pane-marker substring `HALT.md WRITTEN — AGENT HALTED, NEEDS OPERATOR`
is what pane-scrapers anchor on (the unicode siren `🚨` is optional —
substrate-portability discipline anchors on the literal ASCII substring).

After writing this file + printing the marker, STOP. Do not retry.
Do not loop. Wait until either (a) this HALT.md file is deleted, or
(b) an operator types "continue" in your pane.
