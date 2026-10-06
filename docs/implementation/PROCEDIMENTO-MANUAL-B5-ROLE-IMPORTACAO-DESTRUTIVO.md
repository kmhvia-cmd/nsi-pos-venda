# Procedimento Manual — Role `nsi_importacao` (B5.3)

**Natureza deste documento:** procedimento operacional manual. Não é uma ADR e não é executado por nenhum teste automatizado, script de CI ou comando de aceite. Cobre a execução real do provisionamento da role `nsi_importacao` e os cenários destrutivos de `scripts/postgres_local/provisionar_b5_role_importacao.sql` e de `scripts/postgres_local/desprovisionar_b5_role_importacao.sql`.

**Subordinação:** ADR-010 (Seção 16) e Especificação Técnica da Sprint B (`docs/implementation/SPRINT-B-ESPECIFICACAO-TECNICA.md`, Seção 18, B5.2, itens 4, 17, 18 e 20). Complementa, sem alterar, `PROCEDIMENTO-MANUAL-B3-DESTRUTIVO.md` e `PROCEDIMENTO-MANUAL-B4-ROLE-CONGELAMENTO-DESTRUTIVO.md`.

**Status:** DOCUMENTO VIVO. A Seção 2 (provisionamento real) é executada no cluster local principal, pelo operador. As Seções 4 a 9 (cenários destrutivos) permanecem **não executadas** até autorização humana explícita e separada, cenário a cenário, e nunca rodam contra `nsi_dev`/`nsi_test`.

---

## 1. O que é diferente nesta role

`nsi_importacao` é a primeira role do projeto criada com `LOGIN` depois da B3.1, e a única com acesso a um só banco:

- tem `CONNECT` e `USAGE` no schema **somente em `nsi_test`** (ADR-010, Seções 16.2 e 21);
- não pertence a nenhuma role e não tem membros;
- recebe `EXECUTE` somente nas quatro funções de importação, e somente pela migration `0006`;
- é criada **sem senha**. A senha é definida pelo operador, fora dos scripts.

## 2. Provisionamento real (cluster local principal)

Pré-requisitos: B3.1 e B4.3 provisionadas; `nsi_dev` e `nsi_test` na mesma revisão, `0005` ou `0006`.

1. **Primeira execução**, no PowerShell, na raiz do repositório. O psql pede a senha do superusuário local, e a saída fica gravada num log:

   ```powershell
   & "C:\Program Files\PostgreSQL\17\bin\psql.exe" -h localhost -p 5432 -U postgres -d postgres -X -f scripts/postgres_local/provisionar_b5_role_importacao.sql 2>&1 | Tee-Object -FilePath "$env:TEMP\b5_provisionamento_1.log"
   ```

   Resultado esperado: `provisionar_b5_role_importacao.sql concluido - Fase 3 (pos-validacao completa) passou integralmente.`

2. **Definir a senha da role**, interativamente, como superusuário:

   ```powershell
   & "C:\Program Files\PostgreSQL\17\bin\psql.exe" -h localhost -p 5432 -U postgres -d postgres -X
   ```

   Dentro do psql: `\password nsi_importacao`. A senha nunca é escrita em arquivo versionado, em log nem em linha de comando.

3. **Configurar a URL no `.env` local** (fora do versionamento), no mesmo formato das outras variáveis funcionais: a variável `TEST_DATABASE_URL_NSI_IMPORTACAO`, com o usuário `nsi_importacao` e o banco `nsi_test`. A variável `DATABASE_URL_NSI_IMPORTACAO` **não** é configurada na B5: a role não tem `CONNECT` em `nsi_dev`.

4. **Segunda execução** do mesmo comando do passo 1, com o log em `b5_provisionamento_2.log`. Ela é exigida pelo critério de aceite 1 da B5.2. Resultado esperado: as três ações da Fase 2 respondem "ja presente, nada a fazer", e a Fase 3 passa integralmente. A reexecução nunca toca a senha.

5. **Conferência automatizada**, somente leitura:

   ```powershell
   $env:NSI_REQUIRE_PG_TESTS = "1"; $env:NSI_DATABASE_ENV = "test"
   .venv\Scripts\python.exe -m pytest tests/integration/test_provisionamento_b5_role_importacao.py -q
   ```

Na saída do psql no PowerShell 5.1, as linhas `NOTA` aparecem embrulhadas como `NativeCommandError`. Isso não é falha: é o tratamento que o PowerShell dá à saída de erro padrão do psql.

