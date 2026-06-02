#!/usr/bin/env bash
#
# rollback.sh — portable, branch- and path-agnostic git rollback.
#
# Restores a repo to a known-good commit. The DEFAULT strategy is `git revert`
# (a forward-fix: it creates new commits that undo the bad ones, never rewrites
# history, stays pushable, and survives an auto-deploy that keeps pulling the
# branch). A destructive `git reset --hard` is available behind --hard.
#
# Works in any repo, on any branch, from any path inside the working tree. No
# repo-specific assumptions; --poetry is opt-in for Poetry projects. Self-
# contained — copy it into any repo's scripts/ directory.
#
# Usage:
#   scripts/rollback.sh --list                          # show recent commits
#   scripts/rollback.sh --to <ref>  [--push] [--poetry] # revert back to <ref>
#   scripts/rollback.sh --last <n>  [--push] [--poetry] # revert last <n> commits
#   scripts/rollback.sh --to <ref> --hard               # destructive reset (no auto force-push)
#
# Options:
#   --to <ref>      Known-good commit/tag/branch to restore content to.
#   --last <n>      Roll back the last <n> commits (shorthand for --to HEAD~<n>).
#   --list          Print recent commits and exit (to choose a --to ref).
#   --repo <path>   Operate on the repo containing <path> (default: current dir).
#   --remote <name> Remote to push to (default: origin).
#   --push          Push the result to <remote>/<current-branch> (revert mode only).
#   --poetry        Run `poetry install` afterward (resync the venv to the lock).
#   --hard          DESTRUCTIVE: `git reset --hard <ref>` instead of revert.
#                   Does NOT force-push; do that yourself if the branch is shared.
#   --yes, -y       Skip the confirmation prompt.
#   -h, --help      Show this help.
#
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
rollback.sh — portable git rollback (revert by default; --hard to reset).

  scripts/rollback.sh --list
  scripts/rollback.sh --to <ref> [--push] [--poetry]
  scripts/rollback.sh --last <n> [--push] [--poetry]
  scripts/rollback.sh --to <ref> --hard

Options:
  --to <ref>      known-good commit/tag/branch to restore to
  --last <n>      roll back the last <n> commits
  --list          show recent commits, then exit
  --repo <path>   repo containing <path> (default: CWD)
  --remote <name> remote for --push (default: origin)
  --push          push result to <remote>/<branch> (revert mode only)
  --poetry        run `poetry install` afterward
  --hard          DESTRUCTIVE reset --hard (no auto force-push)
  --yes, -y       skip confirmation
  -h, --help      this help
EOF
  exit "${1:-0}"
}

REPO_PATH="."
REMOTE="origin"
TARGET=""
LAST=""
DO_LIST=0; DO_PUSH=0; DO_POETRY=0; DO_HARD=0; ASSUME_YES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --to)     TARGET="${2:?--to needs a ref}"; shift 2;;
    --last)   LAST="${2:?--last needs a number}"; shift 2;;
    --list)   DO_LIST=1; shift;;
    --repo)   REPO_PATH="${2:?--repo needs a path}"; shift 2;;
    --remote) REMOTE="${2:?--remote needs a name}"; shift 2;;
    --push)   DO_PUSH=1; shift;;
    --poetry) DO_POETRY=1; shift;;
    --hard)   DO_HARD=1; shift;;
    --yes|-y) ASSUME_YES=1; shift;;
    -h|--help) usage 0;;
    *) echo "rollback.sh: unknown argument: $1" >&2; usage 1;;
  esac
done

# Locate the repo (path-agnostic).
if ! REPO_ROOT="$(git -C "$REPO_PATH" rev-parse --show-toplevel 2>/dev/null)"; then
  echo "rollback.sh: not inside a git repository: $REPO_PATH" >&2
  exit 1
fi
cd "$REPO_ROOT"
BRANCH="$(git symbolic-ref --quiet --short HEAD || echo DETACHED)"
echo "Repo:   $REPO_ROOT"
echo "Branch: $BRANCH"

if [ "$DO_LIST" -eq 1 ]; then
  echo
  echo "Recent commits (newest first) — pass one as --to <ref>:"
  git --no-pager log --oneline --decorate -15
  exit 0
fi

