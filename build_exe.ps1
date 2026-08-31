Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\pyinstaller.exe")) {
    Write-Host "Installing PyInstaller..."
    & ".venv\Scripts\python.exe" -m pip install pyinstaller
}

$browserDir = Get-ChildItem "$env:LOCALAPPDATA\ms-playwright" -Directory -Filter "chromium_headless_shell-*" |
    Select-Object -First 1
if (-not $browserDir) {
    Write-Error "Chromium headless shell not found under $env:LOCALAPPDATA\ms-playwright. Run '.venv\Scripts\playwright install chromium' first, then re-run this build."
    exit 1
}
Write-Host "Bundling browser from: $($browserDir.FullName)"
Write-Host "(This makes the final .exe large, ~300MB+, since it embeds a real Chromium browser inside it.)"

& ".venv\Scripts\python.exe" -m PyInstaller `
    --name "AmazonBuyBoxChecker" `
    --onefile `
    --windowed `
    --collect-all customtkinter `
    --collect-all playwright `
    --hidden-import=playwright.sync_api `
    --add-data "$($browserDir.FullName);ms-playwright\$($browserDir.Name)" `
    --noconfirm `
    desktop_app.py

Copy-Item "dist\AmazonBuyBoxChecker.exe" "." -Force
Write-Host ""
Write-Host "Build complete: AmazonBuyBoxChecker.exe is in the project folder."
Write-Host "It is fully self-contained (Chromium bundled in) - copy just this one file to any device and run it, no setup step needed."
