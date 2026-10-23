# Atualizar para V1.9 — padrão operacional do CRM

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


## Novidades da V1.9 — regras de compra

A migração acrescenta colunas de embalagem anterior e previsão de entrega e uma tabela de condições por fornecedor; não apaga compras nem altera senhas. O novo módulo procurement.py deve estar no pacote (o atualizador verifica isso).

Depois de atualizar:

1. Salve a entrega prevista no painel. Sem data salva, a regra considera o dia atual em São Paulo.
2. No detalhe de cada insumo, clique em Informar última embalagem e informe a quantidade efetivamente comprada antes, por exemplo 5 kg para amido. Isso não é inferido da quantidade necessária atual. A importação XLSX aceita também as colunas opcionais `Embalagem anterior qtd` e `Embalagem anterior unidade`, mantendo as seis colunas originais na ordem documentada.
3. Nas cotações sugeridas, clique em Conferir cotação / validade para completar a quantidade de uma embalagem, unidade, preço por unidade informada e validade. Por exemplo: 5 kg a R$ 10 por kg = R$ 50. A avaliação exige validade estritamente superior a um ano da entrega prevista. Validade apenas mês/ano usa o primeiro dia do mês como referência conservadora. Datas não reconhecidas ficam pendentes.
4. Em Condições comerciais, confirme o mínimo, o limite de frete grátis e o frete abaixo do limite. R$ 700 / R$ 2.000 são somente referências iniciais, até confirmação. Frete desconhecido não é zero. As condições são compartilhadas por fornecedor entre os processos.
5. Confira desembolso e excedentes de embalagens inteiras. Massa é comparada em g (kg e mg convertidos); cápsulas em milheiros, incluindo conversão de unidades. Não se converte massa em contagem nem volume em massa.

A melhor opção do item prioriza desembolso sem frete entre alternativas com regras atendidas, dando prioridade a vínculos aprovados. O menor preço unitário aparece separadamente. Embalagens maiores que a anterior e dados ausentes impedem seleção automática. Escolhas existentes são preservadas e sinalizadas quando não atendem às regras atuais. Selecionar manualmente uma exceção exige confirmação e justificativa auditada; não remove as pendências de conferência.

Os rascunhos PDF/XLSX incluem o desembolso em embalagens inteiras, alertas e condições da cesta. A diferença teórica contra custo anterior considera só a quantidade necessária; não inclui frete nem o desembolso em excedentes e exige conferir a base do custo anterior.

As transferências são simulações individuais entre cestas, apenas para vínculos aprovados, validade e embalagem atendidas, sem acrescentar excedente de estoque e sem deixar a cesta de origem abaixo do mínimo. Cestas com pendências não são usadas nessas simulações. Condições/fretes não confirmados deixam a diferença com frete pendente. As sugestões não se acumulam nem são aplicadas automaticamente; não representam otimização global de todos os pedidos. Não há envio de pedidos.
