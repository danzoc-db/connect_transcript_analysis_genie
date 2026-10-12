# AI-Assisted Coding - Gotchas & Best Practices

When using AI coding assistants (Cursor, Claude Code, GitHub Copilot, etc.) for
"vibe coding" in this repo, be aware of these common pitfalls. AI is great for
productivity, but **you** are responsible for code quality, security, and Git hygiene.

## Branch Management Issues

### 1. Wrong Branch Creation

- AI tools may create branches without checking you're starting from `main`.
- **Always verify:** Run `git branch` to confirm you're on `main` before creating a feature branch.
- **Manual fix:** If you branched from the wrong base:
  ```bash
  git checkout feat/your-work
  git rebase --onto main <wrong-base-branch> feat/your-work
  ```

### 2. Stale Base Branch

- AI may create a branch when your local `main` is outdated.
- **Always verify:** Pull latest `main` before branching: `git pull origin main`.

### 3. Branch Name Inconsistencies

- AI might suggest branch names that don't follow our convention.
- **Always verify:** Names must match `feat/` or `fix/` prefix and be lowercase.
- **Manual fix:** Rename locally and update remote:
  ```bash
  git branch -m old-name new-name
  git push origin :old-name new-name
  git push origin -u new-name
  ```

## Commit and PR Issues

### 4. Excessive Commit Messages

- AI iterations can create dozens of micro-commits ("fix typo", "update", "fix again").
- **Don't worry:** We use squash-merge, so these get consolidated.
- **Best practice:** Write a meaningful PR title and description - that becomes the final commit message.

### 5. Untracked Changes

- AI may generate or modify files without adding them to Git.
- **Always verify:** Run `git status` before committing.
- **Manual fix:** Review untracked files and either `git add` them or add to `.gitignore`.

### 6. Merge Conflicts

- AI can't always resolve merge conflicts during rebase.
- **Manual verification required:** After rebasing, check for conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).

## Pre-PR Checklist (AI Coding Specific)

Before creating your PR, manually verify in your terminal:

```bash
# 1. Confirm you're on the correct branch
git branch

# 2. Confirm all changes are intentional
git status
git diff main...HEAD

# 3. Verify no secrets or temporary files
git diff main...HEAD | grep -i "password\|token\|key\|secret"

# 4. Ensure branch is up to date
git fetch origin
git log HEAD..origin/main --oneline

# 5. Run the tests and linter - AI-generated code may have logical errors
ruff check . && ruff format --check .
databricks bundle validate -t dev
```

## GitHub PR Verification

After creating your PR:

- **Review the Files Changed tab** - ensure no unexpected files are included.
- **Check the diff** - AI may modify files you didn't mean to change.
- **Delete test/temporary branches** created during vibe coding.
- **CI/CD failures** - AI-generated code may pass locally but fail in CI; check the run.

---

## Code Quality and Best Practices

### 7. Hardcoded Values and Magic Numbers

AI often generates hardcoded paths or config. Prefer configurable values:

```python
# BAD - hardcoded
catalog = "dz_demos"

# GOOD - configurable
import os

catalog = os.environ.get("CATALOG", "default_catalog")
```

### 8. Error Handling

AI-generated code may lack error handling. Wrap external calls, catch specific
exceptions (not bare `except:`), and log properly.

### 9. Dependencies and Version Pinning

- Pin dependencies in `pyproject.toml` / `package.json` rather than leaving them unbounded.
- Test with the versions the repo declares before adding new ones.

### 10. Code Documentation

- Add docstrings to public functions explaining purpose, params, and return values.
- Document non-obvious design decisions - but don't add comments that just narrate code.

---

## Repo-Specific Gotchas (Connect Transcript Analysis)

### 11. Workspace Portability Drift

- This demo must be deployable to **any Databricks workspace**. AI often hard-codes
  workspace IDs, catalog names, or user emails.
- **Always verify:** Search for hardcoded values before committing:
  ```bash
  grep -rnE "(adb-[0-9]+|zoccali|databricks\.com)" --include="*.py" --include="*.sql" --include="*.yml" --include="*.json" . | grep -v "databricks.yml"
  ```

### 12. databricks.yml Target Pollution

- Workspace-specific values (warehouse IDs, service principal IDs, hosts) must go in
  **target overrides**, not the root `variables:` block.

### 13. Customer Name and Non-ASCII Leakage

- The repo is public. The customer is never named. Keep the terms to block in the
  gitignored `docs/internal/denylist.txt` (one per line) and check before every commit:
  ```bash
  grep -rniFf docs/internal/denylist.txt . --exclude-dir=.git --exclude-dir=internal
  LC_ALL=C grep -rnP "[^\x00-\x7F]" . --exclude-dir=.git
  ```

### 14. Classic Endpoint Gateway Creep

- AI assistants default to `model_serving_endpoints` with an `ai_gateway:` block
  (inference_table_config, usage_tracking_config). That is the **old** pattern.
  This repo governs the model with a **Unity AI Gateway model service** (`resources.model_services`)
  routing to a Databricks-hosted provisioned-throughput endpoint. The endpoint itself carries no
  `ai_gateway:` block. See `docs/architecture-decisions.md` ADR-1.

### 15. Sentiment Contract Drift

- The `sentiment*` columns must match `ai_analyze_sentiment` exactly: lowercase
  `positive` / `negative` / `neutral` / `mixed`, or `NULL` on failure. Never `Positive`,
  never `unknown`, never an empty string.

### 16. Token Spend on Reruns

- Sentiment runs in a **streaming table**, so only new transcripts are scored. A pipeline
  **full refresh re-scores every transcript** and costs tokens. Never add `full_refresh: true`
  to the job.

---

## Final Checklist

Before merging AI-generated code:

- [ ] Removed all hardcoded workspace-specific values
- [ ] No secrets or credentials in code
- [ ] No customer name, ASCII-only
- [ ] `ruff check .` clean
- [ ] `databricks bundle validate -t dev` passes
- [ ] Branch is rebased on latest `main`
- [ ] Reviewed the full diff for unintended changes

---

**Remember:** AI is a powerful assistant, but YOU are responsible for the code quality
and Git hygiene. Always review and verify before pushing.
