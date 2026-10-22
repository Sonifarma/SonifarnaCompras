param(
    [string]$Pacote = '',
    [string]$Destino = 'C:\Sonifarmacompras'
)
$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath (Join-Path $Destino 'compras.sqlite3'))) {
    throw "Banco não encontrado em $Destino. Corrija a pasta de destino."
}
if (!$Pacote) {
    Add-Type -AssemblyName System.Windows.Forms
    $seletor = New-Object System.Windows.Forms.OpenFileDialog
    $seletor.Title = 'Selecione o ZIP baixado do Sonifarma/SonifarnaCompras no GitHub'
    $seletor.Filter = 'Arquivo ZIP (*.zip)|*.zip'
    if ($seletor.ShowDialog() -ne 'OK') { Write-Host 'Atualização cancelada.'; return }
    $Pacote = $seletor.FileName
}
$temporario = Join-Path $env:TEMP ('SonifarmaCompras-' + [guid]::NewGuid())
Expand-Archive -LiteralPath $Pacote -DestinationPath $temporario
$pastas = @(Get-ChildItem -LiteralPath $temporario -Directory)
if ($pastas.Count -ne 1) { throw 'Estrutura do ZIP inválida.' }
$atualizador = Join-Path $pastas[0].FullName 'atualizar.py'
if (!(Test-Path -LiteralPath $atualizador)) { throw 'O pacote não contém atualizar.py.' }
py "$atualizador" --pacote "$Pacote" --destino "$Destino"
if ($LASTEXITCODE -ne 0) { throw 'Atualização interrompida. Confira a mensagem acima.' }
& "$Destino\iniciar.bat"
