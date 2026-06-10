# ADR-025: ZenOps specialists are personas of one Hermes, not separate processes

**Status:** Accepted
**Date:** 2026-06-07
**Deciders:** Zen (session da5d6a86-3a69-401b-a8ba-a7b1f4a0b111)
**References:** Plan 1 (`docs/superpowers/plans/2026-06-06-zenops-rl-loop.md`), `~/.copilot/session-state/da5d6a86-.../files/zenops-shadow-ab-design.md`, `design_e_endpoint.py:49`, `~/hermes-agent/AGENTS.md` (laptop checkout — per ADR-031 the VM path was wrong)

### Acceptance criteria (Proposed → Accepted)

This ADR moves from `Proposed` to `Accepted` when ALL of:
1. Zen explicitly approves in chat or via PR review comment (the decider per the line above).
2. The ADR file is merged to `origin/main` of `zenc-cp/zenbrain` (this constitutes the durable decision record).
3. No prior accepted ADR is left logically contradicted without a follow-up amendment ADR (currently none — verified against ADR-005, 013, 021, 022 in the dependency section below).

The `Status:` field at the top of the file is updated to `Accepted` in the same PR that lands the file (one-commit acceptance). Demotion to `Superseded` requires a new ADR that explicitly cites and replaces ADR-025.

## The rule (single sentence, quotable)

> **A ZenOps "specialist" is a named persona — a `{name, system_prompt, allowed_tools, default_model}` tuple — that the single Hermes AIAgent inhabits per dispatch, not a separate process, container, or repository.**

This binds the existing `VALID_SPECIALISTS = {"Scout", "Hunter", "Sentinel", "Trader", "Scribe", "Ops"}` allow-list in `design_e_endpoint.py` to a concrete implementation contract, closing the abstraction gap discovered in session da5d6a86.

## Context

### What we found

Session da5d6a86 spent ~7 hours designing a Shadow A/B self-improvement harness for "the Hunter specialist." Three discoveries collapsed that framing:

1. **`bughunter/` on nanoclaw-az is a Claude security-research CLI** (51-skill bundle, `cbh.py` entrypoint), not an agent. It is operator-driven, not LLM-driven.
2. **`hermes-agent` is one AIAgent class** (`run_agent.py`, ~12k LOC, ReAct loop with tool calls), not a router-to-specialists.
3. **`design_e_endpoint.py` defines `VALID_SPECIALISTS`** as a string allow-list, and `dispatch_specialist` writes a JSON file to `/var/lib/design-e/brain-inbox/` — **but nothing reads that directory.** The bus has a writer with no consumer.

The three artifacts named "hunter" / "Hunter" / "bughunter" were independent things conflated by the plan. The plan assumed a multi-process specialist topology that does not exist.

### Why the gap matters

Without this ADR, every future plan touching "specialists" reproduces the same vapor:
- Plans get written against an imagined multi-agent topology.
- Implementation work either builds the wrong abstraction (heavy multi-process dispatcher) or builds something the abstraction can't host (Shadow A/B harness for a non-existent agent).
- Cross-visibility primitives like `record_event` get designed for traffic that never materializes.

The existing `VALID_SPECIALISTS` allow-list creates a false promise: callers see "Hunter" in the API and assume a Hunter agent exists.

### What's actually deployed

| Layer | Reality |
|---|---|
| `design_e_endpoint.py` | Validates specialist name, writes JSON to brain-inbox, returns 202 |
| `/var/lib/design-e/brain-inbox/` | Empty directory; no daemon polls it |
| `hermes-agent` | One AIAgent with ~80 registered tools, one default model (post 924ab6e routing fix), one persona prompt in `~/.hermes/config.yaml` |
| Hermes-side specialist dispatcher | Does not exist |
| Per-specialist code modules | Do not exist |

## Decision

We adopt the **persona-tuple** definition of a specialist:

