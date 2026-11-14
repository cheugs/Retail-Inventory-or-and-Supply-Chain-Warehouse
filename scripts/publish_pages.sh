#!/usr/bin/env bash
# Publish dashboard/static to the gh-pages branch (served by GitHub Pages).
#
#   scripts/publish_pages.sh             keep the snapshot already online (if any),
#                                        so a code push does not replace the daily data
#   scripts/publish_pages.sh --fresh     publish the local snapshot (daily live job)
#
# Used by .github/workflows/pages.yml and .github/workflows/daily-load.yml.
# It commits from the current checkout (so it reuses its GitHub credentials)
# without touching the main branch or the working copy.
set -euo pipefail

site="$(mktemp -d)"
cp -r dashboard/static/. "$site/"

if [ "${1:-}" != "--fresh" ] && git fetch -q origin gh-pages 2>/dev/null; then
  if git show FETCH_HEAD:data/snapshot.json > "$site/data/snapshot.online.json" 2>/dev/null; then
    mv "$site/data/snapshot.online.json" "$site/data/snapshot.json"
    echo "Keeping the snapshot already online"
  fi
fi
test -s "$site/data/snapshot.json"

# build a commit whose content is exactly the site folder
export GIT_INDEX_FILE="$(mktemp -u)"
export GIT_AUTHOR_NAME="github-actions" GIT_AUTHOR_EMAIL="github-actions@users.noreply.github.com"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
git --work-tree="$site" add -A .
tree="$(git write-tree)"
commit="$(git commit-tree "$tree" -m "Publish dashboard ($(date -u +%Y-%m-%dT%H:%MZ))")"
# the branch only holds the latest published version (no history needed)
git push -q --force origin "$commit:refs/heads/gh-pages"
echo "Dashboard published to gh-pages"
