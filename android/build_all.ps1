# Music DL - Android APK Build Script (Windows PowerShell)
# Run this from the music-dl/android directory

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Music DL - Android APK Builder" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check prerequisites
Write-Host "[1/5] Checking environment..." -ForegroundColor Yellow

$pythonPath = if (Test-Path "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe") {
    "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    (Get-Command python).Source
} else {
    Write-Host "ERROR: Python not found!" -ForegroundColor Red
    exit 1
}
Write-Host "  Python: $pythonPath"

# 2. Pull latest code
Write-Host "[2/5] Pulling latest code..." -ForegroundColor Yellow
Set-Location ..
git pull origin main 2>&1 | Write-Host
Set-Location android

# 3. Set env variables
Write-Host "[3/5] Setting environment..." -ForegroundColor Yellow
$env:CHAQUOPY_PYTHON = $pythonPath

# Check for signing key
$keystore = Join-Path (Get-Location) "musicdl.jks"
if (Test-Path $keystore) {
    $env:MUSICDL_KEYSTORE = $keystore
    Write-Host "  Keystore: $keystore"
    if (-not $env:MUSICDL_KEY_ALIAS) { $env:MUSICDL_KEY_ALIAS = "musicdl" }
    if (-not $env:MUSICDL_STORE_PASS) { Write-Host "  WARNING: MUSICDL_STORE_PASS not set (will build unsigned)" -ForegroundColor Yellow }
} else {
    Write-Host "  No keystore found (will build unsigned)"
}

# 4. Save server_runner.py + copy sources
Write-Host "[4/5] Preparing Python sources..." -ForegroundColor Yellow
$PY_DIR = "app/src/main/python"
$RUNNER = "$PY_DIR/server_runner.py"
$runnerBackup = $null
if (Test-Path $RUNNER) {
    $runnerBackup = Get-Content $RUNNER -Raw
}
Remove-Item -Recurse -Force $PY_DIR -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $PY_DIR | Out-Null

# Copy all Python files
Get-ChildItem .. -Filter "*.py" | ForEach-Object { Copy-Item $_.FullName "$PY_DIR/" }
Copy-Item -Recurse ../sources "$PY_DIR/" -ErrorAction SilentlyContinue
Copy-Item -Recurse ../static "$PY_DIR/" -ErrorAction SilentlyContinue

# Restore server_runner.py (the Android-specific one, not the desktop one)
if ($runnerBackup) {
    Set-Content -Path $RUNNER -Value $runnerBackup
    Write-Host "  Restored server_runner.py"
}
Write-Host "  Done."

# 5. Build
Write-Host "[5/5] Building APK..." -ForegroundColor Yellow
$gradleCmd = if (Test-Path "./gradlew.bat") { ".\gradlew.bat" } else { "gradle" }
& $gradleCmd assembleRelease 2>&1 | Select-Object -Last 20

# Show result
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Get-ChildItem -Recurse app/build/outputs -Filter "*.apk" | ForEach-Object {
    Write-Host "  APK: $($_.FullName) ($('{0:N1}' -f ($_.Length / 1MB)) MB)" -ForegroundColor Green
}
Write-Host ""
Write-Host "To install on phone: adb install <apk_path>" -ForegroundColor Gray
