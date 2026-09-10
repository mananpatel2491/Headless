---

description: "Task list for feature 010 Google Maps Connector"

---

# Tasks: Google Maps Connector

**Input**: Design documents from `/specs/010-google-maps-connector/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md,
contracts/connector-and-check.md, quickstart.md

**Tests**: REQUIRED by the specification (NFR-001, and SC-001 through SC-005 each name a
unit-test-provable outcome). Every test in `tests/test_maps_check.py` already exists and passes.

**Organization**: tasks are grouped by user story so each story is independently implementable
and testable, per this repository's own `tasks-template.md` convention.

**Status**: IMPLEMENTED (already-built feature; this delivery documents it as a Spec Kit set).
T001 through T013 reflect code and tests already present in this worktree
(`headless/mapsmcp.py`, `scripts/maps_check.py`, `tests/test_maps_check.py`, `.mcp.json`,
`terraform/main.tf`, `terraform/variables.tf`, `terraform/outputs.tf`). This delivery's own new
work is the document set itself (T014 onward) plus the docs-of-record updates. No `.py`, `.tf`,
`.json`, or `.hcl` file is touched by this delivery.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on another unchecked task)
- **[Story]**: which user story this task belongs to (US1, US2, US3), or unmarked for
  Foundational/Cross-cutting/Polish
- Every task names its own exact file path

## Path Conventions

Single project at the repository root: `headless/` (the package this feature adds a module to),
`scripts/` (the new maintenance script), `tests/` (pytest), `terraform/` (infrastructure). All
paths below are relative to the worktree root `../worktrees/Headless/v0.0.10/`.

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: the JSON-RPC message shapes every later phase's own logic reads.

- [x] T001 [P] `headless/mapsmcp.py`: define `MCP_ENDPOINT`, `API_KEY_ENV`, `API_KEY_HEADER`,
  `PROTOCOL_VERSION`, `CLIENT_NAME`, `PROBE_QUERY`, `EXPECTED_TOOLS`, and `McpError`
- [x] T002 [P] `headless/mapsmcp.py`: implement `build_request`, `initialize_params`,
  `search_params`, `parse_response`, `tool_names`, `missing_tools`, `count_places`, and
  `CheckOutcome`
- [x] T003 [P] `tests/test_maps_check.py`: unit tests for every function above - both request
  shapes, both response body shapes (plain JSON and SSE), the JSON-RPC error path, the
  missing-result path, `tool_names`/`missing_tools`, `count_places`'s three return paths plus its
  `isError` raise, and `CheckOutcome.lines()`/`.ok` across the PASS/FAIL/SKIP states

**Checkpoint**: every later phase can build and read a JSON-RPC message with no further wiring of
its own.

---

## Phase 2: User Story 1 - A future session identifies a location, computes a route, or reads the weather (Priority: P1)

**Goal**: the server is registered so a future Claude Code session can call it directly.

**Independent Test**: with the key set and the server approved, ask a session to find a public
place; confirm it calls `search_places` with no browser window ever opening.

- [x] T004 [US1] `.mcp.json`: register `google-maps` (`type: "http"`, the endpoint URL, the
  `X-Goog-Api-Key` header carrying the `${HEADLESS_MAPS_API_KEY}` placeholder)

**Checkpoint**: the connector is registered project-wide; a session in this repository offers it
after one Director approval (User Story 2/Scenario 4 in quickstart.md).

---

## Phase 3: User Story 2 - The Director provisions the key once (Priority: P1)

**Goal**: the ONLY cloud resources the connector needs are declared as code, cost-gated, and
applied only by the Director.

**Independent Test**: `terraform validate` from `terraform/` passes with provider
`hashicorp/google ~> 6.0` and exactly three resources declared, with no resource ever created by
this test itself.

- [x] T005 [P] [US2] `terraform/variables.tf`: declare `var.project_id`
- [x] T006 [P] [US2] `terraform/main.tf`: declare `google_project_service.apikeys`,
  `google_project_service.mapstools`, and `google_apikeys_key.maps_grounding_lite` restricted to
  `mapstools.googleapis.com`, depending on both service enablements
- [x] T007 [P] [US2] `terraform/outputs.tf`: declare `maps_api_key` (sensitive) and
  `mcp_endpoint`
- [x] T008 [US2] `terraform/.terraform.lock.hcl`: commit the provider dependency lock
  (`terraform init` against provider `hashicorp/google` 6.50.0, satisfying the `~> 6.0`
  constraint) (depends on T005-T007)
- [x] T009 [US2] `.gitignore`: add the terraform block (`terraform/.terraform/`, `*.tfstate`,
  `*.tfstate.*`, `*.tfvars`, `*.tfvars.json` ignored; the lock file NOT excluded)

**Checkpoint**: `terraform validate` passes; nothing is applied by this delivery itself - only
the Director, per quickstart.md Scenario 1.

---

## Phase 4: User Story 3 - The Director proves the connector with the live check (Priority: P2)

**Goal**: a Lesson 4 live check performs the handshake, lists the tools, and (only with a key and
without `--no-search`) makes exactly one billable call, printing value-free rows.

**Independent Test**: stub `urllib.request.urlopen` to answer the handshake and `tools/list`;
assert the printed rows and exit code match the stub, with no network call and no key value in
the captured output.

### Tests for User Story 3

- [x] T010 [P] [US3] `tests/test_maps_check.py`: `Transport` tests with `urlopen` stubbed - the
  key header sent only when set, the session id reused across requests, an HTTP error becoming a
  value-free `McpError` that never echoes the key
- [x] T011 [P] [US3] `tests/test_maps_check.py`: CLI tests for `main` - a key plus one search
  exits 0 with all three rows PASS and the key never appearing in stdout; no key skips the search
  step and never issues a `tools/call`; `--no-search` never issues a `tools/call` even with a key
  set; a missing tool exits 1; a stubbed transport failure exits 1 printing only
  `FAIL: <ExceptionClassName> reaching the endpoint`; a denied key exits 1 printing the server's
  own public error text without the key value

### Implementation for User Story 3

- [x] T012 [US3] `scripts/maps_check.py`: implement `Transport` (`_headers`, `_post`, `call`,
  `notify`), `_public_error_text`, and `run_check` (depends on T010 existing and passing, and on
  Phase 1)
- [x] T013 [US3] `scripts/maps_check.py`: wire the module docstring, `--no-search`, the hidden
  `--endpoint` test-only override, and `main`'s own exit-code table (depends on T011 existing and
  passing, and on T012)

**Checkpoint**: the live check is proven by test and by a real run against the hosted endpoint
(MEMORY.md's errand row, 2026-09-09, no key set: `server PASS`, `tools PASS`, `search SKIP`, exit
0).

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: docs of record and the commit gate.

- [x] T014 [P] `specs/010-google-maps-connector/`: write the full Spec Kit document set (spec.md,
  plan.md, research.md D1-D7, data-model.md, contracts/connector-and-check.md, quickstart.md,
  this file, checklists/requirements.md)
- [x] T015 [P] `terraform/README.md`: rewrite - keep a short superseded-plan paragraph for the
  Secret Manager history, then this feature's own cost gate, apply steps, key-to-Keychain step,
  gitignore rationale, and terms acknowledgment
- [x] T016 [P] `README.md`: add a "Google Maps connector (optional)" section after "Running an
  errand"
- [x] T017 [P] `scripts/README.md`: add a Maintenance table row for `maps_check.py`
- [x] T018 [P] `Function_Mapping.md`: one sentence noting `scripts/maps_check.py` is a
  maintenance script, not an errand
- [x] T019 [P] `PATTERNS.md`: append one new entry recording the connector choice, the five
  tools, the cost gate, the no-vault reasoning, and the live check
- [x] T020 [P] `Project_Structure.md`: extend the `headless/` row to name `mapsmcp.py`; add rows
  for `scripts/maps_check.py`, `.mcp.json`, and `terraform/`; extend the `tests/` row; append one
  new Changelog row for v0.0.10
- [x] T021 Run the full commit gate: `python -m pytest -q`, `python scripts/verify_structure.py`,
  `python scripts/scan_secrets.py --paths <every file this delivery wrote or edited>` - all
  green, with zero real network calls anywhere in the default suite (spec NFR-001, SC-001)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: no dependencies - can start immediately; BLOCKS User Story 3 (the
  live check calls these message-shape functions)
- **User Story 1 (Phase 2)**: no dependency on Phase 1 - `.mcp.json` is a static file
- **User Story 2 (Phase 3)**: no dependency on Phase 1 or 2 - `terraform/` is independent of the
  Python side entirely
- **User Story 3 (Phase 4)**: depends on Foundational (Phase 1); independent of User Stories 1
  and 2
- **Polish (Phase 5)**: depends on Phases 1 through 4 being complete

### Within Each User Story

- Test tasks (marked `[P]`) before their own implementation task
- `scripts/maps_check.py` implementation tasks (T012, T013) are NOT marked `[P]` against each
  other (both touch the same file)

### Parallel Opportunities

- T001, T002 (Foundational) then T003 (its own tests) in `headless/mapsmcp.py` and
  `tests/test_maps_check.py`
- T004 (User Story 1) in parallel with T005-T009 (User Story 2) and T010-T013 (User Story 3) -
  three independent files/directories
- T014-T020 (Polish, independent files) in parallel; T021 depends on all of them

---

## Implementation Strategy

### MVP First (User Story 2 only)

1. Complete Phase 3 (User Story 2) - the terraform declaration, cost-gated and validated, is the
   precondition every other story's own live behavior depends on
2. **STOP and VALIDATE**: `terraform validate` from `terraform/` passes
3. Phases 1, 2, and 4 (the message shapes, the registration, and the live check) all ship
   together in this same delivery, already part of the Director's own approved brief

### Incremental Delivery

1. Foundational -> the JSON-RPC message shapes are ready for the live check
2. User Story 1 -> independently testable -> the connector is registered and reachable from an
   interactive session, once approved
3. User Story 2 -> independently testable -> `terraform validate` proves the declaration is sound
   before any real apply
4. User Story 3 -> independently testable -> the live check proves the handshake, the tool
   listing, and one billable call all work, value-free
5. Polish -> docs of record, the commit gate

## Notes

- `[P]` tasks touch different files with no dependency on another unchecked task in this list
- `[Story]` maps a task to spec.md's own numbered user story for traceability
- This delivery documents an already-implemented, already-tested feature; T001 through T013
  describe code and tests that exist in this worktree today, not future work
- No merge task and no push task appear anywhere in this list, per this delivery's own brief
- No `--apply`/`terraform apply`/`terraform plan` task appears in this list - those are Director
  actions recorded as pending in MEMORY.md's Open items, never a task this delivery performs
  itself

## Phase 6: Opus verifier fix batch (2026-09-10, as-built)

- [X] T-V01 `Transport._redact` replaces the key value with `***` in every error text; `_public_error_text` never shows a non-JSON body (only its byte length) - the verifier had printed a planted key through a proxy error page.
- [X] T-V02 `CheckOutcome.skipped` carries the skip reason (`SKIP_NO_KEY` / `SKIP_NO_SEARCH`); the `--no-search` row no longer claims the key is unset.
- [X] T-V03 A blank or whitespace-only `HEADLESS_MAPS_API_KEY` counts as unset (`.strip() or None`).
- [X] T-V04 `parse_response` joins SSE continuation lines per event and flattens an array payload.
- [X] T-V05 The transport sends the protocol version the server negotiated in `initialize`.
- [X] T-V06 `count_places` returns None for an unstructured answer; the row prints "answered", never an invented count.
- [X] T-V07 README's terraform block split with the plan-review step; PATTERNS' export line carries `2>/dev/null`; quickstart cites `MEMORY.md` for the terraform install fact.
- [X] T-V08 Tests added: key never echoed from a gateway page (transport and CLI), key redacted from a JSON-RPC error, header absence by name, bare `HTTPError` without body or headers, negotiated protocol version, blank key, `--no-search` stdout, unstructured answer, SSE continuation and array payloads (17 -> 25 tests).
