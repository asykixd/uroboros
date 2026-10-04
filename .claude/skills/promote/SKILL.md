---
name: promote
description: Merge dev into master (stable) after checks and the user's explicit approval; master has no -dev suffix. Use when the user asks to "move to master", "merge dev", "ship to stable" ("перекинуть в мастер", "влить dev").
---

# dev → master

`master` only gets tested changes the user **explicitly approved merging**. Approval of a previous merge doesn't carry over.

1. **Checks in `dev`:**
   ```bash
   git switch dev && git pull --ff-only && git status --short
   .venv/bin/ruff check . && .venv/bin/ruff format --check .
   .venv/bin/python -m pytest -q
   ```
   Clean tree, all green. Otherwise stop and report.
2. **What goes to master:** `git log --oneline --no-merges master..dev`. Show the user the list and the resulting `master` version (`X.Y.Z` from `X.Y.Z-dev`) and **wait for a yes** unless they already approved this exact merge.
3. **Merge:**
   ```bash
   git switch master && git pull --ff-only
   git merge --no-ff --no-commit dev
   ```
   Resolve a version-line conflict in favor of the version **without** `-dev`. Then drop the suffix in `pyproject.toml` and `uroboros/__init__.py` (if present).
4. **Check on master:** `.venv/bin/python -m pytest -q` (including `tests/test_version.py`, which requires no `-dev` on `master`).
5. **Commit and push:** `git commit -m "Merge dev into master: X.Y.Z"` (with the attribution line from system instructions), `git push origin master`.
6. **Back to dev:** `git switch dev`. If `dev` moves on to a new version, bump it there (e.g. `1.1.0-dev`) in a separate commit; confirm the number with the user.

No tags or GitHub releases here: that's `/release`, only on request.
