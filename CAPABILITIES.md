# Headless - Capabilities at a glance

One screen: what this repository can do right now, what is half-built, and what is not built.
Current as of **v0.0.11** (main `357f60c`, 2026-09-14). Update this file in the same commit as
any errand you add, change, or retire (`Function_Mapping.md`, maintenance rule 5).

## Errands you can run today

| Errand | Command (from the repo root, `.venv` active) | What it does | Where it stops |
| :-- | :-- | :-- | :-- |
| Product scan (v0.0.11) | `python scripts/product_scan.py --query "no dig landscape edging" [--reference-url URL] [--reference "Title \| price \| length_ft [\| rating [\| reviews]]"] [--sites amazon,homedepot] [--min-height-in N]` | Reads Amazon search results (Home Depot opt-in), parses height, length, material, and stakes from each title, computes price per foot, ranks by a review-count-weighted rating minus a price penalty, and writes `reports/product/product-scan-<slug>-<date>.md` and `.json`. A reference listing shows where it would rank. | Read-only. No apply mode exists or may be added. |
| Activity scan (v0.0.9) | `python scripts/activity_scan.py --near "<address or lat,lon>" [--day saturday --start 17:00 --end 22:00] [--radius-miles 20]` | Reads the Google Maps list view for 35 activity queries around a point, folds duplicates, ranks by rating, distance, and relevance, checks each top venue's hours against the window, and writes `reports/activity/activity-scan-<date>.md` and `.json`. | Read-only. No apply mode exists or may be added. |
| Probe (v0.0.1) | `python scripts/probe.py <URL> [--apply] [--show]` | Opens any page on the Headless Chrome profile and writes a preview (screenshot plus JSON). With `--apply` it opens a real window so you can log in once; the login persists to later runs. | `--apply` hands off immediately. Nothing is typed. |

Every errand supports `--check` (a read-only probe that proves the site's selectors still
resolve), `--show` (a visible window), and `--profile-dir` / `--preview-dir` overrides.

## Errand line in progress

**Insurance quote comparison** (v0.0.5 to v0.0.7, specs 005 to 007). `python scripts/policy_extract.py`
turns each insured asset's own policy PDF into a confirmed coverage reference with a local model
(Ollama, never a cloud one). `python scripts/quote_compare.py` walks each mapped insurer's quote
funnel and compares the captured quote with that reference in an HTML report. Status: only the
Progressive landing page is mapped, and Progressive ends its funnel for an existing customer, so
no competitor quote has been captured yet. The GEICO funnel mapper (spec 008, branch `v0.0.8`)
is unmerged and paused since 2026-09-03.

## What every errand inherits

- **Preview by default.** A script with no flags writes on no site. `--apply` fills up to a
  declared handoff and never past it. No script submits, pays, e-verifies, or types an OTP.
- **Quiet by default.** Preview and check run in headless Chrome on the Headless profile
  (`~/.headless/chrome-profile`). A window appears only for `--apply` handoffs or `--show`.
- **Login persistence.** Session cookies survive between runs on the launched-profile path.
- **A local vault for profile data.** `python scripts/vault.py {init,set,get,unset,list,path,verify}`
  keeps one age-encrypted JSON (`~/.headless/profile.age`). The passphrase is the approval
  gate. Passwords and payment cards are never stored anywhere.
- **Commit safety gate.** `scripts/scan_secrets.py` runs in the pre-commit hook, in a Claude
  Code hook, and in CI on every push; `scripts/verify_structure.py` keeps the architecture map
  honest; `python scripts/check_env.py` self-tests the machine (5 rows).
- **Google Maps connector (v0.0.10).** `.mcp.json` registers Google's hosted Maps MCP server for
  future location work; `python scripts/maps_check.py` is its live check. Waiting on the
  Director's terraform apply and key export.

## Sites: what renders headless and what refuses

| Renders fully | Refuses headless Chrome |
| :-- | :-- |
| Amazon search and product pages; Google Maps list and place pages | Walmart (`Robot or human?`), Lowe's (`Access Denied`), Google Shopping (captcha), Menards (blank), Yelp (device check), TripAdvisor (blank), Progressive's quote start (403), Home Depot after its first visit in a session (`Error Page`) |

A walled site can still be read once by hand in a headed window (`--show`), and the product
scan accepts a hand-typed `--reference` for exactly that case. Details and dates:
`MEMORY.md`, "Known site traps".

## Not built yet (Director's roadmap of 2026-08-25)

Flights (reuse `cheapsawari`), appointments, and the India ITR portal walk (sessionStorage
login and Aadhaar OTP: the hardest). Target as a product-scan source once it exposes stable
card selectors.
