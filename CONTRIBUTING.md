# Contributing to taiga-cli

Thank you for your interest in improving `taiga-cli`. We welcome bug fixes, documentation improvements, and targeted feature enhancements.

## Core Invariants

Before submitting code, ensure your changes follow these mandatory design rules:

1. **Zero Runtime Dependencies (Hard Rule)**:
   `taiga-cli` must run exclusively on the Python standard library (`urllib`, `json`, `argparse`, `pathlib`, `tempfile`, etc.). Pull requests introducing third-party runtime dependencies (via `pip`, `requirements.txt`, or inline imports) will be rejected.
2. **Python 3.9+ Compatibility**:
   Code must run identically across supported Python versions (`3.9`, `3.10`, `3.11`, `3.12`, and `3.13`) without deprecation warnings.
3. **Dual Audience Synchronization**:
   This repository serves both standalone CLI users and AI agent skill systems. Any new CLI command, argument, or flag requires:
   - Corresponding test coverage in `tests/test_taiga.py`.
   - Updated documentation in `SKILL.md` within the same pull request.
4. **TOON Stability**:
   TOON (Token-Oriented Object Notation) is consumed programmatically by AI agents. Modifications to TOON syntax or structure are breaking changes for downstream consumers. Open an issue for discussion before proposing modifications to TOON encoding logic.

---

## Development Setup

Because `taiga-cli` uses the standard library, no virtualenv or package installation steps are required:

```bash
# Clone the repository
git clone https://github.com/aliepratama/taiga-cli.git
cd taiga-cli

# Run the test suite
python3 -m unittest discover -s tests -v
```

---

## Running Tests

All automated tests use Python's built-in `unittest` module:

```bash
python3 -m unittest discover -s tests -v
```

Verify that all existing tests pass before pushing changes. Add test cases in `tests/test_taiga.py` covering any new functionality or bug fixes.

---

## Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) for clear versioning and changelog tracking:

- `feat:` Adds a new user-facing CLI feature or command.
- `fix:` Patches a bug or unintended behavior.
- `docs:` Modifies documentation, comments, or `SKILL.md`.
- `test:` Adds or refactors unit tests.
- `chore:` Maintenance tasks, repository configuration, or CI workflow updates.

Example:
```
feat(issues): add --priority filter to list subcommand
```

---

## Reporting Issues

- **Bug Reports**: Use the [Bug Report form](https://github.com/aliepratama/taiga-cli/issues/new?template=bug_report.yml). Provide exact reproduction steps, Python version, operating system, and sanitized outputs. Never include API tokens or passwords in issues.
- **Feature Requests**: Use the [Feature Request form](https://github.com/aliepratama/taiga-cli/issues/new?template=feature_request.yml). Explain the concrete use case, the proposed CLI syntax, and the expected impact on `SKILL.md`.
- **Taiga Platform Issues**: If you encounter server outages, project permission errors, or unexpected server 5xx responses unrelated to this CLI, refer directly to official Taiga support at [taiga.io](https://taiga.io).

---

## Pull Request Process

1. Fork the repository and create your branch from `main`.
2. Implement your changes keeping the zero-dependency invariant intact.
3. Add or update tests in `tests/test_taiga.py`.
4. Update `SKILL.md` if any CLI surface changed.
5. Add an entry to the `[Unreleased]` section of `CHANGELOG.md`.
6. Confirm tests pass with `python3 -m unittest discover -s tests -v`.
7. Submit your pull request using the provided pull request template.
