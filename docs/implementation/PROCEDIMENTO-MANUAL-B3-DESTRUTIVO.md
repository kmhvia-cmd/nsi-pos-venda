# Procedimento Manual — Cenários Destrutivos da Sprint B3.1

**Natureza deste documento:** procedimento operacional manual. Não é uma ADR e não é executado por nenhum teste automatizado, script de CI ou comando de aceite. Cobre exclusivamente os cenários destrutivos do script administrativo `scripts/postgres_local/provisionar_b3_roles.sql` e de `scripts/postgres_local/desprovisionar_b3_roles.sql` que, por decisão de segurança aprovada na PARTE 2A, **nunca** podem rodar automaticamente contra o cluster PostgreSQL local compartilhado (`nsi_dev`/`nsi_test`).

**Subordinação:** Especificação Técnica da Sprint B (`docs/implementation/SPRINT-B-ESPECIFICACAO-TECNICA.md`), ADR-008, Parte 1 da B3 e as correções de segurança da PARTE 2A já aprovadas na conversa de planejamento.

**Status:** DOCUMENTO VIVO — nenhuma execução real registrada nesta sessão. Este arquivo é criado como parte do escopo autorizado da B3.1 (item 7 do escopo de arquivos); os procedimentos aqui descritos permanecem **não executados** até autorização humana explícita e separada, cenário a cenário.

---

## 1. Por que estes cenários nunca rodam contra `nsi_dev`/`nsi_test`

`provisionar_b3_roles.sql` e `desprovisionar_b3_roles.sql` são scripts administrativos que criam, alteram e removem roles, propriedade de schema e ACLs de `CONNECT`/`USAGE` no cluster PostgreSQL local. Testar os caminhos **destrutivos** desses scripts — uma role pré-existente com atributo incompatível, um desprovisionamento completo, um desprovisionamento bloqueado por revisão diferente de `0001`, ou a prova de que uma role sem `GRANT` é efetivamente recusada pelo servidor — exige *de fato* colocar o cluster num estado incompatível ou *de fato* remover roles reais.

Fazer isso contra `nsi_dev`/`nsi_test` significaria, na melhor hipótese, recriar trabalho manual já feito (senhas definidas via `\password`, `.env` configurado); na pior hipótese, corromper um ambiente de desenvolvimento compartilhado sem volta fácil. Por isso, a decisão aprovada é: **estes cenários só rodam num cluster PostgreSQL 17 local, descartável e isolado — nunca `nsi_dev`, nunca `nsi_test`, nunca qualquer cluster com dados reais de outra pessoa.**

Este ambiente de trabalho não tem Docker nem `testcontainers` instalados (confirmado nesta sessão de planejamento — `docker --version` não encontrado). O procedimento abaixo assume uma segunda instância local do PostgreSQL 17, iniciada com `initdb`/`pg_ctl` numa porta e diretório de dados diferentes dos usados por `nsi_dev`/`nsi_test` — nunca a mesma instância.

---

## 2. Preparar o cluster descartável

Execute isto **apenas** numa máquina de desenvolvimento pessoal, nunca num servidor compartilhado.

```powershell
# Escolha um diretório de dados e uma porta que NUNCA coincidam com a
# instância principal (a que hospeda nsi_dev/nsi_test, porta 5432).
$env:PGDATA_DESCARTAVEL = "$HOME\pgdata-b3-descartavel"
$PORTA_DESCARTAVEL = 5433

initdb -D $env:PGDATA_DESCARTAVEL -U postgres --auth=trust
pg_ctl -D $env:PGDATA_DESCARTAVEL -o "-p $PORTA_DESCARTAVEL" -l "$env:PGDATA_DESCARTAVEL\log.txt" start
```

Confirme a identidade da instância antes de qualquer passo seguinte — mesma disciplina dos scripts versionados:

```powershell
psql -U postgres -h localhost -p $PORTA_DESCARTAVEL -d postgres -c "SELECT version(), current_database(), inet_server_port();"
```

