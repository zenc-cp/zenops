# ZenOps Architecture Audit — 2026-06-19

**Scope:** `zenc-cp/zenops` @ commit `673e8d1` (branch `copilot/review-audit-architecture`)
**Method:** Static review of repo contents only. **No live VM access** from the audit sandbox (see §0).
**Purpose:** Hand-off record for cross-checking by a second agent / operator with live `nanoclaw-az` access.

---

## 0. Audit environment limitations (read first)

The audit was performed in a GitHub-hosted sandbox with **no route to the live infrastructure**. Every live-VM claim below is therefore **UNVERIFIED** and tagged `[NEEDS-VM]`. Probes attempted and their results:

| Vector | Probe | Result |
|---|---|---|
| Azure CLI creds | `az account list`, `~/.azure` | `Please run az login`; no `~/.azure` dir |
| Managed identity | `az login --identity` (IMDS) | hangs — no IMDS/MI |
| SSH key | `ls ~/.ssh` | directory does not exist |
| DNS | `getent hosts nanoclaw-az / design-e.z3nops.com / z3nops.com / pg-atlas-orchestrator…` | all NXDOMAIN |
| Egress | `curl github.com` vs `curl example.com` | 200 vs 000 (allowlisted to GitHub only) |
| Env secrets | `env \| grep azure/ssh/tenant` | only `GITHUB_*` / `COPILOT_*` tokens |

**Conclusion:** findings derived from repo files are reliable; findings about deployed VM state are inference-only and must be confirmed on `nanoclaw-az`.

---

## 1. Repository facts (verified from repo content)

- Repo is **ops/governance only** — no runtime code. Runtime lives in `zenc-cp/zenbrain` (orchestrator) and `zenc-cp/design-e` (RPC endpoint). Source: `README.md`.
- Contents:
  - `docs/adr/` — ADR-025, ADR-026, ADR-031, ADR-032
  - `docs/superpowers/plans/` — 2 S-class plans
  - `deploy/` — `zenops-consumer`, `claw-runtime` suite, `vm-health-watchdog`, `hermes-edit-config`, `tests/`
  - root static site — `agentarmor.html`, `index.html`
- **Tests:** 31 pytest tests across 3 suites, **all pass locally** (`deploy/tests/test_claw_runtime_hooks.py`, `deploy/vm-health-watchdog/test_vm_health_check.py`, `deploy/hermes-edit-config/test_hermes_edit_config.py`).
- **No CI:** there is no `.github/workflows/` directory.

### Documented architecture (from ADR-025 / ADR-026)
```
zenbrain.orchestrator.dispatch ─(roles: watcher/researcher/coder…)─> runners  [PG: agent_results]
                                       ⊗  do NOT compose  ⊗
design-e /rpc/v1/dispatch ─(specialists: Scout/Hunter/Sentinel/Trader/Scribe/Ops)─> hermes-agent consumer
   brain-inbox/*.json → consumer loads persona YAML → one Hermes AIAgent → results/{task_id}.json
```
Specialist = `{name, system_prompt, allowed_tools, default_model}` persona-tuple inhabited by **one** Hermes agent per dispatch (not a separate process). Boundary enforced defensively via `RESERVED_SPECIALISTS` + lockstep drift contract across 3 repos.

---

## 2. Findings

Severity reflects repo-only evidence. The `[NEEDS-VM]` tag marks claims a second agent must confirm on `nanoclaw-az`.

### F1 — `slimslimchan` path drift vs ADR-031 (governance contradiction) — **MEDIUM**
The entire `claw-runtime` suite hardcodes `slimslimchan` user + `/home/slimslimchan/claw`:
- `deploy/claw-runtime-drift-check.service:18` → `User=slimslimchan`
- `deploy/claw-runtime-git-init.sh:19`, `deploy/claw-runtime-drift-check.sh:19`, `deploy/claw-runtime-pre-commit-hook.sh`, `deploy/RUNBOOK-claw-runtime.md` → `/home/slimslimchan/...`, `sudo -u slimslimchan`

ADR-031 (Accepted, 2026-06-08) asserts `slimslimchan` is **NOT** a Linux user on the VM and mandates `slimslimchan → azureuser`. **However**, the `zenops-consumer.service` (post-ADR-031) *does* use `azureuser`, so the suites disagree with each other.

