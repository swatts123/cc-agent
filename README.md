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

Pick the section that matches your host.

### Windows (Git Bash)

Python on Windows is user-installed and not used by the OS, so plain `pip` works without a virtual environment.

```bash
# from the cc-agent directory
pip install .
cc-agent --version
```

If `pip` is missing, use `python -m pip install .`. If `python` opens the Microsoft Store, disable the `python.exe` and `python3.exe` aliases under **Settings → Apps → Advanced app settings → App execution aliases**.

### Amazon Linux 2023

AL2023 does not enforce PEP 668, so user-scoped `pip` works directly — but the default `python3` is 3.9, below cc-agent's required 3.12. Install 3.12 first:

```bash
sudo dnf install -y python3.12 python3.12-pip git
cd cc-agent
python3.12 -m pip install --user .

# Make sure ~/.local/bin is on PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

cc-agent --version
```

### Ubuntu (and other PEP 668 distros)

Modern Ubuntu (and Debian) mark the system Python as externally managed, so plain `pip install .` will refuse with an `externally-managed-environment` error. The cleanest fix is **pipx**, which installs cc-agent into an isolated venv and links the `cc-agent` command onto `PATH` for you — equivalent to the Windows experience, but isolated.

```bash
sudo apt update
sudo apt install -y pipx
pipx ensurepath
exec $SHELL -l                # reload PATH; or open a new shell

cd cc-agent
pipx install .
cc-agent --version
```

Upgrades later: `pipx upgrade cc-agent`. Uninstall: `pipx uninstall cc-agent`.

If you'll be hacking on the source and want editable installs with dev dependencies, use a venv instead:

```bash
sudo apt install -y python3.12 python3.12-venv python3-full
python3.12 -m venv ~/.venvs/cc-agent
source ~/.venvs/cc-agent/bin/activate
pip install -e ".[dev]"
cc-agent --version
```

Avoid `pip install --break-system-packages` on shared hosts — it works but collides with future `apt upgrade`s.

## AWS CLI profile setup

cc-agent passes `--profile <name>` to every `aws` call, so each entry under `aws.profiles` in the config must correspond to a real profile in `~/.aws/config`. A `default` profile must always exist.

### EC2 instance with an attached instance profile

You don't need static credentials. The CLI's default provider chain falls through to the instance metadata service automatically — you just need a `[default]` section to exist so the CLI doesn't error out when called with `--profile default`.

```bash
mkdir -p ~/.aws
cat > ~/.aws/config <<'EOF'
[default]
region = us-east-1
output = json
EOF
```

Replace `us-east-1` with the region you want CLI calls to target by default (should match `bedrock.region` in your cc-agent config). Verify:

```bash
aws sts get-caller-identity --profile default
```

That should return the assumed-role ARN of the instance profile, e.g. `arn:aws:sts::123456789012:assumed-role/your-instance-role/i-0123abcd…`.

If it errors about credentials, check that `~/.aws/credentials` either doesn't exist or doesn't have a `[default]` block with stale keys — anything in `~/.aws/credentials` takes precedence over IMDS.

### Cross-account profiles from an instance profile

For each AWS account you want the agent to reach, add a profile that assumes the target role using IMDS as the credential source:

```ini
[profile prod]
role_arn = arn:aws:iam::222222222222:role/OrgReadWriteRole
credential_source = Ec2InstanceMetadata
region = us-east-1

[profile security]
role_arn = arn:aws:iam::111111111111:role/OrgReadWriteRole
credential_source = Ec2InstanceMetadata
region = us-east-1
```

The instance role needs `sts:AssumeRole` on each target role ARN, and each target role's trust policy must allow the instance role principal to assume it. Verify each one with `aws sts get-caller-identity --profile <name>` before adding it to cc-agent's config.

### Laptop with static credentials or SSO

For a laptop, configure profiles however you normally would (`aws configure`, `aws configure sso`, `aws-vault`, etc.) — cc-agent just calls the CLI, so anything that works for `aws sts get-caller-identity --profile <name>` works for the agent.

## First run

```bash
cc-agent
```

On first run with no config, the CLI writes `~/.cc-agent/config.yaml` from the bundled defaults and exits with a "review this and run again" message. Edit the file — at minimum, set `bedrock.region` and `bedrock.model_id`, and add entries under `aws.profiles` for the accounts you want to reach — then run `cc-agent` again to start the REPL.

## Slash commands inside the REPL

| Command | Effect |
|---|---|
| `/help` | Show command list |
| `/model <id>` | Swap the active Bedrock model for this session |
| `/tokens` | Show running token usage |
| `/reload` | Re-read the config file |
| `/save` | Save the current transcript |
| `/resume <uuid>` | Resume a saved session |
| `/profiles` | List configured AWS profiles |
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
