# Quickstart: Commit Safety Gate

**Feature**: 002-commit-safety-gate | **Date**: 2026-08-24

Runnable validation scenarios that prove the feature end-to-end. Contracts are in
[contracts/cli-and-hooks.md](contracts/cli-and-hooks.md); entities in
[data-model.md](data-model.md).

## Prerequisites

- From the repo (or worktree) root, the existing `.venv` (no new dependency: the scanner uses
  only what running the project already needs):
  ```bash
  source .venv/bin/activate
  ```
- One-time local activation of the pre-commit hook (Setup, D5):
  ```bash
  git config core.hooksPath .githooks
  python scripts/check_env.py   # git_hooks row should now read PASS
  ```

## Scenario 1: a staged secret is refused before it commits (US1, SC-002)

```bash
echo 'API_KEY = "sk-ant-not-a-real-key-1234567890"' >> scratch_secret_test.py  # scan:allow
git add scratch_secret_test.py
git commit -m "test: should be refused"
```

Expected: `git commit` exits non-zero, no commit is created (`git log -1` still shows the
previous commit), and the pre-commit hook's output names the file, line, pattern
(`api_key_sk`), and severity, with the key shown only as `sk-****90`. Clean up:
`git reset HEAD scratch_secret_test.py && rm scratch_secret_test.py`.

For the "no false refusal" half of SC-002/SC-004, stage a clean change and confirm the same
commit command succeeds immediately with no scanner output.

## Scenario 2: the write-time hook denies a Write (US2, SC-003)

```bash
echo '{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"x.py","content":"pan = \"ABCDE1234G\""}}' | python scripts/scan_secrets.py --stdin-hook  # scan:allow
```

Expected: one JSON object on stdout with
`"hookSpecificOutput": {"permissionDecision": "deny", ...}`, the reason line masked
(`****4G`), exit `0` (the deny lives in the JSON body, not the exit code - contracts.md
section 4). Ask Claude Code itself to write a file containing the same shape of value and
confirm the write is refused in the assistant's own turn, with the reason surfaced back to it.

For the allow path:

```bash
echo '{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"x.py","content":"print(\"hello\")"}}' \
  | python scripts/scan_secrets.py --stdin-hook
```

Expected: no stdout, exit `0`.

## Scenario 3: allowlist a known-safe fixture (US4, SC-001, SC-008)

```bash
python scripts/scan_secrets.py --paths .scanignore  # sanity: .scanignore itself is clean
grep -n 'ABCDE1234F' .scanignore                     # the seeded PAN fixture is already listed
python scripts/scan_secrets.py --paths tests/test_scan_secrets.py
```

Expected: the seeded fixtures (`ABCDE1234F`, `director@example.com`, and the rest of the D3
list) produce no findings when they appear in `tests/test_scan_secrets.py`, because they are
allowlisted repository-wide. To see the allowlist actually matter, temporarily comment out the
`ABCDE1234F` line in `.scanignore` and re-run the same command: the PAN fixture is now flagged.
Restore the line afterward.

For an inline exception on one line only:

```bash
printf 'x = "%s"  # scan:allow\n' 'ABCDE9999Z' > scratch_inline_test.py
python scripts/scan_secrets.py --paths scratch_inline_test.py   # exit 0: the marker suppresses it
printf 'y = "%s"\n' 'ABCDE9999Z' >> scratch_inline_test.py  # scan:allow (this line only; scratch_inline_test.py itself carries no marker)
python scripts/scan_secrets.py --paths scratch_inline_test.py   # exit 1: the unmarked line is still caught
rm scratch_inline_test.py
```

## Scenario 3a: recovering the owning commit of a `--history` finding (FIX-FIRST 7)

`--history` labels a finding `<blob-sha>:<path>:<line>` - a **blob** hash (the short,
8-character form), not a commit hash, since it dedupes by blob content once regardless of how
many commits reference it. To find which commit(s) introduced that blob:

```bash
git log --oneline --find-object=<blob-sha>
```

This lists every commit that introduced or touched an object with that content, even one no
longer reachable from a later commit's tree (the removed-then-re-added case US3 exists for).

## Scenario 4: the CI backstop scans full history at no perceptible cost (US3, SC-006, SC-007)

```bash
time python scripts/scan_secrets.py --history
```

Expected: exit `0` (this repository's real history is known clean - D10), completing in under 2
seconds. Push a branch to see both CI jobs (`scan`, `gitleaks`) run and pass alongside GitHub's
own secret scanning and push protection on the same pull request; a synthetic secret added to a
commit that is later removed in a follow-up commit on the same branch still fails the `scan` job,
because `--history` walks every commit reachable from the pushed ref, not only its tip.

## Scenario 5: commit gate (SC-002, SC-004, SC-005 tie-in)

```bash
python -m pytest -q
python scripts/verify_structure.py
```

Expected: `tests/test_scan_secrets.py` passes alongside the rest of the existing suite, and the
structure check prints SUCCESS with every new file (`scripts/scan_secrets.py`,
`.githooks/pre-commit`, `.github/workflows/secret-scan.yml`, `.scanignore`,
`.claude/settings.json`, `tests/test_scan_secrets.py`) accounted for in `Project_Structure.md`.
