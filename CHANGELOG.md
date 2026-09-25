# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-25

### Added
- Default TOON (Token-Oriented Object Notation) output formatting for tabular data, reducing prompt token usage by 40-60% versus JSON in LLM context windows.
- Zero-dependency CLI design utilizing Python standard library modules (`urllib`, `json`, `argparse`, `pathlib`, `tempfile`) without third-party packages.
- Dedicated resource commands for `projects`, `issues`, `stories`, `tasks`, and `epics`.
- Generic `taiga api` command supporting raw REST passthrough for arbitrary Taiga API endpoints and HTTP methods.
- Optimistic concurrency control with automatic `version` attribute retrieval on resource updates to prevent HTTP 409 conflicts.
- Session token caching at `$XDG_CACHE_HOME/taiga/session.json` (falling back to `~/.cache/taiga/session.json`) with atomic file creation and POSIX file mode `0600`.
- Top-level `--version` CLI flag to inspect release version information.
- AI agent skill specification in `SKILL.md` for drop-in usage with Claude Code and opencode.

### Security
- Cross-origin request rejection: requests to a host other than the configured base URL are refused, preventing bearer-token exfiltration through the generic `taiga api` passthrough.
- Authorization header sent via `add_unredirected_header`, so credentials are not forwarded if the server issues an HTTP redirect to another host.
- Unencrypted `http://` connections to remote hosts are rejected unless explicitly allowed with `--insecure` or `TAIGA_INSECURE=1`; `localhost`, `127.0.0.1`, and `::1` remain permitted.
- Interactive password prompt via `getpass` when running on a TTY, so passwords need not be passed as command-line arguments (argv is readable by other processes).
- Plaintext password reading from `config.json` removed; passwords are only accepted from the environment or an interactive prompt.
- Cached session tokens are ignored when the requested username does not match the username stored in the cache, preventing cross-account token reuse.
- Configuration and cache directories are created with mode `0700` and honour `XDG_CONFIG_HOME` / `XDG_CACHE_HOME`.
- Project slug lookups use encoded query parameters instead of string interpolation.
- Temporary files from interrupted atomic writes are removed rather than left on disk.

[Unreleased]: https://github.com/aliepratama/taiga-cli/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aliepratama/taiga-cli/releases/tag/v0.1.0
