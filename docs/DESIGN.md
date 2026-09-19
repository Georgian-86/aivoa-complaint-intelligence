# Design notes

## The brief behind the brief

The reference screenshot shows a two-pane intake form. The harder question was
what a complaint-management UI should *feel* like, because the obvious answer —
a rounded-card SaaS dashboard in indigo — is what every AI-assisted build
produces, and it is wrong for this domain. A market complaint is a controlled
GMP record. It is printed, signed, filed and produced to an inspector years
later.

So the visual language is **controlled document meets laboratory instrument**:

| Decision | Instead of | Why |
|---|---|---|
| Warm bone paper `#F3F2ED` | Clinical white or grey-50 | Reads as a printed document, not a screen |
| Deep pine `#0F4C43` | Indigo / violet | Sober and specific; the default AI-app accent is an instant tell |
| 1px hairline rules | Soft drop shadows | Documents have rules; shadows are for overlays only |
| 4–10px radii | 12–16px pills | Pill-shaped everything is the template signature |
| Three-step signal scale mapped to Critical / Major / Minor | Red / amber / green | The palette *is* the GMP vocabulary, not decoration |
| Tabular numerals everywhere, monospace identifiers | Proportional figures | Batch codes and scores are scanned in columns |
| A dark navigation rail in both themes | Full theme inversion | The rail anchors the page like a spine anchors a bound document |

Inter is mandated by the brief. It is used with `cv05`/`cv11`/`ss01` enabled
and tight negative tracking on display sizes, and it doubles as the mono face
via `font-variant-numeric: tabular-nums slashed-zero` so identifiers align
without loading a second family.

## Signature elements

These exist so the product does not look generated:

**The numbered section spine.** The form's four sections carry a numbered chip
and a vertical rule down the gutter, like the clause numbering in an SOP.

**Field-level confidence.** Every AI-populated field shows a three-segment bar
and a percentage. Hovering reveals the verbatim sentence the value came from.
Low-confidence fields switch their leading 2px spine from pine to amber, so a
reviewer can see which values need checking without reading a single number.

**The agent rail.** The pipeline is a live vertical timeline — node label,
engine badge (`gemma2-9b`, `llama-3.3-70b` or `heuristic`), output digest and
latency in milliseconds. It turns a spinner into an explanation, and it is the
same component that renders the persisted trace on a saved record.

**The segmented risk meter.** Four 25-point bands that fill proportionally
rather than a donut or a gauge. A dial reads as decoration; a scale reads as a
measurement.

**The document control strip.** Document number, revision, effective date,
owner and reference, in the header of the intake page — the header block a real
controlled document carries.

## Interaction principles

**The machine proposes, the human disposes.** The assistant never writes to the
record. When it wants to change a field it renders a proposal button the
analyst clicks. Applied values are re-stamped `source: "analyst"` and are never
overwritten by a later run.

**Degradation is visible, not hidden.** With no API key the navigation rail
reads "Deterministic mode · no GROQ_API_KEY", every node badges itself
`heuristic`, and a banner on the run says every value must be verified. A
system that silently downgrades its own quality is worse than one that fails.

**Nothing blocks on the network.** The form is fully usable before, during and
after a run. The agent populates it; it does not own it.

## Accessibility

- Every control is reachable and operable from the keyboard; the dropzone
  responds to Enter, the composer sends on Enter and newlines on Shift+Enter.
- Focus is a 2px offset ring in the accent colour, visible on both themes.
- Severity is never carried by colour alone — every chip pairs its colour with
  the word.
- The risk meter exposes `role="img"` with an `aria-label` stating the score
  and band.
- `prefers-reduced-motion` disables the field-landing flash, the rail spinner
  and every transition.
- Both themes were checked for 4.5:1 body contrast and 3:1 on large text and
  non-text indicators.

## What I would do next

1. **Named users and electronic signatures.** The audit model already carries
   `actor` and `actor_type`; Part 11 needs authentication and a signature
   manifest on top.
2. **A golden-set evaluation harness.** Fifty annotated complaints, scored per
   field for extraction accuracy and per record for severity agreement, run in
   CI. Prompt changes should have to pass a regression bar, not a vibe check.
3. **Investigation workflow.** Intake is one module; the record currently stops
   at triage. Next is the investigation, the effectiveness check and closure
   approval.
4. **Human-in-the-loop interrupts in the graph.** LangGraph checkpointing would
   let `classify` pause for reviewer confirmation on a Critical before
   `analyse` proceeds, rather than assessing first and asking afterwards.
