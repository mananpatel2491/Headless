---
name: prototype
description: >-
  Generate a self-contained, clickable HTML/JS PROTOTYPE MOCKUP from an existing
  spec folder (specs/NNN-slug/) into that spec's own prototype/ subfolder — so reviewers
  can click through a proposed feature and validate requirements faster, without building
  anything real. Use whenever the user wants to prototype/mock up a spec: "/prototype",
  "prototype this spec", "make a clickable mockup of specs/NNN", "scaffold a quick prototype
  to validate the requirements", "mock up feature NNN", "turn this spec into a clickable
  demo", or names a specs/NNN-slug folder plus "prototype" / "mockup". Reads spec.md
  (+ data-model.md / contracts/ when present); writes ONLY under prototype/; output is
  offline-only (no backend, no network, no CDN, canned data, clearly marked non-production).
  It does NOT create specs (use your spec generator — e.g. /speckit-specify or /retro-spec —
  for that) and does NOT touch application source or the .specify/ flow.
---

# prototype — clickable mockup generator from a spec

Turn an **existing** `specs/NNN-slug/` folder into a **self-contained, clickable HTML/JS
mockup** written into that spec's own `prototype/` subfolder. The point is to make a paper
spec *visible* — a reviewer opens `index.html` in a browser and clicks through an
approximation of the proposed feature, validating the requirements faster than reading prose
or waiting for the feature to be built.

This is the companion to your **spec generator** (e.g. `/speckit-specify` or `/retro-spec`):
those skills generate the **requirement files**; this skill generates an **optional clickable
mockup** from them, on demand.

## Usage

```
/prototype <NNN | slug>           # generate a clickable mockup into specs/NNN-slug/prototype/
/prototype <NNN | slug> --force   # regenerate, overwriting an existing prototype/
/prototype --help                 # show this usage block
```

- **`<NNN | slug>`** — an existing spec identifier (e.g. `002` or `002-dashboard`). Resolves to
  `specs/NNN-slug/`; fails closed (writes nothing) if the folder or its `spec.md` is missing.
- **`--force`** — overwrite an existing `prototype/`. Without it, the skill refuses to clobber one
  (non-destructive default).
- **`--help`** — print the Usage block and stop.

Output is offline-only (no backend, no network, no CDN, canned data) and clearly marked
non-production. The skill writes **only** under `specs/NNN-slug/prototype/` and never touches app
code or the spec's own files.

## What it produces

One folder `specs/NNN-slug/prototype/` containing **all five** files:

| File | Purpose |
|---|---|
| `index.html` | The mockup UI — screens/controls reflecting the spec's user stories; carries the non-production banner |
| `styles.css` | Self-contained local styling |
| `app.js` | Vanilla client-side interactivity (view switching, rendering canned data); **no network** |
| `mock-data.js` | Canned in-file sample data grounded in the spec's entities/contracts |
| `README.md` | Non-production note + how to open (`file://`) + screen→spec traceability table |

The detailed conventions — bundle layout, the offline/no-CDN/no-secrets invariants, how spec
sections map to screens, and the mock-data grounding rules — live in
[references/pattern.md](references/pattern.md). **Read it before generating.**

## What it is NOT

- **Not** a spec generator — it consumes a spec, it does not create one. (Use your spec
  generator — `/speckit-specify` or `/retro-spec` — to produce `specs/NNN-slug/` first.)
- **Not** production code — the output is a throwaway visual aid. It never writes into
  application source (`src/`, `backend/`, `frontend/`, `app/`) or anywhere outside
  `specs/NNN-slug/prototype/`.
- **Not** a change to the requirement-file flow — the spec skills, the `speckit-*` skills, and
  `.specify/` are left completely untouched.

## Prerequisites

Run from the repo root (this skill is auto-discovered from `.claude/skills/`, like the other
repo skills). The target spec folder must already exist under `specs/` with a `spec.md`.

## Workflow

Create a TodoWrite list from these steps, then execute in order.

### 1. Resolve the target (write nothing until this passes)
- The argument is a spec identifier: a zero-padded **number** (`002`) or a full **slug**
  (`002-dashboard`).