# Resolve the target good commit.
if [ -n "$LAST" ]; then
  case "$LAST" in *[!0-9]*|"") echo "rollback.sh: --last needs a positive integer" >&2; exit 1;; esac
  [ -n "$TARGET" ] && { echo "rollback.sh: use either --to or --last, not both" >&2; exit 1; }
  TARGET="HEAD~$LAST"
fi
[ -z "$TARGET" ] && { echo "rollback.sh: pass --to <ref> or --last <n> (or --list to choose)." >&2; usage 1; }

if ! git rev-parse --verify --quiet "${TARGET}^{commit}" >/dev/null; then
  echo "rollback.sh: not a valid commit: $TARGET" >&2; exit 1
fi
TARGET_SHA="$(git rev-parse --short "$TARGET")"
if [ "$(git rev-parse "$TARGET")" = "$(git rev-parse HEAD)" ]; then
  echo "rollback.sh: target is already HEAD — nothing to roll back."; exit 0
fi
if ! git merge-base --is-ancestor "$TARGET" HEAD; then
  echo "rollback.sh: $TARGET ($TARGET_SHA) is not an ancestor of HEAD — cannot roll back to it." >&2
  exit 1
fi

# Refuse on a dirty tree — a rollback should start from a clean state.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "rollback.sh: working tree has uncommitted changes — commit or stash them first." >&2
  exit 1
fi

RANGE="${TARGET}..HEAD"
COUNT="$(git rev-list --count "$RANGE")"
MERGES="$(git rev-list --merges --count "$RANGE")"
CURRENT_HEAD="$(git rev-parse HEAD)"

echo
echo "Plan: restore content to ${TARGET_SHA} \"$(git log -1 --format='%s' "$TARGET")\""
echo "      undoing ${COUNT} commit(s) on ${BRANCH}:"
git --no-pager log --oneline "$RANGE" | sed 's/^/        /'
echo
echo "      safety: current HEAD is ${CURRENT_HEAD:0:12} (recover with: git reset --hard ${CURRENT_HEAD})"

if [ "$DO_HARD" -eq 1 ]; then
  echo
  echo "  MODE: --hard (DESTRUCTIVE reset --hard ${TARGET_SHA}; will NOT force-push)"
else
  echo
  echo "  MODE: revert (safe: ${COUNT} revert commit(s); pushable; auto-deploy friendly)"
  if [ "$MERGES" -gt 0 ]; then
    echo "  NOTE: range contains ${MERGES} merge commit(s); auto-revert is refused for merges."
    echo "        Use --hard to a pre-merge commit, or revert the merge manually with -m."
  fi
fi

if [ "$ASSUME_YES" -ne 1 ]; then
  printf "Proceed? [y/N] "
  read -r REPLY || true
  case "$REPLY" in [yY]|[yY][eE][sS]) ;; *) echo "Aborted."; exit 1;; esac
fi

if [ "$DO_HARD" -eq 1 ]; then
  git reset --hard "$TARGET"
  echo "Done: reset --hard to ${TARGET_SHA}."
else
  if [ "$MERGES" -gt 0 ]; then
    echo "rollback.sh: refusing to auto-revert a range containing merge commits. Use --hard or revert manually." >&2
    exit 1
  fi
  set +e
  git revert --no-edit "$RANGE"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo >&2
    echo "rollback.sh: revert hit a conflict. Resolve and run 'git revert --continue'," >&2
    echo "             or 'git revert --abort' to bail out and restore the prior state." >&2
    exit "$rc"
  fi
  echo "Done: reverted ${COUNT} commit(s); content now matches ${TARGET_SHA}."
fi

if [ "$DO_PUSH" -eq 1 ]; then
  if [ "$DO_HARD" -eq 1 ]; then
    echo "rollback.sh: --push skipped in --hard mode (would need --force; push manually)." >&2
  elif [ "$BRANCH" = "DETACHED" ]; then
    echo "rollback.sh: --push skipped (detached HEAD)." >&2
  else
    git push "$REMOTE" "$BRANCH"
    echo "Pushed to ${REMOTE}/${BRANCH}."
  fi
fi

if [ "$DO_POETRY" -eq 1 ]; then
  if command -v poetry >/dev/null 2>&1; then
    echo "Running poetry install..."
    poetry install
  else
    echo "rollback.sh: --poetry requested but 'poetry' is not on PATH." >&2
  fi
fi
