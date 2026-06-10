# RUNBOOK — git-harden `/home/slimslimchan/claw/` on nanoclaw-az

Tracks: [zenc-cp/zenops#1](https://github.com/zenc-cp/zenops/issues/1)

`/home/slimslimchan/claw/` on nanoclaw-az hosts production-critical files —
most importantly `mcp-server.py`, which fronts ~25 high-blast-radius ZenOps
MCP tools. Today the directory is **not** a tracked git repo: every edit is
silent, with no audit trail. A recent leaked transcript fragment shows an
agent attempting to inject `return True` into `_check_auth()` — which would
have disabled bearer auth on the public MCP endpoint. The bypass was not
applied, but the risk is real.

This runbook walks the operator (Zen) through the VM-side steps. All
**code-side** artifacts (the four scripts, the systemd unit + timer, and the
pytest suite) ship from this repo under `deploy/`.

---

## Pre-flight (one-time, off-VM)

Pick a **private** GitHub repo to host the claw runtime mirror. The remote URL
will be plugged in as `<TODO-set-remote>` below.

Confirm baseline auth state on the VM matches the issue:

```bash
ssh nanoclaw-az
sha256sum /home/slimslimchan/claw/mcp-server.py
# expect: 59778371c8be736ca92c317345cde8cacce25415f271f2cc9f0768e3e4833f47
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:<PORT>/<TOOL>
# expect: 401
```

---

## Step 1 — bootstrap the repo

Maps to acceptance criterion **"`git log` in `/home/slimslimchan/claw` returns
at least one commit"**.

```bash
sudo -u slimslimchan bash /path/to/zenops/deploy/claw-runtime-git-init.sh
```

What this does:

- `git init -b main` if `.git/` doesn't already exist
- Writes a sane `.gitignore` (pyc, `__pycache__`, `.venv`, `.env`, `*.log`,
  `tmp/`, `output/`, …)
- Creates the initial commit if the repo has no commits yet
- Idempotent — safe to re-run

The script intentionally does **not** set a remote; you pick the private repo:

```bash
sudo -u slimslimchan git -C /home/slimslimchan/claw remote add origin <TODO-set-remote>
sudo -u slimslimchan git -C /home/slimslimchan/claw push -u origin main
```

---

## Step 2 — install the pre-commit hook (auth-bypass guard)

Maps to **"future `_check_auth` bypass attempts are visible before they land"**.

```bash
sudo -u slimslimchan cp /path/to/zenops/deploy/claw-runtime-pre-commit-hook.sh \
  /home/slimslimchan/claw/.git/hooks/pre-commit
sudo -u slimslimchan chmod +x /home/slimslimchan/claw/.git/hooks/pre-commit
```

Behaviour:

- Inspects the staged diff for `mcp-server.py`
- Flags any change inside `_check_auth` whose first executable statement is
  `return True`, `return 1`, or a bare `pass`
- Prints the offending hunk and a WARN banner — **advisory only** in this
  initial roll-out (exits 0 so a legitimate commit isn't blocked)
- To upgrade to **blocking** later, edit the hook and flip the `exit 0` below
  the `UPGRADE-TO-BLOCKING` marker to `exit 1`

---

## Step 3 — install the drift watchdog (systemd timer)

Maps to **"timer alerts on a tree that has been dirty too long"**.

```bash
sudo install -d -o slimslimchan -g slimslimchan -m 0755 /opt/claw-runtime
sudo install -o slimslimchan -g slimslimchan -m 0755 \
  /path/to/zenops/deploy/claw-runtime-drift-check.sh \
  /opt/claw-runtime/claw-runtime-drift-check.sh
sudo install -o root -g root -m 0644 \
  /path/to/zenops/deploy/claw-runtime-drift-check.service \
  /etc/systemd/system/claw-runtime-drift-check.service
sudo install -o root -g root -m 0644 \
  /path/to/zenops/deploy/claw-runtime-drift-check.timer \
  /etc/systemd/system/claw-runtime-drift-check.timer
sudo systemctl daemon-reload
sudo systemctl enable --now claw-runtime-drift-check.timer
```

Confirm:

```bash
systemctl list-timers claw-runtime-drift-check.timer --no-pager
# expect: next run within ~5 min
journalctl -u claw-runtime-drift-check.service --since '15 min ago'
# expect: silent (clean tree) on first runs
```

Tunables (override in `/etc/systemd/system/claw-runtime-drift-check.service.d/override.conf`
via `Environment=`):

| Variable             | Default | Meaning                                            |
| -------------------- | ------- | -------------------------------------------------- |
| `DRIFT_MAX_MINUTES`  | `15`    | Grace window before a dirty tree is alarmed        |
| `CLAW_DIR`           | `/home/slimslimchan/claw` | Path to the tracked claw runtime |

---

## Step 4 — smoke test (edit + revert)

Maps to **"edit/revert cycle works"** and **"timer alerts on dirty tree"**.

```bash
sudo -u slimslimchan -- bash -c '
  cd /home/slimslimchan/claw
  echo "# smoke" >> mcp-server.py
  git status --porcelain          # expect: " M mcp-server.py"
  git diff -- mcp-server.py | head
  git checkout -- mcp-server.py   # revert
  git status --porcelain          # expect: empty
'
sha256sum /home/slimslimchan/claw/mcp-server.py
# expect: 59778371c8be736ca92c317345cde8cacce25415f271f2cc9f0768e3e4833f47
```

To verify the drift alarm fires, leave a dirty file in place for >15 min (or
temporarily set `DRIFT_MAX_MINUTES=0`):

```bash
sudo -u slimslimchan -- bash -c 'echo "# drift" >> /home/slimslimchan/claw/mcp-server.py'
sudo DRIFT_MAX_MINUTES=0 \
  /opt/claw-runtime/claw-runtime-drift-check.sh
# expect: exit 2, "DRIFT ALARM …" with mcp-server.py listed
sudo -u slimslimchan -- bash -c 'git -C /home/slimslimchan/claw checkout -- mcp-server.py'
```

---

## Step 5 — exercise the pre-commit guard

```bash
sudo -u slimslimchan -- bash -c '
  cd /home/slimslimchan/claw
  cp mcp-server.py /tmp/mcp-server.py.bak
  # surgical insert: turn _check_auth into a no-op
  sed -i "/^def _check_auth/a\\    return True" mcp-server.py
  git add mcp-server.py
  git commit -m "test: should warn"   # expect: WARN banner, commit still proceeds
  git reset --soft HEAD~1
  git checkout -- mcp-server.py
'
```

---

## Acceptance-criteria mapping

| Issue criterion                                            | Step  | Artifact                                              |
| ---------------------------------------------------------- | ----- | ----------------------------------------------------- |
| `git log` returns at least one commit                       | 1     | `deploy/claw-runtime-git-init.sh`                     |
| Edit/revert cycle works                                     | 4     | git itself + bootstrap                                |
| Timer alerts on dirty tree                                  | 3 + 4 | `deploy/claw-runtime-drift-check.{sh,service,timer}`  |
| `_check_auth` bypass surfaces before landing                | 5     | `deploy/claw-runtime-pre-commit-hook.sh`              |
| Repo-resident audit trail of every edit                     | 1–2   | bootstrap + remote push                               |

---

## Out of scope (preserved verbatim from the issue)

- No changes to `mcp-server.py` itself in this PR — auth body remains
  `_check_auth` as of sha256 `59778371c8be736ca92c317345cde8cacce25415f271f2cc9f0768e3e4833f47`.
- No ssh / live Azure calls from CI or from the PR author's workstation —
  Zen runs every step above directly on nanoclaw-az.
- No selection of the private mirror repo name — left as `<TODO-set-remote>`
  for the operator to fill in at deploy time.
- No upgrade of the pre-commit hook to blocking mode in this roll-out;
  shipped as advisory, with the `UPGRADE-TO-BLOCKING` marker called out for
  a follow-up.
