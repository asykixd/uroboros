---
name: release
description: Release Uroboros from master: tag vX.Y.Z and a GitHub release with English notes.
disable-model-invocation: true
---

# Uroboros release

Only on the user's direct request. Releases come **from `master`**, version without `-dev`.

1. **`/promote` first** if `dev` has changes for the release (`git log --oneline master..dev`).
2. **Version.** It's already in `master` (`pyproject.toml`, `uroboros/__init__.py`). Compare with recent tags (`git tag --sort=-creatordate | head`) and **confirm with the user**.
3. **Local checks** on `master` (GitHub Actions minutes may be out, don't rely on CI):
   ```bash
   .venv/bin/ruff check . && .venv/bin/ruff format --check .
   .venv/bin/python -m pytest -q
   ```
   If `gh run list --branch master -L 1` shows a finished run, it must be green.
4. **ROADMAP.md:** finished items of the stage are `[x]` (edit in `dev`, then `/promote`).
5. **Tag:** `git tag -a vX.Y.Z -m "Uroboros X.Y.Z"` on the `master` commit, `git push origin vX.Y.Z`.
6. **GitHub release:** concise English notes from commits since the previous release (`git log <prev-tag>..master --oneline --no-merges`), grouped: new, Hikka adapter, fixes, for module authors. Then
   ```bash
   gh release create vX.Y.Z --title "Uroboros X.Y.Z" --notes-file <file>
   ```
7. **PyPI:** publishing the release runs `.github/workflows/publish.yml` (package `uroboros-userbot`, trusted publishing). If Actions are unavailable, build with `python -m build` and ask the user to run `twine upload dist/*` themselves (never enter PyPI tokens).
8. Give the user the release link and switch back to `dev`.
