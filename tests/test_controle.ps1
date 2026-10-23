$ErrorActionPreference = 'Stop'
$Raiz = Split-Path -Parent $PSScriptRoot
$Source = Get-Content -LiteralPath (Join-Path $Raiz 'SONIFARMA_CONTROLE.ps1') -Raw
$Tokens = $null
$Erros = $null
$Ast = [System.Management.Automation.Language.Parser]::ParseInput($Source, [ref]$Tokens, [ref]$Erros)
if ($Erros.Count) { throw "Erro de sintaxe: $Erros" }
foreach ($File in @(Get-ChildItem -LiteralPath $Raiz -Filter '*.ps1')) {
    $E = $null; $T = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($File.FullName, [ref]$T, [ref]$E)
    if ($E.Count) { throw "Erro de sintaxe em $($File.Name): $E" }
}
$Funcoes = $Ast.FindAll({param($No) $No -is [System.Management.Automation.Language.FunctionDefinitionAst]}, $true)
foreach ($F in $Funcoes) { Invoke-Expression $F.Extent.Text }
$Pasta = Join-Path ([IO.Path]::GetTempPath()) ('Compras controle com espacos ' + [guid]::NewGuid())
$null = New-Item -ItemType Directory -Path $Pasta
$Script = Join-Path $Pasta 'iniciar_servidor.py'
$PidFile = Join-Path $Pasta '.sonifarma_compras.pid.json'
$Manutencao = Join-Path $Pasta 'manutencao.py'
$Url = 'http://127.0.0.1:8766'
$script:Processes = @{}
$script:Listeners = @()
$script:Stopped = @()
$script:HealthExit = 0
function Get-CimInstance {
    param($ClassName, $Filter)
    $IdValue = [int]($Filter -replace 'ProcessId=', '')
    return $script:Processes[$IdValue]
}
function Get-NetTCPConnection { return $script:Listeners }
function Stop-Process { param($Id) $script:Stopped += $Id; $script:Processes.Remove([int]$Id) }
function Wait-Process { param($Id,$Timeout) }
function Get-ScheduledTask { return $null }
function Fake-Health {
    Write-Output 'Health command stdout must not become a truthy result'
    $global:LASTEXITCODE = $script:HealthExit
}
function Get-Python { return 'Fake-Health' }
function Assert-True($Value,$Message) { if (!$Value) { throw $Message } }
function Assert-Throws($Action,$Message) {
    $Thrown = $false
    try { & $Action } catch { $Thrown = $true }
    if (!$Thrown) { throw $Message }
}
function Make-Process($Number,$Parent=0,$Path=$Script) {
    return [pscustomobject]@{Name='python.exe';ProcessId=$Number;ParentProcessId=$Parent;
        CommandLine=('python.exe -u "'+$Path+'"');CreationDate=[datetime]'2026-10-23T12:00:00Z'}
}
try {
    $Root = Make-Process 101
    Assert-True (Test-SonifarmaProcess $Root) 'Expected full path with spaces to match'
    Assert-True (!(Test-SonifarmaProcess (Make-Process 202 0 ($Script+'.bak')))) 'Path prefix must not match'
    $Other = Make-Process 202; $Other.Name='node.exe'
    Assert-True (!(Test-SonifarmaProcess $Other)) 'Non-Python process must not match'

    $script:Processes[101]=$Root
    Save-SonifarmaProcess $Root
    Assert-True ((Get-RecordedSonifarmaProcess).ProcessId -eq 101) 'Recorded process not recognized'
    $Reused=Make-Process 101; $Reused.CreationDate=$Reused.CreationDate.AddSeconds(1)
    $script:Processes[101]=$Reused
    Assert-True ($null -eq (Get-RecordedSonifarmaProcess)) 'Reused PID must be rejected'
    $script:Processes[101]=$Root
    $Child=Make-Process 102 101
    $script:Processes[102]=$Child
    $script:Listeners=@([pscustomobject]@{OwningProcess=102;LocalAddress='127.0.0.1'})
    Assert-True ((Get-SonifarmaProcess).ProcessId -eq 102) 'Venv child listener not identified'
    $Unrelated=Make-Process 103 999
    $script:Processes[103]=$Unrelated
    $script:Listeners=@([pscustomobject]@{OwningProcess=103;LocalAddress='127.0.0.1'})
    Assert-True ((Get-SonifarmaProcess).ProcessId -eq 101) 'Unrelated listener must not be adopted'

    Remove-Item -Force -LiteralPath $PidFile
    Stop-Sonifarma
    Assert-True ($script:Stopped.Count -eq 0) 'Unknown process must not be stopped'
    Assert-Throws { Start-Sonifarma } 'Foreign listener must block startup'

    Save-SonifarmaProcess $Root
    $script:Listeners=@([pscustomobject]@{OwningProcess=101;LocalAddress='127.0.0.1'})
    $script:HealthExit=1
    $Ready=Test-SonifarmaReady $Root
    Assert-True (($Ready -is [bool]) -and !$Ready) 'Failed health with stdout must remain false'
    $script:HealthExit=0
    Assert-True (Test-SonifarmaReady $Root) 'Successful health must be true'
    Stop-Sonifarma
    Assert-True ($script:Stopped.Count -eq 1 -and $script:Stopped[0] -eq 101) 'Only recorded process may stop'
    Assert-True (!(Test-Path -LiteralPath $PidFile)) 'Stopped PID record must be removed'

    '{invalid json' | Set-Content -LiteralPath $PidFile
    Assert-True ($null -eq (Get-RecordedSonifarmaProcess)) 'Corrupt PID marker must be ignored'
    & (Join-Path $Raiz 'SONIFARMA_CONTROLE.ps1') status -Pasta $Pasta -SemNavegador
    Write-Host 'Controller regressions passed: syntax, paths, PID reuse, child listener, foreign process, startup guard, health exit status and stop identity.'
} finally {
    Remove-Item -LiteralPath $Pasta -Recurse -Force
}
