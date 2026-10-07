#!/bin/bash
# Free local updater: renders all 8 cards and pushes. No GitHub Actions needed.
# Usage: ./update.sh  (needs: python3, gh logged in)
set -e
cd "$(dirname "$0")"
export GITHUB_TOKEN="${GITHUB_TOKEN:-$(gh auth token)}"
python3 scripts/profile_card.py
python3 scripts/activity.py
python3 scripts/contrib_graph.py
# Bump the ?v= cache-buster so GitHub's image proxy fetches fresh SVGs.
perl -pi -e 's/\?v=(\d+)/"?v=".($1+1)/e' README.md
git add README.md dark_mode.svg light_mode.svg activity_dark.svg activity_light.svg graph_dark.svg graph_light.svg
git diff --cached --quiet && { echo "Cards unchanged."; exit 0; }
git commit -m "chore: update profile cards" && git push
