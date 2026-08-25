#!/usr/bin/env python3
"""scan_secrets: credential and personal-identifier scanner for Headless.

Background: the repository went public on 2026-08-24. This scanner is the one
tool used at every point a change can reach public history: a local git
pre-commit hook (--staged), a Claude Code write-time PreToolUse hook
(--stdin-hook), an ad hoc file check (--paths), and a CI backstop that walks
the whole reachable commit history (--history). It uses only the Python
standard library so every one of those layers works on a fresh clone with no
extra install step, and it must run under the macOS system `python3`
(assume 3.9), not just the project's own .venv - `from __future__ import
annotations` is used, but no `match` statement, no `X | Y` runtime unions,
and no reliance on `str.removeprefix`/`str.removesuffix`.

Site: none. This maintenance script never opens a browser and never touches a
site; see scripts/README.md for the same "not an errand" carve-out check_env.py
already documents.
Reads: staged diff content, named files, git history blobs, or a Claude Code
hook payload on stdin; the repository's own .scanignore.
Writes: nothing, in any mode, ever.
Secrets / profile fields: none. It never reads the vault or the profile
registry; it only looks for values that should never have reached the
repository in the first place.
Handoff: none; this is not a browser errand.

Modes (exactly one required): --staged, --paths PATH [PATH ...], --history,
--stdin-hook. See specs/002-commit-safety-gate/contracts/cli-and-hooks.md for
the full contract (output line format, exit codes, the .scanignore grammar,
and the stdin-hook JSON shapes).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import namedtuple
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

# Same convention as scripts/check_env.py: no packaging step for a personal
# tool, so the repository root is derived from this file's own location, not
# from the current working directory or a git subprocess call.
REPO_ROOT = Path(__file__).resolve().parent.parent

INLINE_MARKER = "# scan:allow"

# Directories skipped in every scan mode, always, regardless of .scanignore.
# The repository's own always-skipped paths plus, per the review that
# hardened this scanner post-implementation, the same vendored/dependency
# directory names ~/.claude/hooks/no-em-dash.py already skips - deliberately
# NOT the same list, though: "dist", "build", "out", "target", and "coverage"
# are left OUT on purpose (generated code can embed a real secret, so it must
# still be scanned), and there is no path escape marker like no-em-dash.py's
# "allow-emdash" (an escape hatch on a secret scanner is a bypass, not a
# convenience). See research.md D1's corrected skip-parity note.
ALWAYS_SKIP_DIRS = {
    "previews", ".venv", "venv", ".git", "__pycache__", ".pytest_cache",
    "node_modules", "vendor", "site-packages", ".gradle", ".idea", ".vscode",
    ".mypy_cache",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".woff", ".woff2",
    ".ttf", ".so", ".dylib", ".dll", ".exe", ".jar", ".class", ".mp4", ".webm",
    ".db", ".sqlite", ".sqlite3", ".pyc", ".keystore", ".webp", ".bmp",
}

# Exact lockfile names skipped regardless of extension, mirroring
# ~/.claude/hooks/no-em-dash.py's SKIP_NAMES.
SKIP_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Cargo.lock", "gradle.lockfile", "composer.lock", "Gemfile.lock",
}

# Filename suffixes (checked against the whole lowercased basename, not
# Path.suffix, so a compound suffix like ".min.js" matches correctly)
# skipped regardless of directory, mirroring no-em-dash.py's SKIP_SUFFIXES.
SKIP_SUFFIXES = (".map", ".min.js", ".min.css", ".lock", ".svg")

# tool name -> the tool_input field holding the text about to be written,
# mirroring ~/.claude/hooks/no-em-dash.py's own TEXT_FIELD convention exactly
# (research.md D1/D6).
TEXT_FIELD = {
    "Write": "content",
    "Edit": "new_string",
    "MultiEdit": "new_string",
    "NotebookEdit": "new_source",
}

Finding = namedtuple("Finding", ["pattern", "severity", "file", "line", "masked_snippet"])


class UsageError(Exception):
    """A mode other than --stdin-hook could not run at all (bad git state,
    unreadable path). Caught once in main() and turned into exit 2."""


class Pattern:
    __slots__ = ("name", "category", "severity", "finder")

    def __init__(self, name, category, severity, finder):
        self.name = name
        self.category = category
        self.severity = severity
        self.finder = finder

    def find(self, line):
        return self.finder(line)


def redact(value: str) -> str:
    """"****" + the value's own last two characters; bare "****" under 3
    characters. Matches headless/preview.py's redact() convention exactly
    (PATTERNS.md), so the Director sees one masking shape everywhere."""
    if len(value) < 3:
        return "****"
    return "****" + value[-2:]


def _simple_finder(rx: "re.Pattern"):
    def finder(line: str) -> List[str]:
        return [m.group(0) for m in rx.finditer(line)]
    return finder


# --- Credential patterns ---------------------------------------------------

GITHUB_TOKEN_RE = re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")
GITHUB_PAT_RE = re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")
AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b")
GOOGLE_KEY_RE = re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")
GOOGLE_OAUTH_RE = re.compile(r"\bya29\.[A-Za-z0-9._-]{20,}\b")
SLACK_TOKEN_RE = re.compile(r"\bxox[abp]-[0-9A-Za-z-]{10,}\b")
SLACK_WEBHOOK_RE = re.compile(
    r"\bhooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]{16,}"
)
# Replaces the old AI_KEY_RE ("sk-..." only): covers OpenAI/Anthropic-shaped
# keys including the "sk-ant-" and "sk-live-"/"sk-test-" variants.
API_KEY_SK_RE = re.compile(r"\bsk[-_](?:live[-_]|test[-_]|ant-)?[A-Za-z0-9_-]{20,}\b")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
PEM_RE = re.compile(
    r"-----BEGIN (?:(?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY|PGP PRIVATE KEY BLOCK)-----"
)

# generic_secret_assignment: keyword, optional whitespace, "=" / ":" / "=>",
# optional whitespace, a quoted value that contains no embedded quote or
# comma before its closing quote. The "no embedded quote or comma" rule is
# what keeps this off prose that happens to sit between two adjacent quoted
# strings (headless/fields.py:37's `..."registry:", "secret:", or "literal:"`
# used to false-positive here, capturing ", or 'literal:" as the "value" -
# impossible now, since a comma can never appear inside the captured group).
GENERIC_SECRET_RE = re.compile(
    r'(?i)\b(?:password|passwd|secret|api[_-]?key|token)\b\s*(?:=>|[:=])\s*'
    r'(?P<q>["\'])(?P<val>[^"\',]{8,}?)(?P=q)'
)

_PLACEHOLDER_KEYWORDS = (
    "changeme", "your-", "your_", "example", "placeholder", "redacted", "dummy", "fake", "xxxx",
)


def _looks_like_placeholder(value: str) -> bool:
    """A generic_secret_assignment capture that is a placeholder, not a real
    secret: all mask characters, an unexpanded template token, an angle-
    bracket instruction, or a value naming itself as a stand-in."""
    if value and all(c in "*xX" for c in value):
        return True
    if value.startswith("${") and value.endswith("}"):
        return True
    if value.startswith("{{") and value.endswith("}}"):
        return True
    if value.startswith("%(") and value.endswith(")s"):
        return True
    if value.startswith("<") and value.endswith(">"):
        return True
    lowered = value.lower()
    return any(keyword in lowered for keyword in _PLACEHOLDER_KEYWORDS)


def find_generic_secret(line: str) -> List[str]:
    out = []
    for m in GENERIC_SECRET_RE.finditer(line):
        val = m.group("val")
        if _looks_like_placeholder(val):
            continue
        out.append(val)
    return out


# --- Personal-identifier patterns ------------------------------------------

PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
# Boundaries kept as word boundaries (not digit-specific): the real guard
# against a SHA-256 hash or an int64 constant false-firing is the Verhoeff
# check-digit validation below, not the boundary, since a hex string's
# letters are word characters too and would not stop a \b-only guard anyway.
AADHAAR_RE = re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}\b")
# Alphanumeric boundaries (not \b) on phone/card shapes: a 10-digit window
# inside a longer digit run (an int64 constant) or a hex digest (digits glued
# to letters) used to match; (?<![0-9A-Za-z])/(?![0-9A-Za-z]) only allow a
# match whose neighbours are neither digits nor letters, which a real phone or
# card number in text never violates. +91 accepts an optional separator before the
# number, and the number itself may be split 5+5 with an optional separator
# between the two 5-digit groups, still first-digit-6-9 gated.
PHONE_IN_RE = re.compile(r"(?<![0-9A-Za-z])(?:\+91[-.\s]?|0)?[6-9]\d{4}[-.\s]?\d{5}(?![0-9A-Za-z])")
PHONE_US_RE = re.compile(r"(?<![0-9A-Za-z])\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?![0-9A-Za-z])")
# Bounded quantifiers (was unbounded "+"): an unbounded local-part/domain
# quantifier is what made this pattern quadratic - 11+ seconds on a single
# 100 KB line, well past the Claude Code hook's 10 s timeout. "@" not being
# in the line at all is checked before the regex even runs (find_email).
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24}\b")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
CARD_CANDIDATE_RE = re.compile(r"(?<![0-9A-Za-z])(?:\d[ -]?){13,19}(?![0-9A-Za-z])")
# Issuer prefixes (IIN): Visa, Mastercard (51-55, 2221-2720 approximated as 22-27),
# Amex, Discover, JCB, Diners. A Luhn-valid digit run without one of these is
# treated as an identifier (a port list, an id sequence), not a card.
_CARD_IIN_RE = re.compile(r"^(?:4|5[1-5]|2[2-7]|3[47]|6011|65|35|3[068])")

# FR-006: an email address at a documented example domain, a documented
# no-reply address, or GitHub's own generated no-reply address is never a
# finding. Domain check is by suffix (a@mail.example.com is allowed, not
# only a@example.com); the no-reply local part is matched as a whole word
# ("no-reply"/"no_reply"/"no.reply"/"noreply"), not merely a startswith.
ALLOWED_EMAIL_DOMAINS = {"example.com", "example.org", "users.noreply.github.com"}
NOREPLY_LOCAL_RE = re.compile(r"^no[-_.]?reply$", re.IGNORECASE)


def _email_domain_allowed(domain: str) -> bool:
    lowered = domain.lower()
    for allowed in ALLOWED_EMAIL_DOMAINS:
        if lowered == allowed or lowered.endswith("." + allowed):
            return True
    return False


def find_email(line: str) -> List[str]:
    if "@" not in line:
        return []
    out = []
    for m in EMAIL_RE.finditer(line):
        value = m.group(0)
        local, _, domain = value.partition("@")
        if _email_domain_allowed(domain):
            continue
        if NOREPLY_LOCAL_RE.match(local):
            continue
        out.append(value)
    return out


def luhn_check(digits: str) -> bool:
    total = 0
    reversed_digits = digits[::-1]
    for i in range(len(reversed_digits)):
        d = int(reversed_digits[i])
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def find_payment_card(line: str) -> List[str]:
    out = []
    for m in CARD_CANDIDATE_RE.finditer(line):
        raw = m.group(0)
        digits = re.sub(r"[ -]", "", raw)
        if 13 <= len(digits) <= 19 and _CARD_IIN_RE.match(digits) and luhn_check(digits):
            out.append(raw)
    return out


# Verhoeff check-digit algorithm (stdlib, like luhn_check above): catches the
# same class of false positive Luhn catches for card numbers - a SHA-256
# hash's digit runs or an int64 constant are astronomically unlikely to also
# pass a checksum by coincidence, so a plain 12-digit shape is no longer
# enough on its own to call something an Aadhaar number.
_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def verhoeff_check(digits: str) -> bool:
    c = 0
    for i, item in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(item)]]
    return c == 0


def find_aadhaar(line: str) -> List[str]:
    out = []
    for m in AADHAAR_RE.finditer(line):
        raw = m.group(0)
        digits = re.sub(r"[- ]", "", raw)
        if len(digits) == 12 and verhoeff_check(digits):
            out.append(raw)
    return out


def iban_check(value: str) -> bool:
    """ISO 7064 MOD 97-10, the standard IBAN checksum: move the first four
    characters to the end, convert letters to numbers (A=10 ... Z=35), and
    the whole thing must be congruent to 1 mod 97."""
    v = re.sub(r"\s", "", value).upper()
    if not (15 <= len(v) <= 34):
        return False
    rearranged = v[4:] + v[:4]
    numeric = []
    for ch in rearranged:
        if ch.isdigit():
            numeric.append(ch)
        elif "A" <= ch <= "Z":
            numeric.append(str(ord(ch) - ord("A") + 10))
        else:
            return False
    try:
        return int("".join(numeric)) % 97 == 1
    except ValueError:
        return False


def find_iban(line: str) -> List[str]:
    out = []
    for m in IBAN_RE.finditer(line):
        raw = m.group(0)
        if iban_check(raw):
            out.append(raw)
    return out


PATTERNS = [
    Pattern("github_token", "credential", "high", _simple_finder(GITHUB_TOKEN_RE)),
    Pattern("github_pat", "credential", "high", _simple_finder(GITHUB_PAT_RE)),
    Pattern("aws_access_key", "credential", "high", _simple_finder(AWS_KEY_RE)),
    Pattern("google_api_key", "credential", "high", _simple_finder(GOOGLE_KEY_RE)),
    Pattern("google_oauth_token", "credential", "high", _simple_finder(GOOGLE_OAUTH_RE)),
    Pattern("slack_token", "credential", "high", _simple_finder(SLACK_TOKEN_RE)),
    Pattern("slack_webhook", "credential", "high", _simple_finder(SLACK_WEBHOOK_RE)),
    Pattern("api_key_sk", "credential", "high", _simple_finder(API_KEY_SK_RE)),
    Pattern("jwt", "credential", "medium", _simple_finder(JWT_RE)),
    Pattern("pem_private_key", "credential", "high", _simple_finder(PEM_RE)),
    Pattern("generic_secret_assignment", "credential", "medium", find_generic_secret),
    Pattern("pan_in", "identifier", "high", _simple_finder(PAN_RE)),
    Pattern("aadhaar_in", "identifier", "high", find_aadhaar),
    Pattern("phone_in", "identifier", "medium", _simple_finder(PHONE_IN_RE)),
    Pattern("phone_us", "identifier", "medium", _simple_finder(PHONE_US_RE)),
    Pattern("email", "identifier", "low", find_email),
    Pattern("payment_card", "identifier", "high", find_payment_card),
    Pattern("iban", "identifier", "high", find_iban),
]


class Allowlist:
    def __init__(self, exact: Set[str], regexes: List["re.Pattern"]):
        self.exact = exact
        self.regexes = regexes

    def is_allowed(self, value: str) -> bool:
        if value in self.exact:
            return True
        for rx in self.regexes:
            if rx.search(value):
                return True
        return False


def load_allowlist(path: Path) -> Allowlist:
    exact = set()
    regexes = []
    if not path.exists():
        return Allowlist(exact, regexes)
    text = path.read_text(encoding="utf-8", errors="replace")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("re:"):
            pattern_text = line[3:]
            try:
                regexes.append(re.compile(pattern_text))
            except re.error:
                continue
        else:
            exact.add(line)
    return Allowlist(exact, regexes)


def is_skipped_path(path_str: str) -> bool:
    norm = path_str.replace("\\", "/")
    parts = set(norm.split("/"))
    if parts & ALWAYS_SKIP_DIRS:
        return True
    base = Path(norm).name
    if base in SKIP_NAMES:
        return True
    lowered_base = base.lower()
    if lowered_base.endswith(SKIP_SUFFIXES):
        return True
    suffix = Path(norm).suffix.lower()
    return suffix in BINARY_EXTENSIONS


def looks_binary(data: bytes) -> bool:
    # Only the first 8 KB is sniffed for a NUL byte: enough to identify the
    # overwhelming majority of binary formats without reading a large file in
    # full just to decide whether to skip it.
    return b"\x00" in data[:8192]


# --- Masking (BLOCK 1) ------------------------------------------------------

SNIPPET_LIMIT = 200


def _mask_all(line: str, raw_values: Iterable[str]) -> str:
    """Replace every matched value on the line with its own redaction in one
    pass, longest value first: replacing a short match before a longer one
    that contains it as a substring would corrupt the longer match's own
    redaction. Every Finding on this line shares the result, so a GitHub
    token and a PAN on the same line no longer leak each other."""
    masked = line
    for raw in sorted(set(raw_values), key=len, reverse=True):
        masked = masked.replace(raw, redact(raw))
    return masked.strip()


def _cap_snippet(masked: str, limit: int = SNIPPET_LIMIT) -> str:
    """Cap the printed snippet to `limit` characters, centered on the first
    mask marker. This bounds output size only. Text on the same line that no
    pattern matched (for example a 40-character AWS secret access key next to
    a detected GitHub token) is printed as-is when it falls inside the window;
    only far-away context is dropped. Matched values are always masked before
    this function runs. Residual recorded in PATTERNS.md."""
    if len(masked) <= limit:
        return masked
    anchor = masked.find("****")
    if anchor == -1:
        anchor = 0
    half = limit // 2
    start = max(0, anchor - half)
    end = start + limit
    if end > len(masked):
        end = len(masked)
        start = max(0, end - limit)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(masked) else ""
    return prefix + masked[start:end] + suffix


def scan_line(line: str, source_label: str, lineno: int, allowlist: Allowlist) -> List[Finding]:
    if INLINE_MARKER in line:
        return []
    matches = []  # List[Tuple[Pattern, str]]
    for pattern in PATTERNS:
        for raw_value in pattern.find(line):
            if allowlist.is_allowed(raw_value):
                continue
            matches.append((pattern, raw_value))
    if not matches:
        return []
    masked_snippet = _cap_snippet(_mask_all(line, (raw for _, raw in matches)))
    return [
        Finding(pattern.name, pattern.severity, source_label, lineno, masked_snippet)
        for pattern, _ in matches
    ]


def scan_text(text: str, source_label: str, allowlist: Allowlist) -> List[Finding]:
    findings = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        findings.extend(scan_line(line, source_label, lineno, allowlist))
    return findings


def format_finding(f: Finding) -> str:
    return "{0}:{1}: {2} ({3}) {4}".format(f.file, f.line, f.pattern, f.severity, f.masked_snippet)


# --- --staged (BLOCK 2 / FIX-FIRST 3) --------------------------------------

DIFF_GIT_PREFIX = "diff --git "
HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _unquote_git_path(raw: str) -> str:
    """Undo git's C-style quoting of a path (octal-escaped bytes wrapped in a
    pair of double quotes). The diff is run with `-c core.quotepath=false` so
    git should not quote a non-ASCII path in the first place, but this is a
    defensive second layer in case some git version or config quotes anyway
    (NIT 11 / BLOCK 2)."""
    if len(raw) < 2 or raw[0] != '"' or raw[-1] != '"':
        return raw
    inner = raw[1:-1]
    out = bytearray()
    simple = {
        "\\": "\\", '"': '"', "a": "\a", "b": "\b", "f": "\f",
        "n": "\n", "r": "\r", "t": "\t", "v": "\v",
    }
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\" and i + 1 < len(inner):
            nxt = inner[i + 1]
            if nxt in "01234567":
                j = i + 1
                digits = ""
                while j < len(inner) and len(digits) < 3 and inner[j] in "01234567":
                    digits += inner[j]
                    j += 1
                out.append(int(digits, 8) & 0xFF)
                i = j
                continue
            if nxt in simple:
                out.extend(simple[nxt].encode("ascii"))
                i += 2
                continue
            out.extend(ch.encode("utf-8", "replace"))
            i += 1
        else:
            out.extend(ch.encode("utf-8", "replace"))
            i += 1
    try:
        return out.decode("utf-8", "replace")
    except Exception:
        return raw


def _parse_diff_target(target: str) -> Optional[str]:
    """The text after "--- "/"+++ " (already newline-stripped) -> a path, or
    None for /dev/null. Strips a trailing tab (git appends one when a path
    needs disambiguation) before unquoting."""
    t = target
    if t.endswith("\t"):
        t = t[:-1]
    if t == "/dev/null":
        return None
    t = _unquote_git_path(t)
    if t.startswith("a/") or t.startswith("b/"):
        t = t[2:]
    return t


def _parse_unified_diff(text: str) -> List[Tuple[str, int, str]]:
    """A unified-diff state machine (BLOCK 2). Only a line beginning with the
    literal, unprefixed "diff --git " starts a new file section - a content
    line that happens to contain that text is always prefixed with "+"/"-"/" "
    inside a hunk and can never be confused with it. "--- "/"+++ " are only
    ever headers in the HEADER state right after "diff --git " (and "+++ "
    only immediately after a "--- " line); once a "@@" hunk header has put
    the state machine into HUNK, every line beginning with a single "+" is
    content, full stop, regardless of what the rest of the line says - this
    is what closes the "a content line reading '++ b/previews/notes.md'
    becomes '+++ b/previews/notes.md' and is mistaken for a real file header"
    bypass: that line is only ever evaluated as HUNK content, never replayed
    through the header checks."""
    OUTSIDE, HEADER, HUNK = "outside", "header", "hunk"
    state = OUTSIDE
    current_file = None
    new_lineno = None
    after_minus = False
    added: List[Tuple[str, int, str]] = []

    for line in text.split("\n"):
        if line.startswith(DIFF_GIT_PREFIX):
            state = HEADER
            current_file = None
            new_lineno = None
            after_minus = False
            continue

        if state == HEADER:
            if line.startswith("--- "):
                after_minus = True
                continue
            if line.startswith("+++ ") and after_minus:
                current_file = _parse_diff_target(line[4:])
                after_minus = False
                continue
            m = HUNK_HEADER_RE.match(line)
            if m:
                new_lineno = int(m.group(1))
                state = HUNK
                continue
            # "index ...", mode/similarity/rename/copy lines, a binary-file
            # notice: none of these are headers this state machine tracks.
            after_minus = False
            continue

        if state == HUNK:
            m = HUNK_HEADER_RE.match(line)
            if m:
                # A later hunk in the same file (multi-hunk file).
                new_lineno = int(m.group(1))
                continue
            if line.startswith("\\ "):
                # "\ No newline at end of file": diff machinery, not content.
                continue
            if line.startswith("+"):
                if current_file is not None and new_lineno is not None:
                    added.append((current_file, new_lineno, line[1:]))
                    new_lineno += 1
                continue
            if line.startswith("-"):
                continue
            if line.startswith(" "):
                if new_lineno is not None:
                    new_lineno += 1
                continue
            # Any other shape (blank line, stray output): ignored.
            continue

    return added


def get_staged_added_lines(repo_root: Path) -> List[Tuple[str, int, str]]:
    try:
        result = subprocess.run(
            [
                "git", "-c", "core.quotepath=false", "--no-pager",
                "diff", "--cached", "--unified=0", "--no-color",
            ],
            cwd=str(repo_root),
            capture_output=True,
        )
    except OSError as exc:
        raise UsageError("git is not available ({0})".format(exc))
    # Decode manually with errors="replace", never text=True (FIX-FIRST 3):
    # staged content is not guaranteed to be valid UTF-8, and text=True raises
    # UnicodeDecodeError on exactly the content this scanner exists to look
    # at, leaving the rest of the diff unscanned.
    stdout_text = result.stdout.decode("utf-8", "replace")
    if result.returncode not in (0,):
        stderr_text = result.stderr.decode("utf-8", "replace")
        raise UsageError(
            "git diff --cached failed (exit {0}): {1}".format(result.returncode, stderr_text.strip())
        )
    return _parse_unified_diff(stdout_text)


def scan_staged(repo_root: Path, allowlist: Allowlist) -> List[Finding]:
    findings = []
    for path, lineno, text in get_staged_added_lines(repo_root):
        if is_skipped_path(path):
            continue
        findings.extend(scan_line(text, path, lineno, allowlist))
    return findings


# --- --paths --------------------------------------------------------------

def scan_paths(paths: Iterable[str], allowlist: Allowlist) -> List[Finding]:
    findings = []
    for p in paths:
        if is_skipped_path(p):
            continue
        path_obj = Path(p)
        try:
            data = path_obj.read_bytes()
        except OSError as exc:
            raise UsageError("cannot read {0} ({1})".format(p, exc))
        if looks_binary(data):
            continue
        text = data.decode("utf-8", "replace")
        findings.extend(scan_text(text, source_label=str(p), allowlist=allowlist))
    return findings


# --- --history --------------------------------------------------------------

def iter_history_blobs(repo_root: Path):
    """Yield (short_blob_sha, path, content_bytes) for every blob reachable
    from HEAD, each scanned exactly once regardless of how many commits
    reference it. Two subprocess calls total, independent of history size."""
    try:
        rev_list = subprocess.run(
            ["git", "rev-list", "--objects", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise UsageError("git is not available ({0})".format(exc))
    if rev_list.returncode != 0:
        raise UsageError(
            "git rev-list failed (exit {0}): {1}".format(rev_list.returncode, rev_list.stderr.strip())
        )

    sha_to_path = {}
    for line in rev_list.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(" ", 1)
        sha = parts[0]
        path = parts[1] if len(parts) > 1 else None
        if path:
            sha_to_path.setdefault(sha, path)

    if not sha_to_path:
        return

    batch_input = "\n".join(sha_to_path.keys()) + "\n"
    try:
        proc = subprocess.Popen(
            ["git", "cat-file", "--batch"],
            cwd=str(repo_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise UsageError("git is not available ({0})".format(exc))
    stdout_data, stderr_data = proc.communicate(input=batch_input.encode("utf-8"))
    if proc.returncode != 0:
        raise UsageError(
            "git cat-file --batch failed (exit {0}): {1}".format(
                proc.returncode, stderr_data.decode("utf-8", "replace").strip()
            )
        )

    pos = 0
    n = len(stdout_data)
    while pos < n:
        nl = stdout_data.find(b"\n", pos)
        if nl == -1:
            break
        header = stdout_data[pos:nl].decode("utf-8", "replace")
        pos = nl + 1
        header_parts = header.split(" ")
        if header_parts[-1] == "missing":
            continue
        if len(header_parts) < 3:
            continue
        obj_sha, obj_type, obj_size_str = header_parts[0], header_parts[1], header_parts[2]
        try:
            size = int(obj_size_str)
        except ValueError:
            continue
        content = stdout_data[pos:pos + size]
        pos += size + 1  # +1 for the trailing newline git cat-file --batch appends
        if obj_type == "blob":
            path = sha_to_path.get(obj_sha, obj_sha)
            yield obj_sha, path, content


def scan_history(repo_root: Path, allowlist: Allowlist) -> List[Finding]:
    findings = []
    for blob_sha, path, content in iter_history_blobs(repo_root):
        if is_skipped_path(path):
            continue
        if looks_binary(content):
            continue
        text = content.decode("utf-8", "replace")
        # <blob-sha>:<path> - a blob hash, not a commit hash (D10/--history
        # dedupes by blob content, independent of which commit introduced
        # it); contracts/cli-and-hooks.md documents how to recover the owning
        # commit(s) from this label with `git log --find-object`.
        label = "{0}:{1}".format(blob_sha[:8], path)
        findings.extend(scan_text(text, source_label=label, allowlist=allowlist))
    return findings


# --- --stdin-hook -----------------------------------------------------------

def run_stdin_hook() -> int:
    """Never raises, never exits non-zero: a malformed or unrecognized
    payload is fail-open (allow, no output), mirroring
    ~/.claude/hooks/no-em-dash.py exactly (research.md D1, corrected)."""
    try:
        raw = sys.stdin.buffer.read()
    except Exception:
        return 0
    try:
        parsed = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return 0
    try:
        if not isinstance(parsed, dict):
            return 0
        tool_name = parsed.get("tool_name")
        field = TEXT_FIELD.get(tool_name)
        if not field:
            return 0
        tool_input = parsed.get("tool_input") or {}
        text = tool_input.get(field)
        if not isinstance(text, str) or not text:
            return 0
        file_path = tool_input.get("file_path") or ""
        if file_path and is_skipped_path(str(file_path)):
            return 0

        try:
            allowlist = load_allowlist(REPO_ROOT / ".scanignore")
        except Exception:
            allowlist = Allowlist(set(), [])

        findings = scan_text(text, source_label="<stdin-hook>", allowlist=allowlist)
        if not findings:
            return 0

        reason = (
            "credential/PII scan found {0} issue(s):\n".format(len(findings))
            + "\n".join(format_finding(f) for f in findings)
            + "\nIf a match is a known-safe test fixture, add it to .scanignore "
              "or mark the line with '# scan:allow'."
        )
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
        print(json.dumps(output))
        return 0
    except Exception:
        return 0


# --- CLI ---------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Credential and personal-identifier scanner for Headless (standard library only)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--staged", action="store_true", help="scan added lines of git diff --cached")
    group.add_argument("--paths", nargs="+", metavar="PATH", help="scan the complete content of the named files")
    group.add_argument("--history", action="store_true", help="scan every blob reachable from HEAD")
    group.add_argument(
        "--stdin-hook", action="store_true", dest="stdin_hook",
        help="scan a Claude Code PreToolUse payload read from stdin",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.stdin_hook:
        return run_stdin_hook()

    try:
        allowlist = load_allowlist(REPO_ROOT / ".scanignore")
        if args.staged:
            findings = scan_staged(REPO_ROOT, allowlist)
        elif args.paths:
            findings = scan_paths(args.paths, allowlist)
        else:
            findings = scan_history(REPO_ROOT, allowlist)
    except UsageError as exc:
        print("scan_secrets: usage error: {0}".format(exc), file=sys.stderr)
        return 2

    for f in findings:
        print(format_finding(f))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
