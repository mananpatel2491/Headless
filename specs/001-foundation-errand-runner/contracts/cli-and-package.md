# Contracts: Foundation Errand Runner

**Feature**: 001-foundation-errand-runner | **Date**: 2026-08-24

Headless exposes two interfaces: the **errand command line** every script follows, and the
**package API** scripts compose. Both are stable contracts for later features.

## 1. Errand command line

```text
python scripts/<errand>.py [URL or errand args] [--apply | --check]
                           [--profile-dir PATH] [--headless] [--preview-dir PATH]
```

| Flag | Meaning | Constraints |
| :--- | :--- | :--- |
| (none) | preview mode: no site writes, artifact written | default |
| `--apply` | fill up to `HANDOFF`, then "Your turn" | requires interactive terminal and visible browser; mutually exclusive with `--check` |
| `--check` | read-only: report each dependent selector found/missing | mutually exclusive with `--apply` |
| `--profile-dir` | override `HEADLESS_PROFILE_DIR` | |
| `--headless` | invisible browser | refused together with `--apply` |
| `--preview-dir` | override `HEADLESS_PREVIEW_DIR` | |

Forbidden flags (must never exist on any errand): `--submit`, `--pay`, `--verify`, `--otp`,
`--yes`, `--confirm`.

**Exit codes**: `0` success; `1` gate refused, missing secret or registry path, config error
(all before any browser launch where applicable); `2` browser or site failure after launch.

**Stdout**: one line per step, final line `PREVIEW <path.json>` / `CHECK <n> found, <m>
missing` / `APPLY handed off at "<HANDOFF>"`. Never a secret or registry value (SC-002).

### `scripts/check_env.py`

```text
python scripts/check_env.py
```

Prints a four-row table (`browser`, `playwright`, `profile_dir`, `vault`) with
`PASS`/`FAIL` and a hint; exit `0` only when all pass. No browser window is opened.

### `scripts/probe.py`

```text
python scripts/probe.py <URL> [--check] [--profile-dir PATH] [--headless] [--preview-dir PATH]
```

Opens the URL in the Headless profile (visible by default), prints the title, writes the
preview artifact. `HANDOFF = "n/a (read-only errand)"`; `--apply` is accepted by the shared
parser but has no fields to fill and therefore behaves like preview with the window left
open until the Director presses Enter (this is how logins are seeded).

## 2. Package API (`headless/`)

```python
# headless/config.py
class ConfigError(RuntimeError): ...
@dataclass(frozen=True)
class Config: profile_dir: Path; headed: bool; cdp_url: str | None; secrets_backend: str;
              keychain_account: str; gcp_project: str | None; preview_dir: Path
def load_config(overrides: dict | None = None) -> Config      # raises ConfigError

# headless/gates.py
class Mode(str, Enum): PREVIEW; APPLY; CHECK
class GateRefused(RuntimeError): ...
def add_mode_arguments(parser: argparse.ArgumentParser) -> None   # --apply/--check + overrides
def resolve_mode(args, *, isatty: bool, headed: bool) -> Mode     # raises GateRefused

# headless/secrets.py
class SecretMissing(KeyError): ...
class VaultBackend(Protocol): get_secret; put_secret; delete_secret; self_test
class KeychainBackend(VaultBackend)
class GcpBackend(VaultBackend)        # google-cloud-secret-manager imported lazily
def open_vault(config: Config) -> VaultBackend

# headless/profile.py
class RegistryMissing(KeyError): ...
class ProfileRegistry:
    @classmethod def load(cls, vault: VaultBackend, item: str = "profile") -> "ProfileRegistry"
    def get(self, dotted: str) -> str

# headless/fields.py
@dataclass(frozen=True) class FieldPlan: name; selector; source; kind = "fill"
def parse_source(text: str) -> Source     # "registry:..", "secret:..", "literal:.."
def redact(value: str) -> str             # "****" + last two characters

# headless/preview.py
@dataclass class PreviewRecord: ...       # values masked in __post_init__
def write_artifacts(record, screenshot_png: bytes, preview_dir: Path) -> tuple[Path, Path]

# headless/session.py
class Session:
    def __init__(self, config: Config, mode: Mode, *, confirm=input, allow_headless_apply_for_tests=False)
    def __enter__/__exit__                # launch persistent context or connect_over_cdp
    def goto(self, url: str) -> None      # one retry on transient error
    def probe(self, selectors: list[str]) -> list[tuple[str, bool]]
    def fill(self, plan: FieldPlan, vault, registry) -> None   # apply mode only
    def screenshot(self) -> bytes
    def handoff(self, handoff_text: str) -> bool   # prints "Your turn", waits, returns window-still-open

# headless/errand.py
class Errand:                              # base class scripts subclass
    name: str; HANDOFF: str; dependencies: list[str]
    def plan(self, registry) -> list[FieldPlan]
    def run(self, argv=None) -> int        # the whole state machine, returns exit code
```

Invariant enforced by the API: `Session.fill` is the only way to type, it accepts only a
`FieldPlan`, and a `FieldPlan` value can only come from the registry, the vault, or a
literal declared in the script.

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

`value_masked` is the only value field; there is no raw-value field in the schema.
