# Infrastructure-as-Code (terraform/)

## Superseded plan: GCP Secret Manager

Headless once planned one cloud dependency here: a Google Cloud project holding the Director's
profile data and secrets in Secret Manager, read at fill-time by `headless/secrets.py` when
`HEADLESS_SECRETS_BACKEND=gcp`. That plan was superseded on 2026-08-25 (spec 004-age-vault): the
default secrets backend became a local, open-source, passphrase-encrypted `age` vault instead.
Building the GCP plan out would have meant a second Google account (Google forbids a principal
approving its own Privileged Access Manager grant, so a single-Director tool would need someone
else to hold the approver role), a standing cloud dependency, and a monthly cost for a tool with
exactly one user - the local vault gets the same per-run approval property (the Director must
type the vault's passphrase, at the keyboard, every time a secret is needed) from a property of
the encryption tool itself, with none of that. `GcpBackend`'s code stays in the tree, inert and
still selectable via `HEADLESS_SECRETS_BACKEND=gcp`, in case a future decision reverses this; no
resource under this superseded plan was ever created.

## Google Maps connector (spec 010-google-maps-connector, v0.0.10)

The Director's brief: "Build the Google Maps connector in the register (in the repo), as I see
in future the repo being used to interact with the web to identify locations." This directory now
declares the ONLY cloud resources that connector needs.

### What the files declare

| File | Declares |
| :--- | :--- |
| `main.tf` | Provider (`hashicorp/google ~> 6.0`), two service enablements (`apikeys.googleapis.com`, `mapstools.googleapis.com`), and one API key restricted to `mapstools.googleapis.com` only |
| `variables.tf` | `var.project_id` - the Google Cloud project the Director chooses; a billing account must already be linked (Maps Platform requires one even inside the free monthly cap) |
| `outputs.tf` | `maps_api_key` (the key string, marked sensitive) and `mcp_endpoint` (the fixed hosted endpoint URL) |
| `.terraform.lock.hcl` | The committed provider dependency lock (`hashicorp/google` 6.50.0, satisfying `~> 6.0`) |

The key is restricted, via `restrictions.api_targets.service`, to exactly one API - a leaked or
misused key can only ever bill Maps Grounding Lite calls, never any other Google API this project
might have enabled.

### Cost gate (Lesson 5)

Maps Grounding Lite is an Essentials SKU (SKU 8CD0-1602-5324), read from Google's pricing page on
2026-09-09:

| Tier | Price |
| :--- | :--- |
| First 10,000 events / month | $0 (free) |
| 10,001 - 100,000 events / month | $7.00 per 1,000 |
| 100,001 - 500,000 events / month | $5.95 per 1,000 |
| Beyond 500,000 events / month | Lower still |

Projected cost for this repository: **$0/month** at personal volume (well under 10,000 calls per
month - occasional interactive lookups plus one billable call per `scripts/maps_check.py` live
check run). A runaway would cost $7 per extra 1,000 calls; the key's own API restriction means it
cannot bill anything outside this one service regardless. A `terraform plan` is reviewed, and its
cost confirmed, before any `apply`. No resource is created from the console or an ad-hoc CLI
call.

### Apply steps (Director only)

```bash
cd terraform
terraform init
terraform plan -var project_id="<your-project-id>"
# review: exactly three resources to create, nothing else
terraform apply -var project_id="<your-project-id>"
terraform output -raw maps_api_key
```

### Key to Keychain

Copy the printed key string directly into the macOS Keychain - never into a file in this
repository, a preview, a log, or a chat message:

```bash
security add-generic-password -a headless -s maps-api-key -w
```

Then export it from the login shell (for example, in `~/.zshrc`):

```bash
export HEADLESS_MAPS_API_KEY="$(security find-generic-password -a headless -s maps-api-key -w 2>/dev/null)"
```

`.mcp.json` expands `${HEADLESS_MAPS_API_KEY}` from that environment variable at Claude Code's
own load time; `scripts/maps_check.py` proves the key works. See `specs/010-google-maps-connector/quickstart.md`
for the full walkthrough, including rotation and revocation.

### What is gitignored, and why the lock file is committed

`.gitignore`'s own terraform block excludes `terraform/.terraform/` (the downloaded provider
plugin cache), every `*.tfstate`/`*.tfstate.*` (state carries the key string itself), and every
`*.tfvars`/`*.tfvars.json` (a `project_id` value is the Director's own cloud project choice).
`terraform/.terraform.lock.hcl` is committed on purpose: it pins the exact provider version
(`hashicorp/google` 6.50.0) every future `terraform init` resolves to, the same way
`requirements.txt` pins this repository's own Python dependencies - without it, a later `init`
could silently pick up a newer, unverified provider release.

### Terms acknowledgment

Maps Grounding Lite's own terms state it "must not be used with any models that use the data
input into the model for any model training or improvement." Claude Code's own data-handling
policy governs whether this condition is met; that is the Director's own account setting, not
something this repository's code controls or can verify. The Director acknowledges this term
before relying on the connector for anything beyond the live check's own fixed public query.
