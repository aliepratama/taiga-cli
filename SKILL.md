---
name: taiga
description: Universal Taiga.io project management CLI & API suite. Manage projects, epics, user stories, tasks, issues, milestones, memberships, wiki, and custom attributes. Use when the user asks to inspect, create, update, or triage Taiga project tickets, tasks, user stories, epics, or issues.
license: MIT
metadata:
  author: aliepratama
  version: 0.1.0
---

# Taiga Universal CLI & API Suite

> **Disclaimer:** This is an independent, community-maintained project. It is **not** affiliated with, endorsed by, sponsored by, or associated with Kaleidos Open Source SL, Taiga Agile LLC, or any of their subsidiaries. "Taiga" and related marks are trademarks of their respective owners. The official Taiga platform lives at https://taiga.io.

This skill provides comprehensive access to the **Taiga.io** project management platform through a zero-dependency Python CLI.

**Invocation**: examples below use `taiga` for brevity. That name is available when the
script is on your `PATH` (for example symlinked into `~/.local/bin/taiga`). When this
skill is installed into an agent skills directory, invoke the script by its path
instead, using the `scripts/taiga.py` file that sits beside this document:

```bash
python3 scripts/taiga.py --version
```

## Key Features

1. **Zero Background Daemon**: Pure Python 3 standard library, on-demand execution via Bash.
2. **Context-Optimized Output**: TOON (Token-Oriented Object Notation) format by default for maximal LLM prompt token efficiency (saving 40-60% tokens vs standard JSON), with optional `--json` and `--fields` flags.
3. **Optimistic Locking**: Automatic `version` resolution on updates to prevent HTTP 409 conflict errors.
4. **100% REST Coverage**: Ergonomic shortcuts for everyday workflows, plus `taiga api` generic passthrough for any endpoint (wiki, memberships, attachments, custom attributes).

---

## Authentication & Configuration

The CLI resolves credentials and configuration using the following rules:
- **Authentication Token**: Provided via `--token`, the `TAIGA_AUTH_TOKEN` environment variable, or loaded from cached session storage.
- **Password**: Provided via the `TAIGA_PASSWORD` environment variable or an interactive `getpass` prompt on a TTY. Passing `--password` as a CLI argument exists but is discouraged because command arguments are visible to other processes; agents should prefer environment variables or pre-cached session tokens.
- **Non-Secret Configuration**: Server URL, username, and default project may be set via arguments (`--url`, `--username`, `--project`), environment variables (`TAIGA_API_URL`, `TAIGA_USERNAME`, `TAIGA_PROJECT_ID`), or stored in `config.json`. Passwords are never stored in `config.json`.
- **Storage Paths**: XDG-aware directory paths are used:
  - Session cache: `$XDG_CACHE_HOME/taiga/session.json` (default `~/.cache/taiga/session.json`, file mode `0600`).
  - Configuration: `$XDG_CONFIG_HOME/taiga/config.json` (default `~/.config/taiga/config.json`).
  - Storage directories are created with directory mode `0700`.
- **Transport Security**: Remote endpoints require HTTPS. Plain `http://` to remote hosts is refused unless `--insecure` or `TAIGA_INSECURE=1` is provided (`localhost`, `127.0.0.1`, and `::1` are exempt).
- **Cross-Origin Protection**: `taiga api` and all commands refuse requests targeted outside the origin of the configured base URL.

Tokens are cached per user. If a request receives an HTTP 401 Unauthorized, the CLI automatically re-authenticates and retries the request transparently if credentials are configured.

---

## Core Workflows

### 1. Projects & Configuration

```bash
# List projects for current user (fast, avoids server-wide 504 timeout)
taiga projects list

# List all public projects across the server
taiga projects list --all

# View project configuration table (types, severities, priorities, statuses)
taiga config [project_id]

# Or get clean JSON for programmatic parsing
taiga config [project_id] --json
```

*Note: The `--project` (or `-p`) flag can be placed anywhere: `taiga -p 123 stories list` or `taiga stories list -p 123`.*
*Note on `get`: Querying by number (e.g. `taiga stories get 88`) automatically checks internal ID first, and safely falls back to project `#ref` if HTTP 403 or 404 occurs.*

### 2. Issues Management

```bash
# List issues with optional filters
taiga issues list [--project <id>] [--status <id>] [--assigned <user_id>] [--limit 30]

# List issues formatted as compact JSON
taiga issues list --json

# Get details by ID or #ref
taiga issues get <id_or_#ref> [--project <id>] [--json]

# Create a new issue
taiga issues create \
  --project <id> \
  --subject "Issue title" \
  --desc "Reproduction steps or issue details" \
  --type <type_id> \
  --severity <severity_id> \
  --priority <priority_id> \
  --status <status_id> \
  --assigned <user_id> \
  --tags "bug,security,critical"

# Update an issue (auto-handles optimistic versioning)
taiga issues update <id> --status <status_id> --comment "Fixed in commit xyz"
taiga issues update <id> --assigned <user_id>
taiga issues update <id> --data '{"subject": "New Title", "status": 12486824}'

# Delete an issue
taiga issues delete <id>
```

### 3. User Stories Management

```bash
# List user stories
taiga stories list [--project <id>] [--milestone <id>] [--status <id>] [--epic <id>]

# Get story details
taiga stories get <id_or_#ref> [--project <id>]

# Create user story
taiga stories create \
  --project <id> \
  --subject "As a user, I want..." \
  --desc "Acceptance criteria" \
  --status <status_id> \
  --milestone <sprint_id>

# Update user story
taiga stories update <id> --status <status_id> --comment "Sprint review approved"

# Delete user story
taiga stories delete <id>
```

### 4. Tasks Management

```bash
# List tasks (optionally filtered by parent user story or sprint)
taiga tasks list [--story <story_id>] [--milestone <sprint_id>] [--status <status_id>]

# Get task details
taiga tasks get <id_or_#ref> [--project <id>]

# Create task under a user story
taiga tasks create \
  --project <id> \
  --story <story_id> \
  --subject "Implement database migration" \
  --status <status_id> \
  --assigned <user_id>

# Update task status
taiga tasks update <id> --status <status_id>

# Delete task
taiga tasks delete <id>
```

### 5. Epics Management

```bash
# List epics
taiga epics list [--project <id>]

# Get epic
taiga epics get <id_or_#ref>

# Create epic
taiga epics create --project <id> --subject "Epic Name" --color "#E4405F"

# Update epic
taiga epics update <id> --subject "Updated Epic"
```

### 6. Full REST API Passthrough (`taiga api`)

For any Taiga endpoint not covered by a high-level shortcut (e.g., wiki pages, memberships, custom attributes, milestones, webhooks):

```bash
# List project memberships
taiga api GET /memberships --params project=<project_id>

# Get wiki page
taiga api GET /wiki --params project=<project_id> slug=home

# Create wiki page
taiga api POST /wiki --data '{"project": 1783724, "slug": "architecture", "content": "Markdown..."}'

# Update custom attribute values for an issue
taiga api POST /issues/custom-attributes-values --data '{"attributes_values": {"123": "Value"}}'

# Milestones / Sprints
taiga api GET /milestones --params project=<project_id>
```

---

## Output Flags

- *(Default)*: Compact TOON (Token-Oriented Object Notation) format (maximum LLM context efficiency).
- `--fields <col1,col2>`: Filter specific columns to output in TOON format.
- `--json`: Clean, essential JSON dictionary/list for scripts or downstream parsing.
- `--full`: Unaltered raw payload from Taiga server (for deep debugging).
- `--version`: Print CLI version string (`taiga-cli 0.1.0`).