- **Repo-only conclusion:** internal inconsistency between ADR-031 + `zenops-consumer.service` (azureuser) and the `claw-runtime` suite (slimslimchan).
- `[NEEDS-VM]` Which user actually owns `/home/slimslimchan/claw`? Note: stored-memory live tracebacks from **2026-06-14** reference `/home/slimslimchan/zen-console/...` and `~/hermes-agent/...` as real paths, which would mean ADR-031's blanket "fabricated path" claim is itself stale.
- **Confirm on VM:**
  ```bash
  getent passwd slimslimchan azureuser
  ls -ld /home/slimslimchan/claw 2>&1
  ```

### F2 — `claw-runtime` auth-bypass control is weaker than its stated threat — **MEDIUM**
`deploy/RUNBOOK-claw-runtime.md` motivates the suite with a real attack: injecting `return True` into `_check_auth()` to disable bearer auth on a **public** MCP endpoint fronting ~25 high-blast-radius tools. Shipped controls:
- `claw-runtime-pre-commit-hook.sh` runs in **ADVISORY mode** (`exit 0`) — bypassable via `git commit --no-verify`, or by editing `mcp-server.py` without committing at all.
- `claw-runtime-drift-check.sh` alarms only **after a 15-min grace window** — i.e. ≥15 min of live exposure before any signal.

- **Recommendation:** the durable control should be **fail-closed runtime auth enforcement** and/or a **server-side / CI check on the mirror**, not a local advisory hook. The hook even documents an `UPGRADE-TO-BLOCKING` marker that ships disabled.
- `[NEEDS-VM]` Current `_check_auth` body integrity:
  ```bash
  sha256sum /home/slimslimchan/claw/mcp-server.py   # RUNBOOK expects 59778371c8be736ca92c317345cde8cacce25415f271f2cc9f0768e3e4833f47
  git -C /home/slimslimchan/claw log --oneline | head
  ```

### F3 — `zenops-consumer.service` references an install path the governance says is absent — **LOW/MEDIUM**
`deploy/zenops-consumer/zenops-consumer.service` (`azureuser` ✔) points `WorkingDirectory`/`ExecStart` at `/home/azureuser/hermes-agent/.venv/...`. ADR-031 Finding 2 + ADR-026 v7 state hermes-agent had **no VM install** and the install path is TBD. Also: **no `zenops-consumer.env.example`** ships, unlike `vm-health-watchdog` which provides one — operator-facing gap (unit reads `EnvironmentFile=/etc/zenops-consumer.env`).

- `[NEEDS-VM]` stored memory (2026-06-14) shows hermes-agent live on the VM under `~/hermes-agent` (task `8517f17b38b3` ran), so this is **likely stale** — but the live install appears to be under `/home/slimslimchan/`, while the unit expects `/home/azureuser/hermes-agent`.
- **Confirm on VM:**
  ```bash
  ls -ld /home/azureuser/hermes-agent /home/slimslimchan/hermes-agent 2>&1
  systemctl cat zenops-consumer 2>/dev/null | grep -E 'User=|ExecStart='
  ```

### F4 — ADR-032 observability sink path not writable by current consumer unit — **LOW (forward-looking)**
ADR-032 (Proposed) puts the shared SQLite at `/var/lib/design-e/observability.sqlite` and notes the consumer needs that path in `ReadWritePaths`. The current `zenops-consumer.service` grants only subdirs (`/var/lib/design-e/results`, `/var/lib/design-e/brain-inbox`), not the parent. Under `ProtectSystem=strict` the `emit()` writer would hit a read-only-FS error when ADR-032 ships. Track against ADR-032 acceptance checklist.

### F5 — `vm-health-watchdog` probes a soon-to-be-retired service; misses the real surface — **LOW/MEDIUM**
`deploy/vm-health-watchdog/vm_health_check.py:108-112` probes the `hermes-workspace` unit + `http://127.0.0.1:8092/health`. Stored decision **ADR-zenops-001 (accepted 2026-06-14)**: retire `hermes-workspace` from the VM (7-day journald: hermes-workspace **0** HTTP reqs vs zen-console **1259**). Once retired:
- the `hermes-workspace` probe becomes a guaranteed **false-positive** alert source, and
- the actual public surface (**zen-console**) has **no probe at all**.

