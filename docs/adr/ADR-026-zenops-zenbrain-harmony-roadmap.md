# ADR-026 — ZenOps + Zenbrain Harmony Roadmap (v6, reconciled with ADR-025 + ADR-030)

**Date:** 2026-06-07 (v1-v4); 2026-06-08 07:46 HKT (v5/v6 reconciliation)
**Status:** Proposed
**Author:** Zen Chan (via Clawpilot /ralplan consensus loop, 5 critic passes + 1 reconciliation loop)
**Supersedes:** None
**Amends:** ADR-024 (cross-system lease architecture) — adds `dispatch_tokens` table + HMAC dual-key KV state machine.
**Consumes:** ADR-025 (persona-tuple specialist model — MERGED to main) + ADR-030 (hermes_coder peer — PR #36 open).

---

## v6 supersedes v4 published last night

ADR-026 v4 was rubric-evaluated 4.12/5 PASS at 2026-06-07 23:50 HKT but **misframed specialists as separate runners** — contradicting ADR-025 which merged to main the same evening (persona-tuple model: one Hermes AIAgent inhabits a persona per dispatch; specialists = YAML files in `~/.hermes/specialists/`, not processes).

v5/v6 reconciles ADR-026 with the now-canonical persona-tuple model. The ADR-024 substrate work (dispatch_tokens, ARU-1, HMAC dual-key) is **preserved unchanged** — it's correct for the zenbrain↔design-e boundary regardless of how many specialists exist on the design-e side.

**Read `option-a-v5.md` in this same folder for the full reconciled sequencing.** This file holds the durable decision record; the planning doc holds the work breakdown.

---

## Decision

Pursue **Option A (Depth-First, reframed)**:
- ADR-024 HTTP gateway is the **zenbrain↔design-e BOUNDARY** (one lease per dispatch, not per specialist).
- The 6 canonical ZenOps personas — **Scout, Hunter, Sentinel, Trader, Scribe, Ops** — live as YAML on nanoclaw-az per ADR-025.
- One Hermes-side consumer process drains `/var/lib/design-e/brain-inbox/`, loads the named persona YAML, runs the same Hermes AIAgent class with that persona's prompt + tool restrictions + model, writes the result to `/var/lib/design-e/results/{task_id}.json` (ADR-025 option b), emits `record_event`.
- Zenbrain side polls `GET /rpc/v1/results/{task_id}` with `POLL_TIMEOUT_S` (default 600s); writes to `agent_results`; `watcher` triggers downstream tasks.
- `hermes_coder` (per ADR-030) is a **zenbrain coder peer**, NOT a persona — different dispatch path; calls Foundry AOAI directly via `LLMClient`.

**Calendar**: ~16 PD / ~5 weeks (was 20.5 PD / 6 weeks v4; persona-tuple model is materially cheaper).

---

## Key architectural decisions

1. **One runner, six personas** (not six runners): `runners_registry` gets one row `hermes_dispatcher` (sandbox+infra scopes). Persona names validated against design-e `VALID_SPECIALISTS` set.
2. **File convention over new endpoint** for result write-back: `/var/lib/design-e/results/{task_id}.json` (ADR-025 option b chosen over option a list_events RPC or option c SSE).
3. **dispatch_tokens stays in PG** (NOT KV): the v2 critic discovery (Azure KV has no atomic check-and-delete → TOCTOU race) means tokens live in `pg-atlas-orchestrator.dispatch_tokens` with atomic `UPDATE ... WHERE consumed_at IS NULL RETURNING`. KV retains only the rotating HMAC signing key.
4. **ARU-1 (Atomic Rollback Unit)** = Steps 2/3a/3b/4. Once Step 4 lands, reverting any one of these requires `aru1_quiesce.ps1` drain procedure first. Drain query checks BOTH consumed-but-not-completed AND issued-but-unexpired tokens.
5. **Persona YAML auto-apply is HUMAN-GATED** (v6 C2 fix): unlike skill markdown drafts (auto-apply on eval pass), persona YAML promotion requires schema validation + 50% diff cap + Teams card human approval + 14-day burn-in. Eval is necessary but not sufficient.
6. **HARD BLOCKER from ADR-025 closed** by Step 3b: result-retrieval surface implemented (file convention) → dispatch becomes observable end-to-end, not fire-and-forget.

---

## Risks accepted (R1-R10, fully documented in option-a-v5.md)

R1-R7 carried from v4. R8 (brain-inbox idempotency via .processing marker + startup sweep), R9 (PR #36 merge sequencing), R10 (git footgun + parallel session — now an explicit Step 0 binary gate) added in v5/v6.

---

## Acceptance Criteria

1. Q1 — each of {Scout, Hunter, Sentinel, Trader, Scribe, Ops} passes 10/10 `dispatch_specialist` round-trip with non-mock response.
2. Q2 — end-to-end test: zenbrain dispatch → gateway → design-e → consumer → AIAgent → result file → zenbrain poll → `agent_results` → `watcher` → downstream task. ALL six personas.
3. Q3 — one full discover→propose→eval→apply cycle: skill markdown drafts may auto-apply on eval pass; **persona YAML drafts require human Teams approval**; rollback on eval-fail demonstrated; 7-day shadow ≥3 cycles for skills, 14-day burn-in before personas eligible.
4. ARU-1 quiesce drill executed cleanly once in production-ish env.
5. ADR-024 amendment paragraph live in PR #34 (or follow-on PR).
6. ADR-025 HARD BLOCKER closed: `/var/lib/design-e/results/{task_id}.json` convention implemented end-to-end; zenbrain side can retrieve any dispatched result with bounded timeout (no infinite hangs per C1 fix).

---

## Provenance

- **v1-v4**: Planner + Architect + Critic 4-loop (session 5b017110, 2026-06-07 23:00-23:50); v4 = 4.12/5 agentic-eval PASS.
- **v5 reconciliation**: 2026-06-08 07:30-07:42 HKT, triggered by overnight ADR-025 + ADR-030 work from parallel session 3d226b90.
- **Critic v5**: NEEDS REVISION (2 NEW CRITICAL C1/C2 + 3 MAJOR + 2 MINOR).
- **v6 surgical patches**: 2026-06-08 07:46 HKT, all 7 items resolved inline in `option-a-v5.md`. PROCEED.

---

## Full plan

The complete v5/v6 work breakdown (Steps 0-8 with all gates and rollbacks) lives at:
**`~/.copilot/session-state/5b017110-0954-42f2-85cc-aa0939efd2b7/files/option-a-v5.md`**

This ADR-026 file is the durable decision record. The planning doc is the work breakdown reviewers should read alongside it.

---

## Decision

Pursue **Option A (Depth-First)**: validate the full Q1→Q2→Q3 stack on **Hermes** as a vertical slice before onboarding the other five ZenOps specialists. Roughly 6 weeks / 20.5 PD calendar at 3-4 PD/week solo cadence.

---

## Context and Drivers

**Ultragoal** (captured 2026-06-06, re-anchored 2026-06-07 23:18 HKT):
ZenOps VM enhancement + the agents inside, in harmony with Zenbrain.

**Operational bars** (anchored 2026-06-07 23:18-23:22 HKT):
- **Q1** — each ZenOps specialist returns a REAL non-mock response on a representative test input. Design-E's `hermes_ask` currently returns a hardcoded mock — fails Q1.
- **Q2** — TWO-WAY lease + result feedback. Zenbrain dispatches via ADR-024 gateway (specialists become `eligible_runners`); ZenOps writes results back into zenbrain `agent_results` so zenbrain composes multi-step workflows.
- **Q3** — discover → propose → eval → auto-apply pipeline. Eval IS the gate (no human gate); `/research-scout` + (`/external-eval` AND `/skill-ab-eval`) compose.

**Why now**: ADR-024 substrate just landed as PR #34 tonight (Steps 1-3 complete). Without Steps 4-6 + specialist onboarding, the substrate is dead weight.

---

## Options Considered

Three divergent options went through Planner + Architect + 4 Critic passes.

| | A (depth-first, **chosen**) | B (foundation-first parallel) | C (PG-native, no gateway) |
|---|---|---|---|
| **Approach** | Hermes vertical slice first; other specialists roll out from validated pattern | Harden substrate fully; flood all 6 specialists in one parallel sprint | Skip ADR-024 HTTP gateway entirely; specialists become native zenbrain runners polling PG |
| **Effort** | 20.5 PD / ~6 wk | ~5-6 wk + parallel-resource gamble | 3.5 wk on paper |
| **ADR-024 cohesion** | RECOMMEND — preserves PR #34 | RECOMMEND — preserves PR #34 | CONCERN — requires superseding ADR-024 |
| **Reversibility** | RECOMMEND — each step bail-out point | NEUTRAL — parallel sprint hard to bisect | CONCERN — re-architecting back is expensive |
| **Architect verdict** | **RECOMMEND** | NEUTRAL | NEUTRAL + CONCERN |

**Why A over B**: B delays end-to-end signal until week 3-4. Tonight's session_store data + the Talos lease race show that "build the substrate then connect riders" works only if substrate hardening was actually sufficient — and the only way to know is to put real load through it. A surfaces unknown unknowns earliest.

**Why A over C**: C is plausibly the simplest architecture, but supersedes ADR-024 (a multi-week commitment + amending ADR overhead) and is the least reversible if it turns out Postgres-as-bus has throughput limits zenbrain didn't budget for. The Architect's recommend-against on C is on reversibility, not correctness.

Full planner output and 3 critic transcripts saved in `session-state/5b017110-.../files/option-a-v[2,3,4].md` and read-via `read_agent` on agents `ralplan-{planner-v2,architect,critic[,-v2,-v3,-v4]}`.

---

## Sequencing (Option A v4)

### Step 0 — Pre-flight (1.5 PD)
- **Transport-compatibility check**: confirm each of 6 specialists fits HTTP-JSON (no streaming binary / WebSocket / persistent socket). If any specialist needs non-HTTP transport, **abort and re-plan before Step 3.**
- **Round-trip migration test**: apply ADR-024 PR #34 forward migration to a `pg_dump` copy of `pg-atlas-orchestrator` → checksum schema → apply down-migration → verify checksum matches pre-migration baseline.
- Write + test `aru1_quiesce.ps1` on synthetic 3-task in-flight scenario.
- Populate rollback table (v3 schema: `step | rollback_action | rollback_owner | tested | estimated_time_minutes | ARU_membership`) for all 8 steps.
- Commit ADR-024 amendment paragraph (in PR #34 description) documenting (a) `dispatch_tokens` PG table holds per-task single-use tokens, NOT KV; (b) KV holds rotating HMAC signing key (`current` + optional `previous` for 7-day window); (c) **rotation step 1→3 window bounded to ≤30 min** (Critic v4 note — prevents prolonged mixed-version signing).

**Gate**: all 5 sub-actions green. Transport-compat 6/6 HTTP-JSON. Round-trip checksum diff = 0.

### Step 1 — Talos Lease Race Fix (1 PD)
Patch `src/zenbrain/orchestrator/dispatch.py` `lease()` PG path with `FOR UPDATE SKIP LOCKED`. Add concurrent-lease regression test.

**Gate**: regression test green; stress test (5 PG lease loops, single pending task) → exactly 1 wins.

**Why first** (was step 2 in v1, moved per Critic v1 CRITICAL): correctness bug, not load bug. Any real LLM traffic in subsequent steps that races would otherwise produce duplicate Design-E calls (real cost) and corrupt audit log.

### Step 2 — Hermes Realification (2.5 PD)
Replace hardcoded mock in `design-e` `hermes_ask` with real LLM call. Credentials sourced exclusively from Azure KV via Managed Identity. Handle streaming + non-streaming. Error: 4xx→400 to caller, 5xx→exponential backoff 1 retry max, 60s timeout. Audit log stores prompt_hash + length + token_count, NOT raw prompt.

**Gate**:
- 10/10 consecutive real responses
- `journalctl -u design-e --since "5 min ago"` shows zero auth errors
- **Identity check** (Critic v3 → v4-2): `az role assignment list --assignee <hermes-gateway MI principalId>` returns ONLY `Key Vault Secrets User` scoped to `dispatch-token-hmac-current` (and optionally `-previous` during rotation). No other roles, no other identities.
- `docker image inspect design-e:latest` → no env vars matching `CF_/ENTRA_/HS256/SECRET/TOKEN`; no `/etc/secrets` or `/var/secrets` files
- `psql -c "SELECT column_name FROM information_schema.columns WHERE table_name='audit_log'"` shows NO `raw_prompt` or `raw_response` columns

**Rollback** (becomes part of ARU-1 once Step 4 lands; standalone safe before then).

### Step 3a — Gateway Deploy + Token Issuance (1.5 PD)
Deploy gateway FastAPI on Container App southeastasia with system-assigned MI → KV.

**`dispatch_tokens` table** (NEW per Critic v2 → v4-3):
```sql
CREATE TABLE dispatch_tokens (
  token_hash    TEXT PRIMARY KEY,
  task_id       TEXT NOT NULL REFERENCES agent_tasks(task_id),
  runner_target TEXT REFERENCES runners_registry(name) ON DELETE SET NULL,
  issued_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at    TIMESTAMPTZ NOT NULL,
  consumed_at   TIMESTAMPTZ,
  completed_at  TIMESTAMPTZ
);
CREATE INDEX idx_dispatch_tokens_expires ON dispatch_tokens(expires_at) WHERE consumed_at IS NULL;
```
- INSERT on issuance (always with non-null runner_target).
- Atomic consume: `UPDATE dispatch_tokens SET consumed_at=now() WHERE token_hash=$1 AND consumed_at IS NULL AND expires_at > now() RETURNING task_id`. 0 rows → 410 Gone.
- HMAC signing key from KV (`current` always loaded; `previous` optional). 7-day dual-key window during rotation.

**Gate**:
- End-to-end smoke ≤30s
- **TOCTOU stress test**: 10 concurrent lease attempts on same token → exactly 1 returns 200, 9 return 410 Gone
- **Replay within window**: capture token, submit twice → first 200, second 410
- **Replay after expiry**: capture token, wait 301s, submit → 410
- **Dual-key rotation test**: rotate v1→v2 with in-flight v1 token outstanding → token validates 7 days → new tokens use v2 → after 7 days v1 rejected
- MI→KV: gateway startup log shows "loaded HMAC key from KV"; no env secret
- Restart resilience: kill container → new instance KV-loaded ready ≤60s

### Step 3b — Per-Runner Mailbox + Result Cache (1 PD)
Per-runner mailbox for Hermes. `GET /rpc/v1/results/{task_id}` reads from `agent_results` (or ADR-025 file cache).

**Gate**: mailbox-only test (bypasses Step 4); race test (5 tasks retrievable any order); cache consistency (mailbox-write equals GET-read).

### Step 4 — Two-Way Write-Back Ingress (2 PD) — **ARU-1 sealed after this**
Design-E calls into zenbrain `agent_results` via new ingress endpoint (NOT direct PG write). Validates `lease_token_hash` matches outgoing task.

**Gate**:
- Two-step workflow test goes through **real gateway** (not harness shortcut): `inbox-harness` dispatches Hermes task → gateway leases → Hermes responds → write-back endpoint → `agent_results` row → `watcher` triggers downstream task.
- Failure modes: write-back 5xx → lease retries up to max_retries then audit "result_lost"; lease expires mid-execution → response rejected 410; unknown task_id → 404 no row.
- **ARU-1 quiesce drill**: trigger drain with 2 in-flight tasks → both complete → drain count = 0 → revert hermes_ask to mock → no mock responses written to agent_results.

### Step 5 — Atlas Runner Rename A1 (0.5 PD)
Rename `atlas` → `aider-production` per `adr-centaur-port.md` Phase A1. Back-compat alias kept for 7 days (removal in Step 7 final sub-action).

### Step 6 — Specialist Coupling Audit (0.5 PD)
6-row table: specialist | shared-with-Hermes | unique-deps | estimated PD. Total must be defensible (no flat 0.5 PD blanket).

### Step 7 — Specialist Roll-Out (4.5 PD)
Per-specialist effort from Step 6 audit; conservative defaults: Scribe/Scout/Ops 0.5 PD each (operator pattern), Trader/Hunter 1.5 PD each (market data / scrape complexity). Each clears Step 2 security gates. Per-specialist gate: 10/10 real responses; runners_registry active=1; end-to-end via gateway; lease single-use replay test green.

**Final sub-action — Atlas alias removal**: after all 6 specialists 10/10 green for 7 consecutive days, remove `atlas` from runners_registry + roles.yaml. Pre-cascade audit-log emission preserves history (per Patch v4-3). Owner: Zen (solo); monitored via daily nightly-reflection automation.

### Step 8 — Self-Improve Loop (5 PD)
**Sub-breakdown** (per Critic v5 / agentic-eval feedback; each sub-row independently testable):
- **8a Discover quarantine + proposal buffer** (0.5 PD): `/research-scout` writes to `~/.copilot/m-skills/<skill>/.proposed/<utc-ts>.md`. SQLite `skill_proposals(id, source, content_hash, status, eval_result, applied_at)` append-only. Gate: scout writes don't escape `.proposed/`; SQLite WAL mode; ≥1 proposal lands cleanly.
- **8b `/external-eval` integration** (1.5 PD): wire Azure OpenAI gpt-5 grading against frozen rubric. Gate: 5 known-good proposals score ≥4.0/5; 5 known-bad score <3.0/5; eval call latency p95 ≤30s; cost per eval ≤$0.05.
- **8c `/skill-ab-eval` frozen test-set** (1.5 PD): functional A/B harness with pass-rate ≥80% threshold. Freeze the test set in `tests/skill_eval_frozen/` — eval CANNOT modify it (CI guard via git pre-commit hook). Gate: 5 known-good proposals pass ≥80%; 5 known-bad fail <50%; self-modification block test green.
- **8d Shadow-mode wiring + 7-day burn-in** (1.5 PD): pipeline runs end-to-end with apply step replaced by Teams notification only. Auto-apply config flag `SELF_IMPROVE_ENABLED=false`. Gate: ≥3 successful end-to-end eval cycles during shadow (route to Teams card, not file write); zero false-positive apply attempts; rollback test (synthetic eval-fail mock returns 2.0/5 → no file written + audit "eval_rejected").

**4 trust boundaries** (cross-cutting all sub-rows):
1. **Discover** — quarantined `.proposed/` dir; never auto-loaded into live skill registry.
2. **Proposal buffer** — append-only SQLite; status transitions only.
3. **Eval gate** — `/external-eval` (≥4.0/5) AND `/skill-ab-eval` (≥80%) BOTH required. Frozen test set; eval cannot modify own gate.
4. **Auto-apply** — `.proposed/` writes ONLY. **NEVER** to live `SKILL.md`. Promotion to live = manual Zen Teams card approval.

**Out of scope** (parked): PG-backed proposals table (only needed if pipeline ever multi-host); `/skill-feedback-agent` integration (defer until Q3 base works).

---

## Consequences

**Positive**:
- Q1 Hermes met week 1-2; Q1 all 6 met week 4-5; Q2 all met week 5; Q3 live week 7-8.
- ADR-024 substrate (PR #34) validated through real load before being extended.
- All architectural decisions documented with concrete gates and rollback procedures.
- Single architect (Zen) can execute solo — no parallel-resource assumption.

**Negative / Trade-offs**:
- Other 5 specialists stay mocked for ~4 weeks (asymmetric integration window).
- 0.5 PD/specialist roll-out estimate may understate Trader/Hunter (Step 6 audit catches this before execution).
- Q3 loop has 5 PD of net-new code (4 sub-systems) — most architectural risk concentrated in Step 8.
- 7-day shadow extends calendar but is non-negotiable for autonomous-apply safety.

**Risks Accepted** (no further mitigation tonight):
- **R1**: `aru1_quiesce.ps1` tested only on synthetic in-flight tasks in Step 0; first production drain may surface edge cases. Mitigation: conservative 20-min drain timer vs 5-min lease window.
- **R2**: HMAC dual-key 7-day rotation is one-shot in test; real 90-day rotation is first production exercise.
- **R3**: Step 0 transport-compat check catches obvious cases; subtle Trader/Hunter coupling at Step 6 may still trigger re-plan (~1 week sunk gateway cost).
- **R4**: SQLite skill_proposals single-host limit — parked.
- **R5**: Calendar +1-2 week realistic (PR review, Container App, Design-E provider variance).
- **R6**: ADR-024 amendment is ~½ page, not a sentence. Acceptable.
- **R7** (Critic v4 note): rotation step 1→3 gap must be bounded ≤30 min to avoid prolonged mixed-version signing. Documented in ADR rotation procedure; operationally enforced via runbook timer.

---

## Acceptance Criteria

The roadmap is "complete" when ALL of the following are true:
1. Q1 — each of {Hermes, Scribe, Trader, Hunter, Scout, Ops} passes 10/10 real-response gate.
2. Q2 — end-to-end test passes: zenbrain dispatch → gateway → specialist → write-back → `agent_results` → next-step trigger, ALL six specialists.
3. Q3 — one full discover→propose→eval→auto-apply cycle completes autonomously (proposals in `.proposed/`, never overwrites live SKILL.md); rollback on eval-fail demonstrated; 7-day shadow observed ≥3 cycles.
4. ARU-1 quiesce drill executed cleanly at least once in production-ish environment.
5. ADR-024 amendment paragraph live in PR #34 (or follow-on PR if #34 already merged).

---

## Parked / Out of Scope

- Caddy HTTP Basic Auth hardening on `z3nops.com/console/` (UI surface, separate concern).
- `adr-centaur-port.md` E3→E2 sequencing (Phase A1 only covered in Step 5).
- Talos ≥2-replica production load test (recommended after Step 1, not gating).
- `/skill-feedback-agent` integration into Q3 loop (defer until base Q3 works).
- PG-backed `skill_proposals` (only needed if Q3 pipeline multi-host).

---

## Provenance

- **Planner**: `ralplan-planner-v2` (Sonnet 4.6, 126s) — 3 divergent options.
- **Architect**: `ralplan-architect` (Sonnet 4.6, 42s) — recommended A.
- **Critic v1**: `ralplan-critic` (code-review, Sonnet 4.6, 69s) — 4 CRITICAL + 5 MAJOR; NEEDS REVISION.
- **Critic v2**: `ralplan-critic-v2` (code-review, 59s) — all v1 resolved/partial; 2 NEW CRITICAL + 4 NEW MAJOR; NEEDS REVISION.
- **Critic v3**: `ralplan-critic-v3` (code-review, 141s) — v2 NC-1/NC-2 resolved; 1 NEW CRITICAL (NC-A drain query) + 2 NEW MAJOR; NEEDS REVISION.
- **Critic v4**: `ralplan-critic-v4` (code-review, 17s) — all v3 resolved; **PROCEED**. One ADR-note observation (rotation 1→3 bound), folded into R7.
- **Agentic-eval pass**: `adr026-eval` (Sonnet 4.6, 59s) — 4.12/5 PASS against 10-dim weighted rubric. Strongest: Coherence 5/5 + Exit criteria 5/5. One mechanical improvement applied (Step 8 sub-breakdown 8a/8b/8c/8d for time-realism falsifiability).

5 loops used of 5 allowed. Total sub-agent time: ~7.5 min. Token spend: estimated $0.40-0.60 across all sub-agent calls.

---

## Status transitions

- Proposed (now)
- Accepted (when Zen merges to `zenbrain` repo + opens execution issues for Steps 0-8)
- In-Progress (when Step 0 starts)
- Implemented (when all 5 acceptance criteria met)
- Superseded (only if a future ADR replaces this roadmap)
