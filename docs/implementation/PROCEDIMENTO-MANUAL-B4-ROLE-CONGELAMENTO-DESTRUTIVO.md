# Procedimento Manual — Cenários Destrutivos da Role `nsi_congelamento` (B4.3)

**Natureza deste documento:** procedimento operacional manual. Não é uma ADR e não é executado por nenhum teste automatizado, script de CI ou comando de aceite. Cobre exclusivamente os cenários destrutivos de `scripts/postgres_local/provisionar_b4_role_congelamento.sql` e de `scripts/postgres_local/desprovisionar_b4_role_congelamento.sql` que, pela mesma decisão de segurança da B3.1, **nunca** rodam contra o cluster PostgreSQL local compartilhado (`nsi_dev`/`nsi_test`).

**Subordinação:** ADR-009 (Seções 11 e 21) e Especificação Técnica da Sprint B (`docs/implementation/SPRINT-B-ESPECIFICACAO-TECNICA.md`, Seção 18, B4.3 — "Role `nsi_congelamento`" e "Critérios de rollback"). Complementa, sem alterar, `docs/implementation/PROCEDIMENTO-MANUAL-B3-DESTRUTIVO.md`.

**Status:** DOCUMENTO VIVO — nenhum dos cenários abaixo foi executado. Permanecem **não executados** até autorização humana explícita e separada, cenário a cenário.

---

## 1. Por que estes cenários nunca rodam contra `nsi_dev`/`nsi_test`

Os caminhos destrutivos destes scripts — uma role `nsi_congelamento` pré-existente em forma incompatível, uma membership de `nsi_aplicacao` fora da exceção da ADR-009, o desprovisionamento completo, o desprovisionamento bloqueado pela presença da `0005` — exigem *de fato* colocar o cluster num estado incompatível ou *de fato* remover a role.

Em `nsi_dev`/`nsi_test`, isso exigiria ainda reverter a `0005`, o que é proibido em `nsi_dev` (Seção 18, "Critérios de rollback": nenhum `downgrade` em `nsi_dev`) e deixaria `nsi_test` fora do head em que a suíte roda. Por isso: **estes cenários só rodam numa instância PostgreSQL 17 local, descartável e isolada — nunca `nsi_dev`, nunca `nsi_test`, nunca qualquer cluster com dados de outra pessoa.**

**Limitação a resolver antes de qualquer execução:** os dois scripts exigem a porta `5432` e recusam qualquer outra (proteção inicial deliberada). A instância descartável do procedimento da B3 usa outra porta (`5433`) justamente para nunca coincidir com a principal. Executar estes cenários exige, portanto, **uma de duas condições, decididas pelo operador antes de começar:** (a) uma cópia local dos dois scripts com a verificação de porta adaptada, nunca versionada e destruída ao final; ou (b) a instância descartável na porta `5432` com a instância principal parada durante todo o cenário. Este documento não escolhe entre as duas — nenhuma delas altera os scripts versionados.

---

## 2. Preparar a instância descartável

Siga a Seção 2 de `PROCEDIMENTO-MANUAL-B3-DESTRUTIVO.md` (instância própria via `initdb`/`pg_ctl`, identidade confirmada antes de qualquer passo, destruição integral ao final de cada cenário), resolvendo antes a limitação de porta da Seção 1 acima. Depois, nessa instância:

1. replique o pré-requisito de B2 (dois bancos, dois migrators, schema `nsi_operacional`);
2. execute `provisionar_b3_roles.sql` (B3.1);
3. aplique as migrations até a revisão exigida pelo cenário — `alembic upgrade 0004` ou `alembic upgrade 0005`, com a mesma revisão nos dois bancos.

Nunca aponte o Alembic para `nsi_dev`/`nsi_test` durante estes cenários: confirme a URL de destino de cada comando antes de executá-lo.

---

## 3. Cenário — role `nsi_congelamento` pré-existente com atributo incompatível

**Objetivo:** confirmar que `provisionar_b4_role_congelamento.sql` aborta na Fase 1, sem nenhuma escrita, quando a role já existe com atributo de segurança diferente do aprovado.

1. Instância descartável na revisão `0004` (Seção 2).
2. Crie manualmente a role incompatível: `CREATE ROLE nsi_congelamento NOLOGIN CREATEDB;`
3. Execute `provisionar_b4_role_congelamento.sql`.
4. **Resultado esperado:** aborto na Fase 1 com `Role nsi_congelamento ja existe com atributos incompativeis (..., createdb=t, ...). Abortando na preflight, sem nenhuma alteracao.` Nenhuma membership concedida, nenhum `USAGE` concedido, e a role continua exatamente como foi criada (o script nunca a corrige).

