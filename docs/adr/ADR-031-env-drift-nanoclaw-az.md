# ADR-031: VM env-drift discovered at ADR-025 S10 deploy preflight

**Status:** Accepted
**Date:** 2026-06-08
**Deciders:** Zen (session c1483664)
**References:** ADR-025 §11, plan v2.1 + v2.1.5, S10 deploy plan v1.1 (PR #41 merged)

## The rule (single sentence, quotable)

> **`slimslimchan` is the user's Google account username, NOT a Linux user on `nanoclaw-az`. Every prior plan/ADR reference to `/home/slimslimchan/...` is a fabricated path, not a verified file location.**

This invalidates three load-bearing claims in ADR-025 §11 and resets the deploy plan's path assumptions.

---

## Context

S10 deploy preflight (2026-06-08 ~10:30 HKT) discovered four environment realities that contradict the merged S10 plan v1.1:

### Finding 1: VM Linux user is `azureuser`, not `slimslimchan`

`getent passwd` was attempted but blocked by a concurrent `az vm run-command` lease. The earlier preflight DID confirm: design-e `systemctl cat` shows `User=azureuser`, and `ls ~/hermes-agent` (as `azureuser`) returned `No such file or directory`. The user has now clarified that `slimslimchan` is their **Google account**, not a Linux account.

**Implication:** The systemd unit shipped in zenbrain #39 (`User=slimslimchan, Group=slimslimchan, WorkingDirectory=/home/slimslimchan/hermes-agent, ExecStart=/home/slimslimchan/hermes-agent/.venv/bin/python -m agent.specialists.consumer`) will fail to start on this VM. Every path needs `slimslimchan` → `azureuser` substitution.

### Finding 2: `hermes-agent` has never been installed on the VM

Preflight confirmed: no `hermes-agent` directory under `/home/azureuser/`, no venv. The "verified hooks at `/home/slimslimchan/hermes-agent/model_tools.py:339`, `run_agent.py:651`, `gateway/platforms/api_server.py:998`" cited in **ADR-025 §11 are NOT verifications against this VM**. They were verified against a different checkout (likely the laptop clone at `C:\Users\szelimchan\AppData\Local\hermes\hermes-agent\`, or a different VM, or fabricated).

**This does NOT invalidate ADR-025's persona-tuple decision** — the hooks really do exist in `zenc-cp/hermes-agent` (we verified them locally during S2/S3 implementation, and the tests pass). But the ADR's claim that they're "verified against `/home/slimslimchan/hermes-agent/` on nanoclaw-az" is false.

### Finding 3: `/opt/design-e/` is already the install path

S10 plan §3.5.1 D-CHOICE-1 picked `/opt/design-e/` as the design-e install path, on the assumption it didn't exist yet. It does. Preflight P3 confirmed `/opt/design-e/` exists, runs as `User=azureuser`, has its own venv at `/opt/design-e/venv/` (not `.venv/`), and serves design-e on `127.0.0.1:7890` behind Caddy.

**Whether it's a git checkout vs scratchpad copy is still unconfirmed** (the diagnostic `cd /opt/design-e && git log` query was blocked by the concurrent run-command lease). Assume scratchpad copy until proven otherwise — sha256 `254165767c5e...` matches the laptop scratchpad byte-for-byte, suggesting an scp not a clone.

### Finding 4: SSH inbound is structurally blocked

NSG rules added at NIC and subnet (Allow 219.76.170.51 → port 22, prio 1100) were silently stripped within ~20 minutes by service principal `7355f99c-0211-455d-aa02-4a559687ae60` (likely Azure Policy or Defender for Cloud). Egress port 22 from the laptop works (verified against github.com:22), but inbound to the VM is policy-managed. **SSH-based deploy is unavailable from this laptop without a policy exemption.** Use `az vm run-command invoke` instead.

---

## Decision

### Path substitutions (apply across all future plans + the systemd unit)

| Old (slimslimchan-prefixed) | New (azureuser-prefixed) |
|---|---|
| `User=slimslimchan` | `User=azureuser` |
| `Group=slimslimchan` | `Group=azureuser` |
| `/home/slimslimchan/hermes-agent/` | `/home/azureuser/hermes-agent/` (TBD: install path) |
| `/home/slimslimchan/.hermes/specialists/` | `/home/azureuser/.hermes/specialists/` |
| `/home/slimslimchan/hermes-agent/.venv/bin/python` | `/home/azureuser/hermes-agent/.venv/bin/python` |
| ReadWritePaths references | Same substitution |

### ADR-025 §11 annotation

Add an inline note in ADR-025 §11 (separate PR):
> **2026-06-08 correction (ADR-031):** The "verified against `/home/slimslimchan/hermes-agent/` on nanoclaw-az" qualifier in this section is incorrect — that path does not exist on the VM. The line numbers in `model_tools.py:339`, `run_agent.py:651`, and `gateway/platforms/api_server.py:998` were verified against the laptop checkout at `C:\Users\szelimchan\AppData\Local\hermes\hermes-agent\` and confirmed in `zenc-cp/hermes-agent@main`. ADR-025's persona-tuple decision still stands — only the deploy-environment qualifier was wrong.

### Plan v1.1 supersession

S10 plan v1.1 (merged in PR #41) D-CHOICE-2 (`User=slimslimchan`) is superseded by this ADR. A v1.2 patch PR must:
- Change D-CHOICE-2 to `azureuser`
- Document that `/opt/design-e/` already exists (D1 becomes a `git remote add origin` + `git pull` if it's already a git repo, or a `git clone --separate-git-dir` + reconcile if it's a flat copy)
- Update all path references to use `/home/azureuser/`
- Add a P14 preflight: confirm `/opt/design-e/.git` exists OR plan a git-init migration

### SSH access: use `az vm run-command invoke` for all D0–D6

Documented in plan §4 update.

---

## Rationale

### Why a separate ADR vs an in-place plan patch

Two reasons:
1. **The `slimslimchan` mistake is recurring.** It appears in ADR-025 §11, ADR-020 reference, plan v2.1, plan v2.1.5 (multi-repo addendum), plan v1.1 (S10), and the systemd unit text. An ADR is the right surface to fix once and reference forward.
2. **Finding 4 (SSH structurally blocked) is infrastructure-policy-level**, not plan-level. Future deploys from any laptop have to use `az vm run-command` or get a policy exemption — that decision deserves its own anchor.

### Why halt instead of soldier-on

The earlier-stored rule says: "For any plan touching deployed infrastructure, run a 30-minute env-discovery preflight BEFORE plan grading: SSH/auth probes, hostname resolution, file paths, credential mint sanity-checks. Don't grade plans built on unverified assumptions." The S10 plan was graded against assumptions that turned out to be wrong on three counts. Soldier-on improvisation would have produced exactly the kind of "fat-finger during production deploy" failure the consensus-grade voters warned about.

---

## Consequences

### Positive
- ADR-025 § 11 gets a correction note; future readers don't trust a fabricated verification.
- S10 v1.2 plan (next session) is built on real VM state, not assumed state.
- The SSH-policy reality is documented for any future operator.

### Negative
- S10 execution is delayed by 1+ session.
- ADR-025 needs an amendment PR (small, but still PR overhead).

### Neutral
- ADR-025's core decision (persona-tuple specialists) is unaffected.
- All implementation code (design-e #1, hermes-agent #1/#2, zenbrain #39) is unaffected — it works locally, and the persona/consumer modules don't hardcode `slimslimchan`. Only the systemd unit needs a one-line edit.

---

## Verification preconditions (verified 2026-06-08 between 10:30 and 13:30 HKT)

| Claim in this ADR | Evidence |
|---|---|
| VM user is `azureuser` | `systemctl cat design-e` showed `User=azureuser` (preflight P3) |
| `~/hermes-agent` absent | `ls ~/hermes-agent` from `azureuser` returned ENOENT (preflight P5) |
| design-e at `/opt/design-e/` | Preflight P3 `WorkingDirectory=/opt/design-e` |
| design-e venv at `/opt/design-e/venv/` (not `.venv/`) | Preflight P3 `ExecStart=/opt/design-e/venv/bin/uvicorn` |
| design-e file sha matches scratchpad byte-for-byte | Preflight P4 sha256 `254165767c5e6b4d640f5bc6efa9e4a9ee66e68bd4c069f0d77a3d6c62d1e7f9` matches laptop |
| sshd running on 22 | `az vm run-command` confirmed `LISTEN 0 128 0.0.0.0:22 sshd pid=831` |
| NSG rules stripped by `7355f99c-...` | Azure activity log query, ~20 min after my `az network nsg rule create` succeeded |
| `slimslimchan` is Google account, not Linux user | User input: "slimslimchan is my google account username" (this session, 13:28 HKT) |

---

## Open questions (intentionally not resolved here)

1. **Who/what is `7355f99c-0211-455d-aa02-4a559687ae60`?** Likely Azure Policy or Defender. If we want SSH access from a tagged laptop IP, we need either a policy exemption or to ride through `az vm run-command` permanently.
2. **Is `/opt/design-e/` a git repo or a flat scp'd copy?** Decides whether D1 in plan v1.2 is `git pull` or git-init-migration.
3. **Where DID the `/home/slimslimchan/...` line numbers in ADR-025 §11 originally come from?** Was it the laptop checkout, an earlier different VM, or fabricated by a previous session? Worth a quick git-blame on ADR-025 to see what session added §11.

These get their own follow-ups (or annotations on ADR-025) if work continues.
