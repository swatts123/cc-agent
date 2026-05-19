# cc-agent

A portable, terminal-first Python CLI that uses AWS Bedrock Claude models to read/edit files, run shell commands, and make AWS API calls across any account reachable through the host's AWS CLI configuration.

Designed as a Claude Code equivalent that runs identically on:

- An EC2 instance with an attached instance profile
- A laptop with `~/.aws/config` already configured and Git Bash on Windows
- A workstation with SSO-configured AWS CLI profiles

## Requirements

- Python 3.12 or newer on `PATH`
- AWS CLI v2 on `PATH`, with credentials Boto3 can resolve and any cross-account named profiles already configured in `~/.aws/config`
- A `bash` binary on `PATH` (`/bin/bash` on Linux/macOS, Git Bash's `bash.exe` on Windows)

No root install, no daemon, no systemd, no log groups to pre-create.

## Install

```bash
pip install .
```

Or from a release:

```bash
pip install cc-agent
```

## First run

```bash
cc-agent
```

On first run with no config, the CLI writes `~/.cc-agent/config.yaml` from the bundled defaults and exits with a "review this and run again" message. Edit the file (in particular, add account entries under `aws.profiles` if you want cross-account reach), then run `cc-agent` again to start the REPL.

## Slash commands inside the REPL

| Command | Effect |
|---|---|
| `/help` | Show command list |
| `/model <id>` | Swap the active Bedrock model for this session |
| `/tokens` | Show running token usage |
| `/reload` | Re-read the config file |
| `/save` | Save the current transcript |
| `/resume <uuid>` | Resume a saved session |
| `/clear` | Start a fresh conversation |
| `/quit` | Exit |

## Tools the agent has

- **`read`, `write`, `edit`** — file operations sandboxed to `agent.workspace_root` in the config.
- **`bash`** — shell commands run through the configured bash binary with allowlist/denylist gates and an interactive approval prompt for anything off the allowlist.
- **`aws_cli`** — runs `aws <service> <operation> --profile <profile>` using the host's pre-configured CLI profiles. Read verbs auto-approve; mutations prompt; a hard blocklist refuses irreversible operations (`iam:DeleteRole`, `kms:ScheduleKeyDeletion`, etc.).

Every tool call is written to `~/.cc-agent/audit.jsonl` and optionally mirrored to CloudWatch.

## Configuration

See `~/.cc-agent/config.yaml` after first run. The bundled default is at `src/cc_agent/default_config.yaml` in the source tree.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Security-focused tests:

```bash
pytest -m security
```

Live Bedrock tests (require working credentials and Bedrock access):

```bash
pytest -m live
```
