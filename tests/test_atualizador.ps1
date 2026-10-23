$ErrorActionPreference = 'Stop'
$Raiz = Split-Path -Parent $PSScriptRoot
$Source = Get-Content -LiteralPath (Join-Path $Raiz 'atualizar-github.ps1') -Raw
$NativeStart = '& "$Destino\iniciar.bat"'
if (!$Source.Contains($NativeStart)) { throw 'Native start seam changed; adapt the integration fixture.' }
# Simulate only external download, Windows file unblock, process controller and BAT launch.
# The updater's extraction, required-file checks, sequencing and failure handling run unchanged.
$Run = [scriptblock]::Create($Source.Replace($NativeStart,'Invoke-TestStart'))
$Root = Join-Path ([IO.Path]::GetTempPath()) ('Compras updater ' + [guid]::NewGuid())
$Installed = Join-Path $Root 'installed'
$PackageRoot = Join-Path $Root 'SonifarnaCompras-main'
$Package = Join-Path $Root 'package.zip'
$null = New-Item -ItemType Directory -Path $Installed,$PackageRoot
'fixture' | Set-Content -LiteralPath (Join-Path $Installed 'compras.sqlite3')
$global:UpdaterEvents = [Collections.Generic.List[string]]::new()
$global:FailDownload = $false
$global:FailUpdate = $false
$global:FailStart = $false
function Invoke-WebRequest {
    param([switch]$UseBasicParsing,$Uri,$OutFile)
    if ($Uri -ne 'https://github.com/Sonifarma/SonifarnaCompras/archive/refs/heads/main.zip') { throw 'Unexpected URL' }
    $global:UpdaterEvents.Add('download')
    if ($global:FailDownload) { throw 'Simulated network error' }
    Copy-Item -LiteralPath $global:FixturePackage -Destination $OutFile
}
function Unblock-File {
    [CmdletBinding()]param([Parameter(ValueFromPipeline=$true)]$InputObject)
    process { }
}
function Invoke-TestStart {
    $global:UpdaterEvents.Add('start')
    $global:LASTEXITCODE = $(if ($global:FailStart) { 1 } else { 0 })
}
function Assert-True($Value,$Message) { if (!$Value) { throw $Message } }
function Assert-Throws($Action,$Message) {
    $Failed=$false
    try { & $Action } catch { $Failed=$true }
    if (!$Failed) { throw $Message }
}
function Reset-Events {
    $global:UpdaterEvents.Clear()
    $global:FailDownload=$false; $global:FailUpdate=$false; $global:FailStart=$false
}
try {
    foreach ($Name in 'app.py','auth.py','procurement.py','document_import.py','manutencao.py','iniciar_servidor.py','iniciar.bat','templates/index.html','static/sonifarma-logo.png') {
        $Path = Join-Path $PackageRoot $Name
        $null = New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force
        'fixture' | Set-Content -LiteralPath $Path
    }
    @'
param($Acao,$Pasta,$Origem,$Destino)
if ($Acao -ne 'update') { throw 'Unexpected action' }
if ($Origem.StartsWith($Pasta + [IO.Path]::DirectorySeparatorChar)) { throw 'Source overlaps installation' }
$global:UpdaterEvents.Add('update')
if ($global:FailUpdate) { throw 'Simulated update failure' }
'@ | Set-Content -LiteralPath (Join-Path $PackageRoot 'SONIFARMA_CONTROLE.ps1')
    Compress-Archive -LiteralPath $PackageRoot -DestinationPath $Package
    $global:FixturePackage=$Package
    & $Run -Destino $Installed
    Assert-True (($global:UpdaterEvents -join ',') -eq 'download,update,start') 'Expected download then update then start'

    Reset-Events; $global:FailDownload=$true
    Assert-Throws { & $Run -Destino $Installed } 'Download failure must abort'
    Assert-True (($global:UpdaterEvents -join ',') -eq 'download') 'Download failure must never reach update/start'

    Reset-Events; $global:FailUpdate=$true
    Assert-Throws { & $Run -Destino $Installed } 'Update failure must abort'
    Assert-True (($global:UpdaterEvents -join ',') -eq 'download,update') 'Update failure must never restart'

    Reset-Events; $global:FailStart=$true
    Assert-Throws { & $Run -Destino $Installed } 'Startup failure must be reported'
    Assert-True (($global:UpdaterEvents -join ',') -eq 'download,update,start') 'Startup failure sequence unexpected'

    Reset-Events
    & $Run -Destino $Installed -Pacote $Package
    Assert-True (($global:UpdaterEvents -join ',') -eq 'update,start') 'Local package must skip download'

    Reset-Events
    Remove-Item -LiteralPath (Join-Path $PackageRoot 'auth.py')
    $Incomplete=Join-Path $Root 'incomplete.zip'
    Compress-Archive -LiteralPath $PackageRoot -DestinationPath $Incomplete
    $global:FixturePackage=$Incomplete
    Assert-Throws { & $Run -Destino $Installed } 'Incomplete package must abort'
    Assert-True (($global:UpdaterEvents -join ',') -eq 'download') 'Incomplete package must not stop/update/start'
    Write-Host 'Updater regressions passed: automatic download, separate source, local ZIP, download failure, incomplete package, update failure and start failure.'
} finally {
    Remove-Item -LiteralPath $Root -Recurse -Force
    Remove-Variable UpdaterEvents,FailDownload,FailUpdate,FailStart,FixturePackage -Scope Global -ErrorAction SilentlyContinue
}