Replique o pré-requisito de B2 nesta instância descartável (os dois migrators, os dois bancos, o schema) — copie e adapte `scripts/postgres_local/provisionar_dev_teste.sql`, apontando para `$PORTA_DESCARTAVEL` em vez de `5432`. **Nunca** rode o script de B2 original sem revisar a porta - ele contém uma verificação de porta `5432` que abortará a execução se você esquecer de adaptá-la, o que é o comportamento correto caso a variável de porta não tenha sido realmente trocada.

Ao final de cada cenário abaixo, destrua a instância inteira:

```powershell
pg_ctl -D $env:PGDATA_DESCARTAVEL stop
Remove-Item -Recurse -Force $env:PGDATA_DESCARTAVEL
```

---

## 3. Cenário — role pré-existente com atributo incompatível

**Objetivo:** confirmar que `provisionar_b3_roles.sql` aborta na Fase 1 (preflight), sem criar nem alterar nada, quando uma das quatro roles já existe com um atributo de segurança diferente do exigido.

1. Prepare o cluster descartável (Seção 2) e replique o pré-requisito de B2.
2. Antes de rodar `provisionar_b3_roles.sql`, crie manualmente uma role incompatível:
   ```sql
   CREATE ROLE nsi_aplicacao LOGIN CREATEDB;
   ```
3. Rode `provisionar_b3_roles.sql` contra esta instância (ajustando a porta na string de conexão do `psql`).
4. **Resultado esperado:** o script aborta na Fase 1, com a mensagem `Role nsi_aplicacao ja existe com atributos incompativeis (..., createdb=t, ...)`. Nenhuma outra role foi criada; `nsi_aplicacao` continua exatamente como foi criada manualmente (o script nunca tenta corrigi-la).
5. Confirme por leitura direta: `SELECT rolname, rolcreatedb FROM pg_roles WHERE rolname = 'nsi_aplicacao';` deve mostrar `rolcreatedb = t` — inalterado.

---

## 4. Cenário — desprovisionamento completo

**Objetivo:** confirmar que `desprovisionar_b3_roles.sql`, do início ao fim, remove exatamente as quatro roles funcionais, preserva o `CONNECT` dos migrators, e nunca concede `CONNECT` de volta a `PUBLIC`.

1. Prepare o cluster descartável e replique o pré-requisito de B2.
2. Rode `provisionar_b3_roles.sql` normalmente (primeira execução, sem incompatibilidade).
3. Confirme o estado pós-provisionamento (as mesmas verificações da Fase 3 do próprio script, ou as consultas equivalentes de `tests/integration/test_provisionamento_b3_roles.py`, adaptadas para a porta descartável).
4. Rode `desprovisionar_b3_roles.sql`. Confirme a leitura de `alembic_version` (deve estar em `0001` nos dois bancos — verdadeiro aqui, pois a migration `0002` da B3.2 ainda não existe). Digite a frase de confirmação exata quando solicitado.
5. **Resultado esperado:** as quatro roles (`nsi_eventos_owner`, `nsi_aplicacao`, `nsi_expiracao`, `nsi_operador_restrito`) não existem mais (`SELECT rolname FROM pg_roles WHERE rolname IN (...)` retorna zero linhas). `nsi_dev_migrator`/`nsi_test_migrator` continuam existindo, com `CONNECT` explícito preservado no próprio banco (consulta via `aclexplode`, mesma forma usada nos scripts). O schema `nsi_operacional` volta a pertencer ao migrator em cada banco.
6. Confirme que `PUBLIC` continua sem `CONNECT` em nenhum dos dois bancos (Seção 6 abaixo).

---

## 5. Cenário — desprovisionamento bloqueado por revisão diferente de `0001`

**Objetivo:** confirmar que o GATE 1 de `desprovisionar_b3_roles.sql` aborta **antes** do prompt de confirmação e antes de qualquer alteração, quando `alembic_version` não está exatamente em `0001`.

