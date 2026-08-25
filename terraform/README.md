# Infrastructure-as-Code (terraform/)

Headless has one planned cloud dependency: a Google Cloud project holding the Director's
profile data and secrets in **Secret Manager**, read at fill-time by `headless/secrets.py`
when `HEADLESS_SECRETS_BACKEND=gcp`.

## Status

Not created, and this plan is now superseded (Director decision 2026-08-25, spec
004-age-vault): the default secrets backend is a local, open-source, passphrase-encrypted
`age` vault (`headless/secrets.py`'s `AgeBackend`, written only by `scripts/vault.py`), not
GCP Secret Manager. Building the GCP plan out would have meant a second Google account
(Google forbids a principal approving its own Privileged Access Manager grant, so a
single-Director tool would need someone else to hold the approver role), a standing cloud
dependency, and a monthly cost for a tool with exactly one user - the local vault gets the
same per-run approval property (the Director must type the vault's passphrase, at the
keyboard, every time a secret is needed) from a property of the encryption tool itself, with
none of that. `GcpBackend`'s code stays in the tree, inert and still selectable via
`HEADLESS_SECRETS_BACKEND=gcp`, in case a future decision reverses this; no cloud resource is
created under this plan. The macOS Keychain (`KeychainBackend`) also remains selectable but is
no longer the default either, for the same reason `age` had to become the default: it is
macOS-only, and the vault is meant to be set up "on their own machine, macOS or Windows" per
the Director's own brief.

## Cost gate (Lesson 5)

| Resource | Projected cost |
| :--- | :--- |
| Secret Manager, up to 6 active secret versions | $0 (free tier) |
| Each additional active version | $0.06 / month |
| Access operations, first 10,000 / month | $0 |

Target: $0 / month. A `terraform plan` is reviewed, and its cost confirmed, before any
`apply`. No resource is created from the console or an ad-hoc CLI call.

## When it is built

Files expected here: `main.tf` (provider, project services `secretmanager.googleapis.com`),
`secrets.tf` (secret shells only; values are added by the Director, never by Terraform),
`variables.tf`, `README.md` (this file, updated with the project id).
