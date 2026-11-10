# Runs all 6 sport/division combos for the 2026-27 season (up to today).
Set-Location "D:\Kinetic Intellegence\All Scrapers\NCAA_Scraper"
foreach ($s in "MBB","WBB") { foreach ($d in 1,2,3) {
  powershell -ExecutionPolicy Bypass -File run_ncaa.ps1 -Sport $s -Division $d -SeasonYear 2026
}}
