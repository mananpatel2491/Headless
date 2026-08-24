"""The Errand base class: argparse wiring plus the run state machine.

Every errand script subclasses `Errand`, sets `name` and `HANDOFF`, declares
`dependencies` (the selectors `--check` probes), and implements
`plan(registry)`. `run()` executes the state machine from data-model.md:
load_config -> resolve_mode -> pre-resolve every plan source, in every mode,
so a missing secret or registry path fails before any window opens -> Session
-> goto -> mode branch -> PreviewRecord + write_artifacts -> stdout line ->
exit code.

Exception handling is split into two blocks with different exit-code and
print-format rules:

- Pre-session block (before any browser is touched): `ConfigError`,
  `GateRefused`, `SecretMissing`, `RegistryMissing` print `REFUSED: <exc>`
  and exit 1 (their messages never carry a raw secret/registry value, only
  names/paths, so printing them is safe). `ProfileError` (malformed `profile`
  JSON; a `ValueError` subclass with a position-only message - see
  profile.py), `SourceError`, and `FileNotFoundError` print
  `ERROR: <ClassName>: <exc>` and exit 1. A bare `ValueError` that is not one
  of these (N10: deliberately narrowed, not "any ValueError") falls through
  to the generic branch below instead. Anything else prints only the class
  name plus a HEADLESS_DEBUG hint and exits 1.
- Post-session block (a real browser process is already running):
  `FillFailed`, `ConfigError`, `GateRefused`, `SecretMissing`,
  `RegistryMissing` print `ERROR: <ClassName>: <exc>` and exit 2 (their
  messages are safe to print; `FillFailed` in particular is engineered to
  hold only redacted values, never a raw one - see session.py). Any other
  exception - including a raw Playwright error whose call log could embed a
  just-typed secret - prints only its class name
  (`ERROR: <ClassName> (rerun with HEADLESS_DEBUG=1 for the traceback)`) and
  exits 2; the traceback goes to stderr only when HEADLESS_DEBUG=1 is set.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback

from headless.config import ConfigError, load_config
from headless.fields import FieldPlan, SourceError, resolve_source
from headless.gates import GateRefused, Mode, add_mode_arguments, resolve_mode
from headless.preview import PreviewRecord, write_artifacts
from headless.profile import ProfileError, ProfileRegistry, RegistryMissing
from headless.secrets import SecretMissing, VaultBackend, open_vault
from headless.session import FillFailed, Session


class _LazyProfileRegistry:
    """Defers `ProfileRegistry.load(vault)` until the first `.get()` call.

    An errand whose plan never references the registry (probe.py's plan is
    empty) must never require a `profile` vault item to exist. `plan()`
    always receives a registry-shaped object; the vault fetch only happens if
    a FieldPlan actually resolves a `registry:` source.
    """

    def __init__(self, vault: VaultBackend) -> None:
        self._vault = vault
        self._loaded: ProfileRegistry | None = None

    def get(self, dotted: str) -> str:
        if self._loaded is None:
            self._loaded = ProfileRegistry.load(self._vault)
        return self._loaded.get(dotted)


def _debug_enabled() -> bool:
    return os.environ.get("HEADLESS_DEBUG") == "1"


def _print_debug_traceback() -> None:
    if _debug_enabled():
        traceback.print_exc(file=sys.stderr)


class Errand:
    name: str = ""
    HANDOFF: str = ""
    dependencies: list[str] = []

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Hook for errand-specific arguments (e.g. a positional URL). No-op by default."""

    def plan(self, registry) -> list[FieldPlan]:
        """The fields apply would fill, in order. Empty for read-only errands."""
        return []

    def url(self, args: argparse.Namespace) -> str:
        """The address this run opens. Override, or add a `url` argument via add_arguments."""
        value = getattr(args, "url", None)
        if not value:
            raise NotImplementedError(f"{type(self).__name__} must define url() or an args.url")
        return value

    def _build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description=self.__doc__ or self.name)
        add_mode_arguments(parser)
        self.add_arguments(parser)
        return parser

    @staticmethod
    def _overrides(args: argparse.Namespace) -> dict[str, object]:
        overrides: dict[str, object] = {}
        if getattr(args, "profile_dir", None):
            overrides["profile_dir"] = args.profile_dir
        if getattr(args, "headless", False):
            overrides["headless"] = True
        if getattr(args, "preview_dir", None):
            overrides["preview_dir"] = args.preview_dir
        if getattr(args, "no_screenshot", False):
            overrides["screenshots"] = False
        if getattr(args, "show", False):
            overrides["show"] = True
        return overrides

    def run(self, argv: list[str] | None = None) -> int:
        parser = self._build_parser()
        args = parser.parse_args(argv)

        try:
            config = load_config(self._overrides(args))
            mode = resolve_mode(args, isatty=sys.stdin.isatty(), headed=config.headed)
            vault = open_vault(config)
            registry = _LazyProfileRegistry(vault)
            plan = self.plan(registry)

            # Fail before any window opens (FR-004, SC-006, data-model.md
            # state transitions): every planned source must resolve now, in
            # every mode - not just apply - so a broken plan never gets as
            # far as a browser window.
            for field_plan in plan:
                resolve_source(field_plan.source, vault, registry)
        except (ConfigError, GateRefused, SecretMissing, RegistryMissing) as exc:
            print(f"REFUSED: {exc}")
            return 1
        except (ProfileError, SourceError, FileNotFoundError) as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}")
            return 1
        except Exception as exc:
            print(f"ERROR: {type(exc).__name__} (rerun with HEADLESS_DEBUG=1 for the traceback)")
            _print_debug_traceback()
            return 1

        try:
            with Session(config, mode) as session:
                session.goto(self.url(args))
                title = session.page.title()
                print(f"Title: {title}")

                fields_for_record: list[dict] = []
                checks_for_record: list[dict] = []

                if mode is Mode.CHECK:
                    checks_for_record = [
                        {"selector": selector, "found": found}
                        for selector, found in session.probe(self.dependencies)
                    ]
                else:
                    for field_plan in plan:
                        value = resolve_source(field_plan.source, vault, registry)
                        fields_for_record.append(
                            {
                                "name": field_plan.name,
                                "selector": field_plan.selector,
                                "source_kind": field_plan.source.kind,
                                "value": value,
                            }
                        )
                        if mode is Mode.APPLY:
                            session.fill(field_plan, vault, registry)

                record = PreviewRecord(
                    errand=self.name,
                    mode=mode.value,
                    url=session.page.url,
                    title=title,
                    handoff=self.HANDOFF,
                    fields=fields_for_record,
                    checks=checks_for_record,
                )
                screenshot = session.screenshot() if config.screenshots else None
                _png_path, json_path = write_artifacts(record, screenshot, config.preview_dir)

                if mode is Mode.APPLY:
                    session.handoff(self.HANDOFF)
                    print(f'APPLY handed off at "{self.HANDOFF}"')
                elif mode is Mode.CHECK:
                    found = sum(1 for c in checks_for_record if c["found"])
                    missing = len(checks_for_record) - found
                    print(f"CHECK {found} found, {missing} missing")
                else:
                    print(f"PREVIEW {json_path}")
        except (FillFailed, ConfigError, GateRefused, SecretMissing, RegistryMissing) as exc:
            # Post-launch: a browser process is already running. Every class
            # here is engineered so str(exc) never carries a raw secret or
            # registry value (FillFailed holds only redact()ed text).
            print(f"ERROR: {type(exc).__name__}: {exc}")
            return 2
        except Exception as exc:
            # Anything else - including a raw Playwright exception whose
            # call log could embed a just-typed secret - never has its
            # message printed, only its class name.
            print(f"ERROR: {type(exc).__name__} (rerun with HEADLESS_DEBUG=1 for the traceback)")
            _print_debug_traceback()
            return 2

        return 0
