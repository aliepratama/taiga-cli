# taiga-cli

A zero-dependency CLI and AI agent skill for the Taiga.io project management REST API.

[![CI](https://github.com/aliepratama/taiga-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/aliepratama/taiga-cli/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

> **Disclaimer:** This is an independent, community-maintained project. It is **not** affiliated with, endorsed by, sponsored by, or associated with Kaleidos Open Source SL, Taiga Agile LLC, or any of their subsidiaries. "Taiga" and related marks are trademarks of their respective owners. The official Taiga platform lives at https://taiga.io.

## Why this exists

- **Zero runtime dependencies**: Implemented using only the Python standard library (`urllib`, `json`, `argparse`, `pathlib`, `tempfile`). No external packages or installation overhead.
- **Token-efficient TOON output**: Formats tabular data in Token-Oriented Object Notation by default, saving 40-60% tokens compared to JSON when passed to LLM agents.
- **Built for agents and humans**: Operates as a native skill inside Claude Code or opencode workspaces, or as an independent command-line utility for developers and QA engineers.
- **Conflict-free updates**: Handles optimistic locking automatically by querying and applying current object version numbers before mutation.

## Install

### AI Agent Skill (recommended)

Install with the [`skills`](https://www.skills.sh) CLI, which places the skill in the
correct directory for whichever agent you use:

```bash
npx skills add aliepratama/taiga-cli
```

This works with Claude Code, opencode, Gemini CLI, GitHub Copilot, Cursor, Codex,
Amp, Zed, and other agents that read the Agent Skills format. Use
`npx skills update` to pull later releases.

#### Manual installation

If you prefer not to use the `skills` CLI, clone the repository directly into your
agent skills directory:

```bash
# Claude Code
git clone https://github.com/aliepratama/taiga-cli ~/.claude/skills/taiga

# opencode
git clone https://github.com/aliepratama/taiga-cli ~/.config/opencode/skills/taiga
```

### Standalone CLI

Download the single executable script into a directory on your `PATH`:

```bash
curl -fsSL https://raw.githubusercontent.com/aliepratama/taiga-cli/main/scripts/taiga.py -o ~/.local/bin/taiga && chmod +x ~/.local/bin/taiga
```

This repository does not publish packages to PyPI and does not require `pip`.

## Quickstart

1. **Authenticate**:
   Set your username and run login:
   ```bash
   export TAIGA_USERNAME="your-username"
   taiga login
   ```
   When executed in a terminal, `taiga login` prompts for your password interactively using `getpass`, keeping credentials out of shell history and process tables. For headless or CI environments, `TAIGA_PASSWORD` can be set as an environment variable.

2. **List accessible projects**:
   ```bash
   taiga projects list
   ```

3. **Inspect project configuration**:
   Display issue types, priorities, severities, and status identifiers for your target project:
   ```bash
   taiga config <project_id>
   # Or using the flag:
   taiga config -p <project_id>
   ```

4. **List project issues**:
   ```bash
   taiga issues list -p <project_id>
   ```

## Configuration

The CLI resolves configuration and credentials using the following precedence:

1. Command-line options (`--url`, `--username`, `--token`, `--project`, `--insecure`)
2. Environment variables
3. Configuration file (`$XDG_CONFIG_HOME/taiga/config.json`)
4. Cached session token (`$XDG_CACHE_HOME/taiga/session.json`)

### Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `TAIGA_API_URL` | Base URL of the Taiga server | `https://api.taiga.io` |
| `TAIGA_USERNAME` | Taiga account username | None |
| `TAIGA_PASSWORD` | Taiga account password (for CI / non-interactive runs) | None |
| `TAIGA_AUTH_TOKEN` | Pre-existing Bearer authentication token | None |
| `TAIGA_PROJECT_ID` | Default project ID or slug for commands | None |
| `TAIGA_INSECURE` | Allow unencrypted HTTP to a remote host (`1`, `true`, `yes`) | Unset |
| `XDG_CONFIG_HOME` | Base directory for configuration files | `~/.config` |
| `XDG_CACHE_HOME` | Base directory for session cache files | `~/.cache` |

### Credential Handling & Security

Passing passwords or auth tokens directly via command-line flags (such as `--password`) is strongly discouraged. Arguments passed via CLI flags are visible in plain text to all users and running processes on the system through process tables (e.g., `ps aux`).

Run `taiga login` to enter your password via an interactive `getpass` prompt, or use the `TAIGA_PASSWORD` or `TAIGA_AUTH_TOKEN` environment variables.

### Transport Security

- **HTTPS Required for Remote Hosts**: Unencrypted `http://` requests to remote hosts are blocked by default to prevent credential leakage.
- **Insecure HTTP Exception**: If accessing a self-hosted instance over plain HTTP, supply `--insecure` or set `TAIGA_INSECURE=1`. *Warning: Transmitting credentials over unencrypted HTTP exposes tokens and passwords in cleartext on the network.*
- **Localhost Exemption**: Local development hosts (`localhost`, `127.0.0.1`, and `::1`) are permitted over HTTP without requiring `--insecure`.
- **Cross-Origin Protection**: The generic `taiga api` passthrough and all API calls reject URLs pointing outside the origin of the configured base URL, preventing bearer token exfiltration.

### Configuration and Session Storage

- **Configuration File (`$XDG_CONFIG_HOME/taiga/config.json`, default `~/.config/taiga/config.json`)**:
  Stores non-sensitive default connection parameters:
  ```json
  {
    "url": "https://api.taiga.io",
    "username": "your-username",
    "default_project": "12345"
  }
  ```
  Pass `--save` during `taiga login` to write URL and username to this file. Passwords are never saved in `config.json`. Configuration directories are created with POSIX directory mode `0700`.

- **Token Cache (`$XDG_CACHE_HOME/taiga/session.json`, default `~/.cache/taiga/session.json`)**:
  Upon successful login, authentication tokens are saved in this file using POSIX file mode `0600` (readable and writable only by the owner). When receiving HTTP 401 Unauthorized responses, the CLI automatically requests a refreshed session if credentials are configured. Tokens cached for a different username are rejected. Cache directories are created with mode `0700`.

## Output Formats

Commands returning lists or resource details support four output modes:

- **TOON (Default)**: Token-Oriented Object Notation outputs compact tabular data with explicit headers, minimizing token usage for LLMs while remaining human-readable.
- **`--fields <field1,field2>`**: Restricts the TOON output to the specified comma-separated columns.
- **`--json`**: Produces standard, indented JSON containing essential resource fields for scripts and pipelines.
- **`--full`**: Emits the raw, unedited API response payload directly from the Taiga server.

## Command Overview

The `--project` (or `-p`) flag can be specified before or after subcommands.

| Command | Usage Example | Description |
| :--- | :--- | :--- |
| `--version` | `taiga --version` | Displays the CLI version number (`taiga-cli 0.1.0`). |
| `login` | `taiga login [--save]` | Authenticates against the API and caches the session token. |
| `whoami` | `taiga whoami [--json]` | Displays profile information for the authenticated user. |
| `config` | `taiga config [project_id]`<br>`taiga config -p <project_id> [--json]` | Lists issue types, severities, priorities, and workflow statuses. |
| `projects` | `taiga projects list [--all] [--member <id>]`<br>`taiga projects get <id_or_slug>` | Lists accessible projects or inspects single project metadata. |
| `issues` | `taiga issues list -p <id> [--status <id>]`<br>`taiga issues get <id_or_#ref> -p <id>`<br>`taiga issues create -p <id> -s "Title" -d "Details"`<br>`taiga issues update <id> --status <status_id>`<br>`taiga issues delete <id>` | Manages issue lifecycle, filtering, assignments, and updates. |
| `stories` | `taiga stories list -p <id> [--milestone <id>]`<br>`taiga stories get <id_or_#ref> -p <id>`<br>`taiga stories create -p <id> -s "Story Title"`<br>`taiga stories update <id> --comment "Approved"`<br>`taiga stories delete <id>` | Manages user stories and sprint backlogs. |
| `tasks` | `taiga tasks list --story <story_id>`<br>`taiga tasks get <id_or_#ref> -p <id>`<br>`taiga tasks create -p <id> --story <id> -s "Task Title"`<br>`taiga tasks update <id> --status <status_id>`<br>`taiga tasks delete <id>` | Manages individual tasks linked to stories or milestones. |
| `epics` | `taiga epics list -p <id>`<br>`taiga epics get <id_or_#ref>`<br>`taiga epics create -p <id> -s "Epic Name" --color "#E4405F"`<br>`taiga epics update <id> -s "Updated Name"`<br>`taiga epics delete <id>` | Manages high-level project epics and color themes. |
| `api` | `taiga api GET /memberships --params project=<id>`<br>`taiga api POST /wiki --data '{"project": 123, "slug": "home"}'` | Generic REST passthrough for any Taiga endpoint. |

## Development

Run tests using the Python standard library `unittest` runner:

```bash
python3 -m unittest discover -s tests -v
```

Before contributing, review the following repository documents:

- [Contributing Guidelines](CONTRIBUTING.md)
- [Security Policy & Advisories](https://github.com/aliepratama/taiga-cli/security/advisories/new)
- [Changelog](CHANGELOG.md)
- [MIT License](LICENSE)