```yaml
# Each specialist is a tuple stored in ~/.hermes/specialists/<name>.yaml
name: Hunter
system_prompt: |
  You are Hunter, ZenOps' security-research specialist. Investigate the
  given target (wallet address, contract, suspicious tx). Use bughunter
  CLI tools via the shell tool. Output structured findings.
allowed_tools: [shell, web_search, web_fetch, file_read]
default_model: gpt-5-chat
output_schema:
  type: object
  required: [findings, confidence, evidence]
  properties:
    findings: {type: array, items: {type: string}}
    confidence: {type: number, minimum: 0, maximum: 1}
    evidence: {type: array, items: {type: string}}
```

When `design-e dispatch_specialist(name="Hunter", task={...})` is called, a thin Hermes-side consumer:

1. Drains the next JSON file from `/var/lib/design-e/brain-inbox/`.
2. Loads `~/.hermes/specialists/Hunter.yaml`.
3. Invokes the **same** `AIAgent` instance with the loaded `system_prompt`, restricted to `allowed_tools`, against the configured `default_model`.
4. Captures the agent's structured output and writes it back via `record_event(event_type="dispatch_completed", task_id=..., details={output, latency_ms, tool_calls})`.

### What specialists are NOT

- **NOT separate processes.** No per-specialist daemon, container, or worker pool.
- **NOT separate repositories.** Specialists live as YAML files in one directory.
- **NOT separate model deployments.** Default to the one Hermes model; per-specialist override only when measured-better.
- **NOT MCP servers.** Specialists are personas, not protocols.
- **NOT tool definitions.** Tools are the things specialists *use*; specialists are *configurations of one agent*.

### Naming

The canonical 6-specialist taxonomy is **`Scout, Hunter, Sentinel, Trader, Scribe, Ops`** — verified by Zen 2026-06-07 against the deployed `VALID_SPECIALISTS` set in `design_e_endpoint.py:49` on nanoclaw-az.

> **Drift to reconcile in follow-up amendments to prior ADRs:** ADR-020 (naming-helm-deck-crew) line 92 and ADR-021 (mas-scaling-heuristic) lines 18, 37, 61, 97 currently list `Post` as the 6th specialist. The deployed code uses `Scribe`. The canonical name is `Scribe`; ADR-020 and ADR-021 need a one-line amendment ADR (or in-place patch with a `# Amended 2026-06-07` annotation) replacing every `Post` mention with `Scribe`. This ADR (024) does not perform that reconciliation; it relies on the deployed code as ground truth.

Adding a seventh specialist requires a follow-up ADR per ADR-021 (MAS scaling heuristic).

## Rationale

### Why persona-tuple over multi-process

| Dimension | Multi-process specialists | Persona-tuple (this ADR) |
|---|---|---|
| Implementation cost | Per-specialist module, per-specialist deployment, dispatcher daemon, queue plumbing | One thin consumer + N YAML files |
| Failure surface | N processes can crash independently | One AIAgent failure mode |
| Shadow A/B target | Hard — each specialist is its own moving target | Easy — swap the YAML, same agent |
| Self-improvement loop | Per-specialist trajectory log, per-specialist judge | One trajectory log keyed by `specialist` field |
| Cross-visibility | N writers to bus, N readers needed | One writer, one reader |
| Hermes-side change | Major refactor | Add ~100 lines (consumer + YAML loader) |
| Matches deployed reality | No | Yes |

### Why this is true even if it sounds reductive

Real multi-agent systems built today (AutoGen, CrewAI, LangGraph subgraphs) implement "specialists" exactly this way under the hood: one model, swapped system prompts, restricted tool sets per role. The marketing language ("multi-agent") obscures the implementation pattern (persona dispatch).

`design-e`'s `dispatch_specialist` API shape — `{specialist: str, task: object, context: object}` — is already isomorphic to "load persona named X, run it on task." It doesn't need any other semantics.

### Why now

Three signals converged in session da5d6a86:
1. Plan 1's transport assumption was rejected by ground truth (no `rotate_and_fetch_trajectories` server exists).
2. The plan's *target* was rejected by ground truth (no Hunter agent exists).
3. The plan's *bus* has a writer with no reader (no specialist consumer exists).

