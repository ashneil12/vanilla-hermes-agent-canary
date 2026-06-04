# Aeon — autonomous upstream-sync agent (v1 BUILT — inert until activated)

> Status: **v1 SHIPPED, INERT.** The canary sync workflow
> (`.github/workflows/aeon-sync.yml`) is in the repo but runs ONLY when manually
> dispatched and does nothing destructive without the `AEON_GITHUB_PAT` secret.
> Ash delegated the design decisions ("u take care of it"); they're recorded
> below as **made**. Aeon goes live the moment Ash completes the 3 Activation
> steps. It still touches only Git — never the fleet — so activation cannot
> disrupt a running agent.

## What Aeon is for
Make HermesOS updates **autonomous**: pull upstream `NousResearch/hermes-agent`
into the canary fork on a cadence, preserve our customizations (per
`.hermesos/customizations.yaml`), and escalate anything non-trivial to a human
instead of guessing — **without a human driving each sync**.

**Primary driver (Ash, 2026-06-04):** Nous iterates on the **chat / webchat
surface constantly**, so our webchat customizations need re-merging against
upstream *frequently*. Aeon automates exactly that toil — the routine clean
merges land unattended; only genuine conflicts wait for a human.

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

## Decisions (Ash delegated — made 2026-06-04)
- **A — Conflict autonomy → clean-merge-only auto.** Routine clean merges open a
  PR that self-merges on green CI; conflicts hold-and-alert (an `aeon-hold`
  issue). The CI **seam-guard tests** (venice/search providers, media-tool
  wiring, agent-elevation, the webchat bake gate) gate the clean path: an
  upstream change that silently breaks a customized seam fails CI → auto-merge
  blocked → the PR sits as a de-facto hold. No semantic-merge guessing.
- **B — Prod promotion → deferred (supply-side first).** v1 keeps the *fork*
  current; building/promoting is left to the existing manual/builderbox-1 lane.
  The `aeon-promote-prod.yml` (alert-then-auto) is a documented follow-up.
- **C — Fleet auto-update → stays OFF for now; roll is deferred + will be
  idle-gated.** Aeon keeps `:canary` *available*; it does NOT auto-roll VMs.
  Auto-rolling a live agent (esp. canary VM 1000) interrupts in-flight turns, so
  the per-VM updater — when built — must be **idle-gated** (pull only when no
  active turn) + self-health-check + auto-rollback. Until then, rolls stay
  manual. This is the one genuinely-disruptive lever; it gets its own careful pass.
- **D — Scope → canary agent fork only.** webui is being retired by the cutover;
  don't automate a dying fork. Prod fork via the promote follow-up.
- **E — Enable cadence → dispatch-only first, then 3h schedule.** Ships inert;
  Ash activates (below) and can watch the first manual runs before the schedule.

## Activation (Ash — Aeon is INERT until these 3 steps)
1. **Add repo secret `AEON_GITHUB_PAT`** — a fine-grained PAT on this repo with
   Contents:write + Pull-requests:write + Workflows:write. REQUIRED: a PR opened
   with the default `GITHUB_TOKEN` does not trigger CI, so auto-merge would hang.
2. **Enable "Allow auto-merge"** in repo Settings → General (one-time).
3. **Uncomment the `schedule:` block** in `aeon-sync.yml` to go from manual to
   every-3h. (Leave it commented to keep triggering runs by hand from the Actions
   tab while you build trust.)

## What ships in v1 vs. follow-ups
**Shipped (`aeon-sync.yml`, inert):** the canary upstream sync — fetch, merge
(not rebase, with the `merge=ours` driver), clean→auto-merge PR, conflict→
`aeon-hold` issue. Session-independent, never touches the fleet.

**Follow-ups (each its own careful pass):**
1. Auto-build trigger after a clean sync merges (so `:canary` is fresh) — gated
   on whether we want to auto-publish CI-green canary builds.
2. `aeon-promote-prod.yml` — promote a 3h-soaked clean canary digest to prod
   `:stable` (alert-then-auto).
3. The **idle-gated per-VM auto-update** path (Decision C) — the only piece that
   can touch a running agent; staged/jittered + self-rollback, light images only.
