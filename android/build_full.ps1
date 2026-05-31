$env:JAVA_HOME = 'E:\jdk17'
$env:ANDROID_SDK_ROOT = 'E:\android-sdk'
$env:CHAQUOPY_PYTHON = 'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PATH = "E:\gradle\bin;E:\jdk17\bin;" + $env:PATH
Set-Location E:\music-dl\android
$pyDir = 'app\src\main\python'

# Save server_runner
$runner = "$pyDir\server_runner.py"
$backup = $null
if (Test-Path $runner) { $backup = Get-Content $runner -Raw }

# Clean python dir
Remove-Item -Recurse -Force $pyDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $pyDir | Out-Null

# Copy ALL .py files
Get-ChildItem ..\*.py | ForEach-Object { Copy-Item $_.FullName $pyDir\ }
Copy-Item -Recurse ..\sources $pyDir\sources -Force -ErrorAction SilentlyContinue
Copy-Item -Recurse ..\static $pyDir\static -Force -ErrorAction SilentlyContinue

# Restore server_runner (Android-specific, not the project root one)
if ($backup) { Set-Content -Path $runner -Value $backup; Write-Host "Restored server_runner.py" }
else { Write-Host "WARNING: No server_runner.py backup" }

# Clean build cache (but NOT .gradle - keeps debug keystore so app data survives reinstall)
Remove-Item -Recurse -Force app\build -ErrorAction SilentlyContinue

Write-Host "Building..."
gradle assembleDebug 2>&1 | Select-Object -Last 3
Get-ChildItem -Recurse app\build\outputs -Filter *.apk | ForEach-Object { Write-Host "APK: $($_.Name) ($([math]::Round($_.Length/1MB,1)) MB)" }
