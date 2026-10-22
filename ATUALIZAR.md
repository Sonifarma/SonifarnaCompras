# Atualizar para V1.8 — padrão operacional do CRM

O fluxo segue a operação documentada em SonifarmaCRM/integracao/painel/OPERACAO_LOCAL.md: baixar código em outra pasta, parar a aplicação, fazer backup verificado, atualizar somente código e reiniciar para validar. O Compras continua com seu próprio banco, porta 8766 e login; os controles de processo e supervisão automática do CRM não foram copiados.

Não é necessário Git instalado no Windows.

1. Abra https://github.com/Sonifarma/SonifarnaCompras com sua conta autorizada.
2. Clique **Code → Download ZIP** para baixar o código atual.
3. Feche a janela que executa o Sonifarma Compras. O atualizador cancela se a porta 8766 continuar ocupada, sem encerrar processos automaticamente.
4. Execute o bloco inteiro abaixo no PowerShell. Selecione o ZIP baixado quando abrir a janela:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $destino = 'C:\Sonifarmacompras'
    if (!(Test-Path -LiteralPath "$destino\compras.sqlite3")) {
        throw 'Banco não encontrado. Confira a pasta em $destino.'
    }
    Add-Type -AssemblyName System.Windows.Forms
    $seletor = New-Object System.Windows.Forms.OpenFileDialog
    $seletor.Title = 'Selecione o ZIP do SonifarnaCompras baixado do GitHub'
    $seletor.Filter = 'Arquivo ZIP (*.zip)|*.zip'
    if ($seletor.ShowDialog() -ne 'OK') { return }
    $pacote = $seletor.FileName
    $temporario = Join-Path $env:TEMP ('SonifarmaCompras-' + [guid]::NewGuid())
    Expand-Archive -LiteralPath $pacote -DestinationPath $temporario
    $pastas = @(Get-ChildItem -LiteralPath $temporario -Directory)
    if ($pastas.Count -ne 1) { throw 'Estrutura do ZIP inválida.' }
    $atualizador = Join-Path $pastas[0].FullName 'atualizar.py'
    if (!(Test-Path -LiteralPath $atualizador)) { throw 'Atualizador não encontrado no pacote.' }
    py "$atualizador" --pacote "$pacote" --destino "$destino"
    if ($LASTEXITCODE -ne 0) { throw 'Atualização interrompida. Confira a mensagem acima.' }
    & "$destino\iniciar.bat"
}
```

Não extraia o ZIP sobre a instalação existente. Ele deve ficar em uma pasta temporária. O atualizador valida a sintaxe dos arquivos Python sem executá-los, cria backup do código substituído e do banco com verificação de integridade, grava manifesto SHA-256 e preserva compras.sqlite3, contas, senhas, configurações locais e amostras. Uma falha de cópia aciona tentativa de restauração do código anterior; se falhar também, o caminho do backup e os arquivos pendentes são informados e o painel não é iniciado. A operação não é transacional contra queda de energia.

Após iniciar, entre no painel, confira o processo e os insumos e use Ctrl+F5 para atualizar o visual. Primeiro acesso: admin / senha inicial 123456, com troca obrigatória para senha de 8 a 128 caracteres. Se a senha já foi alterada, continua a mesma.

Depois desta atualização, também é possível abrir PowerShell na pasta da instalação e executar `./atualizar-github.ps1`; ele solicita o ZIP, atualiza e inicia o sistema. Não altere a política de execução global caso a empresa bloqueie scripts: use o bloco acima ou peça a liberação/assinatura ao administrador.

Para instalação nova, extraia o ZIP em uma pasta nova e execute iniciar.bat. Sem banco ou planilhas locais, um processo vazio é criado.

As sessões expiram em 12 horas; trocar a senha encerra todas as sessões do usuário. Cinco erros de senha bloqueiam o usuário por cinco minutos. O modo padrão permanece em 127.0.0.1; HTTPS exige SONIFARMA_COOKIE_SECURE=1.
