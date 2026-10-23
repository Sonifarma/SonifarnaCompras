# Atualização e controle — V1.10

O Compras agora usa o mesmo modelo de manutenção do SonifarmaCRM: controle com start/stop/restart/status/backup/verify/update, processo identificado por PID e caminho, resposta funcional verificada, ZIP de backup restaurado temporariamente e atualização restrita a uma lista explícita de arquivos de código.

O Compras mantém seu banco, contas e porta 8766. Não usa o PostgreSQL, IP, certificados ou credenciais do CRM. Não foram adicionados supervisão automática nem agendamento. Não é necessário instalar Git.

## Primeira migração para este controle

1. Baixe o código em https://github.com/Sonifarma/SonifarnaCompras, em Code → Download ZIP.
2. Feche a janela antiga do Compras. Essa primeira instância não foi registrada pelo novo gerenciador e não será encerrada automaticamente.
3. Cole o bloco inteiro no PowerShell e selecione o ZIP baixado. Ele usa o atualizador do pacote novo, preservando a instalação existente:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $destino = 'C:\Sonifarmacompras'
    if (!(Test-Path -LiteralPath "$destino\compras.sqlite3")) {
        throw 'Banco não encontrado. Confira a pasta de instalação.'
    }
    Add-Type -AssemblyName System.Windows.Forms
    $seletor = New-Object System.Windows.Forms.OpenFileDialog
    $seletor.Title = 'Selecione o ZIP atualizado do Compras baixado do GitHub'
    $seletor.Filter = 'Arquivo ZIP (*.zip)|*.zip'
    if ($seletor.ShowDialog() -ne 'OK') { return }
    $pacote = $seletor.FileName
    $temporario = Join-Path $env:TEMP ('SonifarmaCompras-' + [guid]::NewGuid())
    Expand-Archive -LiteralPath $pacote -DestinationPath $temporario
    $pastas = @(Get-ChildItem -LiteralPath $temporario -Directory)
    if ($pastas.Count -ne 1) { throw 'Estrutura do ZIP inválida.' }
    $atualizador = Join-Path $pastas[0].FullName 'atualizar.py'
    if (!(Test-Path -LiteralPath $atualizador)) { throw 'Atualizador não encontrado.' }
    py "$atualizador" --pacote "$pacote" --destino "$destino"
    if ($LASTEXITCODE -ne 0) { throw 'Atualização interrompida. Confira a mensagem acima.' }
    & "$destino\START_SONIFARMA.bat"
}
```

A troca de código não modifica o banco. Ao iniciar, migrações aditivas continuam preservando os dados e as senhas. Os backups antigos de outras versões permanecem intactos.

## Próximas atualizações

Baixe o ZIP atual pelo GitHub e abra **ATUALIZAR_SONIFARMA.bat** na instalação. Selecione o pacote. Ele usa o controle para parar somente o servidor registrado desta instalação, faz backup verificado e cópia do código anterior, atualiza e inicia. Se qualquer etapa falhar, a sequência para e não inicia o painel. Se o código for atualizado, mas a inicialização falhar, a mensagem informa isso e aponta para os logs; não reverte o banco automaticamente.

Comandos equivalentes, no padrão do CRM, a partir da instalação:

```powershell
.\SONIFARMA_CONTROLE.ps1 update -Origem 'C:\Atualizacoes\SonifarnaCompras-main' -Destino 'D:\BackupsSonifarmaCompras'
.\SONIFARMA_CONTROLE.ps1 start
```

A origem é a pasta extraída do pacote novo, separada da instalação. `-Destino` no controle é a pasta dos backups; no atualizador antigo `atualizar.py --destino`, é a pasta da instalação. A ferramenta funciona com caminhos contendo espaços. Se houver uma tarefa agendada chamada SonifarmaCompras, desative/remova essa supervisão antes da manutenção para impedir reinício concorrente.

Os atalhos BAT usam a mesma opção de execução de PowerShell do acionamento do CRM, limitada à instância iniciada (`-ExecutionPolicy Bypass`); não alteram a política global nem sobrepõem políticas corporativas. Caso a empresa bloqueie a execução, solicite liberação/assinatura ao administrador.

## Operação diária

- START_SONIFARMA.bat ou iniciar.bat: inicia e abre o painel após confirmar a resposta.
- STOP_SONIFARMA.bat: para somente o processo registrado do Compras.
- RESTART_SONIFARMA.bat: para e inicia novamente.
- STATUS_SONIFARMA.bat: confere processo e resposta.
- ATUALIZAR_SONIFARMA.bat: seleciona o ZIP, atualiza e inicia.

O servidor passa a executar em segundo plano; fechar o navegador não o encerra. Use STOP_SONIFARMA.bat. Não é iniciado automaticamente no login. A inicialização usa o Python do ambiente virtual local quando existe, ou o Python do launcher py; módulos necessários ausentes acionam a instalação pelo requirements.txt. Mudanças de versões das dependências devem seguir as notas da entrega.

Logs: compras_servidor.log e compras_erros.log. O registro .sonifarma_compras.pid.json inclui PID e instante de criação; não identifica outro processo pelo número do PID isoladamente. O controle reconhece um filho do launcher de ambiente virtual quando ele atende a porta. Uma trava por instalação impede operações concorrentes. Uma porta ocupada por processo sem vínculo bloqueia a operação; não há encerramento indiscriminado de Python nem de processos do CRM.

## Backup, verificação e recuperação

```powershell
.\SONIFARMA_CONTROLE.ps1 backup -Destino 'D:\BackupsSonifarmaCompras'
.\SONIFARMA_CONTROLE.ps1 verify -Arquivo 'D:\BackupsSonifarmaCompras\compras_backup_DATA.zip'
```

O backup usa a API do SQLite, incluindo transações confirmadas no WAL. O ZIP contém compras.sqlite3 e um manifesto SHA-256; uma restauração temporária verifica o hash e PRAGMA integrity_check antes da publicação do backup. `verify` aceita este formato novo, não os diretórios de backup de versões anteriores. Usuários e hashes de senha estão no banco, portanto restrinja o acesso ao backup. O destino padrão é a subpasta backups da instalação; escolha outro disco/compartilhamento para proteção fora do disco local. Não há exclusão automática de backups nesta versão.

Antes de atualizar, o código anterior é copiado para codigo_DATA no mesmo destino, com manifesto SHA-256. Cada arquivo novo é validado e substituído por arquivo temporário no mesmo volume. Uma falha de cópia aciona restauração do código anterior; falhas na restauração são informadas. Não é uma transação contra queda de energia. Configurações, bancos, credenciais e arquivos locais não estão na lista de código a substituir. Se SONIFARMA_COMPRAS_DB apontar para outro banco, a manutenção é cancelada para não fazer backup do banco errado.

Em caso de regressão após iniciar: pare pelo controle, preserve o estado atual, restaure os arquivos da pasta codigo_DATA com orientação técnica e valide antes de reiniciar. Não restaure o banco antigo automaticamente: isso apagaria compras registradas depois do backup. As conexões abertas são encerradas quando o processo para, mas tokens persistidos em SQLite continuam sujeitos à expiração/logout/troca de senha; uma reinicialização sozinha não revoga todos os tokens.

## Validação

```powershell
py -m unittest discover -s tests -v
powershell -NoProfile -File tests\test_controle.ps1
```

Os testes Python usam bancos descartáveis; os testes de PowerShell simulam CIM/TCP e não substituem a conferência na máquina Windows real. Foi validado também o entry point iniciar_servidor.py com resposta HTTP real no ambiente de desenvolvimento. Após instalar, confira login, processo, itens e exportações; use Ctrl+F5 para renovar o visual.

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
