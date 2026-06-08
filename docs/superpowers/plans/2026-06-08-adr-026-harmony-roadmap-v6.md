# ADR-026 v5 — ZenOps + Zenbrain Harmony Roadmap (reconciled with ADR-025 + ADR-030)

**Date:** 2026-06-08 07:40 HKT
**Status:** Proposed (resume after ADR-025/030 reconciliation; was Proposed v4 2026-06-07 23:50)
**Author:** Zen Chan
**Supersedes:** ADR-026 v1-v4 (session 5b017110 ralplan output, valid until ADR-025/030 merged overnight)
**Amends:** ADR-024 (gateway substrate + dispatch_tokens design — unchanged); consumes ADR-025 (persona-tuple model) + ADR-030 (hermes_coder peer)

---

## What changed v4 → v5

A parallel session (3d226b90, da5d6a86) landed **ADR-025** (`zenc-cp/zenbrain` main, 2026-06-07 evening) and **ADR-030** (PR #36, open). Both materially changed the harmony framing:

1. **ADR-025**: "ZenOps specialist" = a **persona tuple** `{name, system_prompt, allowed_tools, default_model}` stored as YAML on nanoclaw-az. ONE Hermes AIAgent class inhabits the persona per dispatch. NOT separate processes/containers/runners.
2. **ADR-025 canonical 6 specialists**: `Scout, Hunter, Sentinel, Trader, Scribe, Ops`. Hermes is **the host**, not a specialist.
3. **ADR-025 HARD BLOCKER** explicitly named: `record_event` bus has writer (design-e `dispatch_specialist`) but NO reader. Implementation cannot ship until result-retrieval surface exists (list_events RPC, file convention, or SSE).
4. **ADR-030**: `hermes_coder` ships as a **zenbrain-side peer** (not a design-e specialist) — separate dispatch path, calls Foundry AOAI directly via `LLMClient`. Adds `runner_label` kwarg to `_coder_runner._push_and_open_pr`.

ADR-026 v4 misframed specialists as separate `runners_registry` rows (one per name) — that contradicts ADR-025. v5 reframes the harmony architecture around personas; ADR-024 substrate (dispatch_tokens + ARU-1 + HMAC dual-key) is **preserved as-is** — it's still the correct mechanism for the zenbrain↔design-e BOUNDARY lease, just with a different inhabitant count.

---

## Decision

Pursue **Option A (Depth-First) reframed**:
- The ADR-024 HTTP gateway is the **zenbrain↔design-e boundary** (one lease per dispatch, not per specialist).
- The 6 ZenOps personas live as YAML on nanoclaw-az per ADR-025; one Hermes-side consumer drains brain-inbox, loads the named persona, runs the AIAgent, writes back via `record_event`.
- Q1 bar is per-persona: each of {Scout, Hunter, Sentinel, Trader, Scribe, Ops} returns a real (non-mock) response on a representative test input.
- Q2 bar is round-trip: zenbrain dispatch → gateway → design-e `dispatch_specialist(name=...)` → brain-inbox → Hermes consumer → persona → AIAgent → `record_event` → zenbrain `agent_results`.
- Q3 self-improve loop is unchanged in shape (discover → propose → eval → auto-apply), now lives inside the persona-tuple model (per ADR-025 Shadow A/B is "swap the YAML, same agent" — much cheaper than v4 assumed).

Calendar: ~16 PD / ~5 weeks (was 20.5 PD / ~6 weeks; persona-tuple model is materially cheaper than 6-runners-each-with-mailbox model).

---

## Reconciliation table (v4 → v5 architectural mapping)

| v4 assumption | v5 reality per ADR-025/030 | New design |
|---|---|---|
| 6 specialists each get a `runners_registry` row | One `runners_registry` row for the design-e dispatcher boundary + persona names go in a separate `specialist_personas` config table OR YAML files (ADR-025 says YAML) | New row `hermes_dispatcher` (sandbox+infra scopes) in runners_registry. Persona names validated against design-e `VALID_SPECIALISTS`. |
| "Hermes" was one of the 6 to realify | Hermes is the host AIAgent, not a specialist | "Realify Hermes" step removed; replaced with "wire the Hermes-side consumer" |
| Per-specialist gateway mailbox (6 mailboxes) | One brain-inbox queue drained by one consumer | One mailbox at the design-e boundary; persona name carried in payload |
| `hermes_ask` (mock) is the Q1 unblock target | `hermes_ask` is a separate RPC; the actual Q1 path is `dispatch_specialist` → consumer → real AIAgent. `hermes_ask` may remain mock or be killed as a separate cleanup. | Q1 target = `dispatch_specialist` round-trip producing non-mock persona output |
| Atlas rename → `aider-production` per Phase A1 | ADR-030 added `hermes_coder` peer with `runner_label="hermes"` kwarg requirement on `_coder_runner._push_and_open_pr`. The branch/PR labelling fix happens FIRST. | Atlas rename ordering reviewed; may merge or sequence around hermes_coder PR #36 |
| Write-back endpoint = new design (my invention) | ADR-025 HARD BLOCKER names three options: (a) `list_events` RPC, (b) `/var/lib/design-e/results/{task_id}.json` file convention, (c) SSE/WebSocket | **v5 picks option (b)** — file convention matches existing audit-log shape, requires zero new endpoints, polled by zenbrain side. SSE/WebSocket parked. |

---

## Sequencing (v5)

### Step 0 — Pre-flight (1.5 PD, was 1; M1 + m1 added)
- **ADR-025 reality probe**: SSH to nanoclaw-az, verify (a) `/var/lib/design-e/brain-inbox/` exists and is writable by design-e, (b) `/home/slimslimchan/hermes-agent/` is checked out at expected commit, (c) `~/.hermes/specialists/` directory exists (create if not), (d) confirm `VALID_SPECIALISTS` allow-list matches ADR-025's canonical 6: **Scout, Hunter, Sentinel, Trader, Scribe, Ops** (exact set; no Hermes).
- **M1 colocation check**: from the consumer service account on nanoclaw-az, verify (a) `stat /var/lib/design-e/results/` shows directory exists, writable by `slimslimchan`, (b) the gateway process (Container App or wherever) reads that **exact path** — confirm via the gateway's mount/volume config OR by writing a sentinel file and GET-ing it through the gateway. If gateway runs on a different host than nanoclaw-az, this option requires re-design (file convention assumes shared filesystem); document as REPLAN trigger.
- **Round-trip migration test** for ADR-024 PR #34 (unchanged from v4).
- **Write + test `aru1_quiesce.ps1`** (unchanged from v4).
- **Populate rollback table** (unchanged from v4).
- **ADR-024 amendment paragraph** (unchanged from v4: dispatch_tokens PG, HMAC current+previous, rotation step 1→3 ≤30 min).
- **Confirm zenbrain↔design-e network path** (Container App egress → design-e ingress through Cloudflare).
- **m1 git state preflight**: `git -C ~/.copilot/zenbrain config core.bare` must return false (recover the footgun if true); working tree must be clean and on `main` or a documented feature branch; if parallel session (e.g., 3d226b90) is active, work happens in a separate worktree at `$env:TEMP\zenbrain-adr026\` instead of the canonical checkout. **BINARY GATE**: either preconditions met OR work stops.

**Gate**: all 7 sub-actions green. Specifically: nanoclaw-az SSH reachable; brain-inbox writable by design-e MI; M1 colocation confirmed (no symlink surprises); VALID_SPECIALISTS = exactly the canonical 6; git footgun cleared; working tree on clean branch.

### Step 1 — Talos Lease Race Fix (1 PD)
Unchanged from v4.

### Step 2 — Hermes-side Consumer (3 PD, replaces v4 Step 2 "Hermes Realification")
- Implement `~/hermes-consumer/consumer.py` on nanoclaw-az: polls `/var/lib/design-e/brain-inbox/`, takes oldest JSON, parses `{specialist: name, task: {...}}`, loads `~/.hermes/specialists/<name>.yaml`, invokes Hermes AIAgent with that persona's `system_prompt + allowed_tools + default_model`, captures structured output, writes to `/var/lib/design-e/results/{task_id}.json`, calls `record_event(event_type="dispatch_completed", task_id, details={output, latency_ms, tool_calls})`.
- **Idempotency (R8 mitigation, m2 expanded)**: consumer creates `<task_id>.processing` marker BEFORE AIAgent invocation, removes ON SUCCESS. Markers carry `started_at` ISO timestamp.
  - **Startup sweep**: on consumer start, scan brain-inbox for `*.processing` markers older than `STALE_PROCESSING_TTL_MIN` (default 30 min) → log warning, move marker to `/var/lib/design-e/brain-inbox/orphaned/<task_id>.processing` (preserves audit trail), re-enqueue original task file for re-processing.
  - **Periodic sweep**: every 5 min, same scan; same orphan-detect logic.
  - This prevents the "single crash permanently shadows a task" failure mode m2 surfaced.
- Bootstrap minimal personas: Scout + Sentinel (Sentinel chosen because it's the new face per ADR-025 vs. ADR-020's old "Post" naming).
- Run as systemd unit `hermes-consumer.service`.

**Gate**:
- 10/10 consecutive dispatches: design-e `dispatch_specialist(name="Scout", task=test_task)` → consumer drains → AIAgent runs → result file lands → `record_event` audit row written
- Identity check: consumer process runs as `slimslimchan` user (no root); KV credentials via Azure MI; `systemctl cat hermes-consumer | grep -i environ` shows no secrets
- `journalctl -u hermes-consumer --since "5 min ago"` shows zero errors over 10 dispatches
- **R8 idempotency drill**: simulate crash (kill -9 consumer mid-AIAgent) → restart → orphaned `.processing` marker detected by startup sweep → task re-enqueued → completes successfully on second attempt; no duplicate `record_event` rows
- ADR-025 result-retrieval blocker CLOSED: result files at `/var/lib/design-e/results/<uuid>.json` retrievable by zenbrain side (next step verifies)

**Rollback (standalone safe before Step 4 lands; ARU-1 member after)**: `systemctl stop hermes-consumer && systemctl disable hermes-consumer`. Brain-inbox accumulates; no result corruption.

### Step 3a — Gateway Deploy + Token Issuance (1.5 PD)
Unchanged architectural design from v4 (dispatch_tokens PG table with atomic UPDATE, HMAC dual-key KV state machine, 10-concurrent TOCTOU stress test). Only change: gateway's outbound call is now design-e `POST /rpc/v1/dispatch_specialist`, not a direct Hermes call.

### Step 3b — Result Polling + Cache (1 PD, replaces v4 "Per-Runner Mailbox"; C1 fixed)
- Gateway exposes `GET /rpc/v1/results/{task_id}` that reads from `/var/lib/design-e/results/{task_id}.json` (file convention per ADR-025 option b).
- Zenbrain dispatch poll loop: after gateway returns lease confirmation, zenbrain polls `GET /rpc/v1/results/{task_id}` every 5s (configurable `POLL_INTERVAL_S`) until non-empty OR **`POLL_TIMEOUT_S` reached (default 600s = 10 min, configurable per role)** OR lease expires.
- **C1 fix — explicit error path on timeout**: if `POLL_TIMEOUT_S` reached without a result file: (a) write `agent_results` row with `status='timeout'`, `error="result_poll_timeout: task_id=<id>, waited=<seconds>"`, (b) emit `record_event(event_type="dispatch_failed", task_id, details={reason: "consumer_no_response", waited_s: <int>})`, (c) mark `agent_tasks.status='failed'`, (d) log structured warning. Downstream callers see a definite terminal state, never an infinite hang.
- Cache the file content in `agent_results.output` once retrieved; mark `agent_tasks.status='done'`.

**Gate**: 5-task race test — all 5 results retrievable via GET in any order; cache consistency (file-write = GET-read byte-identical); 200 vs 404 distinction (404 while pending, 200 when ready); **C1 timeout test**: kill consumer mid-task → zenbrain poll reaches `POLL_TIMEOUT_S` → `agent_results.status='timeout'` row written → no infinite hang.

### Step 4 — Two-Way Composition (1.5 PD, was 2.0; replaces v4 "Write-Back Ingress")
Result already lands in zenbrain `agent_results` via Step 3b's polling. Step 4 builds the composition on top:
- `watcher` role observes new completed task → triggers downstream task per role-defined rules (e.g., Scout completes → Scribe gets follow-up).
- End-to-end two-step workflow test through real gateway (no harness shortcut).
- ARU-1 quiesce drill (unchanged: drain dispatch_tokens table for both consumed-but-not-completed AND issued-but-unexpired).

**ARU-1 sealed after this** (Steps 2/3a/3b/4 = atomic unit; rollback requires `aru1_quiesce.ps1`).

### Step 5 — Atlas Runner Rename + ADR-030 Reconciliation (1 PD, was 0.5; M2 added)
- Rename `atlas` → `aider-production` per Phase A1 (unchanged from v4).
- **NEW**: confirm `_coder_runner._push_and_open_pr` accepts `runner_label` kwarg (landed by PR #36 ADR-030). Aider call sites pass `runner_label="aider-production"` (or stay at `aider` if simpler — coordinate with PR #36 author).
- `runners_registry` row for `aider-production` (renamed); `hermes_coder` row added per ADR-030 A7 (may already be there if PR #36 merges first — confirm at Step 5 start; do not defer).
- 7-day back-compat alias for `atlas` (unchanged).
- **M2 — hermes_coder prod scope gate**: ADR-030 declares `hermes_coder: [sandbox, infra, prod]`. Add equivalent of TOCTOU-stress for scope-enforcement: spawn 10 dispatch attempts with `runner_target="hermes_coder"` + `scope="prod"` against a runner that has only sandbox-cap env (`HERMES_PEER_MAX_SCOPE=sandbox`) → all 10 must `dispatch.fail(reason="scope_above_peer_cap")` with zero LLM calls made. Then verify the same 10 succeed when env is lifted to `prod`.

**Gate**: PR #36 merged OR rebased onto our changes; `dispatch.lease(runner="aider-production", role="coder")` and `dispatch.lease(runner="hermes_coder", role="coder")` both work; M2 scope-enforcement stress test green (10/10 refused in sandbox-cap; 10/10 accepted in prod-cap); 41 historical atlas leases trace-able.

### Step 6 — Persona Coverage + Coupling Audit (1 PD, was 0.5; M3 named)
- Personas already covered by Step 2: Scout + Sentinel.
- **M3 — explicit names**: write YAML for the remaining 4 canonical personas: **Hunter, Trader, Scribe, Ops** at `~/.hermes/specialists/<name>.yaml` with starter `system_prompt + allowed_tools + default_model`. No "+ 1 more" placeholder — these are the exact 4 to close the ADR-025 canonical 6.
- Per-persona work:
  - Verify dispatch_specialist round-trip end-to-end.
  - Document per-persona unique-deps (e.g., Hunter needs `bughunter` CLI installed per ADR-025 §What specialists are NOT; Trader may need market data env vars; Scribe likely doc-generation tool affordances; Ops likely shell + KV access).
- **Explicitly exclude `hermes_coder` from the persona count** — it's a zenbrain coder peer per ADR-030, NOT an ADR-025 persona. The coupling table has 6 persona rows, never 7.

**Gate**: 6-row table specialist | yaml_path | unique_deps | round_trip_test_id | status; all 6 in `VALID_SPECIALISTS` represented (Scout, Hunter, Sentinel, Trader, Scribe, Ops); table footer explicitly notes "hermes_coder is a coder peer, not a persona — see ADR-030".

### Step 7 — All-Persona Q1 + Q2 Validation (1.5 PD, was 4.5 PD with per-specialist 0.5-1.5 days)
Personas are cheap (YAML files), not separate runner builds. Per-persona work:
- 10/10 dispatch_specialist round-trip with real (non-mock) AIAgent response
- result file lands in `/var/lib/design-e/results/`
- `record_event(dispatch_completed)` row appears
- zenbrain `agent_results` row populated via Step 3b polling

Per-persona effort: ~0.25 PD each. Total 1.5 PD for 6 personas (much cheaper than v4 because there are no separate runners to build).

**Gate per persona**: same 4-line acceptance. Final: all 6 personas pass; runners_registry shows ONE active row (`hermes_dispatcher`) carrying all 6 personas.

**Final sub-action — atlas alias removal** (unchanged from v4 Step 7).

### Step 8 — Self-Improve Loop (5 PD; C2 fixed in 8e)
Mostly unchanged from v4. **One material simplification per ADR-025**: Shadow A/B becomes "swap persona YAML, same AIAgent, compare outputs" — much cheaper than the v4 assumption of "swap entire runner." The 8a/8b/8c/8d sub-breakdown from v4 stands.

**Step 8e — Persona YAML auto-apply gate (REVISED per C2)**: auto-apply scope expands to `~/.hermes/specialists/<name>.yaml.proposed/` BUT with **strictly stronger gates than skill markdown drafts** because personas are live AIAgent configuration:

**Promotion `.yaml.proposed/<name>.yaml` → `~/.hermes/specialists/<name>.yaml` requires ALL of**:
1. **Schema validation**: YAML must validate against persona schema (`required: [name, system_prompt, allowed_tools, default_model]`; `allowed_tools` must be subset of hermes-agent registered toolset; `default_model` must be in approved deployments list). Failure → reject + log to audit.
2. **Eval gate (same as 8b/8c)**: `/external-eval` ≥4.0/5 AND `/skill-ab-eval` ≥80% on persona-specific frozen test set.
3. **Diff cap**: the diff vs current live YAML cannot exceed 50% of file size (prevents wholesale replacement). Larger changes require manual approval regardless of eval scores.
4. **Human approval via Teams card** (NOT auto-applied like skill drafts). The Teams card shows the diff + eval scores + sample test outputs from both old + new persona; Zen approves OR rejects. **No auto-promotion of persona YAMLs ever — eval is necessary but not sufficient.**
5. **Atomic deploy**: approved promotion uses `cp .proposed/<name>.yaml .live-staging/<name>.yaml && systemctl reload hermes-consumer && wait 10s && verify-roundtrip && mv .live-staging/<name>.yaml ~/.hermes/specialists/<name>.yaml`. Any failure → rollback to previous YAML from `~/.hermes/specialists/<name>.yaml.bak`.
6. **Shadow-mode burn-in for persona YAMLs**: NEW persona YAML auto-apply is **disabled** until 14 consecutive days of skill-markdown auto-apply have run with zero rollback events. Personas are higher-risk; they get the more conservative gate.

This closes C2 — no silent mutation of live ZenOps behavior. Personas are explicit-human-approval; skill markdown drafts may auto-apply (lower blast radius).

---

## Revised totals v4 → v5

| | v4 | v5 |
|---|---|---|
| Total PD | 20.5 | **16.0** |
| Calendar | ~6 wk | **~5 wk** |
| Specialist model | 6 separate runners | 1 dispatcher + 6 persona YAMLs |
| Hermes role | "specialist to realify" | "host AIAgent (not a specialist)" |
| Write-back path | new endpoint | ADR-025 option (b): file convention + GET poll |
| Result-retrieval HARD BLOCKER | unaddressed | closed (Step 3b implements ADR-025 file convention) |

## Risks accepted (v4 R1-R7 preserved; new v5 risks below)

R8 (NEW): **brain-inbox file-system queue** has no built-in idempotency. If consumer crashes after reading file but before posting `record_event`, the dispatch is silently dropped. Mitigation: consumer writes a `<task_id>.processing` marker before AIAgent invocation, removes on completion; **startup sweep + 5-min periodic sweep detect markers older than 30 min, move to `orphaned/` subdir, re-enqueue task** (m2 expanded). Drill in Step 2 gate.

R9 (NEW): **PR #36 (ADR-030) merge order matters.** If PR #34 (ADR-024 substrate) merges first, runners_registry seed will conflict with PR #36's `hermes_coder` addition. Coordinate via rebase. Per-author sequencing: PR #36 lands → rebase #34 → land #34 → ADR-026 PR.

R10 (NEW): **parallel session 3d226b90 was active as of 07:30 HKT today** (last commit `880cd81 "feat: add clean"` on adr/030-hermes-coder). My git working tree is in `core.bare=true` footgun state. **m1 mitigation**: this is now an explicit Step 0 binary gate (`git config core.bare` must = false; working tree clean on a documented branch); if parallel session is active, use a separate worktree at `$env:TEMP\zenbrain-adr026\`. Either preconditions met or work stops.

---

## Acceptance Criteria (revised)

1. Q1 — each of {Scout, Hunter, Sentinel, Trader, Scribe, Ops} passes 10/10 dispatch_specialist round-trip with non-mock response.
2. Q2 — end-to-end test: zenbrain dispatch → gateway → design-e → consumer → AIAgent → result file → zenbrain poll → agent_results → watcher → downstream task. ALL six personas.
3. Q3 — one full discover→propose→eval→auto-apply cycle autonomously (`.proposed/` only; never overwrites live YAML or live SKILL.md); rollback on eval-fail demonstrated; 7-day shadow ≥3 cycles.
4. ARU-1 quiesce drill executed cleanly once in production-ish env.
5. ADR-024 amendment paragraph live in PR #34 (or follow-on PR).
6. **NEW**: ADR-025 HARD BLOCKER closed — `/var/lib/design-e/results/{task_id}.json` convention implemented end-to-end; zenbrain side can retrieve any dispatched result.

---

## Parked / Out of Scope (unchanged from v4 + 1 new)

- Caddy auth hardening on `z3nops.com/console/` (UI surface).
- adr-centaur-port.md E3→E2 sequencing.
- Talos ≥2-replica production load test.
- `/skill-feedback-agent` integration into Q3 loop.
- PG-backed `skill_proposals`.
- **NEW**: kill `hermes_ask` mock entirely (separate cleanup; not on Q1 path per ADR-025).
- **NEW**: SSE/WebSocket result-retrieval surface (parked alternative to file convention).

---

## Provenance v5 → v6

- v1-v4: Planner + Architect + Critic 4-loop (session 5b017110, 2026-06-07 23:00-23:50). 4.12/5 agentic-eval PASS at v4.
- v5 reconciliation: triggered by morning state check (2026-06-08 07:30) discovering ADR-025 merged to main + ADR-030 PR #36 open from parallel session 3d226b90. v4 had misframed specialists as separate runners; v5 reframes per ADR-025 persona-tuple model.
- **Critic v5** (2026-06-08 07:42, code-review, 78s): reconciliation correctness 5/5 CORRECT-or-PARTIAL; 2 NEW CRITICAL (C1 unbounded poll, C2 silent persona auto-apply); 3 NEW MAJOR (M1/M2/M3); 2 NEW MINOR (m1/m2). NEEDS REVISION.
- **v6 surgical patches** (2026-06-08 07:46, inline in same v5 document): all 7 Critic v5 items resolved. C1 → POLL_TIMEOUT_S + explicit terminal error state. C2 → schema validation + 50% diff cap + human Teams approval + 14-day burn-in gate before any persona YAML auto-apply (effectively NO auto-apply for personas; eval gate is necessary but not sufficient). M1 → explicit Step 0 colocation check. M2 → hermes_coder scope-enforcement stress test in Step 5. M3 → 4 personas named (Hunter, Trader, Scribe, Ops); explicit "hermes_coder is not a persona" footnote. m1 → Step 0 binary git-state gate. m2 → orphaned marker startup-sweep + 30-min TTL.
