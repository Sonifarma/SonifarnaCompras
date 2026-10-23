# Atualização e controle — V1.14

O Compras agora usa o mesmo modelo de manutenção do SonifarmaCRM: controle com start/stop/restart/status/backup/verify/update, processo identificado por PID e caminho, resposta funcional verificada, ZIP de backup restaurado temporariamente e atualização restrita a uma lista explícita de arquivos de código.

O Compras mantém seu banco, contas e porta 8766. Não usa o PostgreSQL, IP, certificados ou credenciais do CRM. Não foram adicionados supervisão automática nem agendamento. Não é necessário instalar Git.

## Atualização pelo PowerShell — mesmo fluxo do CRM

O pacote é baixado automaticamente do GitHub, extraído em uma pasta separada e conferido antes de acionar a manutenção. Se estiver na versão antiga iniciada por uma janela de terminal, feche essa janela na primeira migração. Servidores iniciados pelo controle novo são parados automaticamente pela identificação registrada.

```powershell
& {
    Set-Location 'C:\Sonifarmacompras'
    $ErrorActionPreference = 'Stop'
    $instalacao = (Get-Location).Path
    $pasta = Join-Path 'C:\AtualizacoesSonifarmaCompras' (Get-Date -Format 'yyyyMMdd_HHmmss_fff')
    New-Item -ItemType Directory -Path $pasta | Out-Null

    Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/Sonifarma/SonifarnaCompras/archive/refs/heads/main.zip' -OutFile "$pasta\projeto.zip"
    Expand-Archive -LiteralPath "$pasta\projeto.zip" -DestinationPath $pasta
    $origem = Join-Path $pasta 'SonifarnaCompras-main'

    foreach ($arquivo in 'app.py','auth.py','procurement.py','document_import.py','manutencao.py','iniciar_servidor.py','SONIFARMA_CONTROLE.ps1','iniciar.bat','templates\index.html','static\sonifarma-logo.png') {
        if (!(Test-Path -LiteralPath "$origem\$arquivo")) { throw "Pacote incompleto: $arquivo" }
    }
    Get-ChildItem -LiteralPath $origem -Filter '*.ps1' | Unblock-File
    & "$origem\SONIFARMA_CONTROLE.ps1" update -Pasta $instalacao -Origem $origem -Destino "$instalacao\backups"
    & "$instalacao\iniciar.bat"
    if ($LASTEXITCODE -ne 0) { throw 'Codigo atualizado, mas a inicializacao falhou. Confira os logs.' }
}
```

Use o bloco inteiro: uma falha interrompe as etapas seguintes. O controle do pacote novo também permite atualizar instalações que ainda não possuem SONIFARMA_CONTROLE.ps1. O backup vai para a subpasta backups; é possível trocar esse destino por outro disco, por exemplo D:\BackupsSonifarmaCompras.

A tarefa automática do CRM não é alterada. O Compras não instala supervisão/agendamento nesta versão. Se houver uma tarefa personalizada chamada SonifarmaCompras, o controle exige sua remoção antes da manutenção para impedir reinício concorrente.

## Próximas atualizações com um clique

Abra **ATUALIZAR_SONIFARMA.bat**. Ele agora baixa o ZIP automaticamente, confere o pacote, para o processo registrado, faz backup verificado, atualiza somente o código e inicia. Não solicita arquivo, não exige Git e mantém os pacotes extraídos em AtualizacoesSonifarmaCompras, ao lado da pasta de instalação. Nenhum banco, usuário, senha ou configuração local é substituído.

O modo manual continua disponível para um pacote já baixado:

```powershell
.\atualizar-github.ps1 -Pacote 'C:\Atualizacoes\projeto.zip' -Destino 'C:\Sonifarmacompras'
```

Comandos equivalentes ao controle do CRM, a partir da instalação:

