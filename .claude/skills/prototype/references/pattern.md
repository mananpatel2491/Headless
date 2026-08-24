# prototype — mockup pattern (what goes in the bundle)

Read this before generating. It encodes the **bundle layout**, the **hard invariants**, the
**spec→screen mapping**, and the **mock-data grounding** rules so every prototype is consistent,
offline, and reviewable. The structure here; the *content* comes from the target spec.

The mockup is a **throwaway visual aid** to validate requirements — not a step toward
implementation. Optimise for "a reviewer can open it offline and immediately understand and click
through the proposed feature", not for code reuse.

---

## Bundle layout (exactly five files, all under `specs/NNN-slug/prototype/`)

```text
specs/NNN-slug/prototype/
├── index.html      # banner + screens; links ONLY local styles.css / app.js / mock-data.js
├── styles.css      # self-contained styling (no remote @import)
├── app.js          # vanilla browser JS; renders MOCK_DATA; wires clicks; NO network
├── mock-data.js    # const MOCK_DATA = { … }  — canned, grounded in the spec
└── README.md       # non-production note + open steps + screen→spec traceability table
```

Keep it to these five. Don't add build configs, package files, frameworks, or nested asset trees —
a mockup that needs a build step or a server defeats the purpose.

---

## Hard invariants (the skill self-verifies these — see SKILL.md step 5)

1. **Offline / no network.** No `fetch(`, `XMLHttpRequest`, `WebSocket`, `EventSource`, or any
   `http(s)://` request. The page must fully work opened from `file://`.
2. **No external assets / no CDN.** No remote `<script src="http…">`, no remote
   `<link rel="stylesheet" href="http…">`, no `@import url(http…)`, no remote fonts/images. Link
   only local relative files (`styles.css`, `app.js`, `mock-data.js`). Use system fonts and inline
   SVG / CSS shapes / emoji instead of remote icon sets.
3. **No secrets, no real endpoints.** No API keys, tokens, `Authorization: Bearer …`, `sk-…`
   strings, or real service URLs. Canned data only.
4. **Confined writes.** Write nothing outside `specs/NNN-slug/prototype/`.
5. **Non-production framing.** A visible banner in `index.html` and a non-production note in the
   README (below).

These exist because the bundle may be committed into the repo and opened on any machine: it must
never phone home, leak a credential, or be mistaken for shippable code.

---

## The non-production banner (required in `index.html`)

Put a visible, hard-to-miss banner as the first element in `<body>`. Suggested markup:

```html
<div class="proto-banner" role="note">
  ⚠ NON-PRODUCTION PROTOTYPE — generated from <code>specs/NNN-slug</code>.
  Mockup with canned data for requirement validation only. Not wired to any backend.
</div>
```

Style it so it reads as a warning strip (e.g. amber background, full width, sticky top). Replace
`NNN-slug` with the real spec slug.

---

## Mapping the spec → screens (ground every screen)

Read `spec.md` and translate, in this order of priority:

- **User Stories → screens/views.** Each `User Story N (Priority: …)` becomes a screen or a primary
  view. Lead with the P1 stories; lower-priority stories can be secondary tabs/sections.
- **Acceptance Scenarios → clickable states.** The Given/When/Then steps describe the states the UI
  moves through — they become the buttons, toggles, list items, and result panels a reviewer
  clicks. Show empty/typical/edge states where the scenarios call them out.
- **Functional Requirements → controls & affordances.** An `FR-### … MUST …` that describes an
  observable behaviour becomes a visible control or indicator (a button, a status badge, a 403/empty
  message). Don't invent UI the spec doesn't imply.
- **Success Criteria → the "done" view.** What a successful outcome looks like (a summary, a
  confirmation, a populated table) becomes the post-action screen.
- **Key Entities / `data-model.md` → the shapes shown.** What the screens display (rows, cards,
  fields) mirrors the spec's entities.
- **`contracts/` (secondary).** If the spec has REST/SSE/etc. contracts, use them to shape actions
  and response-shaped mock data — but remember most UI features are defined by their stories, not
  their HTTP contract.

**Backend / batch / no-UI specs**: some specs (e.g. a sync job, an ingestion batch) have no
end-user screen. Mock the **observable surface** instead — an operator/trigger panel, a status or
progress view, a preview/confirm dialog, or a simple narrative walkthrough of the flow — and state
in the README that the feature has no end-user UI.

---

## `mock-data.js` — canned, grounded, no live data

- Declare one window-scoped object, e.g. `const MOCK_DATA = { … };`, holding the sample records the
  screens render.
- Shape records after the spec's **Key Entities** / `data-model.md` fields (and `contracts/`
  response shapes when present), so the mockup looks like the real thing.
- Include enough variety to exercise the states the acceptance scenarios mention (e.g. an empty
  list, a typical list, an error/edge item).
- **Never** put secrets, tokens, or real endpoint URLs here. Use obviously-fake values
  (`user@example.com`, `sample-project`, placeholder ids). Keep it small and readable.

---

## `app.js` — vanilla, client-only

- Plain browser JS (no modules/bundler needed): functions on `window`, `addEventListener`, DOM
  rendering from `MOCK_DATA`. No framework, no build.
- Implement only **client-side** interactivity: switching views/tabs, opening a modal,
  filtering/selecting from `MOCK_DATA`, showing a canned "result". Simulate any "server" action with
  a local function that returns canned data (optionally a `setTimeout` to mimic latency) — **never**
  a real request.
- No timers/listeners that leak (a single `setTimeout` to fake latency is fine; avoid unbounded
  `setInterval`).

---

## `styles.css` — self-contained

- All styling local; no remote `@import`, no CDN fonts. System font stack is fine
  (`font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;`).
- Keep it light and legible — this is a mockup, not a design system. A clean header, the banner,
  cards/lists/buttons, and one accent colour are enough.

---

## `README.md` (generated, inside `prototype/`)

Must state:
- **Non-production**: "This is a non-production clickable mockup generated from
  `specs/NNN-slug/` to validate requirements. It uses canned data and is not wired to any backend."
- **How to open**: open `index.html` directly in a browser (`file://`) — no server, no build, no
  network needed.
- **Traceability table**: map each screen/view back to the spec it represents, e.g.

  | Screen / view | Spec source |
  |---|---|
  | Preview panel | US1 (Acceptance Scenarios 1–4), FR-005, FR-006 |
  | Confirm & run | US2, FR-008–FR-011 |
  | Disabled/empty state | US3, FR-002/FR-004 |

- Optionally a one-line "regenerate with `/prototype NNN --force`" note.

---

## Anti-patterns
- A CDN `<script src>` or remote font "just for nicer styling" — breaks offline + adds a remote
  dependency. Inline it or use system styles.
- A `fetch`/XHR to a real or placeholder API — the mockup must be fully self-contained.
- A generic dashboard that ignores the spec's actual stories — the screens must be grounded.
- Writing outside `prototype/`, or editing the spec's own artifacts.
- Leaving secrets/real URLs in `mock-data.js`.
- Overwriting an existing `prototype/` without `--force`.