- **Validate it first**: reject any argument containing a path separator (`/`, `\`) or `..`
  — this is the path-traversal guard. The only thing you may derive from the argument is a
  spec folder name; all output is confined to the resolved `specs/NNN-slug/prototype/`.
- Resolve to `specs/NNN-slug/`. If the argument is just a number, find the single folder
  matching `^NNN-` under `specs/`. If nothing matches, or the matched folder has **no
  `spec.md`**, **stop with a clear error and write nothing** (do not guess a nearest match).

### 2. Decide whether you may write (non-destructive default)
- If `specs/NNN-slug/prototype/` **already exists** and `--force` was **not** passed, **refuse**
  and report ("a prototype already exists — re-run with `--force` to regenerate"). Change nothing.
- If `--force` was passed, you may regenerate (overwrite the bundle).

### 3. Read & ground in the spec (the quality lever)
- Read `specs/NNN-slug/spec.md` in full. Extract: **User Stories** (+ priorities), **Acceptance
  Scenarios** (the Given/When/Then states), **Functional Requirements** (FR-###), **Key
  Entities**, and **Success Criteria**. These define the screens, the controls, and the states
  the mockup must show.
- If present, also read `data-model.md` (entity/field shapes) and `contracts/*` (interface
  surface) to shape realistic **canned data** and actions. `contracts/` is a *secondary* input —
  many specs are UI features whose stories, not their HTTP contract, define the screens.
- Map spec → UI per [references/pattern.md](references/pattern.md): each primary user story
  becomes a screen/view; its acceptance-scenario states become the clickable states; key
  entities become the shapes in `mock-data.js`. For a backend/batch spec with no end-user UI,
  mock the **observable/operator surface** (a trigger/status/preview view) and say so in the README.

### 4. Generate the bundle into `prototype/`
Write the five files into `specs/NNN-slug/prototype/`, obeying the invariants in
[references/pattern.md](references/pattern.md):
- **Self-contained / offline**: vanilla HTML/CSS/JS only. **No** `fetch`/`XMLHttpRequest`/
  `WebSocket` or any `http(s)://` request; **no** external `<script src>` / remote `<link>`
  (no CDN). All assets are local and relative; all interactivity runs over `mock-data.js`.
- **No secrets**: no API keys, tokens, bearer headers, or real endpoint URLs anywhere.
- **Non-production framing**: `index.html` carries a visible
  `NON-PRODUCTION PROTOTYPE — generated from specs/NNN-slug` banner; `README.md` states it is a
  non-production mockup, how to open it (`file://`), and a **screen→spec traceability table**.

### 5. Self-verify before reporting done (the invariant gate)
Confirm, before declaring success:
- All five files exist and are non-empty.
- **No network**: no `fetch(` / `XMLHttpRequest` / `WebSocket` / `http(s)://` in the bundle.
- **No CDN / remote asset**: no remote `<script src>` or `<link href>`.
- **No secrets**: no `api_key` / `secret` / `Authorization: Bearer` / `sk-` style strings.
- **Confined writes**: nothing was written outside `specs/NNN-slug/prototype/`.
- The banner is present in `index.html`.

A quick mechanical check (adjust the path):
```bash
d=specs/NNN-slug/prototype
grep -REn "fetch\(|XMLHttpRequest|WebSocket|https?://" "$d" && echo "FAIL net" || echo "ok net"
grep -REn "<script[^>]+src=\"http|<link[^>]+href=\"http" "$d" && echo "FAIL cdn" || echo "ok cdn"
grep -REni "api[_-]?key|secret|authorization: bearer|sk-" "$d" && echo "FAIL secret" || echo "ok secret"
for f in index.html styles.css app.js mock-data.js README.md; do
  [ -s "$d/$f" ] && echo "ok  $f" || echo "MISSING/EMPTY  $f"; done
```
If any check fails, fix the bundle before reporting done.

### 6. Report (do not commit)
Summarise: the spec read, the `prototype/` files written, and a **screen→spec traceability**
summary (which screen maps to which user story / FR). Tell the user how to open it
(`specs/NNN-slug/prototype/index.html`). Do **not** commit or push unless asked.

## Anti-patterns (do not do these)
- **Touching anything outside `prototype/`** — never edit the spec's own files, application
  source (`src/`, `backend/`, `frontend/`, `app/`), other skills, or `.specify/`. This skill is
  write-confined.
- **Any network dependency** — a `fetch`, a CDN `<script src>`, a remote font/`<link>`. The
  mockup must open offline from `file://`. This is the #1 failure mode.
- **Leaking a secret or a real endpoint** into the bundle — use canned data only.
- **Overwriting an existing `prototype/` without `--force`** — the default is non-destructive.
- **Generating a generic UI that ignores the spec** — the screens and canned data must be
  grounded in the spec's user stories / entities, or the click-through validates nothing.
- **Creating a spec** — that's the spec generator's job; this skill requires the spec to exist.
- **Committing the generated mockup** automatically — leave that to the user.
