param(
    [ValidateSet('start','stop','restart','status','backup','verify','update')]
    [string]$Acao = 'status',
    [string]$Pasta = $PSScriptRoot,
    [string]$Origem,
    [string]$Destino,
    [string]$Arquivo,
    [switch]$SemNavegador
)
$ErrorActionPreference = 'Stop'
$Pasta = (Resolve-Path -LiteralPath $Pasta).Path
$Script = Join-Path $Pasta 'iniciar_servidor.py'
$PidFile = Join-Path $Pasta '.sonifarma_compras.pid.json'
$Manutencao = Join-Path $PSScriptRoot 'manutencao.py'
$Url = 'http://127.0.0.1:8766'

function Test-SonifarmaProcess($Processo) {
    if (!$Processo -or $Processo.Name -notmatch '^python(w)?\.exe$') { return $false }
    $Caminho = [regex]::Escape($Script)
    $Padrao = '(?i)(?:^|\s)(?:"' + $Caminho + '"|' + $Caminho + ')(?=\s|$)'
    return [regex]::IsMatch([string]$Processo.CommandLine, $Padrao)
}
function Get-PortListener {
    return @(Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue | Where-Object { $null -ne $_ })
}
function Get-RecordedSonifarmaProcess {
    if (!(Test-Path -LiteralPath $PidFile)) { return $null }
    try {
        $Registro = Get-Content -LiteralPath $PidFile -Raw | ConvertFrom-Json
        $idProcesso = 0
        if (![int]::TryParse([string]$Registro.process_id, [ref]$idProcesso)) { return $null }
        $Processo = Get-CimInstance Win32_Process -Filter "ProcessId=$idProcesso" -ErrorAction SilentlyContinue
        if (!(Test-SonifarmaProcess $Processo) -or !$Processo.CreationDate) { return $null }
        if ([string]$Processo.CreationDate.ToUniversalTime().Ticks -ne [string]$Registro.created_ticks) { return $null }
        return $Processo
    } catch { return $null }
}
function Save-SonifarmaProcess($Processo) {
    if (!(Test-SonifarmaProcess $Processo) -or !$Processo.CreationDate) {
        throw 'Nao foi possivel identificar com seguranca o processo iniciado.'
    }
    @{process_id=$Processo.ProcessId; created_ticks=[string]$Processo.CreationDate.ToUniversalTime().Ticks} |
        ConvertTo-Json | Set-Content -LiteralPath $PidFile -Encoding ASCII
}
function Get-SonifarmaProcess {
    $Principal = Get-RecordedSonifarmaProcess
    if (!$Principal) { return $null }
    foreach ($Porta in @(Get-PortListener)) {
        $Dono = Get-CimInstance Win32_Process -Filter "ProcessId=$($Porta.OwningProcess)" -ErrorAction SilentlyContinue
        if (!(Test-SonifarmaProcess $Dono)) { continue }
        if ($Dono.ProcessId -eq $Principal.ProcessId) { return $Dono }
        $Ancestral = $Dono
        $Visitados = @{}
        for ($Nivel=0; $Nivel -lt 8; $Nivel++) {
            $Pai = [int]$Ancestral.ParentProcessId
            if ($Pai -eq $Principal.ProcessId) { return $Dono }
            if ($Pai -le 0 -or $Visitados.ContainsKey($Pai)) { break }
            $Visitados[$Pai] = $true
            $Ancestral = Get-CimInstance Win32_Process -Filter "ProcessId=$Pai" -ErrorAction SilentlyContinue
            if (!$Ancestral) { break }
        }
    }
    return $Principal
}
function Get-Python {
    $Virtual = Join-Path $Pasta '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $Virtual) { return $Virtual }
    $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($Launcher) {
        $Executavel = & $Launcher.Source -c 'import sys; print(sys.executable)'
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath ([string]$Executavel).Trim())) {
            return ([string]$Executavel).Trim()
        }
    }
    $Comando = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($Comando) { return $Comando.Source }
    throw 'Python nao localizado. Instale o Python 3.12 ou configure o ambiente virtual local.'
}
function Test-SonifarmaReady($Processo) {
    if (!$Processo) { return $false }
    $Listeners = @(Get-PortListener | Where-Object {
        $_.OwningProcess -eq $Processo.ProcessId -and $_.LocalAddress -eq '127.0.0.1'
    })
    if ($Listeners.Count -eq 0) { return $false }
    & (Get-Python) $Manutencao health --url $Url | Out-Host
    return $LASTEXITCODE -eq 0
}
function Start-Sonifarma {
    $Atual = Get-SonifarmaProcess
    if (!$Atual) {
        if (@(Get-PortListener).Count -gt 0) {
            throw 'Porta 8766 ocupada por processo fora do controle. Na primeira migracao, feche a janela antiga do Compras. Nenhum processo foi encerrado.'
        }
        if (!(Test-Path -LiteralPath $Script)) { throw 'iniciar_servidor.py ausente. Conclua a atualizacao primeiro.' }
        $Processo = Start-Process -FilePath (Get-Python) -ArgumentList @('-u',('"'+$Script+'"')) `
            -WorkingDirectory $Pasta -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $Pasta 'compras_servidor.log') `
            -RedirectStandardError (Join-Path $Pasta 'compras_erros.log')
        $Identificado = Get-CimInstance Win32_Process -Filter "ProcessId=$($Processo.Id)" -ErrorAction SilentlyContinue
        Save-SonifarmaProcess $Identificado
    }
    for ($Tentativa=0; $Tentativa -lt 30; $Tentativa++) {
        $Atual = Get-SonifarmaProcess
        if (!$Atual) { break }
        if (Test-SonifarmaReady $Atual) {
            Save-SonifarmaProcess $Atual
            Write-Host "Compras respondendo em $Url. PID: $($Atual.ProcessId)"
            if (!$SemNavegador) { Start-Process $Url }
            return
        }
        Start-Sleep -Seconds 1
    }
    throw 'Inicializacao nao confirmada. Consulte compras_servidor.log e compras_erros.log; use status antes de tentar novamente.'
}
function Stop-Sonifarma {
    $Atual = Get-SonifarmaProcess
    if (!$Atual) {
        Write-Host 'Nenhum processo Compras identificado. Processos sem registro nao serao encerrados.'
        return
    }
    # Recheck creation time and path immediately before terminating the registered process.
    Save-SonifarmaProcess $Atual
    $Confirmado = Get-RecordedSonifarmaProcess
    if (!$Confirmado) { throw 'Identidade do processo mudou. Encerramento cancelado.' }
    Stop-Process -Id $Confirmado.ProcessId -ErrorAction Stop
    Wait-Process -Id $Confirmado.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
    if (Get-RecordedSonifarmaProcess) { throw 'Processo ainda ativo. Operacao cancelada.' }
    Remove-Item -Force -LiteralPath $PidFile -ErrorAction SilentlyContinue
    Write-Host 'Servidor Compras encerrado.'
}
# Serialize maintenance per installation; never run two starts/updates together.
$Hash = [System.Security.Cryptography.SHA256]::Create()
try {
    $Digest = [BitConverter]::ToString($Hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($Pasta.ToLowerInvariant()))).Replace('-','')
} finally { $Hash.Dispose() }
$Mutex = New-Object System.Threading.Mutex($false, ('Local\SonifarmaCompras_' + $Digest))
$Obtido = $false
try {
    try { $Obtido = $Mutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $Obtido = $true }
    if (!$Obtido) { throw 'Outra operacao do Compras esta em andamento. Aguarde a conclusao.' }
switch ($Acao) {
    'start' { Start-Sonifarma }
    'stop' { Stop-Sonifarma }
    'restart' { Stop-Sonifarma; Start-Sonifarma }
    'status' {
        $Atual = Get-SonifarmaProcess
        if (!$Atual) {
            Write-Host 'Compras nao identificado por este gerenciador.'
            foreach ($Listener in @(Get-PortListener)) { Write-Host "Porta 8766 ocupada por PID $($Listener.OwningProcess), fora do controle." }
        }
        elseif (Test-SonifarmaReady $Atual) { Write-Host "Compras respondendo. PID: $($Atual.ProcessId)" }
        else { throw 'Processo identificado, mas resposta do Compras nao confirmada. Consulte os logs.' }
    }
    'backup' {
        if (!$Destino) { throw 'Informe -Destino para o backup.' }
        & (Get-Python) $Manutencao backup --base $Pasta --destination $Destino
        if ($LASTEXITCODE -ne 0) { throw 'Backup falhou.' }
    }
    'verify' {
        if (!$Arquivo) { throw 'Informe -Arquivo com o ZIP de backup.' }
        & (Get-Python) $Manutencao verify --archive $Arquivo
        if ($LASTEXITCODE -ne 0) { throw 'Verificacao falhou.' }
    }
    'update' {
        if (!$Origem -or !$Destino) { throw 'Informe -Origem (codigo novo) e -Destino (backups).' }
        if (Get-ScheduledTask -TaskName 'SonifarmaCompras' -ErrorAction SilentlyContinue) {
            throw 'Remova a supervisao SonifarmaCompras antes da manutencao; reinstale apos validar.'
        }
        Stop-Sonifarma
        if (@(Get-PortListener).Count -gt 0) {
            throw 'Porta 8766 ocupada. Na primeira migracao, feche a janela antiga do Compras. Atualizacao cancelada.'
        }
        & (Get-Python) $Manutencao update --base $Pasta --source $Origem --destination $Destino
        if ($LASTEXITCODE -ne 0) { throw 'Atualizacao falhou. Mantenha o Compras parado e confira o backup.' }
        Write-Host 'Atualizacao concluida. Execute start ou iniciar.bat e confira o painel.'
    }
}

} finally {
    if ($Obtido) { $Mutex.ReleaseMutex() }
    $Mutex.Dispose()
}
