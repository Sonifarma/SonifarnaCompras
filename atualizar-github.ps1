param(
    [string]$Pacote = '',
    [string]$Destino = 'C:\Sonifarmacompras',
    [string]$Backup = ''
)
$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath (Join-Path $Destino 'compras.sqlite3'))) {
    throw "Banco nao encontrado em $Destino. Corrija a pasta de instalacao."
}
if (!$Backup) { $Backup = Join-Path $Destino 'backups' }
if (!$Pacote) {
    Add-Type -AssemblyName System.Windows.Forms
    $Seletor = New-Object System.Windows.Forms.OpenFileDialog
    $Seletor.Title = 'Selecione o ZIP baixado de Sonifarma/SonifarnaCompras no GitHub'
    $Seletor.Filter = 'Arquivo ZIP (*.zip)|*.zip'
    if ($Seletor.ShowDialog() -ne 'OK') { Write-Host 'Atualizacao cancelada.'; return }
    $Pacote = $Seletor.FileName
}
$Temporario = Join-Path $env:TEMP ('SonifarmaCompras-' + [guid]::NewGuid())
Expand-Archive -LiteralPath $Pacote -DestinationPath $Temporario
$Pastas = @(Get-ChildItem -LiteralPath $Temporario -Directory)
if ($Pastas.Count -ne 1) { throw 'Estrutura do ZIP invalida.' }
$Origem = $Pastas[0].FullName
$Controle = Join-Path $Origem 'SONIFARMA_CONTROLE.ps1'
if (!(Test-Path -LiteralPath $Controle)) { throw 'O pacote nao contem o novo controle de manutencao.' }
& $Controle update -Pasta $Destino -Origem $Origem -Destino $Backup
# An exception from the controller stops this script; never restart after failure.
& "$Destino\iniciar.bat"
if ($LASTEXITCODE -ne 0) { throw 'Atualizacao aplicada, mas inicializacao falhou. Consulte os logs.' }
