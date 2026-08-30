#!/usr/bin/env python3
"""record: watch the Director do an errand by hand once, then scaffold a draft.

Background (spec 007-record-scaffold): every errand so far was hand-written.
This maintenance script lowers the cost of adding one. It opens a visible
window on the Headless profile, the Director performs the errand by hand,
and an injected observer (headless/record.py's INIT_SCRIPT) reports which
fields changed, which wizard buttons were clicked, and where the pages
navigated. When the Director presses Enter here, the recording becomes two
artifacts under previews/recordings/ (vault-grade local data, gitignored):

- <name>-<timestamp>.json: the value-free walk record, and
- <name>-<timestamp>-draft.py: a draft walk-framework errand script.

The recorder observes; it never drives. It types nothing, clicks nothing,
and adds no fourth mode to headless/gates.py - the Director's own hands do
every site interaction during recording, exactly as if this script were not
running. Typed values are compared against the profile registry in memory
and only the outcome is kept: a registry:<dotted.path> source on a match, a
literal: placeholder plus a TODO marker otherwise. A password field's value
never reaches Python at all; an OTP-looking field is skipped the same way;
a click on a pay/submit/verify/OTP-looking control is never scaffolded - it
ends the recording and becomes the draft's handoff point.

Not a browser errand: the errand contract (preview/apply/check modes, a
HANDOFF of its own) does not apply to this script - the DRAFT it writes has
both. The generated draft is a starting point for review, promoted to
scripts/ by hand - see the summary this script prints, and
scripts/README.md's Maintenance table.

Site: any URL the Director passes on the command line.
Reads: the Director's own interactions with the page, structurally.
Writes: nothing on any site; two local artifacts under previews/recordings/.
Secrets / profile fields: reads the whole `profile` vault item (one
passphrase prompt) to build the value-to-path match table, unless
--no-registry is passed; stores paths only, never values.

Usage: python scripts/record.py <URL> <errand-name> [--no-registry]
       [--profile-dir PATH] [--preview-dir PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

# Same convention as every errand: no packaging step for a personal tool, just
# insert the repo root so "import headless" resolves.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from headless.config import ConfigError, load_config
from headless.gates import GateRefused, Mode
from headless.record import (
    INIT_SCRIPT,
    WalkRecording,
    flatten_registry,
    generate_draft,
    to_walk_json,
    utc_timestamp,
    validate_errand_name,
)
from headless.secrets import SecretMissing, open_vault
from headless.session import Session


def _debug_enabled() -> bool:
    return os.environ.get("HEADLESS_DEBUG") == "1"


def _print_debug_traceback() -> None:
    if _debug_enabled():
        traceback.print_exc(file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", help="The address the errand starts at.")
    parser.add_argument(
        "name",
        help="The draft errand's name: a lowercase slug (letters, digits, hyphens).",
    )
    parser.add_argument(
        "--no-registry",
        action="store_true",
        help="Skip the profile-registry match table: every recorded field becomes a TODO source.",
    )
    parser.add_argument("--profile-dir", dest="profile_dir", default=None, help="Override HEADLESS_PROFILE_DIR.")
    parser.add_argument("--preview-dir", dest="preview_dir", default=None, help="Override HEADLESS_PREVIEW_DIR.")
    return parser


def _load_match_table(config, *, skip: bool) -> list[tuple[str, str]]:
    """The value-to-path table recorded values are matched against. Any
    failure to build it (no vault yet, no profile item, malformed JSON)
    collapses to one value-free note and recording proceeds unmatched -
    the recorder must work on a machine whose vault is not seeded yet."""
    if skip:
        return []
    try:
        vault = open_vault(config)
        document = json.loads(vault.get_secret("profile"))
        if not isinstance(document, dict):
            raise ValueError("profile item is not a JSON object")
        return flatten_registry(document)
    except SecretMissing:
        print("note: no `profile` vault item - recording without registry matching")
        return []
    except Exception as exc:
        print(f"note: registry match table unavailable ({type(exc).__name__}) - recording without it")
        return []


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        validate_errand_name(args.name)
        overrides: dict[str, object] = {"show": True}
        if args.profile_dir:
            overrides["profile_dir"] = args.profile_dir
        if args.preview_dir:
            overrides["preview_dir"] = args.preview_dir
        config = load_config(overrides)
        if not sys.stdin.isatty():
            raise GateRefused("recording needs an interactive terminal")
        if not config.headed:
            raise GateRefused("recording needs a visible browser (HEADLESS_HEADED is off)")
        if config.cdp_url:
            raise GateRefused(
                "recording is refused on the CDP-attach path: the observer would be "
                "injected into the Director's own browser context, not one Headless launched"
            )
    except (ConfigError, GateRefused) as exc:
        print(f"REFUSED: {exc}")
        return 1
    except ValueError as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 1

    flattened = _load_match_table(config, skip=args.no_registry)
    recording = WalkRecording(start_url=args.url, flattened=flattened)

    def on_event(_source, payload: str) -> None:
        # The binding delivers one JSON string per interaction. A malformed
        # payload is dropped silently: the observer is best-effort and a
        # recorder problem must never disturb the Director's own walk.
        try:
            recording.add_event(json.loads(payload))
        except Exception:
            pass

    try:
        # Preview mode plus show=True: a visible window, and Session's own
        # gates still refuse fill/click outright - this run never calls them.
        with Session(config, Mode.PREVIEW) as session:
            session.context.expose_binding("_headlessRecordEvent", on_event)
            session.context.add_init_script(INIT_SCRIPT)

            def on_navigated(frame) -> None:
                try:
                    if frame is session.page.main_frame:
                        recording.add_event({"type": "nav", "url": frame.url})
                except Exception:
                    pass

            session.page.on("framenavigated", on_navigated)
            session.goto(args.url)
            print(f"Title: {session.page.title()}")
            print()
            print("Recording. Do the errand by hand in the window - fill the fields the way")
            print("you normally would. Stop at the step only you may take (pay, submit,")
            print("verify, OTP) and press Enter HERE to finish the recording. If you click")
            print("such a control anyway, the recording ends there by itself and nothing")
            print("past it is scaffolded.")
            input("Press Enter when done... ")
            # Flush: queued observer events are dispatched while the driver
            # is servicing calls, so give it a few short turns before reading
            # the recording.
            for _ in range(3):
                session.page.wait_for_timeout(200)
    except (ConfigError, GateRefused) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 2
    except Exception as exc:
        # A raw Playwright error's message can embed page content; print the
        # class name only. The recording gathered so far is still written
        # below - a window the Director closed early is a normal ending.
        print(f"note: browser session ended early ({type(exc).__name__})")
        _print_debug_traceback()

    timestamp = utc_timestamp()
    recordings_dir = Path(config.preview_dir) / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    json_path = recordings_dir / f"{args.name}-{timestamp}.json"
    json_path.write_text(to_walk_json(recording, args.name), encoding="utf-8")

    fields = recording.field_steps()
    clicks = recording.click_steps()
    unmatched = [step for step in fields if not step.matched]

    if not fields and not clicks:
        print("RECORDED nothing: no field changes or wizard clicks were observed.")
        print(f"Walk record (empty): {json_path}")
        return 0

    draft_path = recordings_dir / f"{args.name}-{timestamp}-draft.py"
    draft_path.write_text(generate_draft(recording, args.name), encoding="utf-8")

    print(
        f"RECORDED {len(fields)} field(s) ({len(fields) - len(unmatched)} matched to the "
        f"registry, {len(unmatched)} TODO), {len(clicks)} click(s), "
        f"{len(recording.skipped)} skipped control(s)."
    )
    if recording.handoff_label:
        print(f"Handoff detected: stopped before {recording.handoff_label!r}.")
    else:
        print("No terminal control was seen: the draft's HANDOFF is a TODO to write.")
    print(f"Walk record: {json_path}")
    print(f"Draft errand: {draft_path}")
    print()
    print("Next: review the draft (every selector, every TODO source, the HANDOFF text),")
    print(f"then promote it: move it to scripts/{args.name}.py, add its Function_Mapping.md")
    print("row in the same commit, and run it in preview mode first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
