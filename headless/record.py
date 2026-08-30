"""Recorded-errand scaffolding: turn one hand-driven walk into a draft errand
(spec 007-record-scaffold, v0.0.7).

`scripts/record.py` opens a visible window on the Headless profile and the
Director performs the errand by hand once. A context-wide init script (the
`INIT_SCRIPT` constant below) observes what the Director does - which fields
change, which wizard buttons are clicked, where the pages navigate - and
delivers one structural event per interaction over an exposed binding. This
module is the pure-logic half: it never imports Playwright, so every rule
here is unit-testable without a browser.

The recorder observes; it never drives. Nothing in this module or in
`scripts/record.py` types into a page, clicks anything, or adds any fourth
mode to `headless/gates.py`. The output is a *draft* under
`previews/recordings/` (vault-grade local data, gitignored) that the
Director reviews and promotes to `scripts/` by hand; the draft itself is an
ordinary walk-framework errand and obeys every existing gate when run.

Value handling (the load-bearing invariant): a typed value exists in this
module only inside `WalkRecording.add_event`, in memory, long enough to be
compared against the profile registry's own flattened scalars. What is
stored - and all that can ever reach the JSON artifact or the generated
draft - is the *outcome* of that comparison: a `registry:<dotted.path>`
source reference on a match, or a `literal:` placeholder plus a TODO marker
on a miss. A password field's value never even reaches Python (the init
script sends a flag instead of the value), and an OTP-looking field is
skipped the same way. A click on a terminal-looking control (pay, submit,
verify, OTP...) is never recorded as a step: it becomes the draft's handoff
point and ends the recording, so the generated errand stops exactly where
the constitution requires a human.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# The in-page observer. Injected via `context.add_init_script` so it re-arms
# on every navigation, and delivers events through the exposed binding
# `_headlessRecordEvent` (a context-wide `expose_binding`, which survives
# navigation the same way). Guarded so a page that re-runs init scripts (an
# SPA soft reload) never double-registers, and wrapped so a recorder bug can
# never break the page the Director is working in.
#
# The script sends a password field's *flag*, never its value, and truncates
# every text fragment it does send (labels, button captions) to `MAX_TEXT`
# characters. Selector derivation prefers, in order: a unique `#id`, a
# unique `[data-testid=...]`, a unique `tag[name=...]`, a unique
# `[aria-label=...]`, then a short `tag:nth-of-type` path - the same kind of
# selector an errand author would have written by hand.
# ---------------------------------------------------------------------------

INIT_SCRIPT = r"""
(() => {
  if (window.__headlessRecorderInstalled) return;
  window.__headlessRecorderInstalled = true;
  const MAX_TEXT = 60;
  const esc = (s) => (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/[^a-zA-Z0-9_-]/g, "_");
  const trim = (s) => (s || "").replace(/\s+/g, " ").trim().slice(0, MAX_TEXT);
  const unique = (sel) => {
    try { return document.querySelectorAll(sel).length === 1; } catch (e) { return false; }
  };
  const selectorFor = (el) => {
    if (el.id && unique("#" + esc(el.id))) return "#" + el.id;
    const testid = el.getAttribute && el.getAttribute("data-testid");
    if (testid && unique('[data-testid="' + esc(testid) + '"]')) return '[data-testid="' + testid + '"]';
    const tag = el.tagName ? el.tagName.toLowerCase() : "";
    if (el.name && unique(tag + '[name="' + esc(el.name) + '"]')) return tag + '[name="' + el.name + '"]';
    const aria = el.getAttribute && el.getAttribute("aria-label");
    if (aria && unique('[aria-label="' + esc(aria) + '"]')) return '[aria-label="' + aria + '"]';
    const parts = [];
    let node = el;
    for (let depth = 0; node && node.nodeType === 1 && depth < 5; depth++) {
      const t = node.tagName.toLowerCase();
      if (node.id) { parts.unshift("#" + node.id); break; }
      let nth = 1, sib = node;
      while ((sib = sib.previousElementSibling)) { if (sib.tagName === node.tagName) nth++; }
      parts.unshift(t + ":nth-of-type(" + nth + ")");
      node = node.parentElement;
    }
    return parts.join(" > ");
  };
  const labelFor = (el) => {
    if (el.labels && el.labels.length) return trim(el.labels[0].innerText);
    const closest = el.closest && el.closest("label");
    if (closest) return trim(closest.innerText);
    return trim(el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.name || el.id || "");
  };
  const deliver = (payload) => {
    try {
      if (window._headlessRecordEvent) window._headlessRecordEvent(JSON.stringify(payload));
    } catch (e) { /* never break the page the Director is working in */ }
  };
  document.addEventListener("change", (ev) => {
    try {
      const el = ev.target;
      if (!el || !el.tagName) return;
      const tag = el.tagName.toLowerCase();
      if (tag !== "input" && tag !== "textarea" && tag !== "select") return;
      const inputType = (el.getAttribute("type") || (tag === "input" ? "text" : tag)).toLowerCase();
      const isPassword = inputType === "password";
      const payload = {
        type: "change",
        selector: selectorFor(el),
        tag: tag,
        inputType: inputType,
        name: el.name || "",
        id: el.id || "",
        label: labelFor(el),
        autocomplete: (el.getAttribute("autocomplete") || "").toLowerCase(),
        password: isPassword,
        checked: (inputType === "checkbox" || inputType === "radio") ? !!el.checked : null,
        value: "",
      };
      if (!isPassword && inputType !== "checkbox" && inputType !== "radio") payload.value = String(el.value);
      deliver(payload);
    } catch (e) { /* observation must never throw into the page */ }
  }, true);
  document.addEventListener("click", (ev) => {
    try {
      const el = ev.target && ev.target.closest ? ev.target.closest(
        'button, a, [role="button"], input[type="button"], input[type="submit"], input[type="image"], summary'
      ) : null;
      if (!el) return;
      deliver({
        type: "click",
        selector: selectorFor(el),
        text: trim(el.innerText || el.value || el.getAttribute("aria-label") || ""),
      });
    } catch (e) { /* observation must never throw into the page */ }
  }, true);
})();
"""

# A click whose visible text looks like a terminal action ends the recording
# and becomes the handoff point instead of a step. Mirrors the constitution's
# terminal-actions list (pay, submit, e-verify, confirm booking, OTP);
# deliberately broad - a false positive costs one hand-written ClickStep in
# review, a false negative would scaffold a click the framework must never
# perform.
TERMINAL_TEXT_RE = re.compile(
    r"(?i)\b(pay(?:ment)?|purchase|buy|checkout|place\s+order|submit|confirm|"
    r"e-?verify|verify|otp|one[\s-]?time)\b"
)

# An input whose name, id, label, or autocomplete hints at a one-time code is
# skipped entirely - same posture as a password field. The autocomplete
# standard's own token is `one-time-code`.
OTP_HINT_RE = re.compile(r"(?i)(?:^|[\s_-])(otp|one[\s_-]?time|verification[\s_-]?code|2fa|mfa)(?:$|[\s_-])")

_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*$")

MAX_STEP_NAME = 60


@dataclass
class RecordedField:
    """One form control the Director filled, with its value already replaced
    by the registry-match outcome. `source_ref` is a full `registry:...`,
    or `literal:...` string; `alternatives` lists further registry paths the
    same value matched (paths only, never values)."""

    name: str
    selector: str
    kind: str  # "fill" | "select" | "check"
    source_ref: str
    matched: bool
    alternatives: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RecordedClick:
    name: str
    selector: str


@dataclass(frozen=True)
class RecordedNav:
    url: str


@dataclass(frozen=True)
class SkippedField:
    """A password or OTP-looking control: recorded as a fact (selector and
    reason only, both value-free) so the draft can explain the gap, never as
    a fillable step."""

    selector: str
    reason: str  # "password" | "otp"


def flatten_registry(document: object, prefix: str = "") -> list[tuple[str, str]]:
    """Flatten a profile document into `(dotted.path, value)` pairs, the
    match table `WalkRecording` compares typed values against.

    Mirrors `ProfileRegistry.get`'s own addressing exactly, in reverse: a
    scalar becomes one pair; a dict recurses; a list uses type-discriminated
    addressing (spec 005, research.md D13) - each element that is a dict
    with a scalar `type` field is addressed as `<prefix>.<type>`, and an
    element without one is skipped, exactly as traversal would never reach
    it. A `type` value shared by two elements is skipped for both: the
    forward path would raise `RegistryAmbiguous`, so no pair built from it
    could ever resolve. Empty-string scalars are dropped - matching an
    untouched empty field against them would be noise, never signal.
    """
    pairs: list[tuple[str, str]] = []
    if isinstance(document, dict):
        for key, value in document.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            pairs.extend(flatten_registry(value, path))
    elif isinstance(document, list):
        seen: dict[str, int] = {}
        for element in document:
            if isinstance(element, dict):
                type_value = element.get("type")
                if isinstance(type_value, str) and type_value:
                    seen[type_value] = seen.get(type_value, 0) + 1
        for element in document:
            if not isinstance(element, dict):
                continue
            type_value = element.get("type")
            if not isinstance(type_value, str) or not type_value or seen.get(type_value, 0) > 1:
                continue
            pairs.extend(flatten_registry(element, f"{prefix}.{type_value}" if prefix else type_value))
    elif isinstance(document, (str, int, float, bool)):
        text = str(document).strip()
        if text:
            pairs.append((prefix, text))
    return pairs


def match_value(value: str, flattened: list[tuple[str, str]]) -> list[str]:
    """Every registry path whose value equals `value` exactly (after both
    sides strip whitespace), in flattened order. The caller keeps the paths
    and discards the value."""
    needle = value.strip()
    if not needle:
        return []
    return [path for path, candidate in flattened if candidate == needle]


def _clean_name(text: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()[:MAX_STEP_NAME]
    return cleaned or fallback


class WalkRecording:
    """Accumulates in-page events into an ordered, value-free walk.

    `add_event` is the only place a typed value exists; it leaves as a
    source reference or a placeholder. Events arriving after a terminal
    click are ignored - the recording is over at that point by definition.
    """

    def __init__(self, start_url: str, flattened: list[tuple[str, str]] | None = None) -> None:
        self.start_url = start_url
        self._flattened = flattened or []
        self.steps: list[object] = []  # RecordedField | RecordedClick | RecordedNav, in order
        self.skipped: list[SkippedField] = []
        self.handoff_label: str | None = None
        self._field_index: dict[str, int] = {}  # selector -> position in steps
        self._skipped_selectors: set[str] = set()

    @property
    def terminal_reached(self) -> bool:
        return self.handoff_label is not None

    def add_event(self, event: dict) -> None:
        if self.terminal_reached:
            return
        kind = event.get("type")
        if kind == "change":
            self._add_change(event)
        elif kind == "click":
            self._add_click(event)
        elif kind == "nav":
            url = str(event.get("url", ""))
            if url and not (self.steps and isinstance(self.steps[-1], RecordedNav) and self.steps[-1].url == url):
                self.steps.append(RecordedNav(url=url))

    def _add_change(self, event: dict) -> None:
        selector = str(event.get("selector", ""))
        if not selector:
            return
        hint_text = " ".join(
            str(event.get(key, "")) for key in ("name", "id", "label", "autocomplete")
        )
        if event.get("password"):
            reason = "password"
        elif event.get("autocomplete") == "one-time-code" or OTP_HINT_RE.search(hint_text):
            reason = "otp"
        else:
            reason = None
        if reason is not None:
            if selector not in self._skipped_selectors:
                self._skipped_selectors.add(selector)
                self.skipped.append(SkippedField(selector=selector, reason=reason))
            return

        name = _clean_name(str(event.get("label", "")), fallback=selector)
        input_type = str(event.get("inputType", "text"))
        if input_type in ("checkbox", "radio"):
            kind = "check"
            source_ref = "literal:true" if event.get("checked") else "literal:false"
            matched, alternatives = True, []
        else:
            kind = "select" if event.get("tag") == "select" else "fill"
            value = str(event.get("value", ""))
            matches = match_value(value, self._flattened)
            del value  # the raw value's lifetime ends at the comparison above
            if matches:
                source_ref = f"registry:{matches[0]}"
                matched, alternatives = True, matches[1:]
            else:
                source_ref = "literal:"
                matched, alternatives = False, []

        recorded = RecordedField(
            name=name, selector=selector, kind=kind, source_ref=source_ref,
            matched=matched, alternatives=alternatives,
        )
        if selector in self._field_index:
            # The Director corrected an earlier entry: the field keeps its
            # original position in the walk, only its outcome updates.
            self.steps[self._field_index[selector]] = recorded
        else:
            self._field_index[selector] = len(self.steps)
            self.steps.append(recorded)

    def _add_click(self, event: dict) -> None:
        selector = str(event.get("selector", ""))
        if not selector:
            return
        text = _clean_name(str(event.get("text", "")), fallback=selector)
        if TERMINAL_TEXT_RE.search(text):
            self.handoff_label = text
            return
        self.steps.append(RecordedClick(name=text, selector=selector))

    def field_steps(self) -> list[RecordedField]:
        return [s for s in self.steps if isinstance(s, RecordedField)]

    def click_steps(self) -> list[RecordedClick]:
        return [s for s in self.steps if isinstance(s, RecordedClick)]

    def dependencies(self) -> list[str]:
        seen: list[str] = []
        for step in self.steps:
            if isinstance(step, (RecordedField, RecordedClick)) and step.selector not in seen:
                seen.append(step.selector)
        return seen


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def to_walk_json(recording: WalkRecording, errand_name: str) -> str:
    """The value-free JSON artifact written beside the draft. Holds
    selectors, names, source references, and match facts - the same
    information the draft itself shows, in a shape a later tool can read."""
    steps: list[dict] = []
    for step in recording.steps:
        if isinstance(step, RecordedField):
            steps.append({
                "kind": step.kind, "name": step.name, "selector": step.selector,
                "source": step.source_ref, "matched": step.matched,
                "alternatives": step.alternatives,
            })
        elif isinstance(step, RecordedClick):
            steps.append({"kind": "click", "name": step.name, "selector": step.selector})
        elif isinstance(step, RecordedNav):
            steps.append({"kind": "nav", "url": step.url})
    payload = {
        "schema_version": 1,
        "errand": errand_name,
        "start_url": recording.start_url,
        "recorded_at_utc": utc_timestamp(),
        "handoff": recording.handoff_label,
        "steps": steps,
        "skipped": [{"selector": s.selector, "reason": s.reason} for s in recording.skipped],
    }
    return json.dumps(payload, indent=2)


def validate_errand_name(name: str) -> None:
    """A draft's name must be a lowercase-hyphen slug: it becomes the file
    name, the `Errand.name`, and (camelized) the class name."""
    if not _SLUG_RE.match(name):
        raise ValueError(
            f"errand name {name!r} must be a lowercase slug (letters, digits, hyphens; starts with a letter)"
        )


def _camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("-"))


def generate_draft(recording: WalkRecording, errand_name: str) -> str:
    """Render the recording as a draft errand script: an ordinary
    walk-framework `Errand` subclass, review markers included. The returned
    source contains no typed value - only selectors, names, and source
    references - and compiles as-is.
    """
    validate_errand_name(errand_name)
    class_name = f"{_camel(errand_name)}Errand"
    if recording.handoff_label:
        handoff = (
            f"{recording.handoff_label}: stopped before this control - the recording ended here "
            "and this action stays yours"
        )
    else:
        handoff = "TODO: describe the step only you may take (the recording saw no terminal control)"

    uses_clicks = bool(recording.click_steps())
    unmatched = [s for s in recording.field_steps() if not s.matched]

    lines: list[str] = []
    walk_body: list[str] = []
    for step in recording.steps:
        if isinstance(step, RecordedNav):
            walk_body.append(f"            # arrived: {step.url}")
        elif isinstance(step, RecordedField):
            if not step.matched:
                walk_body.append(
                    "            # TODO: no registry match for this field - set the real source"
                )
                walk_body.append(
                    "            # (registry:<dotted.path>, secret:<item>, or literal:<text>)"
                )
            elif step.alternatives:
                walk_body.append(
                    f"            # the recorded value also matches: {', '.join(step.alternatives)}"
                )
            kind_arg = "" if step.kind == "fill" else f", kind={step.kind!r}"
            walk_body.append(
                f"            FieldPlan(name={step.name!r}, selector={step.selector!r}, "
                f"source=parse_source({step.source_ref!r}){kind_arg}),"
            )
        elif isinstance(step, RecordedClick):
            walk_body.append(
                f"            ClickStep(name={step.name!r}, selector={step.selector!r}),"
            )
    if not walk_body:
        walk_body.append("            # the recording captured no steps")

    skip_notes = []
    for skipped in recording.skipped:
        if skipped.reason == "password":
            why = "password: login seeding stays human, the session-cookie mechanism keeps it"
        else:
            why = "OTP: one-time codes are human-only"
        skip_notes.append(f"{skipped.selector} ({why})")

    lines.append("#!/usr/bin/env python3")
    doc = [
        f'"""{errand_name}: DRAFT errand recorded by scripts/record.py (spec 007-record-scaffold).',
        "",
        "REVIEW BEFORE USE. This file was scaffolded from one hand-driven walk and is a",
        "starting point, not a finished errand: verify every selector, resolve every TODO",
        "source, tighten the handoff text, then move this file into scripts/ and add its",
        "row to Function_Mapping.md (same commit). It runs the ordinary walk framework -",
        "preview by default, --check probes selectors, --apply fills up to the handoff.",
        "",
        f"Site: {recording.start_url}",
        "Reads: page titles and the masked preview screenshot.",
        f"Writes (up to): the {len(recording.field_steps())} recorded field(s) and "
        f"{len(recording.click_steps())} recorded click(s) below, never past the handoff.",
        "Secrets / profile fields: the registry paths named in walk() below.",
        f"Handoff: {handoff}",
    ]
    if skip_notes:
        doc.append("Skipped during recording (never scaffolded): " + "; ".join(skip_notes) + ".")
    doc.append('"""')
    lines.extend(doc)
    lines.extend([
        "",
        "from __future__ import annotations",
        "",
        "import sys",
        "from pathlib import Path",
        "",
        "# Same convention as every errand: no packaging step for a personal tool, just",
        '# insert the repo root so "import headless" resolves.',
        "REPO_ROOT = Path(__file__).resolve().parent.parent",
        "if str(REPO_ROOT) not in sys.path:",
        "    sys.path.insert(0, str(REPO_ROOT))",
        "",
        "from headless.errand import Errand",
        "from headless.fields import FieldPlan, parse_source",
    ])
    if uses_clicks:
        lines.append("from headless.steps import ClickStep")
    lines.extend([
        "",
        f"HANDOFF = {handoff!r}",
        "",
        "",
        f"class {class_name}(Errand):",
        f"    name = {errand_name!r}",
        "    HANDOFF = HANDOFF",
        f"    dependencies = {recording.dependencies()!r}",
        "",
        "    def url(self, args) -> str:",
        f"        return {recording.start_url!r}",
        "",
        "    def walk(self, registry) -> list:",
        "        return [",
        *walk_body,
        "        ]",
        "",
        "",
        "def main(argv: list[str] | None = None) -> int:",
        f"    return {class_name}().run(argv)",
        "",
        "",
        'if __name__ == "__main__":',
        "    raise SystemExit(main())",
        "",
    ])
    if unmatched:
        # A draft with unresolved sources must say so at the top as well as
        # inline: the Director reads the head of the file first.
        marker = (
            f"# NOTE: {len(unmatched)} field(s) below carry a TODO source - "
            "resolve them before any --apply run.\n"
        )
        lines.insert(1, marker.rstrip("\n"))
    return "\n".join(lines)
