param(
    [string]$Pacote = '',
    [string]$Destino = 'C:\Sonifarmacompras',
    [string]$Backup = ''
)
$ErrorActionPreference = 'Stop'
$Destino = (Resolve-Path -LiteralPath $Destino).Path
if (!(Test-Path -LiteralPath (Join-Path $Destino 'compras.sqlite3'))) {
    throw "Banco nao encontrado em $Destino. Corrija a pasta de instalacao."
}
if (!$Backup) { $Backup = Join-Path $Destino 'backups' }
$Pasta = Join-Path (Join-Path (Split-Path -Parent $Destino) 'AtualizacoesSonifarmaCompras') ((Get-Date -Format 'yyyyMMdd_HHmmss_fff') + '_' + [guid]::NewGuid().ToString('N').Substring(0,8))
$null = New-Item -ItemType Directory -Path $Pasta
if (!$Pacote) {
    $Pacote = Join-Path $Pasta 'projeto.zip'
    Write-Host 'Baixando codigo do Sonifarma Compras pelo GitHub...'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/Sonifarma/SonifarnaCompras/archive/refs/heads/main.zip' -OutFile $Pacote
}
$Extraido = Join-Path $Pasta 'extraido'
Expand-Archive -LiteralPath $Pacote -DestinationPath $Extraido
$Pastas = @(Get-ChildItem -LiteralPath $Extraido -Directory)
if ($Pastas.Count -ne 1 -or $Pastas[0].Name -ne 'SonifarnaCompras-main') {
    throw 'Estrutura do ZIP invalida: esperado SonifarnaCompras-main.'
}
$Origem = $Pastas[0].FullName
foreach ($Arquivo in 'app.py','auth.py','procurement.py','document_import.py','manutencao.py','iniciar_servidor.py','SONIFARMA_CONTROLE.ps1','iniciar.bat','templates\index.html','static\sonifarma-logo.png') {
    if (!(Test-Path -LiteralPath (Join-Path $Origem $Arquivo))) { throw "Pacote incompleto: $Arquivo" }
}
Get-ChildItem -LiteralPath $Origem -Filter '*.ps1' | Unblock-File
# No stop happens before the download, extraction and required-file checks succeed.
$Controle = Join-Path $Origem 'SONIFARMA_CONTROLE.ps1'
& $Controle update -Pasta $Destino -Origem $Origem -Destino $Backup
# A controller exception stops this script; never start after an update failure.
& "$Destino\iniciar.bat"
if ($LASTEXITCODE -ne 0) { throw 'Atualizacao aplicada, mas inicializacao falhou. Consulte os logs.' }
Write-Host 'Atualizacao concluida. Confira o painel e use Ctrl+F5.'