- **Recommendation:** swap the `hermes-workspace` probe for a `zen-console` probe when the retire lands.
- `[NEEDS-VM]` Confirm:
  ```bash
  systemctl is-active hermes-workspace zen-console
  curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8092/health
  ```

### F6 — No CI despite shipping testable artifacts — **PROCESS**
31 pytest tests + several shell scripts, but no `.github/workflows/`. For an ops repo whose artifacts gate production-deploy correctness, a minimal CI (pytest + shellcheck) on PRs is low-effort / high-leverage. (Repo-verified; not VM-dependent.)

### F7 — Recurring "writer-with-no-reader" pattern + line-number-coupled ADRs — **LOW (observation)**
The persona substrate has repeatedly shipped a writer before its consumer (brain-inbox; `record_event`/F3 in ADR-025; ADR-032's 3-store silo). Each gap was caught by audits after the fact. ADRs also cite volatile `file.py:NNN` line numbers; ADR-025 itself warns these drift and says to `grep` instead — good self-awareness, but several tables still depend on exact line refs.

---

## 3. Strengths (preserve)
- **ADR-025** is high quality: ground-truth-driven, explicit about what specialists are *not*, documents the non-composing dispatch-vs-role boundary, enforces it across 3 lockstep sites with a drift-contract test.
- `vm_health_check.py` separates a pure, unit-tested decision layer from I/O probes; its TCP probe (`:8642`) was added specifically to catch the "`systemctl active` but inner socket never bound" outage class (claw-stack-jp#165).
- systemd units apply real least-privilege hardening (`ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, scoped `ReadWritePaths`, `NoNewPrivileges`).
- `hermes-edit-config.sh` correctly handles the `chattr +i` immutability ritual with backups + restart verification.

---

## 4. Recommended actions (priority order)
1. **F1** — Reconcile `claw-runtime` suite with ADR-031: substitute `slimslimchan → azureuser` across 6 files, **or** amend ADR-031 to scope the exception if `claw/` genuinely runs under a different account. (Resolve internal contradiction first.)
2. **F2** — Strengthen `_check_auth` control: move to fail-closed runtime enforcement + CI on the mirror; at minimum flip the hook to blocking and shorten the drift grace window.
3. **F3** — Add `zenops-consumer.env.example`; reconcile the `ExecStart` install path with reality.
4. **F6** — Add minimal CI (pytest + shellcheck) gating PRs.
5. **F4** — Add the ADR-032 sink path to the consumer unit's `ReadWritePaths` before ADR-032 ships.
6. **F5** — Repoint `vm-health-watchdog` from `hermes-workspace` to `zen-console` when the retire lands.

---

## 5. Cross-check checklist for the second agent (live VM)

Run on `nanoclaw-az` (SSH inbound is policy-blocked per ADR-031 §Finding 4 — use `az vm run-command invoke`):

```bash
getent passwd slimslimchan azureuser
ls -ld /home/slimslimchan/claw /home/slimslimchan/hermes-agent /home/azureuser/hermes-agent 2>&1
sha256sum /home/slimslimchan/claw/mcp-server.py
git -C /home/slimslimchan/claw log --oneline 2>&1 | head
systemctl is-active design-e hermes-gateway hermes-workspace zenops-consumer zen-console
systemctl cat zenops-consumer 2>/dev/null | grep -E 'User=|ExecStart=|ReadWritePaths='
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8092/health
ls -ld /var/lib/design-e /var/lib/design-e/brain-inbox /var/lib/design-e/results 2>&1
```

| Finding | What to confirm | Expected if finding holds |
|---|---|---|
| F1 | `getent passwd slimslimchan` | If user EXISTS → ADR-031 is stale, claw scripts may be correct. If ABSENT → claw scripts are broken. |
| F2 | `sha256sum …/mcp-server.py` | matches `59778371…`; `_check_auth` still enforces auth |
| F3 | `ls hermes-agent` paths | unit's `/home/azureuser/hermes-agent` exists (else path is wrong) |
| F4 | `systemctl cat zenops-consumer` `ReadWritePaths` | parent `/var/lib/design-e` NOT yet present (ADR-032 unmet) |
| F5 | `systemctl is-active hermes-workspace zen-console` | hermes-workspace inactive/retired; zen-console active+unmonitored |
