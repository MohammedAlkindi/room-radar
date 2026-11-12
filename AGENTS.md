# Agents — room-radar

## Scope
Agents may edit source, tests, and docs in this repo.

## Branch policy
- Never commit directly to `main` for reviewable/multi-commit work.
- Branch format `<type>/<kebab>`; agent branches use the `claude/` (Claude) prefix.

## Requires confirmation
- Pushing, opening PRs, merging.
- Adding dependencies or changing build/test tooling.
- Deleting files or history-rewriting operations.
- Flashing a board or opening a serial port on the owner's machine.

## Never
- Commit failing tests. Commit secrets. Force-push shared branches.
- Put a real Wi-Fi SSID or password in any file.
