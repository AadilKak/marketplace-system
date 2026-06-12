@echo off
echo Cleaning git lock file...
del /f ".git\index.lock" 2>nul

echo Staging all changes...
git add -A

echo Committing...
git commit -m "Feat: Add server-side Playwright scraper + /api/scrape trigger endpoint"

echo Pushing to GitHub...
git push origin main

echo.
echo Done! Check GitHub to confirm.
pause
