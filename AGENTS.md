# Instruções de manutenção

Depois de cada alteração entregue ao usuário, inclua os comandos de atualização na resposta final e atualize ATUALIZAR.md e a versão do pacote quando pertinente. O usuário opera no Windows; o destino original é C:\Sonifarmacompras.

Preserve compras.sqlite3 e os usuários/senhas existentes. Use banco temporário em testes via SONIFARMA_COMPRAS_DB. Nunca execute testes sobre o banco original. Não publique bancos nem credenciais no Git. Não inclua senhas reais em logs ou documentação; a senha inicial de instalação deve ser substituída no primeiro acesso.

A identidade visual segue Sonifarma/SonifarmaCRM. Use o checkout existente, sem criar worktrees automaticamente. Rode os testes funcionais e de autenticação antes da entrega.
