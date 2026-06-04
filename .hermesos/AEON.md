# Aeon — autonomous upstream-sync agent (DESIGN — awaiting Ash sign-off)

> Status: **PROPOSAL.** Nothing here runs yet. Aeon reverses two deliberate
> prior decisions, so it needs an explicit design nod before any workflow is
> enabled. This doc is the blueprint + the decisions only Ash can make.

## What Aeon is for
Make HermesOS updates **autonomous**: pull upstream `NousResearch/hermes-agent`
into the forks on a cadence, preserve our customizations (per
`.hermesos/customizations.yaml`), build images, and let the fleet converge —
**without a human driving each sync**. It replaces the manual
`hermes-upstream-sync` SOP for the common (clean) case and **escalates the rest
to a human** instead of guessing.

## What it REVERSES (why sign-off is required)
1. **"Auto-rebase is OFF — all syncs are manual and Ash-initiated"** (the
   `track-upstream` workflows were deleted on purpose). Aeon re-introduces
   automation — but *safer* than the old blind auto-rebase: a manifest contract,
   hold-and-alert on anything non-trivial, canary-first, prod-trails-3h.
2. **Fleet auto-update is DISABLED fleet-wide** (`/etc/hermes/auto-update-disabled`,
   set 2026-06-03 across 637 VMs). Aeon *publishes* images, but they only reach
   VMs if the per-VM updater is re-enabled. **Aeon's value is null unless this is
   reversed** — see Decision C.

## Cardinal guardrails (inherited from the manifest `autonomy:` block)
- `on_ci_red: hold-and-alert` — never ship a red build.
- `on_low_confidence_merge: hold-and-alert` — never guess a conflict.
- `rollout: pull-based` — VMs pull their tag; **Aeon never holds fleet SSH** (it
  only touches GitHub + GHCR). This is the hard security boundary.
- `canary_tag: :canary` (bleeding edge) · `prod_tag: :stable` (promote =
  re-tag the canary digest that has soaked ≥3h).
- Per-VM updater: self health-check + **auto-rollback** to the prior digest.

## Architecture (proposed v1 — conservative)
Aeon = **GitHub Actions in the canary fork**, not a Claude session (session-
independent, has GITHUB_TOKEN + GHCR creds, naturally SSH-free).

**`aeon-sync-canary.yml`** — every 3h (DISABLED until sign-off; `workflow_dispatch`-only to start):
1. `git remote add upstream …; git fetch upstream`.
2. `git config merge.ours.driver true` (REQUIRED, else the `.gitattributes`
   `merge=ours` on `docker-publish.yml` is a silent no-op), then
   `git merge --no-commit --no-ff upstream/main`.
3. **Clean merge** (no conflicts) → push `aeon/sync-<utc-date>` → open PR →
   enable auto-merge. CI green → merge to `main` → `docker-publish.yml` builds +
   repoints canary `:stable` → canary VMs pull. **This is the only path Aeon
   does unattended.**
4. **Conflict OR CI red** → abort, open a **draft** PR with the conflict markers,
   label `aeon-hold`, and alert (GitHub + a dashboard signal). A human (or the
   `hermes-upstream-sync` skill via a Claude task) resolves it. Aeon never
   force-merges.

**`aeon-promote-prod.yml`** — every 3h (DISABLED until sign-off):
- Find the canary digest that has been clean-`:stable` for **≥3h** with a green
  build, and promote it to the **prod** fork's `:stable` (re-tag, the
  builderbox-1 lane). v1 default: **alert "promote ready" + one-click confirm**,
  not silent auto-promote — prod is the whole paying fleet. Flip to auto after a
  few weeks of clean trailing (Decision B).

## Integration points (do NOT reinvent)
- `docker-publish.yml` — the existing build/tag pipeline Aeon triggers (push-to-
  main). Respect its "must not race `:stable`" guards.
- `.gitattributes merge=ours` on `docker-publish.yml` — protects the fork-owned
  build workflow from upstream clobber. Aeon MUST set `merge.ours.driver true`.
- `hermes-upstream-sync` skill — the conflict-classification knowledge (classes
  A/B/C, the seam-guard CI tests). Aeon's hold-and-alert hands conflicts BACK to
  this skill; it does not duplicate the semantic-merge judgment.
- `.hermesos/customizations.yaml` — the merge contract (keep-ours / take-theirs /
  merge-careful). Aeon reads it to decide whether a clean merge is actually safe
  (e.g. an auto-clean merge that touched a `merge-careful` path → downgrade to
  hold-and-alert even though git didn't conflict).

## Decisions only Ash can make (the sign-off)
- **A — Conflict autonomy.** v1 = **clean-merge-only** auto; every conflict (and
  every touch of a `merge-careful` path) holds-and-alerts. Alternative: let a
  scheduled Claude task attempt manifest-guided semantic merges. *Recommend A
  (clean-only) to start* — it's the safest re-introduction of automation.
- **B — Prod promotion.** Alert-and-confirm vs silent auto-promote of the
  3h-soaked canary digest. *Recommend alert-and-confirm first*, auto later.
- **C — Fleet auto-update.** Aeon publishing images is inert unless the per-VM
  updater is re-enabled (you disabled it fleet-wide on purpose). Re-enable it
  (staged/jittered pulls + self-health-check + auto-rollback, light images only),
  or keep manual rolls and let Aeon only *prepare* `:stable`? **This is the crux
  — "autonomous updates" needs C reversed.**
- **D — Scope.** Agent fork only (webui is being retired by the cutover — don't
  automate a dying fork), or both? *Recommend agent-only.*
- **E — Enable cadence.** Start `workflow_dispatch`-only (you trigger each run +
  watch), graduate to the 3h `schedule:` after N clean manual runs. *Recommend
  dispatch-only first.*

## Build order once approved
1. `aeon-sync-canary.yml` (dispatch-only) + the manifest-aware clean-merge gate.
2. Dry-run it by hand a few times; confirm clean merges PR + build correctly and
   conflicts hold-and-alert.
3. `aeon-promote-prod.yml` (alert mode).
4. Per Decision C: the per-VM staged auto-update path (separate, careful).
5. Graduate triggers to `schedule:` once each step is proven.