## 3. Por que os cenários destrutivos nunca rodam contra `nsi_dev`/`nsi_test`

Os caminhos destrutivos (role pré-existente em forma incompatível, concessão indevida em `nsi_dev`, desprovisionamento completo, desprovisionamento bloqueado pela `0006`) exigem *de fato* colocar o cluster num estado incompatível ou *de fato* remover a role. No cluster principal, isso exigiria reverter a `0006`, o que é proibido em `nsi_dev`.

Por isso, esses cenários só rodam numa instância PostgreSQL 17 local, descartável e isolada, preparada como na Seção 2 de `PROCEDIMENTO-MANUAL-B3-DESTRUTIVO.md`, com a B3.1 e a B4.3 provisionadas nela e as migrations na revisão exigida pelo cenário.

**Limitação a resolver antes de qualquer execução:** os dois scripts exigem a porta `5432`. Como no procedimento da B4.3, o operador escolhe antes de começar entre (a) uma cópia local dos scripts com a verificação de porta adaptada, nunca versionada e destruída ao final, ou (b) a instância descartável na porta `5432` com a instância principal parada durante todo o cenário.

## 4. Cenário — role pré-existente com atributo incompatível

**Objetivo:** confirmar que o provisionamento aborta na Fase 1, sem nenhuma escrita.

1. Instância descartável na revisão `0005`.
2. Crie a role incompatível: `CREATE ROLE nsi_importacao NOLOGIN;`
3. Execute `provisionar_b5_role_importacao.sql`.
4. **Resultado esperado:** `Role nsi_importacao ja existe com atributos incompativeis (canlogin=f, ...). Abortando na preflight, sem nenhuma alteracao.` A role permanece como foi criada.

## 5. Cenário — membership indevida

**Objetivo:** confirmar que qualquer membership de `nsi_importacao` aborta o provisionamento (ADR-010, Seção 16.2).

1. Instância descartável na revisão `0005`, com a role já provisionada uma vez.
2. Crie uma role de prova e conceda a ela uma membership proibida: `CREATE ROLE prova_membro NOLOGIN; GRANT nsi_importacao TO prova_membro;` (Não use `nsi_aplicacao` como membro: nesse caso quem aborta primeiro é a verificação do estado da B4.3, com outra mensagem.)
3. Execute novamente o provisionamento.
4. **Resultado esperado:** `Role nsi_importacao com membership inesperada (pertence_a=0, membros=1; esperado zero e zero - ADR-010, Secao 16.2). Abortando na preflight, sem nenhuma alteracao.` A membership proibida permanece: o script nunca a corrige.

## 6. Cenário — `CONNECT` indevido em `nsi_dev`

**Objetivo:** confirmar que uma concessão de banco fora de `nsi_test` aborta o provisionamento.

1. Instância descartável na revisão `0005`, com a role provisionada.
2. Conceda o acesso proibido: `GRANT CONNECT ON DATABASE nsi_dev TO nsi_importacao;`
3. Execute novamente o provisionamento.
4. **Resultado esperado:** `Role nsi_importacao possui 1 dependencia(s) inesperada(s) no cluster (...). Abortando na preflight, sem nenhuma alteracao.` A concessão indevida permanece: o script nunca a corrige.

## 7. Cenário — desprovisionamento bloqueado pela `0006`

**Objetivo:** confirmar que o desprovisionamento aborta na Fase 1, antes do prompt de confirmação.

1. Instância descartável na revisão `0006`, com a role provisionada.
2. Execute `desprovisionar_b5_role_importacao.sql`.
3. **Resultado esperado:** aborto na Fase 1, porque a role tem concessões em função que só existem com a `0006` (`Role nsi_importacao possui ... dependencia(s) inesperada(s) no cluster (aceito somente CONNECT em nsi_test e ACL em schema de nsi_test). Abortando na preflight, sem nenhuma alteracao.`). O prompt não chega a aparecer.

## 8. Cenário — confirmação textual incorreta

1. Instância descartável na revisão `0005`, com a role provisionada.
2. Execute o desprovisionamento e digite qualquer texto diferente de `CONFIRMO-DESPROVISIONAR-NSI-B5-ROLE-IMPORTACAO`.
3. **Resultado esperado:** `Confirmacao incorreta ou ausente - encerrando sem nenhuma alteracao.` Role, `CONNECT` e `USAGE` permanecem intactos.

## 9. Cenário — ciclo completo

