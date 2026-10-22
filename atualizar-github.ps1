$ErrorActionPreference = 'Stop'
if (!(Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Instale o Git para Windows e abra novamente o PowerShell: https://git-scm.com/download/win'
}
$destino = 'C:\Sonifarmacompras'
if (!(Test-Path -LiteralPath (Join-Path $destino 'compras.sqlite3'))) {
    throw "Banco não encontrado em $destino. Corrija a pasta de destino antes de atualizar."
}
$temporario = Join-Path $env:TEMP ('SonifarmaCompras-' + [guid]::NewGuid())
git clone --depth 1 --branch main https://github.com/Sonifarma/SonifarnaCompras.git $temporario
if ($LASTEXITCODE -ne 0) { throw 'Falha ao baixar do GitHub. Confira a conexão e o acesso à conta.' }
py "$temporario\atualizar.py" --origem "$temporario" --destino "$destino"
if ($LASTEXITCODE -ne 0) { throw 'Atualização interrompida. Confira a mensagem acima.' }
& "$destino\iniciar.bat"
