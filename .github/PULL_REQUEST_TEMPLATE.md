## Description

Please include a summary of the changes and the motivation behind them. If this PR resolves an open issue, link it below.

Fixes #(issue)

## Type of Change

- [ ] Bug fix (`fix`)
- [ ] New feature (`feat`)
- [ ] Documentation update (`docs`)
- [ ] Test addition or refactor (`test`)
- [ ] Maintenance or chore (`chore`)

## Pre-Submission Quality Checklist

Please confirm that your pull request meets each requirement:

- [ ] **Zero runtime dependencies**: No third-party packages or external imports have been added to runtime code.
- [ ] **Test coverage**: Unit tests in `tests/test_taiga.py` have been added or updated to cover all new or modified behavior.
- [ ] **Test suite passes**: `python3 -m unittest discover -s tests -v` runs cleanly without failures across Python 3.9+.
- [ ] **Skill documentation synchronized**: If CLI arguments, subcommands, or output formats changed, `SKILL.md` was updated in this PR.
- [ ] **Credential hygiene**: No passwords, tokens, API keys, or private URLs are present in code, commit history, test fixtures, or test output.
- [ ] **Changelog updated**: An entry describing this change has been added under the `[Unreleased]` section of `CHANGELOG.md`.
