# Atualizar para V1.7 no Windows

Feche a janela do Sonifarma Compras antes de atualizar. Execute o bloco inteiro no PowerShell. É necessário Git para Windows; se o repositório for privado, use sua conta autorizada quando o Git solicitar login. Ajuste o destino se necessário.

```powershell
& {
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
}
```

Também é possível usar o ZIP baixado pelo GitHub em Code → Download ZIP: extraia em uma pasta temporária e execute `py atualizar.py --pacote CAMINHO_DO_ZIP --destino C:\Sonifarmacompras` a partir da pasta extraída. O atualizador aceita tanto o ZIP da entrega quanto o ZIP da branch main do GitHub.

O atualizador verifica o pacote, recusa atualização com a porta 8766 em uso, cria backup do código substituído e do banco (com verificação de integridade), e preserva compras.sqlite3, usuários/senhas, dados locais e amostras. Não extraia pacotes diretamente sobre a instalação existente. O GitHub contém somente código, sem banco nem planilhas comerciais. O caminho do backup é mostrado no terminal. Em caso de falha durante a cópia, mantenha o sistema parado e restaure os arquivos pelo backup antes de iniciar.

Para instalação nova, baixe o código em uma pasta nova e execute iniciar.bat. Sem banco ou planilhas locais, um processo vazio é criado automaticamente.

Primeiro acesso: usuário **admin**, senha inicial **123456**. O primeiro acesso exige uma senha nova de 8 a 128 caracteres. Depois da troca, entre novamente. Atualizações seguintes preservam a senha alterada. Use “Alterar senha” ou “Sair” no menu.

As sessões expiram após 12 horas. Trocar a senha encerra todas as sessões desse usuário. Cinco erros de senha bloqueiam temporariamente o usuário por 5 minutos. Senhas são armazenadas com PBKDF2-SHA256 e salt aleatório, sem texto puro. A autenticação protege leitura, alterações e exportações da API. Para instalação em HTTPS, configure SONIFARMA_COOKIE_SECURE=1; o modo padrão continua restrito ao computador local em 127.0.0.1.
