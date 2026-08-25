"""Unit tests for scripts/scan_secrets.py (specs/002-commit-safety-gate).

Every synthetic sample below is fake, never a real secret. A sample not
already covered by the repository's own seeded `.scanignore` (research.md D3)
is assembled at test-run time from two or more separate string literals, so
the complete matching value never appears as one contiguous literal in this
file's own committed source - otherwise this very test file would fail its
own `--staged`/`--history` scan on commit (tasks.md T003/T026).
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import string
import subprocess
import sys
import time
from pathlib import Path

import pytest

import scripts.scan_secrets as scan_secrets
from scripts.scan_secrets import Allowlist, load_allowlist, scan_line

REPO_ROOT = Path(__file__).resolve().parent.parent

EMPTY_ALLOWLIST = Allowlist(set(), [])


def _git(args, cwd, **kwargs):
    return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True, **kwargs)


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    (repo / "README.md").write_text("hello world\n", encoding="utf-8")
    _git(["add", "README.md"], repo)
    _git(["commit", "-q", "-m", "initial"], repo)
    return repo


# ---------------------------------------------------------------------------
# Runtime-assembled synthetic samples for patterns not already covered by
# the repository's seeded .scanignore.
# ---------------------------------------------------------------------------

_GITHUB_PREFIX = "ghp_"
_GITHUB_BODY = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
GITHUB_TOKEN_SAMPLE = _GITHUB_PREFIX + _GITHUB_BODY

_AWS_PREFIX = "AKIA"
_AWS_BODY = "IOSFODNN7EXAMPLE"
AWS_KEY_SAMPLE = _AWS_PREFIX + _AWS_BODY

_GOOGLE_PREFIX = "AIza"
_GOOGLE_BODY = "SyABCDEFGHIJKLMNOPQRSTUVWXYZabcdef0"
GOOGLE_KEY_SAMPLE = _GOOGLE_PREFIX + _GOOGLE_BODY

_SLACK_PREFIX = "xoxb-"
# letters interspersed so no single 10+-digit run exists (would now
# false-positive phone_us's digit-boundary bracketing, FIX-FIRST 5)
_SLACK_BODY = "1a2b3c4d5e6f7g8h9i"
SLACK_TOKEN_SAMPLE = _SLACK_PREFIX + _SLACK_BODY

_AI_PREFIX = "sk-"
# split so no single literal piece contains a bare run of 10+ digits (that
# alone would false-positive phone_us, the same shape T025 found in this
# repository's own pre-existing history - see .scanignore's second block).
_AI_BODY = "ant-api03-FAKE" + "abc" + "1234567"
AI_PROVIDER_KEY_SAMPLE = _AI_PREFIX + _AI_BODY

_JWT_PREFIX = "eyJ"
_JWT_BODY = "hbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dGVzdHNpZ25hdHVyZQ"
JWT_SAMPLE = _JWT_PREFIX + _JWT_BODY

_PEM_PREFIX = "-----BEGIN "
_PEM_BODY = "RSA PRIVATE KEY-----"
PEM_SAMPLE = _PEM_PREFIX + _PEM_BODY

_PHONE_IN_PREFIX = "+91-"
# a bare 10-digit run matches on its own (that is the whole point of the
# pattern), so it must be split into two literal pieces even though it has
# no other prefix character to lean on within its own line.
_PHONE_IN_BODY = "98765" + "43210"
PHONE_IN_SAMPLE = _PHONE_IN_PREFIX + _PHONE_IN_BODY

_PHONE_US_PREFIX = "(415) "
_PHONE_US_BODY = "555-0199"  # only 7 digits on its own; needs the prefix's 3 more to complete the 3-3-4 shape
PHONE_US_SAMPLE = _PHONE_US_PREFIX + _PHONE_US_BODY

_CARD_PART_A = "4111 1111 "
_CARD_PART_B = "1111 1111"
LUHN_VALID_CARD_SAMPLE = _CARD_PART_A + _CARD_PART_B  # a well-known Luhn-valid test PAN

_CARD_INVALID_A = "1234 5678 "
_CARD_INVALID_B = "9012 3455"
LUHN_INVALID_CARD_SAMPLE = _CARD_INVALID_A + _CARD_INVALID_B  # 16 digits, deliberately not Luhn-valid

# A real, mod-97-checksum-valid IBAN (post-implementation review NIT-13:
# find_iban now validates the checksum, so a shape-only sample no longer
# fires). Split so no single literal piece is itself IBAN-shaped.
_IBAN_PREFIX = "GB93NWBK"
_IBAN_BODY = "1234" + "5698" + "765432"
IBAN_SAMPLE = _IBAN_PREFIX + _IBAN_BODY  # assembled value is mod-97 valid

# An IBAN-shaped string that is NOT checksum-valid (NIT-13): must never fire
# now that iban_check() is required. Safe to write as one literal - the
# whole point of this sample is that the scanner does not flag it.
IBAN_INVALID_SAMPLE = "US2024ABCDEFGHIJKL"

_SECRET_KEYWORD_PART = "secret"
_SECRET_VALUE_PART = "fresh" + "generic" + "value999"
GENERIC_SECRET_LINE = _SECRET_KEYWORD_PART + ' = "' + _SECRET_VALUE_PART + '"'

# A Verhoeff check-digit-valid 12-digit Aadhaar-shaped sample (FIX-FIRST 5:
# find_aadhaar now validates the Verhoeff checksum, so the old shape-only
# "9998-8877-7666" sample - dropped from .scanignore on 2026-08-25 (inert), no
# longer Verhoeff-valid - no longer fires). Split so no single literal piece
# is itself a bare 10+-digit run.
_AADHAAR_VALID_A = "2345-"
_AADHAAR_VALID_B = "6789-"
_AADHAAR_VALID_C = "0124"
AADHAAR_VALID_SAMPLE = _AADHAAR_VALID_A + _AADHAAR_VALID_B + _AADHAAR_VALID_C

# Aadhaar-shaped sequences that must stay clean once the Verhoeff check is
# in place (FIX-FIRST 5): plausible-looking but not checksum-valid, the same
# false-positive shape as the SHA-256 hash and int64 constants .scanignore
# used to carry entries for.
AADHAAR_CLEAN_SEQUENCE_1 = "8000 8010 8020 8030"  # Luhn-valid by coincidence; no issuer prefix, so not a card
AADHAAR_CLEAN_SEQUENCE_2 = "1990 1991 1992"
# The exact int64-max constant .scanignore used to allowlist twice (as two
# 10-digit substrings near its end) before phone_us gained a digit
# boundary; now the whole 19-digit constant must be clean on its own.
INT64_MAX = "9223372036854775807"

# FIX-FIRST 8: new credential shapes. Each split so the complete matching
# value never appears as one contiguous literal (same convention as above).
_GITHUB_PAT_PREFIX = "github_pat_"
_GITHUB_PAT_BODY = "11AAAAAAA0" + "ABCDEFGHIJKLMNOP"
GITHUB_PAT_SAMPLE = _GITHUB_PAT_PREFIX + _GITHUB_PAT_BODY

_GOOGLE_OAUTH_PREFIX = "ya29."
_GOOGLE_OAUTH_BODY_A = "a0AfH6SMC"
_GOOGLE_OAUTH_BODY_B = "a1B2c3D4e5"
_GOOGLE_OAUTH_BODY_C = "F6g7H8i9J0"
GOOGLE_OAUTH_SAMPLE = _GOOGLE_OAUTH_PREFIX + _GOOGLE_OAUTH_BODY_A + _GOOGLE_OAUTH_BODY_B + _GOOGLE_OAUTH_BODY_C

_SLACK_WEBHOOK_PREFIX = "hooks.slack.com/services/"
_SLACK_WEBHOOK_T = "T00000000"
_SLACK_WEBHOOK_B = "B00000000"
_SLACK_WEBHOOK_TOKEN = "XXXXXXXXXXXXXXXX"
SLACK_WEBHOOK_SAMPLE = (
    _SLACK_WEBHOOK_PREFIX + _SLACK_WEBHOOK_T + "/" + _SLACK_WEBHOOK_B + "/" + _SLACK_WEBHOOK_TOKEN
)

# aws_access_key widened (FIX-FIRST 8) to ASIA/ABIA/ACCA in addition to AKIA.
_AWS_ASIA_PREFIX = "ASIA"
_AWS_ASIA_BODY = "ABCDEFGHIJKLMNOP"  # 16 chars, [0-9A-Z]{16}
AWS_ASIA_SAMPLE = _AWS_ASIA_PREFIX + _AWS_ASIA_BODY

# pem_private_key extended (FIX-FIRST 8) to also match a PGP private-key
# block, not only the RSA/EC/OPENSSH/DSA/ENCRYPTED "PRIVATE KEY" forms.
PEM_PGP_SAMPLE = "-----BEGIN " + "PGP PRIVATE KEY BLOCK-----"

# phone_in accepts a space between the 5+5 digit groups, not only contiguous
# (FIX-FIRST 8).
_PHONE_IN_SPACED_PREFIX = "+91 "
_PHONE_IN_SPACED_A = "98765"
_PHONE_IN_SPACED_B = "43210"
PHONE_IN_SPACED_SAMPLE = _PHONE_IN_SPACED_PREFIX + _PHONE_IN_SPACED_A + " " + _PHONE_IN_SPACED_B

# PAN-shaped constants reused across the staged/history/paths/stdin-hook
# tests below, so this file needs only two concatenated (non-allowlisted)
# values instead of scattering many distinct literals through test bodies.
SAFE_PAN = "ABCDE1234F"  # the D3-seeded, already-allowlisted PAN - safe to write literally
_FRESH_PAN_A, _FRESH_PAN_B = "ABCDE", "1234G"
FRESH_PAN = _FRESH_PAN_A + _FRESH_PAN_B  # NOT allowlisted: used where a write must be denied
_UNRELATED_PAN_A, _UNRELATED_PAN_B = "QRSTU", "5678V"
UNRELATED_PAN = _UNRELATED_PAN_A + _UNRELATED_PAN_B  # distinct from SAFE_PAN, for "unrelated occurrence still flagged"


# ---------------------------------------------------------------------------
# Pattern detection: each fires on its sample against an empty allowlist,
# regardless of what the repository's own .scanignore currently contains.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pattern_name,line",
    [
        ("github_token", "token = " + GITHUB_TOKEN_SAMPLE),
        ("github_pat", "pat = " + GITHUB_PAT_SAMPLE),
        ("aws_access_key", "key = " + AWS_KEY_SAMPLE),
        ("aws_access_key", "key = " + AWS_ASIA_SAMPLE),  # widened prefix set (FIX-FIRST 8)
        ("google_api_key", "key = " + GOOGLE_KEY_SAMPLE),
        ("google_oauth_token", "tok = " + GOOGLE_OAUTH_SAMPLE),
        ("slack_token", "token = " + SLACK_TOKEN_SAMPLE),
        ("slack_webhook", "hook = " + SLACK_WEBHOOK_SAMPLE),
        ("api_key_sk", "key = " + AI_PROVIDER_KEY_SAMPLE),  # renamed from ai_provider_key (FIX-FIRST 8)
        ("jwt", "auth = " + JWT_SAMPLE),
        ("pem_private_key", PEM_SAMPLE),
        ("pem_private_key", PEM_PGP_SAMPLE),  # extended to PGP blocks (FIX-FIRST 8)
        ("generic_secret_assignment", GENERIC_SECRET_LINE),
        ("pan_in", "pan = " + SAFE_PAN),
        ("aadhaar_in", "aadhaar = " + AADHAAR_VALID_SAMPLE),  # Verhoeff-valid (FIX-FIRST 5)
        ("phone_in", "phone = " + PHONE_IN_SAMPLE),
        ("phone_in", "phone = " + PHONE_IN_SPACED_SAMPLE),  # 5+5 space-separated (FIX-FIRST 8)
        ("phone_us", "phone = " + PHONE_US_SAMPLE),
        ("email", "contact = director@realmail.test"),  # scan:allow (not example.com; the point of this sample is that it is NOT on the allowed-domain list)
        ("payment_card", "card = " + LUHN_VALID_CARD_SAMPLE),
        ("iban", "iban = " + IBAN_SAMPLE),  # mod-97 valid (NIT-13)
    ],
)
def test_pattern_fires_on_sample(pattern_name, line):
    findings = scan_line(line, "test.txt", 1, EMPTY_ALLOWLIST)
    fired = {f.pattern for f in findings}
    assert pattern_name in fired, "{0} did not fire on: {1}".format(pattern_name, line)


def test_pattern_count():
    # Regression guard (FIX-FIRST 8): 15 patterns -> 18 (github_pat,
    # google_oauth_token, slack_webhook added; ai_provider_key renamed
    # api_key_sk, not counted twice). See data-model.md's Pattern table.
    assert len(scan_secrets.PATTERNS) == 18


@pytest.mark.parametrize(
    "line",
    [
        "x = " + AADHAAR_CLEAN_SEQUENCE_1,
        "x = " + AADHAAR_CLEAN_SEQUENCE_2,
        "x = " + INT64_MAX,
    ],
)
def test_aadhaar_does_not_fire_on_non_checksum_sequences(line):
    # FIX-FIRST 5: a plausible-looking 12-digit grouping, or a window inside
    # a longer digit constant, must not fire aadhaar_in once the Verhoeff
    # check-digit validation is in place - these are exactly the shapes the
    # .scanignore false positives used to come from.
    findings = scan_line(line, "test.txt", 1, EMPTY_ALLOWLIST)
    assert not any(f.pattern == "aadhaar_in" for f in findings), line


def test_aadhaar_does_not_fire_on_a_sha256_hex_digest():
    # A hex digest mixes letters into what would otherwise be a bare digit
    # run; the real protection here is the Verhoeff checksum, not the (still
    # word-boundary-only, unchanged) boundary around aadhaar_in.
    digest = hashlib.sha256(b"spec-kit-template-fixture").hexdigest()
    findings = scan_line("hash = " + digest, "test.txt", 1, EMPTY_ALLOWLIST)
    assert not any(f.pattern == "aadhaar_in" for f in findings), digest


def test_iban_invalid_checksum_never_fires():
    # NIT-13: iban now requires a mod-97-valid checksum; an IBAN-shaped
    # string that fails it must never be reported.
    findings = scan_line("iban = " + IBAN_INVALID_SAMPLE, "test.txt", 1, EMPTY_ALLOWLIST)
    assert not any(f.pattern == "iban" for f in findings)


def test_email_allowed_domains_never_flagged():
    for line in [
        "a = director@example.com",
        "b = someone@example.org",
        "c = noreply@anything.test",
        "d = octocat@users.noreply.github.com",
    ]:
        findings = scan_line(line, "test.txt", 1, EMPTY_ALLOWLIST)
        assert not any(f.pattern == "email" for f in findings), line


def test_email_allowed_domain_matches_by_suffix():
    # NIT-13: a@mail.example.com is clean (subdomain of an allowed domain),
    # not only a@example.com itself.
    findings = scan_line("a = someone@mail.example.com", "test.txt", 1, EMPTY_ALLOWLIST)
    assert not any(f.pattern == "email" for f in findings)
    # A domain that merely ends with the allowed string as a substring, not
    # a real subdomain, is still flagged.
    findings = scan_line("a = someone@notexample.com", "test.txt", 1, EMPTY_ALLOWLIST)  # scan:allow (asserts this DOES fire)
    assert any(f.pattern == "email" for f in findings)


def test_email_noreply_local_part_variants_never_flagged():
    # NIT-13: local part matches no[-_.]?reply, not only a bare "noreply"
    # prefix - and only as the WHOLE local part, not a substring of it.
    for local in ("no-reply", "no_reply", "no.reply", "noreply", "NoReply"):
        line = "a = {0}@realmail.test".format(local)
        findings = scan_line(line, "test.txt", 1, EMPTY_ALLOWLIST)
        assert not any(f.pattern == "email" for f in findings), line
    # "noreplyxyz" is not the no-reply local part, just a local part that
    # starts with it - still flagged.
    findings = scan_line("a = noreplyxyz@realmail.test", "test.txt", 1, EMPTY_ALLOWLIST)  # scan:allow (asserts this DOES fire)
    assert any(f.pattern == "email" for f in findings)


def test_luhn_rejects_non_card_number():
    line = "card = " + LUHN_INVALID_CARD_SAMPLE
    findings = scan_line(line, "test.txt", 1, EMPTY_ALLOWLIST)
    assert not any(f.pattern == "payment_card" for f in findings)


# ---------------------------------------------------------------------------
# generic_secret_assignment: placeholder exemptions and the fields.py:37
# false positive (FIX-FIRST 6)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "line",
    [
        'token = "xxxxxxxx"',
        'token = "********"',
        'api_key = "${OPENAI_API_KEY}"',
        'api_key = "{{ vault_secret }}"',
        "secret: '%(env_value)s'",
        "password = '<your-password-here>'",
        'secret = "changeme123"',
        'token = "your-token-here"',
        'api_key = "sk-example-not-real"',
        'password = "placeholder999"',
        'secret = "REDACTED-value-1"',
        'token = "dummy-token-value"',
        'secret = "fake-secret-value"',
    ],
)
def test_generic_secret_placeholder_values_never_fire(line):
    findings = scan_line(line, "test.txt", 1, EMPTY_ALLOWLIST)
    assert not any(f.pattern == "generic_secret_assignment" for f in findings), line


def test_generic_secret_prose_between_two_quoted_strings_never_fires():
    # The exact shape headless/fields.py:37 used to false-positive on: a
    # keyword ("secret") sitting inside one quoted string, immediately
    # followed by a comma and another quoted string - .scanignore used to
    # carry ", or 'literal:" as the captured (non-secret) "value". Fixed by
    # requiring no embedded quote or comma before the closing quote, so this
    # shape can never match at all now.
    line = (
        'raise SourceError(f"source {text!r} must start with '
        "'registry:', 'secret:', or 'literal:'\")"
    )
    findings = scan_line(line, "test.txt", 1, EMPTY_ALLOWLIST)
    assert not any(f.pattern == "generic_secret_assignment" for f in findings)


def test_generic_secret_random_value_still_fires():
    # The tightened pattern must still catch a real-looking secret: a
    # keyword, an operator, a quoted value with no comma/quote inside, that
    # is not shaped like any of the placeholder exemptions.
    random_value = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(12))
    line = 'password = "' + random_value + '"'
    findings = scan_line(line, "test.txt", 1, EMPTY_ALLOWLIST)
    assert any(f.pattern == "generic_secret_assignment" for f in findings), line


def test_generic_secret_hash_rocket_operator_fires():
    # "optionally =>" (FIX-FIRST 6): a Ruby/JS-style hash-rocket assignment.
    random_value = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(12))
    line = 'token => "' + random_value + '"'
    findings = scan_line(line, "test.txt", 1, EMPTY_ALLOWLIST)
    assert any(f.pattern == "generic_secret_assignment" for f in findings), line


def test_masking_never_leaks_raw_value():
    samples = [GITHUB_TOKEN_SAMPLE, AWS_KEY_SAMPLE, "ABCDE1234F", LUHN_VALID_CARD_SAMPLE]
    for raw in samples:
        line = "value = " + raw
        findings = scan_line(line, "test.txt", 1, EMPTY_ALLOWLIST)
        assert findings, "expected at least one finding for {0}".format(raw)
        for f in findings:
            assert raw not in f.masked_snippet, "raw value leaked in masked_snippet"
            dumped = json.dumps(f._asdict())
            assert raw not in dumped, "raw value leaked in a serialized finding"


def test_output_line_format():
    findings = scan_line("pan = ABCDE1234F", "some/file.py", 7, EMPTY_ALLOWLIST)
    pan_findings = [f for f in findings if f.pattern == "pan_in"]
    assert len(pan_findings) == 1
    line = scan_secrets.format_finding(pan_findings[0])
    assert line.startswith("some/file.py:7: pan_in (high) ")
    assert "ABCDE1234F" not in line
    assert "****4F" in line


# ---------------------------------------------------------------------------
# BLOCK 1: multi-match lines share one fully-masked snippet
# ---------------------------------------------------------------------------

def test_two_different_pattern_matches_on_one_line_both_masked():
    # A GitHub token and a PAN on the same line: the old per-Finding masking
    # replaced only its own value, so the PAN finding's line still showed
    # the raw GitHub token (and vice versa). Both findings must now share
    # one snippet with BOTH values redacted.
    line = "token = " + GITHUB_TOKEN_SAMPLE + " pan = " + FRESH_PAN  # scan:allow (the source line's own "token = "..."" shape self-matches generic_secret_assignment)
    findings = scan_line(line, "test.txt", 1, EMPTY_ALLOWLIST)
    fired = {f.pattern for f in findings}
    assert "github_token" in fired
    assert "pan_in" in fired
    for f in findings:
        assert GITHUB_TOKEN_SAMPLE not in f.masked_snippet
        assert FRESH_PAN not in f.masked_snippet
    # every finding on the line shares the exact same snippet
    snippets = {f.masked_snippet for f in findings}
    assert len(snippets) == 1


def test_undetected_neighbor_value_excluded_by_snippet_cap():
    # A detected GitHub token beside an undetected 40-character AWS SECRET
    # ACCESS KEY (not the AKIA... access key ID this scanner has a pattern
    # for - the 40-char secret half of an AWS credential pair has no
    # pattern here). The 200-character snippet cap, not per-value masking,
    # is what keeps it out of the printed output: padding the line past the
    # cap puts the undetected value outside the window entirely.
    fake_aws_secret = "".join(random.choice(string.ascii_letters + string.digits + "/+") for _ in range(40))
    padding = "x" * 250
    line = "token = " + GITHUB_TOKEN_SAMPLE + " " + padding + " unrelated_secret = " + fake_aws_secret  # scan:allow (same self-match shape as above)
    findings = scan_line(line, "test.txt", 1, EMPTY_ALLOWLIST)
    assert any(f.pattern == "github_token" for f in findings)
    for f in findings:
        assert fake_aws_secret not in f.masked_snippet
        assert len(f.masked_snippet) <= 206  # 200 + up to 2x "..." markers


def test_masked_snippet_capped_at_200_characters():
    padding = "y" * 300
    line = "pan = " + FRESH_PAN + " " + padding
    findings = scan_line(line, "test.txt", 1, EMPTY_ALLOWLIST)
    assert findings
    for f in findings:
        assert len(f.masked_snippet) <= 206
        assert FRESH_PAN not in f.masked_snippet


# ---------------------------------------------------------------------------
# FIX-FIRST 4: EMAIL_RE performance (was quadratic: 11+ seconds on a single
# 100 KB line, well past the Claude Code hook's 10 s timeout)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(bool(os.environ.get("CI")), reason="in-process timing is flaky on shared CI runners")
def test_large_lines_scan_through_all_patterns_quickly():
    random.seed(1234)
    dotted_200k = "a." * 100000  # ~200 KB, no "@"
    b64_200k = "".join(
        random.choice(string.ascii_letters + string.digits + "-_") for _ in range(200000)
    )
    for text in (dotted_200k, b64_200k):
        start = time.monotonic()
        scan_line("x = " + text, "test.txt", 1, EMPTY_ALLOWLIST)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, "scan took {0:.2f}s on a {1}-char line".format(elapsed, len(text))


@pytest.mark.skipif(bool(os.environ.get("CI")), reason="in-process timing is flaky on shared CI runners")
def test_email_with_at_sign_on_large_line_scans_quickly():
    # Directly exercises the bounded quantifiers (not just the "@ not in
    # line" guard, which the two lines above never even reach): a large
    # local-part-charset run followed by one "@" and a domain that never
    # completes a match, the exact shape that took 11+ seconds pre-fix.
    line = "x = " + ("a" * 100000) + "@nomatchdomainhere.test"
    start = time.monotonic()
    scan_line(line, "test.txt", 1, EMPTY_ALLOWLIST)
    elapsed = time.monotonic() - start
    assert elapsed < 0.5, "scan took {0:.2f}s".format(elapsed)


# ---------------------------------------------------------------------------
# .scanignore and inline marker suppression
# ---------------------------------------------------------------------------

def test_scanignore_exact_entry_suppresses_only_that_value():
    allowlist = Allowlist({SAFE_PAN}, [])
    suppressed = scan_line("pan = " + SAFE_PAN, "f.py", 1, allowlist)
    still_flagged = scan_line("pan = " + UNRELATED_PAN, "f.py", 1, allowlist)
    assert suppressed == []
    assert any(f.pattern == "pan_in" for f in still_flagged)


def test_scanignore_regex_entry_suppresses_by_pattern():
    import re

    allowlist = Allowlist(set(), [re.compile(r"^ABCDE\d{4}F$")])
    suppressed = scan_line("pan = ABCDE1234F", "f.py", 1, allowlist)
    assert suppressed == []


def test_load_allowlist_ignores_blank_lines_and_comments(tmp_path):
    scanignore = tmp_path / ".scanignore"
    scanignore.write_text("\n# a comment\n\nABCDE1234F\nre:^ZZ.*$\n", encoding="utf-8")
    allowlist = load_allowlist(scanignore)
    assert allowlist.exact == {"ABCDE1234F"}
    assert len(allowlist.regexes) == 1
    assert allowlist.is_allowed("ZZtest")


def test_inline_marker_suppresses_only_its_own_line():
    marked = "pan = " + SAFE_PAN + "  # scan:allow"
    unmarked = "pan = " + SAFE_PAN
    assert scan_line(marked, "f.py", 1, EMPTY_ALLOWLIST) == []
    assert any(f.pattern == "pan_in" for f in scan_line(unmarked, "f.py", 2, EMPTY_ALLOWLIST))


def test_unrelated_occurrence_of_same_shape_still_flagged():
    allowlist = Allowlist({SAFE_PAN}, [])
    # a different PAN-shaped value, not the allowlisted one
    findings = scan_line("pan = " + UNRELATED_PAN, "f.py", 1, allowlist)
    assert any(f.pattern == "pan_in" for f in findings)


def test_scanignore_seed_matches_d3_list():
    # The D3 seed list must always be present, so a future edit cannot
    # silently drop or rename one of the six genuine test fixtures. Revised
    # 2026-08-25 (post-implementation review, NIT-12): "Director Name" was
    # removed - no pattern this scanner defines can ever match a plain
    # two-word name, so it was never a real exception, just an unused line.
    # The four false-positive entries T025's --history self-test added
    # (a template hash, a bash int64-max constant, a Python source string)
    # were separately removed once their root cause was fixed at the
    # pattern level (FIX-FIRST 5/6) rather than allowlisted - see
    # PATTERNS.md.
    scanignore = REPO_ROOT / ".scanignore"
    allowlist = load_allowlist(scanignore)
    expected_seed = {
        "ABCDE1234F",
        "director@example.com",
        "super-secret-value-12345",
        "hunter2-XY",
    }
    assert expected_seed <= allowlist.exact

    assert allowlist.exact == expected_seed


# ---------------------------------------------------------------------------
# --staged
# ---------------------------------------------------------------------------

def test_staged_flags_added_secret(temp_git_repo):
    target = temp_git_repo / "config.py"
    target.write_text("pan = " + SAFE_PAN + "\n", encoding="utf-8")
    _git(["add", "config.py"], temp_git_repo)
    findings = scan_secrets.scan_staged(temp_git_repo, EMPTY_ALLOWLIST)
    assert any(f.pattern == "pan_in" for f in findings)


def test_staged_ignores_removed_lines(temp_git_repo):
    target = temp_git_repo / "config.py"
    target.write_text("pan = " + SAFE_PAN + "\n", encoding="utf-8")
    _git(["add", "config.py"], temp_git_repo)
    _git(["commit", "-q", "-m", "add secret"], temp_git_repo)
    target.write_text("", encoding="utf-8")
    _git(["add", "config.py"], temp_git_repo)
    findings = scan_secrets.scan_staged(temp_git_repo, EMPTY_ALLOWLIST)
    assert findings == []


def test_staged_clean_diff_has_no_findings(temp_git_repo):
    target = temp_git_repo / "clean.py"
    target.write_text("print('hello')\n", encoding="utf-8")
    _git(["add", "clean.py"], temp_git_repo)
    findings = scan_secrets.scan_staged(temp_git_repo, EMPTY_ALLOWLIST)
    assert findings == []


# ---------------------------------------------------------------------------
# BLOCK 2: unified-diff state machine hardening
# ---------------------------------------------------------------------------

def test_staged_content_lines_never_mistaken_for_diff_headers(temp_git_repo):
    # The original bug: a CONTENT line reading "++ b/previews/notes.md"
    # becomes "+++ b/previews/notes.md" once git prefixes it with the
    # unified-diff "+" marker, and an old, state-blind parser mistook that
    # for a real file header - silently attributing (and thus ignoring,
    # since previews/ is always skipped) every following line to
    # "previews/notes.md" instead of the real file. Every line below is
    # adversarial diff-machinery-shaped CONTENT inside one new file; only
    # the real "diff --git "/"@@" header lines (never "+"-prefixed) may ever
    # start a new section or a new hunk.
    target = temp_git_repo / "attack.md"
    content_lines = [
        "++ b/previews/notes.md",
        "+++ b/x",
        "--- a/x",
        "diff --git a/y b/y",
        "@@ -1 +1 @@",
        "token = " + FRESH_PAN,
    ]
    target.write_text("\n".join(content_lines) + "\n", encoding="utf-8")
    _git(["add", "attack.md"], temp_git_repo)
    findings = scan_secrets.scan_staged(temp_git_repo, EMPTY_ALLOWLIST)
    matches = [f for f in findings if f.pattern == "pan_in"]
    assert matches, "the bypass would have swallowed this finding entirely"
    assert matches[0].file == "attack.md"
    assert matches[0].line == 6


def test_staged_path_with_spaces_and_non_ascii(temp_git_repo):
    spaced = temp_git_repo / "my notes.py"
    spaced.write_text("pan = " + FRESH_PAN + "\n", encoding="utf-8")
    nonascii_name = "naïve.py"  # naïve.py
    nonascii = temp_git_repo / nonascii_name
    nonascii.write_text("pan = " + UNRELATED_PAN + "\n", encoding="utf-8")
    _git(["add", "my notes.py", nonascii_name], temp_git_repo)
    findings = scan_secrets.scan_staged(temp_git_repo, EMPTY_ALLOWLIST)
    files = {f.file for f in findings}
    assert "my notes.py" in files
    assert nonascii_name in files


def test_staged_multi_hunk_reports_correct_line_numbers(temp_git_repo):
    target = temp_git_repo / "multi.py"
    initial_lines = ["line{0}".format(i) for i in range(1, 40)]
    target.write_text("\n".join(initial_lines) + "\n", encoding="utf-8")
    _git(["add", "multi.py"], temp_git_repo)
    _git(["commit", "-q", "-m", "seed"], temp_git_repo)

    new_lines = list(initial_lines)
    new_lines[4] = "pan = " + SAFE_PAN         # 1-indexed line 5
    new_lines[34] = "pan = " + UNRELATED_PAN   # 1-indexed line 35
    target.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    _git(["add", "multi.py"], temp_git_repo)

    findings = scan_secrets.scan_staged(temp_git_repo, EMPTY_ALLOWLIST)
    reported_lines = sorted(f.line for f in findings if f.pattern == "pan_in")
    assert reported_lines == [5, 35]


def test_unquote_git_path_handles_c_style_quoting():
    # NIT-11: the diff is run with `-c core.quotepath=false`, so git should
    # not C-quote a non-ASCII path in the first place - but _unquote_git_path
    # is a defensive second layer in case some git version/config quotes
    # anyway. "naïve.py" C-quoted the way git would if quotepath were on:
    # non-ASCII bytes as octal escapes, wrapped in a double-quoted string.
    assert scan_secrets._unquote_git_path('"na\\303\\257ve.py"') == "naïve.py"
    # an embedded escaped double quote and a tab escape
    assert scan_secrets._unquote_git_path('"my \\"quoted\\" file.py"') == 'my "quoted" file.py'
    assert scan_secrets._unquote_git_path('"tab\\tend.py"') == "tab\tend.py"
    # an unquoted path passes through unchanged
    assert scan_secrets._unquote_git_path("plain/path.py") == "plain/path.py"


def test_staged_non_utf8_content_does_not_crash(temp_git_repo):
    # FIX-FIRST 3: text=True on the git diff subprocess raised
    # UnicodeDecodeError on non-UTF-8 staged bytes, leaving the whole diff
    # unscanned (and crashing the pre-commit hook). Line 1 is latin-1 bytes
    # invalid as standalone UTF-8; line 2 carries a runtime-assembled PAN
    # that must still be found.
    target = temp_git_repo / "latin1.py"
    raw = "# caf\xe9 note\n".encode("latin-1") + ("pan = " + FRESH_PAN + "\n").encode("utf-8")
    target.write_bytes(raw)
    _git(["add", "latin1.py"], temp_git_repo)
    findings = scan_secrets.scan_staged(temp_git_repo, EMPTY_ALLOWLIST)
    assert any(f.pattern == "pan_in" and f.line == 2 for f in findings)


def test_staged_cli_exit_code(temp_git_repo):
    # scan_secrets.py resolves its own repo root from `Path(__file__).resolve()
    # .parent.parent` (the same convention as scripts/check_env.py), which is
    # correct for the real pre-commit hook (it cds to the actual worktree root
    # before invoking the script by a relative path - contracts/cli-and-hooks.md
    # section 3), but means a CLI-level test needs its own copy of the script
    # inside the temp repo so `__file__` resolves to *that* repo, not this one.
    scripts_dir = temp_git_repo / "scripts"
    scripts_dir.mkdir()
    script_copy = scripts_dir / "scan_secrets.py"
    script_copy.write_text(
        (REPO_ROOT / "scripts" / "scan_secrets.py").read_text(encoding="utf-8"), encoding="utf-8"
    )

    target = temp_git_repo / "config.py"
    target.write_text("pan = " + SAFE_PAN + "\n", encoding="utf-8")
    _git(["add", "config.py"], temp_git_repo)
    result = subprocess.run(
        [sys.executable, str(script_copy), "--staged"],
        cwd=str(temp_git_repo),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "pan_in" in result.stdout
    assert SAFE_PAN not in result.stdout


# ---------------------------------------------------------------------------
# --history
# ---------------------------------------------------------------------------

def test_history_finds_secret_removed_in_later_commit(temp_git_repo):
    target = temp_git_repo / "config.py"
    target.write_text("pan = " + SAFE_PAN + "\n", encoding="utf-8")
    _git(["add", "config.py"], temp_git_repo)
    _git(["commit", "-q", "-m", "add secret"], temp_git_repo)
    target.write_text("clean now\n", encoding="utf-8")
    _git(["add", "config.py"], temp_git_repo)
    _git(["commit", "-q", "-m", "remove secret"], temp_git_repo)

    findings = scan_secrets.scan_history(temp_git_repo, EMPTY_ALLOWLIST)
    matches = [f for f in findings if f.pattern == "pan_in"]
    assert matches, "secret still in history was not found"
    assert ":" in matches[0].file
    assert "config.py" in matches[0].file


def test_history_on_real_repo_is_clean():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "scan_secrets.py"), "--history"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout


@pytest.mark.skipif(bool(os.environ.get("CI")), reason="wall-clock timing is flaky on shared CI runners")
def test_history_completes_within_time_budget():
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "scan_secrets.py"), "--history"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - start
    assert result.returncode == 0
    assert elapsed < 2.0, "history scan took {0:.2f}s, budget is 2s".format(elapsed)


# ---------------------------------------------------------------------------
# --paths
# ---------------------------------------------------------------------------

def test_paths_mode_scans_full_file_content(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("line one\npan = " + SAFE_PAN + "\n", encoding="utf-8")
    findings = scan_secrets.scan_paths([str(f)], EMPTY_ALLOWLIST)
    assert any(x.pattern == "pan_in" and x.line == 2 for x in findings)


def test_paths_mode_skips_binary(tmp_path):
    f = tmp_path / "sample.bin"
    f.write_bytes(b"\x00\x01pan = " + SAFE_PAN.encode("ascii") + b"\x00")
    findings = scan_secrets.scan_paths([str(f)], EMPTY_ALLOWLIST)
    assert findings == []


# ---------------------------------------------------------------------------
# --stdin-hook
# ---------------------------------------------------------------------------

def _run_stdin_hook(payload: dict):
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "scan_secrets.py"), "--stdin-hook"],
        cwd=str(REPO_ROOT),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


def test_stdin_hook_denies_write_with_pan():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "x.py", "content": "pan = " + FRESH_PAN},
    }
    result = _run_stdin_hook(payload)
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert FRESH_PAN not in result.stdout
    assert scan_secrets.redact(FRESH_PAN) in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_stdin_hook_allows_clean_write():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "x.py", "content": "print('hello')"},
    }
    result = _run_stdin_hook(payload)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_stdin_hook_edit_reads_new_string():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": "x.py", "old_string": "a", "new_string": "pan = " + FRESH_PAN},
    }
    result = _run_stdin_hook(payload)
    out = json.loads(result.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_stdin_hook_multiedit_reads_new_string():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "MultiEdit",
        "tool_input": {"file_path": "x.py", "new_string": "pan = " + FRESH_PAN},
    }
    result = _run_stdin_hook(payload)
    out = json.loads(result.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_stdin_hook_notebookedit_reads_new_source():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "NotebookEdit",
        "tool_input": {"new_source": "pan = " + FRESH_PAN},
    }
    result = _run_stdin_hook(payload)
    out = json.loads(result.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_stdin_hook_malformed_json_is_fail_open():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "scan_secrets.py"), "--stdin-hook"],
        cwd=str(REPO_ROOT),
        input="not json {{{",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_stdin_hook_unrecognized_tool_is_fail_open():
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}}
    result = _run_stdin_hook(payload)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_stdin_hook_missing_text_field_is_fail_open():
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {"file_path": "x.py"}}
    result = _run_stdin_hook(payload)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_settings_json_hook_command_fails_open_when_project_dir_unset():
    # FIX-FIRST 10 regression: the registered command must fall back to "."
    # and end in "|| exit 0", so an unset $CLAUDE_PROJECT_DIR degrades to
    # allow instead of crashing python3 (exit 2, fail-closed - blocking
    # every Write/Edit/MultiEdit/NotebookEdit in the session).
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert '${CLAUDE_PROJECT_DIR:-.}' in command
    assert command.rstrip().endswith("|| exit 0")

    result = subprocess.run(
        ["sh", "-c", command],
        cwd=str(REPO_ROOT),
        env={k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"},
        input="{}",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_stdin_hook_allowlisted_value_allows():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "x.py", "content": "pan = ABCDE1234F"},
    }
    result = _run_stdin_hook(payload)
    assert result.returncode == 0
    assert result.stdout.strip() == ""

def test_digit_runs_flanked_by_letters_never_fire_phone_or_card():
    """Alphanumeric boundaries: a hex digest or an id with a 10- or 15-digit
    run glued to letters is not a phone or card number. Values assembled at
    runtime so this file never carries a matching literal."""
    hex_ten = "abc" + "5575" + "493404" + "def"
    luhn_fifteen = "9f" + "6724966" + "36365691" + "e1"
    for text in (hex_ten, luhn_fifteen, "sha256:" + hex_ten + luhn_fifteen):
        names = {f.pattern for f in scan_secrets.scan_text(text, "x", EMPTY_ALLOWLIST)}
        assert not names & {"phone_us", "phone_in", "payment_card"}, names


def test_phone_and_card_still_fire_with_punctuation_neighbours():
    us = "(415) " + "555-" + "0198"
    card = "4111 " + "1111 " + "1111 " + "1111"
    for text, name in ((f"call {us}.", "phone_us"), (f'"card": "{card}",', "payment_card")):
        names = {f.pattern for f in scan_secrets.scan_text(text, "x", EMPTY_ALLOWLIST)}
        assert name in names, (text, names)


def test_payment_card_requires_an_issuer_prefix():
    """NEW-2: a Luhn-valid digit run without a known IIN (a port list, an id
    sequence) is an identifier, not a card; real network prefixes still fire."""
    clean = ["ports " + AADHAAR_CLEAN_SEQUENCE_1, "ids 1000 2000 " + "3000 4000"]
    for text in clean:
        names = {f.pattern for f in scan_secrets.scan_text(text, "x", EMPTY_ALLOWLIST)}
        assert "payment_card" not in names, (text, names)
    cards = ["5500 0000 " + "0000 0004", "3714 496353 " + "98431", "6011 1111 " + "1111 1117", LUHN_VALID_CARD_SAMPLE]
    for card in cards:
        names = {f.pattern for f in scan_secrets.scan_text("card = " + card, "x", EMPTY_ALLOWLIST)}
        assert "payment_card" in names, (card, names)
