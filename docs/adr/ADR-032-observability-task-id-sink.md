# ADR-032: Single task_id observability sink across the dispatch fabric

**Status:** Proposed
**Date:** 2026-06-11
**Deciders:** Zen (session bbe7c703)
**References:** ADR-025 (specialist dispatch), audit-improve-grade sweep 2026-06-10 (F7), zenops#6

## The rule (single sentence, quotable)

> **Every hop that processes a `task_id` MUST emit its lifecycle events to one shared SQLite sink at `/var/lib/design-e/observability.sqlite`, indexed by `task_id`, so an operator can run `SELECT * WHERE task_id = ?` once and see the full trace.**

---

## Context

Audit finding F7 (audit-adr025-e2e, 2026-06-10) showed that `task_id` propagates correctly through the dispatch fabric but observability is siloed across three stores:

| Hop | Sink | Tool to read |
|---|---|---|
| `design-e` ingress / RPC | JSONL files at `AUDIT_LOG_PATH` | `jq` over files |
| `hermes-agent` consumer | stderr (systemd journal) | `journalctl -u zenops-consumer` |
| `zenbrain` orchestrator | `agent_results` PG table | `psql` |

Triaging a single dispatch requires three different tools, three different auth surfaces, and manual join-by-`task_id`. ADR-025's "cross-visibility" promise is partially met (the ID propagates), but the **query plane** does not exist.

## Decision

Adopt a **shared SQLite sink** at `/var/lib/design-e/observability.sqlite` with a single append-only table:

```sql
CREATE TABLE task_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id     TEXT    NOT NULL,
  hop         TEXT    NOT NULL,   -- 'design-e' | 'consumer' | 'zenbrain'
  event       TEXT    NOT NULL,   -- 'dispatched' | 'leased' | 'heartbeat' | 'completed' | 'failed' | 'expired' | 'reaped'
  timestamp   TEXT    NOT NULL,   -- ISO8601 UTC
  payload     TEXT,               -- optional JSON blob
  CHECK (length(task_id) BETWEEN 1 AND 128)
);
CREATE INDEX idx_task_events_task_id ON task_events(task_id);
CREATE INDEX idx_task_events_ts ON task_events(timestamp);
```

### Scope (what's in)

- `design-e` (FastAPI, runs as `azureuser` on nanoclaw-az): emit `dispatched`, `result_read` events.
- `hermes-agent` consumer (runs as `azureuser`): emit `leased`, `heartbeat`, `completed`, `failed`, `expired`, `reaped`.

### Scope (what's out)

- `zenbrain` orchestrator stays on PG (`agent_results`). It's a separate process tree, often runs off-VM (laptop / atlas-runner), and its own table already satisfies its operator's query needs. Cross-joining zenbrain + the SQLite sink is a **manual** operator task — that's the 80% close mentioned in the F7 finding, and accepting the residual 20% is what makes this a small change instead of a platform rebuild.

### Why SQLite, not Application Insights / Loki

- Both design-e and the consumer already run on the same VM with the same filesystem. SQLite needs **zero new infra**.
- Append-only `INSERT` with one writer process per hop and `journal_mode=WAL` handles the contention pattern fine (low write rate, single-digit TPS even under burst).
- An operator can `scp` the file off and inspect locally; no auth dance.
- AI / Loki are correct answers when the dispatch fabric grows past one VM. This ADR explicitly defers that.

## Implementation sketch

1. New module `design_e/observability.py` exposing `emit(task_id, hop, event, payload=None)` that opens the SQLite file with `journal_mode=WAL`, inserts the row, closes.
2. `design_e_endpoint.py` calls `emit(task_id, "design-e", "dispatched", ...)` inside `dispatch_specialist` after the inbox write, and `emit(task_id, "design-e", "result_read", ...)` inside the `/results/{task_id}` handler on 200.
3. `agent/specialists/consumer.py` calls `emit(...)` at the same 6 terminal branches that already call `_write_status_atomic` (success / malformed / persona-not-found / agent-error / TTL-expired / reaper-abandoned), plus one `leased` emission at lease-acquire time and one `heartbeat` emission per `extend_lease` tick (rate-limited to once per 30s to keep the table small).
4. A tiny CLI: `python -m design_e.observability tail <task_id>` that prints the joined timeline. Optional `--watch` flag.

Path is owned by the design-e systemd unit (`ReadWritePaths=/var/lib/design-e`), already covered by the existing service config; the consumer needs the same path added to its `ReadWritePaths` override.

## Alternatives considered

- **A. OpenTelemetry + collector**: correct long-term answer but requires a collector process, a backend, and SDK adoption in three repos. Too heavy for one VM.
- **B. Per-hop JSONL files, scanned together**: file-per-hop avoids contention but reintroduces the multi-tool problem this ADR exists to close.
- **C. Reuse the `agent_results` PG table for all three hops**: requires opening PG access from design-e + consumer (currently they don't have a PG client), and PG is off-box (Azure Flexible Server, auto-stops to save cost — see memory). Higher operational burden.

## Acceptance criteria

For this ADR to be considered SHIPPED:

1. [ ] `design_e/observability.py` exists with `emit()` and the `tail` CLI.
2. [ ] design-e + consumer write to `/var/lib/design-e/observability.sqlite` at the events listed in §Implementation sketch.
3. [ ] Integration test: dispatch a task with `ttl_sec=1`; after 60s the SQLite file shows `dispatched -> leased -> expired -> reaped` for that `task_id`.
4. [ ] `python -m design_e.observability tail <task_id>` returns a non-empty timeline for any task dispatched within the last 24h.
5. [ ] zenops#6 closed citing this ADR + the implementation PR.

## Residual risk

- **SQLite write contention** if dispatch rate goes >50 TPS. Mitigation: monitor the WAL file size; if `wal` >32MB sustained, that's the signal to graduate to option A (OTel).
- **Disk pressure** on `/var/lib/design-e`. Mitigation: cron job to delete rows older than 30 days (`DELETE FROM task_events WHERE timestamp < datetime('now', '-30 days')` + `VACUUM`). Keep recent traffic, drop the old tail.
- **Schema evolution** locked in by the CHECK + indexes. Mitigation: any new column gets a new migration file under `design-e/migrations/` (matches the design-e convention already in use for the results-directory layout).
