@echo off
REM Free local updater for Windows: renders all 8 cards and pushes. No GitHub Actions needed.
REM Usage: update.bat  (needs: python, gh logged in)
cd /d "%~dp0"
for /f "delims=" %%t in ('gh auth token') do set GITHUB_TOKEN=%%t
python scripts/profile_card.py || exit /b 1
python scripts/activity.py || exit /b 1
python scripts/contrib_graph.py || exit /b 1
REM Bump the ?v= cache-buster so GitHub's image proxy fetches fresh SVGs.
powershell -NoProfile -Command "(Get-Content README.md) -replace '\?v=(\d+)', { param($m) '?v=' + ([int]$m.Groups[1].Value + 1) } | Set-Content README.md"
git add README.md dark_mode.svg light_mode.svg activity_dark.svg activity_light.svg graph_dark.svg graph_light.svg
git diff --cached --quiet && echo Cards unchanged. && exit /b 0
git commit -m "chore: update profile cards" && git push
