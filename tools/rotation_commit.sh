#!/usr/bin/env bash
# Commit one slot's changed canonical files to auto/refresh-<slot> and push that branch (force, so the
# PR always shows this week's proposal). Never touches the default branch. Phase 51.
set -euo pipefail
slot="$1"; report="$2"
branch="auto/refresh-${slot}"
mapfile -t files < <(python3 -c "import json,sys;[print(f) for f in json.load(open(sys.argv[1]))['changed_files']]" "$report")
if [ "${#files[@]}" -eq 0 ]; then echo "nothing to commit"; exit 0; fi
# GitHub's own bot identity (noreply), exported so it overrides any ambient git identity.
export GIT_AUTHOR_NAME="github-actions[bot]" GIT_COMMITTER_NAME="github-actions[bot]"
export GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
git checkout -B "$branch"
git add -- "${files[@]}"
msg=$(python3 tools/fetch_rotation.py --commit-message "$report")
git commit -q -m "$msg"
git push -f origin "$branch"
echo "pushed $branch: ${files[*]}"
