# Procedimento Manual — Roles `nsi_envio` e `nsi_webhook` (C3)

**Natureza deste documento:** procedimento operacional manual. Não é uma ADR e não é executado por nenhum teste automatizado. Cobre a execução real de `scripts/postgres_local/provisionar_c3_roles_envio.sql` e as condições de `desprovisionar_c3_roles_envio.sql`.

**Subordinação:** ADR-011 (Seção 11) e `SPRINT-C-ESPECIFICACAO-TECNICA.md` (Seção 3). Complementa, sem alterar, os procedimentos manuais da B3 à B6.

**Status:** DOCUMENTO VIVO. A Seção 2 é executada pelo operador, com o superusuário local. A Seção 4 (reversão) permanece **não executada**.

---

## 1. O que são estas roles

- `nsi_envio` registra os quatro eventos de envio; `nsi_webhook`, os dois eventos de notificação da plataforma.
- As duas têm `LOGIN` e credencial própria, `CONNECT` em `nsi_dev` e em `nsi_test` e `USAGE` no schema. **Não pertencem a nenhuma role e não têm membros.**
- O script não concede `EXECUTE`: isso é feito pela migration `0007`.
- São criadas **sem senha**. As senhas são definidas pelo operador, fora dos scripts.

## 2. Provisionamento (cluster local principal)

Pré-requisitos: `nsi_dev` e `nsi_test` na mesma revisão (`0006` ou `0007`); o ambiente de ensaio da B6 descartado.

**Antes de começar:** depois deste provisionamento, os scripts da B3.1, da B4.3, da B5.3 e da B6 deixam de ser reexecutáveis sem adaptação, porque não conhecem as duas roles novas. Se a confirmação do critério de aceite 1 da B5 (duas execuções do script de `nsi_importacao`) ainda for desejada, ela precisa ocorrer **antes** deste passo.

1. **Execução**, no PowerShell, na raiz do repositório:

   ```powershell
   & "C:\Program Files\PostgreSQL\17\bin\psql.exe" -h localhost -p 5432 -U postgres -d postgres -X -f scripts/postgres_local/provisionar_c3_roles_envio.sql
   ```

   Resultado esperado: `provisionar_c3_roles_envio.sql concluido - Fase 3 (pos-validacao completa) passou integralmente.`

2. **Definir as senhas**, interativamente, como superusuário: dentro do psql, `\password nsi_envio` e `\password nsi_webhook`. A senha nunca é escrita em arquivo versionado, em log nem em linha de comando.

3. **Configurar o `.env` local** (fora do versionamento) com quatro variáveis, no formato `postgresql://usuario:senha@localhost:5432/banco`, **sem** sufixo de driver e com caracteres especiais da senha codificados (`$` vira `%24`):

   | Variável | Usuário | Banco |
   |---|---|---|
   | `DATABASE_URL_NSI_ENVIO` | `nsi_envio` | `nsi_dev` |
   | `TEST_DATABASE_URL_NSI_ENVIO` | `nsi_envio` | `nsi_test` |
   | `DATABASE_URL_NSI_WEBHOOK` | `nsi_webhook` | `nsi_dev` |
   | `TEST_DATABASE_URL_NSI_WEBHOOK` | `nsi_webhook` | `nsi_test` |

4. **Reexecução** do comando do passo 1 é segura: as duas ações de criação respondem "ja presente, nada a fazer", e a senha nunca é tocada.

Na saída do psql no PowerShell 5.1, as linhas `NOTA` podem aparecer embrulhadas como `NativeCommandError`. Isso não é falha.

## 3. O que vem depois

A migration `0007` (Subetapa C4) exige as duas roles e aborta se não existirem. Ela concede a `nsi_envio` as funções de envio e as três funções de claim de que o envio depende, e a `nsi_webhook` as duas funções de notificação.

## 4. Reversão

`desprovisionar_c3_roles_envio.sql` remove as duas roles e suas concessões. Exige a frase `CONFIRMO-DESPROVISIONAR-NSI-C3-ROLES-ENVIO`, não derruba sessão e **aborta se a `0007` estiver aplicada** em `nsi_dev` ou em `nsi_test`. Como nenhum `downgrade` é permitido em `nsi_dev`, a reversão só é executável enquanto `nsi_dev` estiver em `0006`.

## 5. Falhas

| Sinal | Causa | Ação |
|---|---|---|
| "O ambiente de ensaio da B6 existe" | `nsi_ensaio` ainda presente | descartar o ambiente de ensaio e executar de novo |
| "existe com atributos diferentes" ou "membership(s)" | uma das roles foi criada ou alterada fora do script | nada foi escrito; investigar antes de qualquer correção manual |
| "fora das revisoes 0006 e 0007" | bancos em revisão não prevista | nada foi escrito; conferir as migrations |
| Falha no meio da Fase 2 | interrupção | executar de novo: o script converge a partir de qualquer estado previsto |