Este cenário só é executável de fato **depois** que a migration `0002` da B3.2 existir e puder ser aplicada — fora do escopo desta rodada (B3.1). Enquanto isso, um teste aproximado pode ser feito manualmente escrevendo uma segunda linha ou um valor diferente na própria tabela `alembic_version` de um cluster descartável:

```sql
UPDATE nsi_operacional.alembic_version SET version_num = '0099';
```

**Resultado esperado:** `desprovisionar_b3_roles.sql` aborta no GATE 1 com a mensagem `... esta em revisao 0099 - esperado exatamente '0001'`, antes de exibir o prompt de confirmação. Nenhuma role foi tocada.

Repita este cenário com validade plena assim que a B3.2 (migration `0002`) for aprovada e implementada, aplicando `alembic upgrade 0002` de verdade contra o cluster descartável antes de tentar o desprovisionamento.

---

## 6. Cenário — `PUBLIC` permanece sem `CONNECT`

**Objetivo:** confirmar, por leitura direta (nunca `has_database_privilege('public', ...)` — ver nota abaixo), que `PUBLIC` não tem `CONNECT` em nenhum dos dois bancos, tanto logo após o provisionamento quanto após o desprovisionamento.

```sql
SELECT d.datname, acl.privilege_type
  FROM pg_database d,
       aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) AS acl
 WHERE d.datname IN ('nsi_dev', 'nsi_test')
   AND acl.grantee = 0;
```

**Resultado esperado:** nenhuma linha com `privilege_type = 'CONNECT'` para nenhum dos dois bancos, em nenhum dos dois momentos (pós-provisionamento e pós-desprovisionamento).

**Nota sobre `has_database_privilege`:** `has_database_privilege('public', 'nsi_dev', 'CONNECT')` **não** deve ser usado — `'public'` (minúsculo, como string) é interpretado pelo PostgreSQL como o nome de uma role real, que normalmente não existe, produzindo um erro em vez de checar o pseudo-role `PUBLIC`. `grantee = 0` dentro de `aclexplode()` é a forma documentada e correta de identificar `PUBLIC`.

---

## 7. Cenário — privilégio efetivo de uma role sem `GRANT`

**Objetivo:** confirmar, conectando de fato como uma role sem nenhum privilégio concedido, que o servidor recusa `INSERT`/`SELECT`/`EXECUTE` — nunca apenas inferido a partir de metadados de ACL.

1. No cluster descartável, após provisionar B3.1 (Seção 2–3), crie uma role de prova, só para este teste, com senha temporária local:
   ```sql
   CREATE ROLE prova_sem_grants LOGIN PASSWORD 'apenas-para-teste-local-descartavel';
   GRANT CONNECT ON DATABASE nsi_dev TO prova_sem_grants;
   ```
2. Conecte como `prova_sem_grants` (`psql -U prova_sem_grants -h localhost -p $PORTA_DESCARTAVEL -d nsi_dev`).
3. Tente `SELECT 1 FROM nsi_operacional.claims;` (quando a tabela existir, após a B3.2) ou, nesta rodada (só B3.1, sem tabelas ainda), tente `SET ROLE nsi_eventos_owner;` — **deve ser recusado** (`prova_sem_grants` nunca recebeu essa membership).
4. **Resultado esperado:** todas as tentativas falham com erro de permissão do próprio servidor (`permission denied` / `must be a member of role`) — nunca um erro de sintaxe ou de objeto inexistente que mascare uma falha de teste.
5. Destrua o cluster descartável inteiro ao final (Seção 2) — a role `prova_sem_grants` e sua senha temporária nunca sobrevivem além deste cenário.

---

## 8. Registro de execução

Nenhum destes cenários foi executado nesta sessão de planejamento/implementação. Quando um operador humano executar qualquer um deles, registre aqui: data, cenário executado, resultado (esperado/inesperado), e se algum ajuste nos scripts versionados foi necessário como consequência.

| Data | Cenário | Resultado | Ajuste necessário? |
|---|---|---|---|
| — | — | — | — |
