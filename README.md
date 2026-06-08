# zenops

## Repository scope

This repo (`zenc-cp/zenops`) is the **ops/governance home** for the ZenOps specialist substrate. It hosts:

- Operational ADRs (e.g., [ADR-025](docs/adr/ADR-025-zenops-specialist-abstraction.md) — ZenOps specialist abstraction; [ADR-031](docs/adr/ADR-031-env-drift-nanoclaw-az.md) — env drift between nanoclaw and Azure).
- Deploy units under [`deploy/zenops-consumer/`](deploy/zenops-consumer/) (e.g., the `zenops-consumer.service` systemd unit).
- S-class deploy plans under [`docs/superpowers/plans/`](docs/superpowers/plans/) (e.g., the 2026-06-08 ADR-025 S10 deploy plan).

The static **AgentArmor** landing site (`agentarmor.html`, `index.html`) is preserved as-is at the repo root and continues to be served from this repo.

### Where other ZenOps code lives

- **Orchestrator and peers source code** lives in [`zenc-cp/zenbrain`](https://github.com/zenc-cp/zenbrain) — *not here*. Zenbrain is the runtime/orchestrator code home; this repo holds only ops, governance, and deploy artifacts.
- **The runtime RPC endpoint** (`design-e.z3nops.com`) lives in [`zenc-cp/design-e`](https://github.com/zenc-cp/design-e). That repo owns the on-the-wire service implementation.

When in doubt: code → `zenbrain`; RPC endpoint → `design-e`; ADRs, plans, and deploy units → here (`zenops`).