## 4. Cenário — membership de `nsi_aplicacao` fora da exceção da ADR-009

**Objetivo:** confirmar que o provisionamento aborta na Fase 1 quando `nsi_aplicacao` pertence a alguma role em forma diferente da única exceção aprovada (ADR-009, Seção 21).

1. Instância descartável na revisão `0004`, com a role já provisionada uma vez (execução normal do script).
2. Altere manualmente a membership para uma forma proibida: `REVOKE nsi_congelamento FROM nsi_aplicacao; GRANT nsi_congelamento TO nsi_aplicacao WITH INHERIT TRUE, SET TRUE;`
3. Execute novamente `provisionar_b4_role_congelamento.sql`.
4. **Resultado esperado:** aborto na Fase 1 com `nsi_aplicacao possui membership inesperada (...; aceito: nenhuma, ou exatamente uma em nsi_congelamento com inherit=false, set=true, admin=false - ADR-009, Secao 21). Abortando na preflight, sem nenhuma alteracao.` A membership proibida permanece como estava — nunca é corrigida silenciosamente.

## 5. Cenário — desprovisionamento bloqueado pela `0005`

**Objetivo:** confirmar que `desprovisionar_b4_role_congelamento.sql` aborta na Fase 1, antes do prompt de confirmação e sem nenhuma escrita, enquanto a `0005` estiver aplicada.

1. Instância descartável na revisão `0005`, com a role provisionada.
2. Execute `desprovisionar_b4_role_congelamento.sql`.
3. **Resultado esperado:** aborto na Fase 1 com `nsi_operacional.alembic_version em <banco> esta em revisao 0005 - aceito: somente 0004 (a 0005 deve ser revertida antes, exclusivamente pelo downgrade do Alembic). Abortando na preflight, sem nenhuma alteracao.` O prompt de confirmação não chega a aparecer; role, membership, `USAGE` e `EXECUTE` permanecem intactos.

## 6. Cenário — confirmação textual incorreta

**Objetivo:** confirmar que o gate de confirmação encerra o desprovisionamento sem nenhuma alteração quando a frase não é digitada exatamente.

1. Instância descartável na revisão `0004`, com a role provisionada.
2. Execute `desprovisionar_b4_role_congelamento.sql` e, no prompt, digite qualquer texto diferente de `CONFIRMO-DESPROVISIONAR-NSI-B4-ROLE-CONGELAMENTO` (ou apenas Enter).
3. **Resultado esperado:** `Confirmacao incorreta ou ausente - encerrando sem nenhuma alteracao.` Role, membership e `USAGE` nos dois bancos permanecem intactos.

## 7. Cenário — ciclo completo: reverter a `0005`, desprovisionar e reprovisionar

**Objetivo:** confirmar, do início ao fim, que a reversão administrativa remove exatamente os efeitos do provisionamento e que o provisionamento volta a convergir depois dela.

1. Instância descartável na revisão `0005`, com a role provisionada.
2. Reverta a `0005` **exclusivamente pelo Alembic**, nos dois bancos da instância descartável: `alembic downgrade 0004`. O script de desprovisionamento nunca remove as funções nem revoga `EXECUTE`.
3. Execute `desprovisionar_b4_role_congelamento.sql`; digite a frase exata quando solicitado.
4. **Resultado esperado:** `desprovisionar_b4_role_congelamento.sql concluido - Fase 3 (pos-validacao completa) passou integralmente.` A role `nsi_congelamento` não existe mais; `nsi_aplicacao` não pertence a nenhuma role; as quatro roles da B3.1, os migrators, `PUBLIC` sem `CONNECT`, a propriedade do schema e `alembic_version` estão exatamente como antes.
5. Execute novamente `provisionar_b4_role_congelamento.sql`. **Resultado esperado:** `provisionar_b4_role_congelamento.sql concluido - Fase 3 (pos-validacao completa) passou integralmente.`
6. Aplique `alembic upgrade 0005` e confirme por leitura a matriz de `EXECUTE` das cinco funções (`EXECUTE` de `fn_registrar_congelamento` somente para `nsi_congelamento`).
7. Destrua a instância inteira.

---

## 8. Registro de execução

Nenhum destes cenários foi executado. Quando um operador humano executar qualquer um deles, registre aqui: data, cenário, opção usada para a limitação de porta (Seção 1), resultado (esperado/inesperado) e se algum ajuste nos scripts versionados foi necessário.

| Data | Cenário | Opção de porta | Resultado | Ajuste necessário? |
|---|---|---|---|---|
| — | — | — | — | — |
