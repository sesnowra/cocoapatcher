# Build single-file united.exe (PyInstaller --onefile)

param(

    [string]$Python = "python"

)



$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot

Set-Location $Root



Write-Host "Installing cocoapatcher + PyInstaller..."

& $Python -m pip install -e ".[windows]" pyinstaller -q



Write-Host "Building united.exe (onefile)..."

& $Python -m PyInstaller united.spec --noconfirm --clean



$Out = Join-Path $Root "dist\united.exe"

if (Test-Path $Out) {

    $size = [math]::Round((Get-Item $Out).Length / 1MB, 1)

    Write-Host ""

    Write-Host "OK: $Out ($size MB)"

    Write-Host "Place united.exe in mixed_tahoe root (next to OpenCore-Legacy-Patcher, etc.) or set MIXED_TAHOE_ROOT."

    Write-Host "  Double-click -> GUI"

    Write-Host "  united.exe paths"
    Write-Host "  united.exe export-report"

    Write-Host "  united.exe build-efi --report Report.json --macos 26.0.0"

} else {

    Write-Error "Build failed: united.exe not found"

}

