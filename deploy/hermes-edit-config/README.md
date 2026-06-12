# hermes-edit-config

Safe edit helper for the immutable (`chattr +i`) hermes configuration files on nanoclaw-az.

## Why this exists

`~/.hermes/.env`, `~/.hermes/config.yaml`, and `~/.hermes/webui/settings.json` are marked immutable to prevent accidental clobber from systemd `ExecStartPre` coherence scripts. Editing by hand requires the `chattr -i` → edit → `chattr +i` ritual, which is non-obvious and easy to skip.

The `API_SERVER_KEY` outage of 2026-06-03 → 2026-06-12 (claw-stack-jp#165) sat unfixed for 9 days in part because the immutable bit silently rejected an `echo "API_SERVER_KEY=..." >> .env` attempt. This helper makes that workflow boring.

## Usage

```bash
# Update a single key (defaults to ~/.hermes/.env)
hermes-edit-config API_SERVER_KEY=sPEEdIWG2j9...

# Read a key without editing
hermes-edit-config --get API_SERVER_KEY

# Edit a non-default file
hermes-edit-config --file ~/.hermes/config.yaml HERMES_MODEL=gpt-5-chat

# Edit + restart the gateway in one step
hermes-edit-config API_SERVER_KEY=$(openssl rand -hex 32) --restart hermes-gateway
```

## Guarantees

- Always creates a timestamped `.bak-<epoch>` backup before editing
- Restores `chattr +i` even if the edit fails (script runs `set -euo pipefail`; trap cleans tmp)
- Preserves original owner + mode (0600)
- Updates a key in place (preserving file order) or appends if absent

## Tests

```bash
python -m pytest test_hermes_edit_config.py -o addopts=
```

Stubs `sudo` and `chattr` via PATH so the suite runs cleanly without root.

## Install

```bash
sudo cp hermes-edit-config.sh /usr/local/bin/hermes-edit-config
sudo chmod 755 /usr/local/bin/hermes-edit-config
```
