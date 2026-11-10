# ============================================================
#  NCAA scraper launcher (Cloudflare-resilient).
#
#  Same bypass idea as NAIA, adapted for the NCAA JSON API:
#    - Default: curl_cffi with a real Chrome TLS fingerprint
#      (fast; defeats the common TLS/rate block with NO browser).
#    - On a real block it auto-opens a headful Chrome, passes
#      Cloudflare, and keeps scraping - never skipping data.
#    - -Attach: use a real Chrome you opened (debug port 9222)
#      and solve the box once by hand (best for data-center IPs).
#
#  Pipeline: discover all contest IDs for the season -> scrape
#  every boxscore (player stats) -> Final_All_Games_Data_*.json
#  (resume-safe: re-run anytime, it only scrapes what's missing).
#
#  USAGE:
#    powershell -ExecutionPolicy Bypass -File run_ncaa.ps1 -Sport MBB -Division 1 -SeasonYear 2025
#    powershell -ExecutionPolicy Bypass -File run_ncaa.ps1 -Sport WBB -Division 2 -SeasonYear 2025 -Headful
#    powershell -ExecutionPolicy Bypass -File run_ncaa.ps1 -Sport MBB -Division 1 -Attach
#    powershell -ExecutionPolicy Bypass -File run_ncaa.ps1 -Sport MBB -Division 1 -SkipDiscover   # reuse existing season file
# ============================================================

param(
    [ValidateSet("MBB","WBB")] [string]$Sport = "MBB",
    [ValidateSet(1,2,3)]       [int]$Division = 1,
    [int]$SeasonYear   = 2025,            # 2025 = the 2025-2026 season
    [double]$Delay     = 1.0,             # min seconds between requests
    [switch]$Attach,                      # attach to a real Chrome (port 9222)
    [switch]$Headful,                     # open a headful Chrome up-front
    [switch]$SkipDiscover                 # skip contest discovery, reuse season file
)

$ErrorActionPreference = "Continue"
$scriptDir = "D:\Kinetic Intellegence\All Scrapers\NCAA_Scraper"
Set-Location $scriptDir

# Force UTF-8 so Python's banners / accented team names don't crash the
# Windows console (cp1252) with a UnicodeEncodeError.
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"   # live progress instead of block-buffered output

# --- Pick a Python that has the scraper deps (curl_cffi + playwright) ---
function Get-Python {
    $cands = @("D:\Apps\Python\python.exe", "python", "py")
    foreach ($c in $cands) {
        try {
            $cmd = Get-Command $c -ErrorAction SilentlyContinue
            if (-not $cmd) { continue }
            & $c -c "import curl_cffi, playwright" 2>$null
            if ($LASTEXITCODE -eq 0) { return $c }
        } catch {}
    }
    Write-Host "[ERR] No Python with curl_cffi + playwright found. Install with:" -ForegroundColor Red
    Write-Host '      python -m pip install curl_cffi playwright ; python -m playwright install chromium' -ForegroundColor Yellow
    exit 1
}
$py = Get-Python
Write-Host "[OK] Using Python: $py" -ForegroundColor Green

# --- Cloudflare bypass flag for the python scripts ---
$cfFlag = "--cf"
if ($Attach)  { $cfFlag = "--attach" }
elseif ($Headful) { $cfFlag = "--headful" }

# --- Attach mode: make sure a debug Chrome is running ---
if ($Attach) {
    $port = 9222
    function Test-Port([int]$p) {
        try { $c = New-Object System.Net.Sockets.TcpClient; $c.Connect("127.0.0.1", $p); $c.Close(); return $true }
        catch { return $false }
    }
    if (Test-Port $port) {
        Write-Host "[OK] Debug Chrome already running on port $port - reusing it." -ForegroundColor Green
    } else {
        Write-Host "[..] Opening real debug Chrome (solve the box once if it appears)..." -ForegroundColor Cyan
        Start-Process powershell -ArgumentList "-ExecutionPolicy","Bypass","-File","`"$scriptDir\start_chrome_debug_ncaa.ps1`""
        $tries = 0
        while (-not (Test-Port $port) -and $tries -lt 40) { Start-Sleep -Milliseconds 500; $tries++ }
    }
    Write-Host ">>> If a 'verify you are human' box appears in Chrome, solve it once." -ForegroundColor Yellow
}

# --- File names (match the existing data convention) ---
$endYear     = $SeasonYear + 1
# Data folder per season (keep in sync with ncaa_paths.py):
#   <=2025 -> 2024_2025_2026_data ; >=2026 -> <YYYY>_<YY>_data (e.g. 2026_27_data)
if ($SeasonYear -le 2025) { $dataFolder = "2024_2025_2026_data" }
else { $dataFolder = "{0}_{1:D2}_data" -f $SeasonYear, ($endYear % 100) }
$dataDir = Join-Path $scriptDir $dataFolder
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$seasonFile  = Join-Path $dataDir "season_${Sport}_d${Division}_${SeasonYear}-${endYear}.json"
$outputFile  = Join-Path $dataDir "Final_All_Games_Data_${Sport}_D${Division}_${SeasonYear}_${endYear}.json"

# --- 1) Discover contest IDs for the whole season ---
if (-not $SkipDiscover) {
    Write-Host ""
    Write-Host "[STEP 1/2] Discovering $Sport D$Division contest IDs for $SeasonYear-$endYear ..." -ForegroundColor Cyan
    & $py fetch_season_contests.py $Sport $Division $SeasonYear $cfFlag
    if (-not (Test-Path $seasonFile)) {
        Write-Host "[ERR] Discovery did not produce $seasonFile" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[SKIP] Using existing $seasonFile" -ForegroundColor Yellow
    if (-not (Test-Path $seasonFile)) {
        Write-Host "[ERR] $seasonFile not found - run without -SkipDiscover first." -ForegroundColor Red
        exit 1
    }
}

# --- 2) Scrape every boxscore (resume-safe) ---
Write-Host ""
Write-Host "[STEP 2/2] Scraping boxscores -> $outputFile ..." -ForegroundColor Cyan
& $py ncaa_game_scraper2.py $seasonFile $outputFile $cfFlag --delay $Delay

Write-Host ""
Write-Host "[DONE] $outputFile" -ForegroundColor Green
