# Sonifarma — Inteligência de Compras

Aplicação FastAPI + SQLite para importar necessidades/cotações, comparar fornecedores e gerar rascunhos em PDF/XLSX. A versão 1.10 segue a identidade visual do painel SonifarmaCRM: logotipo, turquesa #00a6ad, botões #00777d, laranja #ff6900, cartões e navegação responsiva.

## Executar

Python 3.12, a partir da pasta deste projeto:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8766
```

No Windows, execute `iniciar.bat` (agora funciona a partir da própria pasta) ou substitua `.venv/bin/python` por `.venv\Scripts\python.exe`. Acesse a porta 8766 localmente. A aplicação não depende de PostgreSQL nem da integração ERP do CRM.

## Dados e segurança

O banco original `compras.sqlite3` do ZIP foi preservado. Não publique bancos, credenciais ou ambientes virtuais no Git. Faça backup do banco antes de atualizar. `SONIFARMA_COMPRAS_DB` permite apontar para uma cópia isolada; o padrão continua sendo o banco ao lado de `app.py`. Um banco vazio recebe os dados iniciais de `amostras/comparativo_inicial.xlsx` quando esse arquivo local existe; caso contrário, inicia com um processo vazio. Planilhas comerciais não são publicadas no Git.

A V1.7 inclui login local próprio (admin e troca obrigatória da senha inicial), sessões de 12 horas, logout e alteração de senha. As contas não são compartilhadas com o CRM. Consulte ATUALIZAR.md para instalação, acesso e atualização com backup. O padrão continua sendo execução local em loopback.

## Melhorias e correções

- Identidade visual compartilhada, logotipo, menu utilizável no celular, foco de teclado e rótulos acessíveis.
- Histórico de decisões na interface, incluindo aprovação manual de vínculos.
- Remover uma escolha impede que a seleção automática a recrie ao atualizar. Uma seleção manual posterior continua permitida; a ação explícita de campeões aprovados também pode selecionar novamente.
- Indicadores distinguem insumos selecionados, escolhas manuais e campeões automáticos.
- Erros de API apresentados na interface, bloqueio de envio duplicado durante importação e proteção contra respostas de processos trocados rapidamente.
- Validação de nome do processo, processo inexistente, arquivos corrompidos e números não finitos; preços negativos não entram no cálculo do total.

A seleção automática original por nome exato e unidade igual continua sendo uma pré-seleção a conferir, sem comprovação de equivalência farmacotécnica. PDF tem extração conservadora; imagens/OCR não são suportados. Exportações continuam sendo rascunhos, sem envio de pedidos.

## Verificação

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
```

Os testes usam banco temporário e cobrem remoção persistente, preservação de escolha manual, estimativas, exportações PDF/XLSX, importação, auditoria, rejeição de vínculos entre processos e entradas inválidas. Também foi verificado no Chromium: carregamento dos 122 insumos da cópia do banco original, logotipo, expansão, busca, navegação móvel e ausência de erros JavaScript.

## Atualização

Consulte [os comandos de atualização para Windows](ATUALIZAR.md). Nunca sobrescreva o banco ao extrair um ZIP sobre uma instalação existente.

Versão 1.10 publicada em Sonifarma/SonifarnaCompras. O código não contém bancos nem planilhas comerciais.

V1.8: atualização por ZIP do GitHub sem Git instalado, seguindo o fluxo operacional do CRM; validação de sintaxe, manifesto de backup e restauração do código em caso de falha de cópia.

V1.9: validade superior a um ano na entrega, massa em g e cápsulas em milheiros, comparação com embalagem anterior, desembolso em embalagens inteiras, condições comerciais por fornecedor e simulações de transferência. Consulte ATUALIZAR.md para cadastro dos dados e limites das sugestões.

V1.10: controle operacional equivalente ao CRM (start/stop/restart/status/backup/verify/update), atalhos BAT, processo identificado, logs e verificação de resposta, backup ZIP com restauração temporária e atualização atômica por arquivo com recuperação de código. Consulte ATUALIZAR.md para a primeira migração e para atualizações pelo ATUALIZAR_SONIFARMA.bat.
