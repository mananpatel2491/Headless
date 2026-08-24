# Infrastructure-as-Code (terraform/)

Headless has one planned cloud dependency: a Google Cloud project holding the Director's
profile data and secrets in **Secret Manager**, read at fill-time by `headless/secrets.py`
when `HEADLESS_SECRETS_BACKEND=gcp`.

## Status

Not created. Until the `gcloud` SDK is installed on the Director's machine and
`gcloud auth application-default login` has been run interactively, the default backend is
the macOS Keychain, which needs no cloud resources.

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
