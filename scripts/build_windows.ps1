# Build cocoapatcher Windows distribution (PyInstaller one-folder)
param(
    [string]$Python = "python",
    [string]$OutDir = "dist"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Installing cocoapatcher editable + PyInstaller..."
& $Python -m pip install -e ".[windows]" pyinstaller

$Entry = "cocoapatcher\cli\main.py"
$Name = "cocoapatcher"

& $Python -m PyInstaller `
    --noconfirm `
    --onedir `
    --name $Name `
    --console `
    --collect-all customtkinter `
    --hidden-import win32com.client `
    $Entry

Write-Host ""
Write-Host "Build output: $Root\$OutDir\$Name\"
Write-Host "Run: $Root\$OutDir\$Name\$Name.exe gui"
Write-Host ""
Write-Host "Bundle PatcherSupportPkg_new alongside the app for offline OCLP embed (several GB)."
