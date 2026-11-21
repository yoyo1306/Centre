param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$PublishDir = Join-Path $Root "publish"
$DistDir = Join-Path $Root "dist"

Write-Host "[1/5] Nettoyage du dossier publish..." -ForegroundColor Cyan
if (Test-Path $PublishDir) { Remove-Item -Recurse -Force $PublishDir }
New-Item -ItemType Directory -Force $PublishDir | Out-Null

Write-Host "[2/5] Publication de CentreControle (WinUI 3, self-contained win-x64)..." -ForegroundColor Cyan
dotnet publish "src\CentreControle.App\CentreControle.App.csproj" `
    -c Release -r win-x64 --self-contained true `
    -p:Platform=x64 `
    -p:WindowsAppSDKSelfContained=true `
    -p:DebugType=none -p:DebugSymbols=false `
    -o $PublishDir
if ($LASTEXITCODE -ne 0) { throw "Echec publication CentreControle.App" }

Write-Host "[3/5] Publication de Moniteur 480x320 (.NET 10, self-contained win-x64 partage)..." -ForegroundColor Cyan
dotnet publish "src\CentreControle.Monitor\CentreControle.Monitor.csproj" `
    -c Release -r win-x64 --self-contained true `
    -p:Platform=x64 `
    -p:DebugType=none -p:DebugSymbols=false `
    -o $PublishDir
if ($LASTEXITCODE -ne 0) { throw "Echec publication CentreControle.Monitor" }

Write-Host "[4/5] Copie des ressources (assets, themes, PawnIO_setup.exe, config.ini, ico.ico)..." -ForegroundColor Cyan
# Supprime les dossiers de langues non necessaires (conserve fr, fr-FR, en, en-US) pour alleger l'installateur
$KeepDirs = @("assets", "themes", "libs", "fr", "fr-FR", "en", "en-US", "Microsoft.UI.Xaml")
Get-ChildItem -Path $PublishDir -Directory | Where-Object { $KeepDirs -notcontains $_.Name } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item -Recurse -Force "assets" (Join-Path $PublishDir "assets")
Copy-Item -Recurse -Force "themes" (Join-Path $PublishDir "themes")
New-Item -ItemType Directory -Force (Join-Path $PublishDir "libs") | Out-Null
if (Test-Path "libs\PawnIO_setup.exe") {
    Copy-Item -Force "libs\PawnIO_setup.exe" (Join-Path $PublishDir "libs\PawnIO_setup.exe")
}
Copy-Item -Force "ico.ico" (Join-Path $PublishDir "ico.ico")
if (Test-Path "config.ini") { Copy-Item -Force "config.ini" (Join-Path $PublishDir "config.ini") }
if (Test-Path "README.md") { Copy-Item -Force "README.md" (Join-Path $PublishDir "README.md") }
if (Test-Path "CHANGELOG.md") { Copy-Item -Force "CHANGELOG.md" (Join-Path $PublishDir "CHANGELOG.md") }

if (-not $SkipInstaller) {
    Write-Host "[5/5] Compilation de l'installateur Inno Setup..." -ForegroundColor Cyan
    $IsccCandidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    $Iscc = $IsccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Iscc) {
        throw "Inno Setup 6 (ISCC.exe) introuvable. Installe-le via: winget install JRSoftware.InnoSetup"
    }
    New-Item -ItemType Directory -Force $DistDir | Out-Null
    & $Iscc (Join-Path $Root "installer\CentreControle.iss")
    if ($LASTEXITCODE -ne 0) { throw "Echec compilation Inno Setup" }
    Write-Host "Installateur pret dans dist\" -ForegroundColor Green
}