```powershell
.\SONIFARMA_CONTROLE.ps1 update -Origem 'C:\AtualizacoesSonifarmaCompras\PASTA_DA_VERSAO\SonifarnaCompras-main' -Destino 'D:\BackupsSonifarmaCompras'
.\SONIFARMA_CONTROLE.ps1 start
```

A origem deve ser uma pasta separada, fora da instalação. `-Destino` no controle é a pasta de backups; no script atualizar-github.ps1 e em atualizar.py --destino, é a pasta da instalação. Uma falha impede o reinício. Se o código tiver sido aplicado e a inicialização falhar, consulte os logs antes de tentar novamente; não reverta o banco automaticamente.

Os atalhos BAT usam a mesma opção de execução de PowerShell do acionamento do CRM, limitada à instância iniciada (`-ExecutionPolicy Bypass`); não alteram a política global nem sobrepõem políticas corporativas. Caso a empresa bloqueie a execução, solicite liberação/assinatura ao administrador.

## Operação diária

- START_SONIFARMA.bat ou iniciar.bat: inicia e abre o painel após confirmar a resposta.
- STOP_SONIFARMA.bat: para somente o processo registrado do Compras.
- RESTART_SONIFARMA.bat: para e inicia novamente.
- STATUS_SONIFARMA.bat: confere processo e resposta.
- ATUALIZAR_SONIFARMA.bat: baixa o ZIP do GitHub, atualiza e inicia.

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
powershell -NoProfile -File tests\test_atualizador.ps1
```

Os testes Python usam bancos descartáveis; os testes de PowerShell simulam CIM/TCP e as operações externas de download/inicialização e não substituem a conferência na máquina Windows real. Foi validado também o entry point iniciar_servidor.py com resposta HTTP real no ambiente de desenvolvimento. Após instalar, confira login, processo, itens e exportações; use Ctrl+F5 para renovar o visual.

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


## Importação de vários arquivos — V1.13

Em Importar documentos, selecione vários arquivos com Ctrl/Shift. Necessidades aceitam planilhas XLSX; cotações aceitam XLSX e PDF no mesmo lote. Limites: 30 arquivos, 15 MB por arquivo e 50 MB de conteúdo processado no lote. Todos são importados no processo selecionado.

Cada cotação tem seu próprio campo de fornecedor. O fornecedor padrão é opcional e preenche as linhas ainda não personalizadas. Confira esses nomes antes de enviar. Uma planilha no layout “Todas as cotações” mantém os fornecedores declarados nas próprias linhas; o nome informado no formulário é usado onde estiver ausente. Não há identificação automática confiável de fornecedores em PDFs.

Ao concluir, a fila mostra o resultado de cada arquivo: importado, sem registros reconhecidos ou erro. Arquivos sem registros não são apresentados como importação bem-sucedida. Um erro não impede os outros arquivos. Cada arquivo tem uma transação: registros e auditoria são gravados juntos, ou nenhum registro dele é mantido.

Os arquivos concluídos ficam fora de novos envios dessa mesma fila. O botão permite tentar de novo apenas os que falharam; se a conexão cair após a gravação, o identificador mantido na fila evita gravar novamente o arquivo na tentativa seguinte. Não recarregue a página para repetir um envio não confirmado: a fila e seus identificadores são mantidos nesta página. Recarregar e selecionar os arquivos novamente cria uma importação nova; não existe deduplicação global por nome ou por conteúdo. Para corrigir o conteúdo de um arquivo, selecione a versão corrigida sem incluir os arquivos que já foram importados.

A atualização cria apenas uma tabela de recibos de importação para as tentativas da fila, sem apagar dados ou alterar senhas. Os endpoints antigos de arquivo único continuam disponíveis. Até a V1.12 os PDFs usavam extração conservadora sem OCR; a V1.13 amplia esse suporte; cabeçalhos, unidades, embalagens e validades continuam sujeitos às verificações existentes. A importação acrescenta registros; não substitui as compras anteriores.


## Leitura de PDF, imagens e Excel — V1.13

Cotações agora aceitam PDF, JPG/JPEG, PNG, XLS e XLSX no mesmo lote. Necessidades aceitam XLS e XLSX no layout documentado. A importação conserva os limites de arquivos/tamanho existentes.

A leitura de PDF foi adaptada aos layouts enviados de Florien, Infinity, Purifarma, Sovita, Galena, I9, PN Farma e Pharmaspecial/Brenntag, incluindo tabelas que continuam em outras páginas. Preços com separadores brasileiros e ingleses são tratados conforme o layout. Quantidade cotada e embalagem não são confundidas: uma cotação de 30 milheiros em embalagens de 5 milheiros é registrada com embalagem de 5. Quando a cotação não explicita embalagem (como no modelo Galena), a quantidade cotada serve somente de referência e exige conferência.

Imagens e PDFs digitalizados usam OCR local por RapidOCR/ONNX. Os modelos acompanham a dependência Python; não é necessário instalar Tesseract nem enviar documentos a um serviço externo. A primeira atualização instalará as dependências adicionais e poderá levar alguns minutos. Imagens precisam estar nítidas, orientadas corretamente e conter a tabela completa. Há limite de 30 megapixels por imagem, 50 páginas por PDF e 10 páginas com OCR por arquivo; divida arquivos maiores. OCR pode omitir linhas ou ler incorretamente descrições, números e datas. Nem todo layout é reconhecido.

Todo item lido por OCR fica sinalizado e bloqueado para seleção automática. Valores antes de IPI/ST, divergências de totais e embalagens ambíguas também ficam sinalizados. Use **Revisar cotações importadas**, busque por fornecedor/arquivo, abra **Conferir / corrigir**, confira descrição, embalagem, unidade do preço, impostos e validade no original e marque a confirmação antes de salvar. A correção é auditada. Se a descrição mudar, vínculos de equivalência anteriores dessa cotação são retirados para nova conferência; escolhas já feitas são preservadas e devem ser revistas. Validade ausente não é inventada. Volume não é convertido em massa sem informação de densidade.

Arquivos de conteúdo idêntico e mesmo fornecedor no mesmo lote são ignorados após a primeira importação bem-sucedida, mesmo que tenham nomes diferentes. Fornecedores distintos podem usar arquivos iguais. Isso não é deduplicação global de todo o banco: reimportar manualmente em outro lote ainda acrescenta itens, conforme a versão anterior.

Na validação isolada com os arquivos enviados, foram reconhecidos 383 itens de nove PDFs diferentes; o décimo PDF era uma cópia idêntica do I9 e foi ignorado no lote. Nenhum PDF, planilha comercial, banco ou informação de cliente foi incluído no GitHub. Testes automatizados usam documentos sintéticos. Também foram conferidos JPG por OCR, PDF digitalizado, XLS e o fluxo de revisão no navegador. Essa validação não substitui a conferência comercial e farmacotécnica pelo comprador.

## Correção da atualização do painel após importar — V1.14

Incluída a dependência `tzdata`, necessária no Windows para consultar `America/Sao_Paulo`. Sem a base de fusos, uma importação pode terminar e gravar seus registros, mas a atualização do comparativo falha ao calcular a data de entrega. O `iniciar.bat` passa a verificar a consulta ao fuso e instalar as dependências quando necessário.

A interface distingue uma importação confirmada de uma falha posterior ao atualizar o painel. Os arquivos concluídos permanecem marcados e não são reenviados pela mesma fila. Erros de servidor mostram o código HTTP e indicam `compras_erros.log` para diagnóstico. Se os registros já aparecem como importados, atualize o programa e recarregue a página; não reimporte a planilha. Banco e senhas existentes são preservados.

Atualização pelo PowerShell:

```powershell
& "C:\Sonifarmacompras\ATUALIZAR_SONIFARMA.bat"
```
