# ============================================================
#  Starts a DEDICATED Chrome window with the remote-debugging
#  port (9222) open, so the NCAA scraper can attach to it
#  (run with --attach) and pass Cloudflare as a REAL browser.
#
#  Only needed if the NCAA API ever hard-blocks your IP and the
#  curl_cffi fast path + auto headful fallback are not enough
#  (e.g. running from a data-center / VPN IP). On a normal home
#  connection you usually never need this - just use run_ncaa.ps1.
#
#  - Uses its OWN profile folder, so your normal Chrome is
#    untouched and can stay open.
#  - First run: install + sign in to a VPN extension here if you
#    need one; it is saved in the profile for next time.
#
#  HOW TO RUN:  right-click -> "Run with PowerShell"
#               (or:  ! powershell -File .\start_chrome_debug_ncaa.ps1 )
# ============================================================

$port       = 9222
$profileDir = "D:\chrome-debug-profile"   # shared with NAIA; kept between runs
$startUrl   = "https://www.ncaa.com/scoreboard/basketball-men/d1"

$candidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chrome = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $chrome) {
    Write-Host "ERROR: Could not find chrome.exe in the usual places." -ForegroundColor Red
    Write-Host "Edit this script and set the full path to chrome.exe manually." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

Write-Host "Launching debugging Chrome..." -ForegroundColor Cyan
Write-Host "  chrome   : $chrome"
Write-Host "  profile  : $profileDir"
Write-Host "  debugPort: $port"
Write-Host ""

& $chrome "--remote-debugging-port=$port" "--user-data-dir=$profileDir" $startUrl

Write-Host ""
Write-Host "Chrome started with debugging on port $port." -ForegroundColor Green
Write-Host "1) If a 'verify you are human' box appears, solve it once in this window." -ForegroundColor Yellow
Write-Host "2) Leave this Chrome window open." -ForegroundColor Yellow
Write-Host "3) Then run:  powershell -ExecutionPolicy Bypass -File run_ncaa.ps1 -Attach" -ForegroundColor Yellow