**Objetivo:** confirmar que a reversão remove exatamente os efeitos do provisionamento e que o provisionamento volta a convergir.

1. Instância descartável na revisão `0006`, com a role provisionada.
2. Reverta a `0006` **exclusivamente pelo Alembic**, nos dois bancos da instância descartável: `alembic downgrade 0005`.
3. Feche qualquer sessão aberta como `nsi_importacao`: a remoção da role é bloqueada enquanto houver sessão dela.
4. Execute o desprovisionamento e digite a frase exata.
5. **Resultado esperado:** `desprovisionar_b5_role_importacao.sql concluido - Fase 3 (pos-validacao completa) passou integralmente.` A role não existe mais; as roles da B3.1, `nsi_congelamento`, os migrators e `PUBLIC` estão exatamente como antes.
6. Execute o provisionamento de novo, redefina a senha e aplique `alembic upgrade 0006`. Confirme por leitura que `nsi_importacao` tem `EXECUTE` somente nas quatro funções de importação.
7. Destrua a instância inteira.

---

## 10. Registro de execução

| Data | Etapa ou cenário | Resultado | Ajuste necessário? |
|---|---|---|---|
| 2026-10-06 | Seção 2, primeira execução do provisionamento (`nsi_dev` e `nsi_test` em `0005`) | esperado: Fase 1 sem escrita; as três ações executadas (role criada sem senha, `CONNECT` em `nsi_test`, `USAGE` no schema); Fase 3 passou integralmente nos passos 3.1 a 3.6 | não |
| 2026-10-06 | Seção 2, segunda execução do provisionamento | esperado: as três ações responderam "ja presente, nada a fazer"; Fase 3 passou integralmente. Os dois logs diferem só no resumo da Fase 1 e nas três mensagens de ação | não |

---

## 11. Pendências registradas na revisão da B5.3

Nenhuma delas foi resolvida por alteração de lógica: dependem de decisão humana ou pertencem a outra subetapa.

| # | Pendência | Situação atual | Depende de |
|---|---|---|---|
| 1 | **Alcance efetivo do acesso da role.** A ADR-010 (Seção 16.2) fala em `CONNECT` somente em `nsi_test`. O PostgreSQL concede a `PUBLIC`, por padrão, `CONNECT` no banco de manutenção `postgres` e `TEMPORARY` nos bancos, e a B3.1 e a B4.3 não alteraram esses padrões. Por isso `nsi_importacao`, como toda role com `LOGIN`, consegue conectar ao banco `postgres`, que não contém dado do projeto, e criar objetos temporários em `nsi_test`. | O script concede e confere o `CONNECT` nominal somente em `nsi_test` e a ausência de `CONNECT` efetivo em `nsi_dev`. O alcance está declarado no cabeçalho do script ("ALCANCE DE NENHUM OUTRO PRIVILEGIO"). | decisão humana: aceitar o alcance, ou revogar esses privilégios de `PUBLIC` por ato administrativo separado, que afeta todas as roles do cluster |
| 2 | **Sessões abertas no desprovisionamento.** As sessões da role só são conferidas na última ação (remoção). Com uma sessão aberta, as duas primeiras ações revogam `USAGE` e `CONNECT` e a terceira aborta. | O estado resultante (role presente, sem concessões) é aceito pela Fase 1, e o script é reexecutável depois de fechar a sessão. O lembrete 5 do script e o cenário 9 deste documento mandam fechar as sessões antes. | decisão humana: conferir as sessões também na Fase 1, o que altera a lógica do script |
| 3 | **Exigências sobre a migration `0006` (B5.4).** A Fase 3 do provisionamento só passa depois da `0006` se (a) a migration conceder a `nsi_importacao` o `EXECUTE` das quatro funções de importação **nos dois bancos**, inclusive em `nsi_dev`, onde a concessão fica inerte, e (b) toda função nova do schema `nsi_operacional`, inclusive as funções de trigger, tiver o `EXECUTE` de `PUBLIC` revogado. | Requisito a cumprir pela B5.4. Se não for cumprido, a reexecução do provisionamento aborta na Fase 3, sem alterar nada. | implementação da B5.4 |
| 4 | **Senha da role.** Entre a primeira execução e a definição da senha, a role existe com `LOGIN` e sem senha. O cluster usa `scram-sha-256`, e uma role sem senha não autentica. | Coberto pelo passo 2 da Seção 2: definir a senha logo depois da primeira execução. | operador |