All three failures share one root cause: **no decision on what a specialist is.** Without this ADR, the next plan reproduces the same three failures.

## Consequences

### Positive

- Plan 1 can be rewritten in <500 lines (was 95KB). Shadow A/B becomes "swap persona YAMLs and compare outputs," not "build a custom MCP transport."
- The `record_event` bus has a clear shape: dispatch produces `dispatch_created` + `dispatch_completed` events with `details.specialist` discriminator.
- Cross-visibility (Zenbrain ↔ ZenOps) is a single query: `SELECT * FROM audit_logs WHERE event_type = 'dispatch_completed' AND ts > ?`.
- New specialists are added by writing one YAML file. No new code, no new deployment.

### Negative

- Per-specialist Python implementations (if ever wanted, e.g. for a specialist that needs custom Python before/after the LLM call) require revisiting this ADR.
- "Specialist" terminology may mislead readers expecting separate processes. Mitigation: this ADR is linked from `design_e_endpoint.py` and from any README that uses the word.
- Multi-tenant isolation between specialists is conversation-level only (Hermes session ID). No process-level boundary. Acceptable for current single-operator (Zen) deployment.

### Neutral

- The existing `bughunter/` CLI continues to exist and continues to be operator-driven. The `Hunter` specialist *uses* `bughunter` via the shell tool, but they are not the same artifact.

## Operational dependency on related ADRs

- **ADR-005** (peer-collision lease primitives) — unaffected. Lease semantics apply to Hermes invocations as a whole, not per-specialist.
- **ADR-013** (paperclip pivot) — unaffected.
- **ADR-021** (MAS scaling heuristic) — applies: adding a 7th specialist requires the scaling argument named in ADR-021 before the YAML is added.
- **ADR-022** (research-scout SKIP/DEFER) — unaffected; that ADR is about research-scout's own routing logic, not specialists.

## Verification preconditions (verified 2026-06-07 against the laptop checkout + `zenc-cp/hermes-agent@main`)

> **2026-06-08 correction (ADR-031):** The original heading said "verified against `/home/slimslimchan/hermes-agent` on nanoclaw-az". That qualifier is incorrect — `slimslimchan` is the author's Google account, not a Linux user on the VM, and no `hermes-agent` checkout existed on the VM at the time of writing. The file paths + line numbers below are verified against the laptop clone at `C:\Users\szelimchan\AppData\Local\hermes\hermes-agent\` and confirmed present in `zenc-cp/hermes-agent@main` (commits f9dae81f9 and prior). The persona-tuple decision in this ADR is unaffected.

This ADR's persona-tuple shape depends on three concrete Hermes mechanisms. All three were verified before this ADR moved past draft:

| Mechanism the ADR commits to | Verified hook in hermes-agent code |
|---|---|
| Per-dispatch tool restriction (`allowed_tools` in YAML) | `model_tools.py:339` exposes `enabled_toolsets` per-agent — the YAML's `allowed_tools` maps to this parameter at AIAgent construction. |
| Per-dispatch model selection (`default_model` in YAML) | `run_agent.py:651` provides `AIAgent.switch_model(new_model, new_provider, api_key, base_url, api_mode)` — model can be set per dispatch. |
| Concurrent dispatches → no shared-state races | `gateway/platforms/api_server.py:998`, `gateway/stream_consumer.py:85`, `gateway/run.py:8695/11925/12400/16902`, `gateway/platforms/feishu_comment.py:1074` — `AIAgent(...)` is instantiated **per request**, never as a singleton. |

These verifications removed three concerns from a critic review of the draft (one-Hermes-bottleneck, allowed_tools enforcement, per-call model override) by showing the deployed code already supports the pattern.

## Open questions (intentionally not resolved here)

These get their own follow-up ADRs only if and when the work demands them:

1. **Inter-specialist handoff:** can Scout dispatch to Hunter as part of its task? (Likely answer: yes via shell tool calling design-e RPC; no special primitive needed.)

