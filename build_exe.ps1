Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\pyinstaller.exe")) {
    Write-Host "Installing PyInstaller..."
    & ".venv\Scripts\python.exe" -m pip install pyinstaller
}

& ".venv\Scripts\python.exe" -m PyInstaller `
    --name "AmazonBuyBoxChecker" `
    --onefile `
    --windowed `
    --collect-all customtkinter `
    --hidden-import=playwright.sync_api `
    --noconfirm `
    desktop_app.py

Copy-Item "dist\AmazonBuyBoxChecker.exe" "." -Force
Write-Host ""
Write-Host "Build complete: AmazonBuyBoxChecker.exe is in the project folder."
Write-Host "Double-click it to run, or pin it to your taskbar/desktop."
