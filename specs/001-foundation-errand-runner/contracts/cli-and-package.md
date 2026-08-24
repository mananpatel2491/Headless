# Contracts: Foundation Errand Runner

**Feature**: 001-foundation-errand-runner | **Date**: 2026-08-24

Headless exposes two interfaces: the **errand command line** every script follows, and the
**package API** scripts compose. Both are stable contracts for later features.

## 1. Errand command line

```text
python scripts/<errand>.py [URL or errand args] [--apply | --check]
                           [--profile-dir PATH] [--headless | --show]
                           [--preview-dir PATH] [--no-screenshot]
```

Quiet by default (v0.0.1, Director decision 2026-08-24): preview and check are invisible
unless `--show`; apply always opens a real window (the handoff needs one) but keeps it
hidden until the handoff, unless `--show`.

| Flag | Meaning | Constraints |
| :--- | :--- | :--- |
| (none) | preview mode: no site writes, artifact written, invisible | default |
| `--apply` | fill up to `HANDOFF`, then "Your turn" | requires interactive terminal and a real window available; mutually exclusive with `--check` |
| `--check` | read-only: report each dependent selector found/missing | mutually exclusive with `--apply` |
| `--profile-dir` | override `HEADLESS_PROFILE_DIR` | |
| `--headless` | force invisible for preview/check (explicit; overrides `HEADLESS_SHOW=1`) | refused together with `--apply` (the handoff needs a window); mutually exclusive with `--show` |
| `--show` | force the window visible for any mode; for apply, disables the quiet-until-handoff hide (does not change what mode does, only when the window is shown) | mutually exclusive with `--headless` |
| `--preview-dir` | override `HEADLESS_PREVIEW_DIR` | must be absolute, or the literal default `previews` (which resolves against the repository root, never the process's cwd); any other relative value raises `ConfigError` before any browser call (N3: relative paths would escape `.gitignore`) |
| `--no-screenshot` | write only the JSON preview artifact | equivalent to `HEADLESS_SCREENSHOTS=0`; `Config.screenshots` defaults `True` |

Forbidden flags (must never exist on any errand): `--submit`, `--pay`, `--verify`, `--otp`,
`--yes`, `--confirm`.

**Exit codes**: `0` success. `1`: gate refused, missing secret or registry path, or config
error, always caught before any browser is touched (every plan source is pre-resolved in
every mode - preview, check, and apply - before `Session` opens). `2`: any failure once a
browser process is already running, including a `FillFailed` (a locator action failed during
`--apply`) and a gate refusal that surfaces post-launch (e.g. the profile-lock `GateRefused`
raised by `Session.__enter__`).

**Stdout**: one line per step, final line `PREVIEW <path.json>` / `CHECK <n> found, <m>
missing` / `APPLY handed off at "<HANDOFF>"`. Never a secret or registry value (SC-002). A
pre-launch refusal prints `REFUSED: <message>`; a post-launch failure prints
`ERROR: <ExceptionClassName>: <message>` only for the five exception classes engineered to
never carry a raw value (`ConfigError`, `GateRefused`, `SecretMissing`, `RegistryMissing`,
`FillFailed`) - any other exception prints only its class name
(`ERROR: <ExceptionClassName> (rerun with HEADLESS_DEBUG=1 for the traceback)`); its traceback
goes to stderr only when `HEADLESS_DEBUG=1` is set, never to stdout.

### `scripts/check_env.py`

```text
python scripts/check_env.py
```

A maintenance script (see `scripts/README.md`), not an errand: it takes no
`--apply`/`--check`/`--profile-dir`/`--headless`/`--preview-dir` flags and has
no `HANDOFF`. Its own minimal argument parser (help only) refuses an unknown
flag (e.g. `--submit`) with a non-zero exit, the same as every other script.

Prints a four-row table (`browser`, `playwright`, `profile_dir`, `vault`);
each row prints `PASS`, `FAIL`, or `SKIP` (skipped because an earlier
configuration failure makes the check meaningless - for example every row
but `vault` is `SKIP` when `HEADLESS_SECRETS_BACKEND=gcp` is set without
`HEADLESS_GCP_PROJECT`) with a hint on `FAIL`/`SKIP`; exit `0` only when
every row is `PASS`. No browser window is opened.

### `scripts/probe.py`

```text
python scripts/probe.py <URL> [--check] [--profile-dir PATH] [--headless | --show]
                              [--preview-dir PATH] [--no-screenshot]
```

Opens the URL in the Headless profile (invisible by default), prints the title, writes the
preview artifact. `HANDOFF = "n/a (read-only errand)"`; `--apply` is accepted by the shared
parser but has no fields to fill and therefore behaves like preview except the window opens
hidden and is surfaced only when the Director presses Enter at the handoff (this is how
logins are seeded); `--show` keeps it visible throughout instead.

## 2. Package API (`headless/`)

```python
# headless/config.py
class ConfigError(RuntimeError): ...
@dataclass(frozen=True)
class Config: profile_dir: Path; headed: bool; cdp_url: str | None; secrets_backend: str;
              keychain_account: str; gcp_project: str | None; preview_dir: Path;
              screenshots: bool = True; show: bool = False
    # headed: can a real windowed Chrome be produced (HEADLESS_HEADED, --headless).
    # show: is the window visible from launch (HEADLESS_SHOW, --show) - independent
    # of headed; see headless/session.py's _effective_headed (quiet by default).
def load_config(overrides: dict | None = None) -> Config      # raises ConfigError

# headless/gates.py
class Mode(str, Enum): PREVIEW; APPLY; CHECK
class GateRefused(RuntimeError): ...
def add_mode_arguments(parser: argparse.ArgumentParser) -> None
    # --apply/--check + --profile-dir/--headless|--show/--preview-dir/--no-screenshot
    # overrides. --headless and --show are their own mutually exclusive group.
def resolve_mode(args, *, isatty: bool, headed: bool) -> Mode     # raises GateRefused
    # `headed` here is Config.headed (can a real window be produced), unchanged by
    # quiet-by-default; whether it is actually SHOWN is Config.show, resolved later
    # in headless/session.py's _effective_headed, not part of this gate.

# headless/secrets.py
class SecretMissing(KeyError): ...
class VaultBackend(Protocol): get_secret; put_secret; delete_secret; self_test
class KeychainBackend(VaultBackend)
class GcpBackend(VaultBackend)        # google-cloud-secret-manager imported lazily
def open_vault(config: Config) -> VaultBackend

# headless/profile.py
class RegistryMissing(KeyError): ...
class ProfileError(ValueError):
    # the `profile` vault item is not valid JSON, or not a JSON object; the
    # message is position-only (item name + JSONDecodeError's own report),
    # never document content, so Errand.run's pre-session handler prints it
    # by name (N10) rather than treating it as an unnamed bare ValueError
class ProfileRegistry:
    @classmethod def load(cls, vault: VaultBackend, item: str = "profile") -> "ProfileRegistry"
        # raises ProfileError
    def get(self, dotted: str) -> str

# headless/fields.py
@dataclass(frozen=True) class Source: kind: str; ref: str
@dataclass(frozen=True) class FieldPlan: name; selector; source; kind = "fill"
def parse_source(text: str) -> Source     # "registry:..", "secret:..", "literal:.."
def redact(value: str) -> str             # "****" + last two characters
def resolve_source(source: Source, vault, registry) -> str
    # the one place in the package a raw secret/registry value is produced;
    # session.fill() and errand.py's record-building both call through here

# headless/preview.py
@dataclass class PreviewRecord: ...       # values masked in __post_init__
def write_artifacts(record, screenshot_png: bytes | None, preview_dir: Path) -> tuple[Path | None, Path]
    # screenshot_png=None (config.screenshots=False / --no-screenshot, or
    # Session.screenshot() returned None because the page's CSP blocked the
    # mask - N1) writes only the JSON; the returned png path is then None

# headless/session.py
class FillFailed(RuntimeError):
    # raised by Session.fill when the underlying locator action (fill/
    # select_option/check) raises; the message holds only FieldPlan metadata
    # and redact(value) - never the original exception object or its message,
    # which can embed the raw value in a Playwright call log
    def __init__(self, plan: FieldPlan, value: str, cause: BaseException) -> None
class Session:
    def __init__(self, config: Config, mode: Mode, *, confirm=input, allow_headless_apply_for_tests=False)
        # raises GateRefused immediately if mode is APPLY and not config.headed
        # and not allow_headless_apply_for_tests (the one sanctioned bypass,
        # a constructor argument only - never reachable from the CLI)
    def __enter__/__exit__
        # launched (persistent context): closes the context.
        # CDP-attached: ALWAYS opens a brand-new page (never reuses an
        # existing tab, which may be the Director's own); __exit__ closes
        # only that page and disconnects (browser.close() on a CDP-attached
        # Browser disconnects the client, it does not kill the Director's
        # real Chrome process - verified, see PATTERNS.md).
    def goto(self, url: str) -> None      # one retry on transient error
    def probe(self, selectors: list[str]) -> list[tuple[str, bool]]
    def fill(self, plan: FieldPlan, vault, registry) -> None
        # apply mode only (else GateRefused); raises FillFailed on a locator
        # action failure, never lets the underlying exception propagate
    def screenshot(self) -> bytes | None
        # injects a form-control text mask (input/textarea/[contenteditable]/
        # select) before screenshotting, removes it after (BLOCK 2a; a visual
        # mask, not redaction - see the module docstring and CLAUDE.md).
        # If the page's CSP blocks the mask's <style> injection, returns None
        # instead of ever capturing unmasked, and prints one note (N1).
    def handoff(self, handoff_text: str) -> bool
        # restores/surfaces a quietly-hidden apply window first (best-effort;
        # see PATTERNS.md "Quiet by default"), then prints "Your turn", waits,
        # returns window-still-open
    # `page` is exposed for reads (goto/probe/screenshot use it); never for typing

# headless/errand.py
class Errand:                              # base class scripts subclass
    name: str; HANDOFF: str; dependencies: list[str]
    def add_arguments(self, parser: argparse.ArgumentParser) -> None
        # hook for errand-specific arguments (e.g. probe.py's positional url); no-op by default
    def plan(self, registry) -> list[FieldPlan]
    def url(self, args: argparse.Namespace) -> str
        # the address this run opens; default reads args.url, override for
        # anything else
    def run(self, argv=None) -> int        # the whole state machine, returns exit code
```

Invariant enforced by the API: `Session.fill` is the only sanctioned way to type; `Session.page`
is exposed for reads. A structural test (`tests/test_no_direct_typing.py`) scans `scripts/*.py`
and refuses any direct `.fill(`, `.type(`, `.press(`, `.click(`, `.select_option(`, `.check(`
call on a page or locator, so an errand cannot type outside the registry/vault/literal path
without failing the commit gate. A `FieldPlan` value can only come from the registry, the vault,
or a literal declared in the script.

## 3. Preview JSON schema

```json
{
  "errand": "probe",
  "mode": "preview",
  "url": "https://example.com/",
  "title": "Example Domain",
  "timestamp_utc": "20260824T131500Z",
  "handoff": "n/a (read-only errand)",
  "fields": [
    {"name": "PAN", "selector": "#pan", "source_kind": "registry", "value_masked": "****7K"}
  ],
  "checks": [
    {"selector": "#pan", "found": true}
  ]
}
```

`value_masked` is the only value field; there is no raw-value field in the schema. The JSON is
always written; the `.png` screenshot is written alongside it unless `--no-screenshot` /
`HEADLESS_SCREENSHOTS=0` is set, in which case only the JSON exists for that run - the final
stdout line always points at the JSON either way.