## Resolved during preflight (no follow-up ADR needed)

1. **Concurrency:** what happens when two `dispatch_specialist` calls arrive concurrently? **Resolved**: each dispatch instantiates its own `AIAgent` via the gateway's per-request construction pattern (verified at `gateway/platforms/api_server.py:998` and 5 other call sites). No shared-state race at the agent level. Tool-level concurrency (file system, AOAI rate limits) is the consumer's responsibility.
2. **Per-specialist memory:** should each specialist have its own context window or share Hermes's session memory? **Resolved**: per-dispatch fresh session. Same evidence as concurrency — per-request `AIAgent` means no carried context across dispatches. Specialists don't accrue independent persistent state inside the agent; persistence (if needed) goes through `record_event` or external storage.

## Blocking prerequisite for implementation — RESOLVED 2026-06-10

> **Status: RESOLVED.** The result-retrieval surface flagged as a HARD BLOCKER in v1 of this ADR shipped via option (b) — the status-file convention. Verified by audit-adr025-e2e on 2026-06-10.

Resolution evidence:

- **Writer**: `consumer.py` defines `_write_status_atomic(results_dir, task_id, payload)` (search the file; the function is called from every terminal-outcome branch — malformed JSON, TTL expired, persona load failure, invoke_agent failure, happy-path completion, and the reaper's abandoned path). All paths atomically write `/var/lib/design-e/results/{task_id}.json` from the hermes-agent consumer. (Line numbers omitted intentionally — they drift with every refactor; use grep for `_write_status_atomic` instead.)
- **Reader**: `design_e_endpoint.py` `GET /rpc/v1/results/{task_id}` route — JWT validation, regex path-traversal defense (`^[A-Za-z0-9_\-]{1,128}$`), `is_relative_to()` belt-and-suspenders, 404 on missing.
- **Round-trip test**: `tests/test_results_rpc.py` covers happy path, 404, 401, path traversal, length cap, and UUID format (7 tests, all green).
- **Audit verdict**: "Is the ADR-025 HARD BLOCKER (result-retrieval reader) still open? **NO**. The round-trip is complete, tested, and deployed."

The follow-up audit (also 2026-06-10) surfaced **separate** gaps that are NOT this ADR's blocker but are tracked separately:

- **F2** — Lease-expiry / reaper missing in consumer. A dead consumer ghosts the task: inbox file is deleted in `finally` regardless of completion, no lease expiry surface, no retry. Tracked in design-e issues + hermes-agent issues.
- **F3** — `record_event` writer exists with no reader. Audit-log files are write-only. A `GET /rpc/v1/events?task_id=X` reader was added on 2026-06-10 as the canonical reader path. Tracked in design-e.

These are not blockers for ADR-025 (the dispatch round-trip works), but they are blockers for production reliability and observability. See follow-up issues.

### Historical context (original v1 blocker text, kept for archaeology)

The original v1 text said: "Implementation of this ADR cannot ship until a result-retrieval surface exists." That constraint is now satisfied by option (b) from the v1 alternatives list (status-file convention at `/var/lib/design-e/results/{task_id}.json`). The other two alternatives (`list_events` RPC and SSE/WebSocket) were not pursued — option (b) was simpler and sufficient.

## Implementation pointer (informative, not normative)

The minimum work to make this ADR real:

1. Create `/home/azureuser/.hermes/specialists/{Scout,Hunter,Sentinel,Trader,Scribe,Ops}.yaml` with starter prompts. *(was `/home/slimslimchan/...` — corrected per ADR-031: VM Linux user is `azureuser`)*
2. Add a Hermes-side consumer (~80 lines) that polls `/var/lib/design-e/brain-inbox/`, loads the named YAML, runs Hermes with that persona, posts back via `record_event`.
3. Add an integration test that round-trips: design-e dispatch → consumer → Hermes → record_event → query audit log.

This work is NOT in scope of this ADR. The ADR's job is to fix the abstraction. Implementation lives in its own plan, written after this is accepted.
