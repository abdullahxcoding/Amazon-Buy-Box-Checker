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
    --collect-all playwright `
    --hidden-import=playwright.sync_api `
    --noconfirm `
    desktop_app.py

& ".venv\Scripts\python.exe" -m PyInstaller `
    --name "InstallBrowser" `
    --onefile `
    --console `
    --collect-all playwright `
    --noconfirm `
    install_browser.py

Copy-Item "dist\AmazonBuyBoxChecker.exe" "." -Force
Copy-Item "dist\InstallBrowser.exe" "." -Force
Write-Host ""
Write-Host "Build complete: AmazonBuyBoxChecker.exe and InstallBrowser.exe are in the project folder."
Write-Host "Double-click AmazonBuyBoxChecker.exe to run, or pin it to your taskbar/desktop."
Write-Host "On a NEW device, run InstallBrowser.exe once first (one-time browser setup)."
