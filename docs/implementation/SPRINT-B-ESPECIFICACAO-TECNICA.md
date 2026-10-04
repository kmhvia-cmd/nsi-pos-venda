# Especificação Técnica — Sprint B: Persistência Imutável, Claims e Idempotência

**Natureza deste documento:** especificação técnica de implementação. **Não é uma ADR** — não fixa arquitetura nova, não redefine nem amplia nada já congelado na ADR-008. Traduz as decisões arquiteturais já aprovadas em desenho técnico concreto, mantendo explicitamente rastreadas as decisões que ainda dependem de aprovação humana ou de infraestrutura externa a este repositório.

**Subordinação:** integral à ADR-008 (APROVADA E CONGELADA) e ao `ROADMAP-SPRINTS-B-G.md`. Nenhuma frase deste documento pode contradizer a ADR-008; onde houver aparente tensão, a ADR-008 prevalece e este documento deve ser corrigido.

**Status:** DOCUMENTO VIVO — **B1 (esta especificação) CONCLUÍDA**; **B2 (Infraestrutura, Conexão e Migrations) CONCLUÍDA** (Seção 18); **B3.1 (Provisionamento administrativo, roles e isolamento) CONCLUÍDA** (Seção 18); **B3.2 (Migration `0002` — tabelas, constraints, índices e trigger defensiva) CONCLUÍDA** (Seção 18); **B3.3 (Migration `0003` — seis funções `SECURITY DEFINER`) CONCLUÍDA** (Seção 18); **B3.4 (Testes finais e documentação de encerramento da Sprint B3) CONCLUÍDA** (Seção 18). **Sprint B3 (B3.1–B3.4) integralmente CONCLUÍDA.** **B4.1 (decisão arquitetural do catálogo de eventos operacionais — ADR-009) CONCLUÍDA** (Seção 18); **B4.2 (Migration `0004` — schema relacional de lotes, registros de coleta e eventos operacionais) CONCLUÍDA** (Seção 18); **B4.3 (role `nsi_congelamento` e Migration `0005` — cinco funções `SECURITY DEFINER`) CONCLUÍDA** (Seção 18). B5–B7 pendentes, cada uma com autorização própria e separada.

**Autorização:** este documento, por si só, **não autoriza nenhuma implementação**. Cada subetapa (B2–B7) exige autorização própria, seguindo a mesma disciplina já usada nas Sprints A1–A3 (plano → aprovação → implementação → teste → diff → stage → commit → push). B7 exige autorização distinta de B5/B6 e está bloqueada por pré-requisitos próprios (Seção 14).

---

## 1. Relação com a ADR-008 e o ROADMAP

Implementa a fundação técnica da Sprint B delimitada por: ADR-008 §5 (PostgreSQL, escopo estrito), §6 (evento imutável/projeção corrente), §7-8 (claim, granularidade, token de posse), §9 (tempos aprovados), §10-13 (estados, catálogo fechado, heartbeat, expiração, proibição de reatribuição automática), §14 (fronteira com `numero_tentativa`), §15 (transação, idempotência, imutabilidade sem exceção), §16-17 (migração por corte controlado, preservação de JSONs), §18 (fronteira Sprint B / C-G); e `ROADMAP-SPRINTS-B-G.md`, seção Sprint B.

## 2. Estado Atual (resumo da auditoria técnica)

Nenhum banco de dados, driver, ORM ou ferramenta de migration instalados. Toda persistência hoje é `lote.json` por lote, mutável, reescrito por inteiro a cada mutação, protegido apenas por `threading.Lock` em memória, por processo (`adapters/storage.py::_obter_lock_lote`). `historico_versoes` (Sprint A3) é a única estrutura hoje próxima de um log append-only, mas vive dentro do mesmo arquivo mutável. Consumidores mapeados (`app.py`, `core/scheduler.py`, `integration/nsi_integration.py`, `services/webhook_handler.py`) não são alterados nesta especificação — a interface pública de `adapters/storage.py` é preservada; apenas seu backend interno muda, em sprints futuras.

## 3. Direção Técnica Consolidada

1. `psycopg` v3, modo síncrono.
2. Alembic standalone (sem exigir ORM completo).
3. Identidade global do evento (UUID4) separada da ordenação transacional (contador por agregado, com unicidade) separada do timestamp observável (`TIMESTAMPTZ`).
4. PostgreSQL como autoridade temporal única em produção — nunca o relógio de um worker.
5. Payload híbrido: colunas fixas para os campos comuns, `JSONB` para o específico de cada tipo de evento.
6. Credenciais lidas via `Config`/variáveis de ambiente; `.env` permitido somente em desenvolvimento local, nunca em produção.
7. **Token de posse: `secrets.token_urlsafe(32)` + `SHA-256` simples, sem HMAC/pepper nesta sprint** (decisão final, Seção 16).
8. Defesa em profundidade para imutabilidade, via funções `SECURITY DEFINER` restritas por role — nunca `GRANT`/`REVOKE` ingênuo de tabela distinguindo valor de coluna.
9. Nenhuma reatribuição automática, sob nenhuma circunstância.
10. Identidade do executor: `session_user` (confiável) + rótulo autodeclarado opcional (Seção 4).
11. B7 exige autorização própria, separada de B5 e B6.

---

## 4. Modelo de Identidade

| Conceito | Papel | Muda ao longo do tempo? |
|---|---|---|
| `registro_coleta_id` | escopo de exclusividade; chave primária da projeção de claim | não — nasce na ADR-007, imutável |
| `claim_id` | identidade de uma instância concreta de claim | sim — nova a cada `claim_criado`/`claim_reatribuido` |
| `token_de_posse` (ver 4.1) | credencial de posse da instância vigente | sim — regenerado junto com `claim_id` |
| `evento_id` | identidade global de cada evento (UUID4) | não |
| `aggregate_id` | = `registro_coleta_id` — escopo do fluxo contínuo de eventos | não |
| `aggregate_version`/`versao_atual` | contador monotônico, único por `(aggregate_id, versão)`, incrementado atomicamente **por todos os seis tipos de evento**, mesmo quando o estado de negócio não muda | sim |
| `occurred_at` | timestamp observável, `TIMESTAMPTZ`, nunca decide ordem | sim, mas nunca usado para correção lógica |

O agregado dos seis eventos de claim é o `registro_coleta_id` (não o `claim_id`) — um fluxo contínuo, atravessando múltiplas gerações de `claim_id` ao longo do tempo, inclusive reatribuições. `claim_reatribuido` carrega, no seu payload: `claim_id_anterior`, referência ao `evento_id` da revisão que autorizou, e `claim_id_novo` + novo token.

### 4.1 Proteção do Token de Posse (decisão final)

**Aprovado:** `token_bruto` gerado com `secrets.token_urlsafe(32)` (256 bits de entropia, formato deliberadamente distinto de um UUID); `token_hash = SHA-256(token_bruto)`, **sem HMAC/pepper nesta sprint** — a entropia do token já torna força bruta inviável, e um segredo adicional (pepper) não seria proporcional ao risco nesta etapa. **Uma evolução futura poderá adotar HMAC com pepper mediante decisão técnica formal própria — B3 implementa SHA-256 simples.**

**Fluxo único, coerente:**
1. **Geração** — Python: `token_bruto = secrets.token_urlsafe(32)`.
2. **Hash** — Python: `token_hash = hashlib.sha256(token_bruto.encode()).hexdigest()`.
3. **Passagem à função SQL** — apenas `token_hash`. **O `token_bruto` nunca trafega para o PostgreSQL**, nunca aparece em log de query, `pg_stat_statements`, ou qualquer persistência.
4. **Retorno ao chamador** — o próprio processo Python (que já tinha `token_bruto` em memória) o devolve; a função SQL nunca gera nem revela token.
5. **Validação (heartbeat/liberação)** — Python recalcula `hashlib.sha256(token_bruto_apresentado)` e envia só o hash resultante.
6. **Comparação decisiva** — **dentro do PostgreSQL**, por igualdade simples (`WHERE token_hash = :hash_apresentado`), como parte do **mesmo** `UPDATE` condicional que já muda o estado — elimina a janela de corrida entre "validar" e "mutar". Esta comparação **não** usa `hmac.compare_digest()` (função Python, não executável em SQL) — é aceitável porque o valor comparado é um hash de 256 bits: mesmo um canal lateral de tempo revelaria só o hash, cuja reversão ao token original exige quebrar a resistência a pré-imagem do SHA-256, computacionalmente inviável. `hmac.compare_digest()` continua tendo seu lugar correto: no lado Python, sempre que houver comparação local de hashes.

**Nunca persistido em texto puro:** nenhuma tabela, log ou evento grava `token_bruto`. `token_fingerprint` (se usado para correlação de auditoria) é derivado com domínio separado do `token_hash` (ex.: `HMAC-SHA256("fingerprint", token_bruto)[:8]`) — não decidido como obrigatório nesta sprint, candidato.

**Invalidação por reatribuição:** a projeção guarda um único `token_hash` vigente por `registro_coleta_id` — reatribuir sobrescreve esse valor; o token anterior deixa de corresponder a qualquer comparação futura, tornando-se definitivamente inutilizável, sem lista de revogação separada.

### 4.2 Comportamento Fail-Safe na Perda da Resposta de Criação/Reatribuição (decisão final)

Se o commit ocorreu mas a resposta contendo `token_bruto` se perdeu antes de chegar ao chamador (falha de rede): uma repetição com a mesma `idempotency_key` confirma `claim_id` e `expira_em`, **mas não reentrega nem reconstrói o token** — ele nunca foi persistido em lugar algum. O claim permanece `ativo` até expirar naturalmente (até 5 minutos); depois passa a `expirado_pendente_revisao`; **nenhuma reatribuição automática ocorre**; a recuperação exige o fluxo formal de revisão (Seção 17). Esta escolha privilegia segurança e integridade de dados, mesmo com custo operacional eventual — decisão final, não uma limitação a resolver nesta sprint.

### 4.3 Identidade do Executor (corrigida — `session_user`, nunca identidade humana)

`current_user`, dentro de uma função `SECURITY DEFINER`, é o **owner da função** (quem a executa de fato), **não** o chamador. A identidade confiável do chamador é `session_user` — fixada pela autenticação da conexão, imutável durante toda a sessão, impossível de forjar via SQL.

**`session_user` identifica a role de conexão que efetivamente chamou a função — nunca uma pessoa nem um worker individual.** É a garantia de QUAL PAPEL (aplicação normal, expiração automática, operador restrito) está agindo, não QUEM especificamente. A identidade humana individual (Sprint D) e a identidade granular de um worker específico são conceitos distintos, mais fracos, tratados a seguir.

| Camada | Fonte | Confiável para quê |
|---|---|---|
| `session_user` | autenticação da conexão PostgreSQL | identifica a **role** chamadora — nunca uma pessoa, nunca um worker específico |
| `app.worker_id` (via `SET LOCAL`) | autodeclarado pela aplicação | **rótulo informativo apenas** — nunca fonte de autorização; qualquer valor pode ser declarado sem conceder privilégio algum |
| Identidade humana individual | inexistente nesta sprint | **pendente da Sprint D** |

`SET LOCAL app.worker_id = '...'` vale apenas para a transação corrente, revertido automaticamente em `COMMIT`/`ROLLBACK` — sem limpeza explícita necessária, crítico sob *connection pooling*. O controle de acesso real vem exclusivamente de `GRANT EXECUTE`/pertencimento de role (checado pelo PostgreSQL antes do corpo da função rodar) e de `session_user` — **nenhum parâmetro textual de executor concede privilégio**. Um chamador que declare `app.worker_id = 'nsi_expiracao'` sem estar de fato conectado como a role `nsi_expiracao` não ganha privilégio nenhum — apenas produziria um rótulo de auditoria mentiroso, limitação documentada, não falha de controle de acesso.

`executado_por` é registrado como valor composto: `{"role": session_user, "worker_id": current_setting('app.worker_id', true)}`.

---

## 5. Modelo de Dados — Nomes Aprovados

**Schema:** `nsi_operacional`.

**Tabelas:**
- `nsi_operacional.claims` — projeção corrente, **uma linha por `registro_coleta_id`** (chave primária), nunca duplicada. Colunas candidatas: `registro_coleta_id` (PK), `claim_id`, `token_hash`, `estado` (`ativo`|`liberado`|`expirado_pendente_revisao`), `criado_em`, `expira_em`, `ultimo_heartbeat_em` (todos `TIMESTAMPTZ`), `versao_atual`.
- `nsi_operacional.eventos_claim` — log imutável. Colunas candidatas: `evento_id` (UUID4, PK), `aggregate_type`, `aggregate_id` (=`registro_coleta_id`), `aggregate_version`, `tipo` (catálogo fechado de 6), `claim_id`, `occurred_at TIMESTAMPTZ`, `executado_por JSONB`, `payload JSONB`. Constraints: `UNIQUE (aggregate_id, aggregate_version)`; `UNIQUE (claim_id) WHERE tipo='claim_expirado'`.
- `nsi_operacional.comandos_idempotentes` — mecanismo de idempotência persistente. Colunas candidatas: `comando`, `aggregate_id`, `idempotency_key`, `payload_hash`, `resultado JSONB`, `criado_em TIMESTAMPTZ`. Constraint: `UNIQUE (comando, aggregate_id, idempotency_key)`.

**Funções (todas `SECURITY DEFINER`, schema `nsi_operacional`):** `fn_criar_claim`, `fn_registrar_heartbeat`, `fn_liberar_claim`, `fn_materializar_expiracao`, `fn_registrar_revisao_abandono`, `fn_reatribuir_claim`.

**Roles conceituais** (nomes físicos podem receber prefixo de ambiente no provisionamento; responsabilidades e separação são obrigatórias):
- `nsi_eventos_owner` — `NOLOGIN`, dona das tabelas e funções.
- `nsi_aplicacao` — fluxo normal (criar, heartbeat, liberar; também `EXECUTE` em `fn_materializar_expiracao` para a checagem lazy).
- `nsi_expiracao` — varredura automática (`EXECUTE` apenas em `fn_materializar_expiracao`).
- `nsi_operador_restrito` — fluxo excepcional (`fn_registrar_revisao_abandono`, `fn_reatribuir_claim`).

Nomes de coluna permanecem candidatos (a decidir na implementação de B3); schema, tabelas, funções e roles conceituais estão **aprovados** por esta rodada.

---

## 6. Mecanismo de Exclusividade e Concorrência na Criação

```sql
INSERT INTO nsi_operacional.claims
       (registro_coleta_id, claim_id, token_hash, estado, criado_em, expira_em, versao_atual)
VALUES (:registro_coleta_id, :novo_claim_id, :novo_token_hash, 'ativo',
        now(), now() + interval '5 minutes', 1)
ON CONFLICT (registro_coleta_id) DO UPDATE
   SET claim_id     = EXCLUDED.claim_id,
       token_hash   = EXCLUDED.token_hash,
       estado       = 'ativo',
       criado_em    = now(),
       expira_em    = now() + interval '5 minutes',
       versao_atual = nsi_operacional.claims.versao_atual + 1
 WHERE nsi_operacional.claims.estado = 'liberado'
RETURNING versao_atual;
```

- **Primeiro claim:** ramo `INSERT`.
- **Novo claim após `liberado`:** ramo `ON CONFLICT ... DO UPDATE ... WHERE estado='liberado'`.
- **Registro ocupado (`ativo`/`expirado_pendente_revisao`):** a condição `WHERE` falha, zero linhas afetadas, recusa determinística.
- **Dois workers simultâneos:** o próprio `INSERT ... ON CONFLICT` do PostgreSQL serializa a resolução no nível da linha — apenas um vence.
- **`versao_atual`** embutido na própria projeção, incrementado na mesma instrução que muda o estado — sem lock avulso, sem *advisory lock*, sem segunda consulta. A constraint `UNIQUE (aggregate_id, aggregate_version)` em `eventos_claim` permanece como rede de segurança de última instância, não como mecanismo primário.

---

## 7. Mecanismo de Expiração — Fronteira Exata e Materialização Segura

**Autoridade temporal:** PostgreSQL (`now()`/`transaction_timestamp()`), nunca o relógio de um worker; todas as colunas de tempo `TIMESTAMPTZ`.

**Regra exata:** claim `ativo` somente enquanto `now() < expira_em`. Quando `now() >= expira_em`, já está expirado. Materialização usa `expira_em <= now()`. Heartbeat só é aceito estritamente antes da fronteira (`now() < expira_em`) — na fronteira exata, é recusado.

```sql
-- fn_registrar_heartbeat
UPDATE nsi_operacional.claims
   SET expira_em           = now() + interval '5 minutes',
       ultimo_heartbeat_em = now(),
       versao_atual        = versao_atual + 1
 WHERE registro_coleta_id = :id
   AND claim_id   = :claim_id
   AND token_hash = :hash_apresentado
   AND estado     = 'ativo'
   AND now() < expira_em
RETURNING versao_atual, expira_em;

-- fn_materializar_expiracao
UPDATE nsi_operacional.claims
   SET estado       = 'expirado_pendente_revisao',
       versao_atual = versao_atual + 1
 WHERE registro_coleta_id = :id
   AND estado    = 'ativo'
   AND expira_em <= now()
RETURNING versao_atual, claim_id;
```

Zero linhas afetadas em qualquer um dos dois é tratado como no-op idempotente — nunca como novo fato. Se o heartbeat falhar exclusivamente por fronteira temporal (claim ainda `ativo` na projeção, mas `now() >= expira_em`), a mesma transação invoca a materialização, convertendo a tentativa recusada na observação formal da expiração. Nenhum heartbeat ressuscita um claim já em `expirado_pendente_revisao` — a condição `estado='ativo'` garante isso estruturalmente.

**Testes de fronteira sem espera real:** `now()`/`transaction_timestamp()` ficam congelados no início da transação. Compondo setup e chamada da função na **mesma transação**, é possível fixar `expira_em` exatamente igual, um microssegundo antes ou um microssegundo depois do `now()` que a própria função vai ler — com precisão total, determinística, sem sleep:

```sql
BEGIN;
UPDATE nsi_operacional.claims SET expira_em = now() WHERE registro_coleta_id = :id; -- fronteira exata
SELECT nsi_operacional.fn_registrar_heartbeat(:id, ...);  -- mesma transação, mesmo now()
COMMIT;
```

Nenhuma função de produção aceita parâmetro de relógio arbitrário — este artifício é exclusivo de teste.

---

## 8. Modelo de Permissão e Segurança

**Owner e execução:** `nsi_eventos_owner` (`NOLOGIN`) é dona de tabelas e funções; as seis funções são `SECURITY DEFINER`, executando com os privilégios do owner independentemente de quem chamou. `nsi_eventos_owner` **nunca** tem senha definida, **nunca** é usada para conexão de aplicação — validado operacionalmente (auditoria de `pg_roles.rolcanlogin = false`).

**Concessões mínimas explícitas:**
```sql
REVOKE ALL ON SCHEMA nsi_operacional FROM PUBLIC;
REVOKE CREATE ON SCHEMA nsi_operacional FROM PUBLIC;
GRANT USAGE ON SCHEMA nsi_operacional TO nsi_aplicacao, nsi_expiracao, nsi_operador_restrito;

REVOKE ALL ON ALL TABLES IN SCHEMA nsi_operacional FROM PUBLIC;
-- nenhuma role de aplicação recebe INSERT/UPDATE/DELETE direto — apenas EXECUTE nas funções.
-- leitura direta (SELECT), se necessária para consulta de status fora das funções,
-- é concedida explicitamente e apenas onde estritamente necessário — candidato, a
-- confirmar em B3, nunca concedida por padrão:
-- GRANT SELECT ON nsi_operacional.claims TO nsi_aplicacao;

REVOKE EXECUTE ON FUNCTION nsi_operacional.fn_criar_claim(...) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION nsi_operacional.fn_criar_claim(...),
                          nsi_operacional.fn_registrar_heartbeat(...),
                          nsi_operacional.fn_liberar_claim(...),
                          nsi_operacional.fn_materializar_expiracao(...)
   TO nsi_aplicacao;
GRANT EXECUTE ON FUNCTION nsi_operacional.fn_materializar_expiracao(...) TO nsi_expiracao;
GRANT EXECUTE ON FUNCTION nsi_operacional.fn_registrar_revisao_abandono(...),
                          nsi_operacional.fn_reatribuir_claim(...)
   TO nsi_operador_restrito;
```
(Padrão de `REVOKE EXECUTE ... FROM PUBLIC` repetido para cada função — obrigatório porque o PostgreSQL concede `EXECUTE` a `PUBLIC` por padrão em funções novas.)

**`search_path` fixo, dentro de cada função:** `SET search_path = nsi_operacional, pg_catalog` — fecha a classe de ataque de "search path injection" contra `SECURITY DEFINER`. Toda referência interna a tabela/função é qualificada por schema (`nsi_operacional.eventos_claim`), redundante com o `search_path` fixo.

**Identidade do executor não falsificável para fins de privilégio:** ver Seção 4.3 — o controle de acesso nunca depende de um parâmetro textual, apenas de `GRANT EXECUTE`/`session_user`.

**Extensão criptográfica:** não exigida nesta sprint (SHA-256 é calculado em Python); se uma extensão (`pgcrypto` ou equivalente) vier a ser necessária no futuro, sua instalação é um passo de migration Alembic explícito e versionado.

---

## 9. Modelo de Dados — Eventos Operacionais (B4) — NÃO Definido Aqui

A ADR-008 aprova apenas o modelo geral de evento imutável/projeção corrente (§6) e fecha exclusivamente o catálogo de eventos de **claim** (§11). Esta especificação **não inventa** catálogo, semântica, agregado, payload mínimo, identidade idempotente ou versão para eventos de lote, registro de coleta ou correção. **B4 permanece formalmente condicionada** a uma decisão arquitetural própria (evolução da ADR-008 ou ADR complementar), cobrindo exatamente esses pontos. Sem essa decisão, B4 não pode iniciar.

**Condição satisfeita (2026-09-16):** a decisão arquitetural exigida por esta seção foi tomada pela **ADR-009 — Catálogo de Eventos Operacionais de Lote, Registro de Coleta e Correção (APROVADA E CONGELADA)**, registrada como Subetapa B4.1 (Seção 18). O texto acima é preservado como registro histórico da condição; o catálogo, o agregado, o payload, a identidade idempotente e os papéis de cada evento são os da ADR-009 — esta especificação não os redefine, apenas os traduz em desenho técnico (Seção 18, Detalhamento de B4).

## 10. Registros Legados Sem Identidade Técnica

Preservação integral, nunca invenção nem omissão. Classificação candidata "legado sem identidade técnica", referenciada por `lote_id` de origem + localização/índice original + checksum do conteúdo bruto — nunca apresentada como identidade técnica nascida no passado. Permanecem auditáveis; nunca enviáveis automaticamente; nunca recebem claim (exclusão estrutural — invariante a testar); nunca confundidos com registros A1+; exigem tratamento humano ou política formal futura. Nome final da classificação pendente da decisão da Seção 9.

## 11. Migração de Estado Sem Fabricar História

Diferenciação obrigatória: (1) evento de negócio realmente ocorrido — reconstrução honesta usando timestamp original já existente (`recebido_em`); (2) registro técnico de importação — distinto, rotulado, nunca confundido com evento de negócio; (3) snapshot legado observado no corte — estado tal como visto no momento da migração, honesto sobre ser um retrato; (4) projeção reconstruída a partir de eventos nativos pós-corte — caso normal. Nunca se atribui retroativamente operador, horário ou evento inexistente — mesmo princípio de `_inicializar_historico_se_necessario` (Sprint A3). Eventual evento técnico (`snapshot_legado_importado` ou equivalente) tem nome/payload/semântica dependentes da decisão da Seção 9.

## 12. Infraestrutura e Isolamento

| Opção | Isolamento | Risco residual |
|---|---|---|
| A. Mesmo banco, schema separado | lógico mínimo | compartilha recursos físicos e superfície de incidente com a ADR-006 |
| B. Mesma instância, database separado | lógico mais forte | ainda compartilha a instância física |
| C. Instância dedicada | físico total | **menor raio de impacto compartilhado** (não "nenhum risco"): permanecem falha da própria instância, configuração incorreta, perda de credenciais, ausência de backup testado, indisponibilidade, custo e complexidade operacional |

**Recomendação:** isolamento lógico mínimo = Opção B. Escolha final entre A/B/C **permanece pendente** de visibilidade de infraestrutura, volume, disponibilidade e orçamento.

## 13. Credenciais e Secrets

Leitura via `Config`/variáveis de ambiente. `.env` somente em desenvolvimento local, nunca produção. Produção injeta secrets pelo ambiente do processo ou gerenciador de secrets do provedor — nunca arquivo de credenciais separado. Logs/erros/relatórios nunca exibem URL de conexão completa com senha. Vault não é necessário nesta sprint, mas isso não torna `.env` aceitável para produção.

## 14. Backup e Recuperação — Pré-requisitos Bloqueantes de B7

Antes de autorizar B7: mecanismo de backup; responsável; retenção; teste de restauração já executado com sucesso; RPO e RTO mínimos; procedimento de rollback preservando eventos posteriores ao corte (ADR-008 §17). Backup único pós-corte é proteção adicional, nunca substituto. Todas essas decisões **permanecem pendentes** e bloqueiam especificamente B7.

---

## 15. Especificação Completa das Seis Funções

Regras transversais a todas: `idempotency_key` **obrigatória** em `fn_criar_claim`, `fn_registrar_heartbeat`, `fn_liberar_claim`, `fn_registrar_revisao_abandono`, `fn_reatribuir_claim` (comando externo repetível); `fn_materializar_expiracao` dispensa chave externa — idempotência estrutural via `UPDATE` condicional + constraint. Todas incrementam `versao_atual` na mesma transação que produzem evento, mesmo sem mudar `estado`. `executado_por` sempre derivado de `session_user` (Seção 4.3). Nenhuma autoriza disparo; nenhuma altera `numero_tentativa`.

| | `fn_criar_claim` | `fn_registrar_heartbeat` | `fn_liberar_claim` | `fn_materializar_expiracao` | `fn_registrar_revisao_abandono` | `fn_reatribuir_claim` |
|---|---|---|---|---|---|---|
| **Executa** | `nsi_aplicacao` | `nsi_aplicacao` | `nsi_aplicacao` | `nsi_aplicacao` e `nsi_expiracao` | `nsi_operador_restrito` | `nsi_operador_restrito` |
| **Parâmetros** | `registro_coleta_id`, `token_hash`, `idempotency_key` | `registro_coleta_id`, `claim_id`, `token_hash`, `idempotency_key` | idem heartbeat | `registro_coleta_id` | `registro_coleta_id`, `decisao`, `justificativa`, `idempotency_key` | `registro_coleta_id`, `evento_id_revisao`, `token_hash_novo`, `idempotency_key` |
| **Validação de estado** | ausente OU `liberado` | `ativo` | `ativo` | `ativo` | `expirado_pendente_revisao` | `expirado_pendente_revisao` |
| **Validação de token** | n/a (nasce aqui) | comparação de `token_hash` | comparação de `token_hash` | não exigida | n/a | n/a |
| **Evento** | `claim_criado` | `heartbeat_registrado` | `claim_liberado` | `claim_expirado` | `revisao_de_abandono_registrada` (**sempre**) | `claim_reatribuido` |
| **Projeção** | `INSERT`/`UPDATE` condicional (Seção 6) | `expira_em`, `ultimo_heartbeat_em` (nunca `estado`) | `estado='liberado'` | `estado='expirado_pendente_revisao'` | **nenhuma mudança de estado**; `versao_atual` avança | mesma linha, `claim_id`/`token_hash` novos, `estado='ativo'` |
| **Regra temporal** | `expira_em=now()+5min` | aceito só se `now()<expira_em` | idem, senão materializa | `expira_em<=now()` | — | `expira_em=now()+5min` |
| **`versao_atual`** | incrementa | incrementa | incrementa | incrementa | **incrementa mesmo sem mudar estado** | incrementa |
| **Retorno** | `claim_id`, `token_bruto` (só aqui, 1x — devolvido pela camada Python, Seção 4.1) | `expira_em` nova ou recusa | confirmação | materializado ou não | `evento_id` da revisão | `claim_id_novo`, `token_bruto` (1x) |
| **Repetição (mesma chave)** | mesmo resultado, sem token reentregue (Seção 4.2) | mesmo resultado, sem novo evento | idem | idempotente por desenho | mesmo resultado | mesmo resultado, sem token reentregue |
| **Conflito (chave/registro)** | recusa explícita | recusa | recusa | n/a | recusa | recusa |
| **Vínculo adicional** | — | — | — | — | grava `claim_id` revisado no payload | valida `registro_coleta_id`, `claim_id` revisado, `decisao='reatribuir'`, consumo único (Seção 17) |

---

## 16. Idempotência Persistente (obrigatória, mecanismo híbrido)

Tabela dedicada `nsi_operacional.comandos_idempotentes`, escopo `UNIQUE (comando, aggregate_id, idempotency_key)` — mesmo padrão de escopo já usado pela política de idempotência da ADR-006 §18. Armazena `payload_hash` (detecta reuso com conteúdo diferente → conflito explícito) e `resultado` (devolvido em qualquer repetição). Checagem/gravação ocorre **na mesma transação** do efeito de negócio — fecha a janela ambígua "commit incerto/resposta perdida" que uma idempotência em memória Python nunca fecharia. Nenhuma idempotência depende de estado em memória do processo.

**`resultado` nunca contém:** `token_bruto`; hash reutilizável como credencial; segredo; URL ou credencial de banco. Na repetição de criação/reatribuição já commitada, confirma `claim_id`/`expira_em` e informa explicitamente que o token não é reentregue (Seção 4.2).

**Retenção:** mecanismo definido; prazo **pendente**, mesma honestidade já praticada pela ADR-006 §18 quanto à retenção de chaves de idempotência.

## 17. Vínculo e Consumo Único da Revisão

`revisao_de_abandono_registrada` registra, no payload, o `claim_id` revisado (lido da projeção corrente pela própria função). `fn_reatribuir_claim` valida: revisão pertence ao mesmo `registro_coleta_id`; `claim_id` referenciado é o mesmo atualmente em `expirado_pendente_revisao`; decisão é `reatribuir`.

```sql
UPDATE nsi_operacional.claims
   SET claim_id     = :claim_id_novo,
       token_hash   = :token_hash_novo,
       estado       = 'ativo',
       criado_em    = now(),
       expira_em    = now() + interval '5 minutes',
       versao_atual = versao_atual + 1
 WHERE registro_coleta_id = :registro_coleta_id
   AND estado = 'expirado_pendente_revisao'
   AND claim_id = :claim_id_revisado_pela_revisao
RETURNING versao_atual;
```

Consumo único decorre estruturalmente da combinação `(estado, claim_id)` na cláusula `WHERE`: depois de uma reatribuição bem-sucedida, essa combinação exata nunca mais se repete para aquele `registro_coleta_id` — nenhuma coluna extra de "revisão consumida" é necessária. Duas reatribuições concorrentes referenciando a mesma revisão: apenas uma tem a cláusula satisfeita; a outra, zero linhas afetadas, recusa determinística. Uma revisão sobre `claim_id` antigo nunca autoriza geração futura, pois a combinação já não existe.

**Revisão que decide não reatribuir:** o evento é sempre gravado (auditável), mas nenhuma alteração de projeção ocorre além do avanço técnico de `versao_atual` — sem inventar um quarto estado. O registro permanece em `expirado_pendente_revisao`, não liberado automaticamente. Múltiplas revisões podem se acumular ao longo do tempo até que uma eventualmente autorize reatribuição.

---

## 18. Divisão em Subetapas B1–B7

| Subetapa | Conteúdo | Status |
|---|---|---|
| **B1** | Esta especificação técnica | **CONCLUÍDA** |
| **B2** | Infraestrutura, conexão, Alembic configurado | **CONCLUÍDA** — detalhada abaixo (B2.1/B2.2/B2.3) |
| **B3.1** | Provisionamento administrativo, roles e isolamento | **CONCLUÍDA** — detalhada abaixo |
| **B3.2** | Migration `0002` — tabelas, constraints, índices parciais e trigger defensiva | **CONCLUÍDA** — detalhada abaixo |
| **B3.3** | Migration `0003` — exatamente as seis funções `SECURITY DEFINER` e seus `REVOKE`/`GRANT` | **CONCLUÍDA** — detalhada abaixo |
| **B3.4** | Testes finais e documentação de encerramento da Sprint B3 | **CONCLUÍDA** — detalhada abaixo |
| **B4.1** | Decisão arquitetural formal do catálogo de eventos operacionais (ADR-009) | **CONCLUÍDA** — detalhada abaixo |
| **B4.2** | Migration `0004` — tabelas `lotes`, `registros_coleta`, `eventos_lote`, `eventos_registro_coleta`, triggers defensivas e ampliação de `comandos_idempotentes` | **CONCLUÍDA** — detalhada abaixo |
| **B4.3** | Provisionamento administrativo da role `nsi_congelamento` e Migration `0005` — exatamente as cinco funções `SECURITY DEFINER` do catálogo da ADR-009 e seus `REVOKE`/`GRANT` | **CONCLUÍDA** — detalhada abaixo |
| **B5** | Importador e validação de migração, ambiente de teste/staging | pendente |
| **B6** | Ensaio de corte completo, ambiente controlado | pendente — regras abaixo |
| **B7** | Corte real + preservação dos JSONs, produção | **bloqueada** até Seção 14 estar satisfeita; autorização própria e separada de B5/B6 |

### Detalhamento de B2 — CONCLUÍDA

**B2.1 — Dependências e configuração (concluída):** `psycopg[binary]==3.3.5` e `alembic==1.19.2` em `requirements.txt`; nova seção de configuração em `config.py` (`DATABASE_URL`, `TEST_DATABASE_URL`, `NSI_DATABASE_ENV`, `DATABASE_SSLMODE`, `resolver_url_banco()`, `mascarar_dsn()`, `DSNInvalida`) — nenhuma credencial ou DSN bruta exposta em exceção, log ou saída, inclusive em casos de DSN malformada (verificado por teste, com `__context__` genuinamente limpo). 30 testes unitários novos (`tests/unit/test_config_banco.py`), todos passando, sem exigir banco real.

**B2.2 — Estrutura Alembic e scripts administrativos (concluída):** `alembic.ini` (URL nunca gravada, placeholder deliberado), `migrations/env.py` (resolve a URL via `resolver_url_banco()`; verifica — nunca cria — o schema `nsi_operacional`), `migrations/versions/0001_bootstrap_vazio.py` (revisão vazia, sem tabela de negócio), `scripts/postgres_local/provisionar_dev_teste.sql` e `desprovisionar_dev_teste.sql` (com `ON_ERROR_STOP`, verificação de identidade do servidor, confirmação textual obrigatória no desprovisionamento, sem senha em nenhum dos dois), `pytest.ini` e `tests/conftest.py` (marcador `pg_integration`, proteção fail-vs-skip), `tests/integration/test_alembic_postgres.py` (comprovação de identidade — banco, servidor, porta — dentro do próprio teste destrutivo, antes de qualquer chamada ao Alembic).

**B2.3 — Provisionamento real e validação (concluída):** Provisionados manualmente, no PostgreSQL 17 local desta máquina (uso exclusivo de desenvolvimento/teste, nunca produção): os bancos `nsi_dev` e `nsi_test`; as roles de migração `nsi_dev_migrator` e `nsi_test_migrator` — **distintas das quatro roles funcionais já aprovadas para a Sprint B3** (`nsi_eventos_owner`, `nsi_aplicacao`, `nsi_expiracao`, `nsi_operador_restrito`), que permanecem exclusivas de B3; o schema `nsi_operacional` nos dois bancos. Senhas definidas interativamente via `\password`. As credenciais não são persistidas em código, logs automatizados ou Git. O `.env` foi configurado localmente pelo operador, é carregado pela aplicação durante a execução e permanece fora do versionamento.

Aplicada `alembic upgrade head` (revisão `0001`) em `nsi_dev` e em `nsi_test` — em ambos, o único objeto criado em `nsi_operacional` foi `alembic_version`, confirmado por consulta direta ao catálogo (nenhuma tabela de negócio). Suíte de testes de integração PostgreSQL real (`pg_integration`) executada com sucesso: **3 de 3 aprovados, zero pulados** — os três, antes pulados por ausência de banco, agora rodam de fato contra `nsi_test`. Suíte completa do projeto: **246/246 aprovados** (213 legados + 30 de configuração + 3 de integração real).

**Dois problemas reais, encontrados e corrigidos somente na execução real** (não previstos nesta especificação até então) — ambos em `migrations/env.py`:

- **(a) Dialeto SQLAlchemy incorreto por padrão:** `create_engine()` do SQLAlchemy assume o dialeto `psycopg2` para qualquer URL `postgresql://` sem driver explícito — `psycopg2` nunca foi instalado neste projeto (Seção 3 já decide `psycopg` v3). Corrigido com `_url_para_sqlalchemy()`, que reescreve a URL para `postgresql+psycopg://` **somente dentro de `migrations/env.py`** — `Config.DATABASE_URL`/`TEST_DATABASE_URL` permanecem genéricas, usadas diretamente por `psycopg.connect()` no resto do projeto sem esse prefixo.
- **(b) Transação "autobegin" do SQLAlchemy 2.0 consumida pela verificação de schema:** a consulta de leitura em `_verificar_schema_existe()` iniciava implicitamente uma transação na mesma conexão entregue ao Alembic logo em seguida; `context.begin_transaction()` herdava essa transação já aberta em vez de abrir e possuir a sua própria, e não comitava corretamente ao final — `alembic upgrade head` reportava sucesso, mas nada era persistido (nem `alembic_version`, nem o carimbo de revisão), confirmado por consulta direta ao banco (zero tabelas). Corrigido com `connection.rollback()` logo após a verificação (leitura pura, sem efeito a desfazer), garantindo que a transação do Alembic comece do zero e seja comitada corretamente.

Nenhuma decisão já congelada na ADR-008 foi alterada por essas correções — ambas são exclusivamente de mecânica de conexão do Alembic/SQLAlchemy, sem tocar o modelo de identidade, claim, evento ou permissão já aprovado.

**Critério de aceite: satisfeito integralmente.**

### Detalhamento de B3 — divisão em subetapas B3.1–B3.4

Formalizada nesta revisão do documento: a Sprint B3, tratada como bloco único nas revisões anteriores desta especificação, foi dividida em quatro subetapas fixas — decisão tomada numa rodada de planejamento posterior a este documento ("Parte 1 da B3", aprovada e encerrada) e agora incorporada aqui. `0002` e `0003` nunca são fundidas na mesma migration.

- **B3.1** — provisionamento administrativo, roles e isolamento.
- **B3.2** — migration `0002`: tabelas, constraints, índices parciais e trigger defensiva.
- **B3.3** — migration `0003`: exatamente as seis funções `SECURITY DEFINER` e seus `REVOKE`/`GRANT`.
- **B3.4** — testes finais e documentação de encerramento da Sprint B3.

#### B3.1 — Provisionamento administrativo, roles e isolamento — CONCLUÍDA

**Roles funcionais criadas, com atributos de segurança explícitos** (nunca apenas o default do PostgreSQL): `nsi_eventos_owner` (`NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`, dona do schema e, nas subetapas seguintes, das tabelas/funções de negócio); `nsi_aplicacao`, `nsi_expiracao`, `nsi_operador_restrito` (`LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`). Nenhuma das quatro pertence a nenhuma outra role (verificado por preflight e por pós-validação).

**Provisionamento idempotente e seguro, em três fases** (`scripts/postgres_local/provisionar_b3_roles.sql`): Fase 1, somente leitura, valida antecipadamente as quatro roles (se já existirem: os seis atributos de segurança + ausência de membership inesperada), as duas memberships dos migrators (`nsi_dev_migrator`/`nsi_test_migrator` → `nsi_eventos_owner`, com `INHERIT FALSE, SET TRUE, ADMIN FALSE`) e a propriedade do schema `nsi_operacional` nos dois bancos — qualquer estado inesperado aborta aqui, sem nenhuma escrita e sem corrigir nada silenciosamente; Fase 2 executa exclusivamente o que a Fase 1 já autorizou (`CREATE ROLE`/`GRANT`/`ALTER SCHEMA` condicionais via `\if`; `GRANT`/`REVOKE` de `CONNECT`/`USAGE` sempre reaplicados, por serem ACLs declarativas naturalmente idempotentes); Fase 3 repete integralmente a validação a partir do zero — atributos, ausência de membership inesperada, as duas memberships dos migrators, `PUBLIC` sem `CONNECT` nos dois bancos, cada migrator com `CONNECT` somente no próprio banco, as três roles funcionais com `CONNECT` nos dois bancos, `owner` do schema nos dois bancos, `USAGE` correto, e `alembic_version` ainda pertencendo ao migrator correspondente (nunca ao owner). Limite estrutural documentado e aceito: o PostgreSQL não tem transação distribuída entre bancos diferentes, e `\c` fecha a conexão/transação anterior — a Fase 1 global elimina a classe de falha "já escrevi X, descobri que Y está incompatível, X fica órfão", mas não cria atomicidade entre `nsi_dev` e `nsi_test`; o script é seguro para reexecução (confirmado nesta subetapa: executado duas vezes, ambas concluindo com "Fase 3 (pós-validação completa) passou integralmente").

**Isolamento de permissões:** `PUBLIC` sem `CONNECT` em `nsi_dev`/`nsi_test` (verificado via `aclexplode`/`grantee = 0` — nunca `has_database_privilege('public', ...)`, que trataria `'public'` como nome de role real, inexistente); cada migrator com `CONNECT` explícito apenas no próprio banco (nunca depende só de propriedade implícita de banco); as três roles funcionais com `CONNECT` explícito nos dois bancos locais; `USAGE` no schema `nsi_operacional` concedido aos dois migrators e às três roles funcionais; propriedade do schema transferida para `nsi_eventos_owner` nos dois bancos, sem afetar a propriedade de `alembic_version` (permanece com o respectivo migrator).

**Reversão segura** (`scripts/postgres_local/desprovisionar_b3_roles.sql`, não executada nesta subetapa): exige revisão exatamente `'0001'` em `nsi_operacional.alembic_version` nos dois bancos antes de qualquer ação destrutiva — nunca usa "alembic downgrade base" como referência; verifica ausência de objetos residuais (`pg_class`/`pg_proc`) das quatro roles antes de qualquer `DROP ROLE`; exige confirmação textual exata; preserva o `CONNECT` explícito dos migrators (nunca revogado, sob risco de inutilizar B2); nunca restaura `CONNECT` a `PUBLIC` automaticamente; não contém senha.

**Configuração (`config.py`):** `resolver_url_banco_papel()` — função única e tipada para as seis variáveis funcionais (`DATABASE_URL_NSI_APLICACAO`/`TEST_DATABASE_URL_NSI_APLICACAO`, e equivalentes para `nsi_expiracao`/`nsi_operador_restrito`), reaproveitando as proteções já existentes de `resolver_url_banco()`: papel fechado (`PapelBancoInvalido`), ambiente fechado sem fallback entre development/test nem entre papéis (`AmbienteBancoInvalido`, `ConfiguracaoBancoAusente`), banco exigido exato por ambiente (`nsi_dev`/`nsi_test`, `BancoFuncionalNaoPermitido`), usuário da URL exatamente igual ao papel solicitado — nunca `postgres`, um migrator ou outro papel funcional (`UsuarioBancoDivergente`), validação e ausência de conflito de `sslmode`, nenhuma credencial exposta em exceção, `repr`, `stdout`/`stderr`, `__context__` ou `__cause__`.

**Execução real (procedimento manual, autorização separada):** senhas das três roles `LOGIN` definidas interativamente via `\password`; as seis URLs funcionais configuradas localmente no `.env` (fora do versionamento). `provisionar_b3_roles.sql` executado duas vezes contra o cluster PostgreSQL 17 local — a segunda execução comprovando a convergência idempotente, sem nenhuma alteração destrutiva — ambas concluindo com "Fase 3 (pós-validação completa) passou integralmente".

**Testes:** estáticos do conteúdo/ordem/gates dos dois scripts (`tests/unit/test_scripts_b3_roles.py`); unitários de `resolver_url_banco_papel()` (`tests/unit/test_config_banco.py`); de integração real, exclusivamente leitura, nunca `CREATE`/`ALTER`/`GRANT`/`REVOKE`/`DROP` (`tests/integration/test_provisionamento_b3_roles.py`, marcado `pg_integration`) — **20 aprovados** contra o cluster real, após o provisionamento. Cenários destrutivos (role incompatível, desprovisionamento completo, revisão diferente de `0001`, prova de privilégio efetivo) permanecem exclusivamente manuais, documentados em `docs/implementation/PROCEDIMENTO-MANUAL-B3-DESTRUTIVO.md`, nunca executados contra `nsi_dev`/`nsi_test` — nenhum teste automatizado executa o provisionamento ou o desprovisionamento administrativo real. Suíte completa do projeto: **331/331 aprovados**, nenhuma falha, nenhum pulado.

**Critério de aceite: satisfeito integralmente.**

#### B3.2 — Migration `0002` — tabelas, constraints, índices e trigger defensiva — CONCLUÍDA

**Objetos criados** (`migrations/versions/0002_claims_eventos_comandos_idempotentes.py`), na ordem fixa aprovada na Parte 1 da B3, executando integralmente como `nsi_eventos_owner` (`SET LOCAL ROLE`, com `RESET ROLE` explícito e autoverificação de `current_user` no caminho de sucesso): `nsi_operacional.claims`, `nsi_operacional.eventos_claim`, `nsi_operacional.comandos_idempotentes` — com todas as `CHECK`s, a `PRIMARY KEY` composta de `comandos_idempotentes` e as duas `UNIQUE` normais de `eventos_claim` já aprovadas; a FK composta diferível **`claims_revisao_atual_fk`** (`DEFERRABLE INITIALLY DEFERRED`); os dois índices únicos parciais **`eventos_claim_expirado_unico`** e **`eventos_claim_origem_claim_id_unica`**; a função da trigger **`fn_bloquear_alteracao_eventos_claim`** e a trigger **`eventos_claim_bloqueia_alteracao`** (`BEFORE UPDATE OR DELETE`, bloqueia inclusive o owner); `REVOKE ALL` explícito de `PUBLIC` e das três roles funcionais em cada uma das três tabelas, e `REVOKE ALL` de `PUBLIC` na função da trigger. Não toca `lote.json`.

**Três defeitos encontrados exclusivamente nos testes, nunca na migration** — corrigidos sem alterar `0002`: (a) o teste de ciclo assumia estado inicial `0001`, incompatível com o fluxo real aprovado (que aplica `alembic upgrade 0002` manualmente antes da suíte rodar); (b) um caso de teste de `comandos_idempotentes` usava uma data fixa no passado para `concluido_em`, violando genuinamente `ck_comandos_idempotentes_concluido_apos_criado` por dado de teste incoerente, não por defeito de schema; (c) `SET CONSTRAINTS claims_revisao_atual_fk IMMEDIATE` sem qualificação de schema falhava por resolução de nome via `search_path` (que não inclui `nsi_operacional` para o migrator) — corrigido para `nsi_operacional.claims_revisao_atual_fk`. Um quarto ponto, descoberto na validação real: o inventário estrutural usava `information_schema.tables`, que filtra por privilégio do usuário corrente — como `nsi_test_migrator` não tem DML direto nas três tabelas (owner é `nsi_eventos_owner`; membership `WITH INHERIT FALSE`, B3.1), a visão as ocultava mesmo existindo; corrigido para `pg_catalog.pg_tables`, que lista por catálogo, sem filtro de privilégio. Endurecimento adicional de segurança nos testes: nenhuma função de teste recebe a DSN como parâmetro nomeado (obtida internamente via `request.getfixturevalue`); nenhuma asserção compara a DSN bruta contra uma saída capturada (substituída por checagem com mensagem fixa, nunca interpolando a DSN).

**Execução real:** `0002` aplicada primeiro em `nsi_test`; suíte específica da B3.2 (`test_migration_0002_upgrade_downgrade.py`, `test_schema_b3_constraints.py`, `test_schema_b3_unicidade_e_fk.py`, `test_trigger_imutabilidade_eventos_claim.py`): **97/97 aprovados**. Ciclo real comprovado em `nsi_test`: `0002 → 0001 → 0002` — gate de identidade (`nsi_test`, servidor local, porta 5432, `nsi_test_migrator`) confirmado antes do único `downgrade`; `nsi_test` termina em `0002`. Identidade de `nsi_dev` confirmada antes de qualquer ação; `0002` aplicada em `nsi_dev` **somente por `upgrade`** — nenhum `downgrade` executado em `nsi_dev` nesta ou em nenhuma subetapa futura de B3.2. `nsi_dev` termina em `0002`. Suíte completa do projeto, com integração real obrigatória: **428/428 aprovados, nenhuma falha, nenhum pulado**.

**Nenhuma das seis funções `SECURITY DEFINER` nem a migration `0003` foram criadas nesta subetapa — pertencem integralmente a B3.3.**

**Critério de aceite: satisfeito integralmente.**

#### B3.3 — Migration `0003` — seis funções `SECURITY DEFINER` — CONCLUÍDA

**Objetos criados** (`migrations/versions/0003_seis_funcoes_claim.py`), executando integralmente como `nsi_eventos_owner` (`SET LOCAL ROLE`, com `RESET ROLE` explícito e autoverificação de `current_user` antes de o Alembic carimbar a revisão): exatamente as seis funções `SECURITY DEFINER` da Seção 15 — `fn_criar_claim`, `fn_registrar_heartbeat`, `fn_liberar_claim`, `fn_materializar_expiracao`, `fn_registrar_revisao_abandono`, `fn_reatribuir_claim`. Cada função: envelope de idempotência completo (reserva/conclusão via `comandos_idempotentes`, ou leitura do resultado existente e comparação de `payload_hash`, com conflito recusado por `SQLSTATE 22023` e mensagem fixa, nunca interpolando segredo); regra de negócio expressa como `UPDATE`/`INSERT ... ON CONFLICT` atômico, nunca `SELECT ... FOR UPDATE` nem *advisory lock*; `search_path` fixo (`pg_catalog, nsi_operacional, pg_temp`); qualificação de schema em toda referência interna. `fn_reatribuir_claim` valida o vínculo da revisão sem `SELECT` prévio, via subconsulta `EXISTS` correlacionada dentro da própria cláusula `WHERE` do `UPDATE`. Concessões: `REVOKE EXECUTE ... FROM PUBLIC` explícito nas seis, seguido de `GRANT EXECUTE` restrito por role — `nsi_aplicacao` em `fn_criar_claim`/`fn_registrar_heartbeat`/`fn_liberar_claim`; `nsi_aplicacao` e `nsi_expiracao` em `fn_materializar_expiracao`; `nsi_operador_restrito` em `fn_registrar_revisao_abandono`/`fn_reatribuir_claim`. Nenhuma role funcional recebe `SELECT`/`INSERT`/`UPDATE`/`DELETE` direto nas tabelas.

**Nenhum defeito real encontrado na migration.** Múltiplas rodadas de teste real contra `nsi_test` revelaram exclusivamente bugs de simulação temporal e de desenho de teste, nunca de `0003`: (a) backdating de `expira_em` isolado, sem mover `criado_em` junto, violando `ck_claims_expira_apos_criado` — corrigido atualizando `criado_em`/`expira_em` sempre juntos, numa única instrução, por cenário (claim expirado, fronteira exata, um microssegundo antes/depois, cenário válido); (b) o ajuste anterior deixava `ultimo_heartbeat_em` fora da nova janela `[criado_em, expira_em)`, violando `ck_claims_heartbeat_dentro_da_janela` — corrigido reposicionando `ultimo_heartbeat_em` condicionalmente (`CASE WHEN ... IS NOT NULL`), nunca zerando-o incondicionalmente, preservando a prova de que é a própria função `fn_reatribuir_claim` — não o setup do teste — quem zera um heartbeat pré-existente; (c) risco de vazamento de conexão em três testes de concorrência real (`conn_b` aberta fora do `try` de `conn_a`) — corrigido aninhando a abertura de `conn_b` dentro do `try` de `conn_a`; (d) comparações diretas de segredo (`assert token_hash_x == token_hash_y`) e checagem de vazamento restrita a `str(exc)` — endurecidas para comparação booleana + `pytest.fail` com mensagem fixa, e checagem em `str()` **e** `repr()` em todos os testes de conflito de idempotência.

**Resíduo de teste deliberado e permanente em `nsi_test`** (nunca em `nsi_dev`), descoberto durante a validação real: `eventos_claim` é imutável mesmo para o owner (trigger de B3.2) e referencia `claims` por FK **não diferível** — uma vez que um evento existe para um `registro_coleta_id`, a linha correspondente de `claims` nunca mais pode ser removida. Dois testes que exigem commit real (a garantia sendo provada só existe com dado genuinamente persistido, visível a uma segunda conexão) deixam, por desenho, resíduo sintético permanente: `test_duas_reatribuicoes_concorrentes_uma_vencedora` (1 linha em `claims` + 1 em `eventos_claim`) e `test_idempotencia_sobrevive_a_reinicio_de_processo` (1 em `claims` + 1 em `eventos_claim` + 1 em `comandos_idempotentes`). Ambos os testes verificam a presença de evento referenciando a linha **antes** de tentar qualquer `DELETE` de limpeza, e tratam o resíduo como intencional (nunca como falha), em vez de assumir remoção incondicional.

**Execução real:** identidade de `nsi_test` confirmada antes de qualquer ação; `0003` aplicada em `nsi_test`; suíte específica da B3.3: **63/63 aprovados**. Regressão completa compatível com `nsi_test` em `0003`, excluindo deliberadamente `tests/integration/test_migration_0002_upgrade_downgrade.py` (seus três testes pertencem ao ciclo destrutivo isolado da `0002`, incompatível com o banco já em `0003`): **488/488 aprovados**. Verificações estáticas prévias: **491 coletados**; **308 aprovados e 183 deselecionados** sem `pg_integration`. Identidade de `nsi_dev` confirmada antes de qualquer ação; `0003` aplicada em `nsi_dev` **somente por `upgrade`** — nenhum `downgrade` executado em `nsi_dev` em nenhum momento desta subetapa. `nsi_test` e `nsi_dev` terminam ambos em `0003 (head)`. Inspeção somente leitura pós-upgrade em `nsi_dev` confirmou: exatamente as seis funções; owner `nsi_eventos_owner` em todas; `SECURITY DEFINER` ativo em todas; `search_path` fixo em todas; matriz de `EXECUTE` idêntica à planejada; `PUBLIC` sem `EXECUTE` em nenhuma.

**Critério de aceite: satisfeito integralmente.**

#### B3.4 — Testes finais e documentação de encerramento da Sprint B3 — CONCLUÍDA

**Ajuste realizado** (`tests/integration/test_migration_0002_upgrade_downgrade.py`): o teste de ciclo completo, escrito originalmente para o estado terminal `0002` (B3.2), foi atualizado para o head atual — `0003` — sem reabrir nenhuma regra já aprovada. O piso `0001` do downgrade intermediário, o gate obrigatório de identidade (banco `nsi_test`, servidor local, porta `5432`, `session_user = nsi_test_migrator`) executado antes de qualquer ação destrutiva, o inventário esperado em `0001` e as verificações de segurança (ausência de DSN na saída do Alembic, mascaramento da DSN) permanecem exatamente como aprovados na B3.2. Único teste de ciclo renomeado para `test_ciclo_downgrade_0001_upgrade_0003`, refletindo o novo alvo.

**Execução real:** identidade de `nsi_test` comprovada antes de qualquer ação; ciclo destrutivo `0003 → 0001 → 0003` executado exclusivamente contra `nsi_test` — suíte específica do ciclo: **3 passed em 3.82s**. Suíte completa do projeto, sem exclusões ou filtros: **491 passed em 35.22s**, zero falhas. `nsi_test` terminou o ciclo em `0003 (head)`. Identidade e revisão de `nsi_dev` confirmadas por leitura, também em `0003 (head)` — nenhum `downgrade` executado em `nsi_dev` nesta subetapa, nem em nenhuma subetapa anterior da Sprint B3.

**Critério de aceite de B3 como um todo: satisfeito integralmente** — todos os testes da Seção 20 passando; suíte completa sem regressão; nenhum item da Sprint B3 permanece pendente.

**Critério de aceite: satisfeito integralmente.**

### Detalhamento de B4 — subetapas B4.1–B4.3

A Seção 9 condicionava B4 a uma decisão arquitetural própria. Essa decisão foi tomada (B4.1) e a B4 passou a ser executada em subetapas, no mesmo padrão da B3: decisão/arquitetura → schema → funções. `0004` e `0005` nunca são fundidas na mesma migration. Esta especificação registra as subetapas B4.1 a B4.3; uma eventual subetapa posterior de encerramento da B4 não está definida por este documento.

#### B4.1 — Decisão arquitetural do catálogo de eventos operacionais — CONCLUÍDA

**Entrega** (`docs/architecture/ADR-009-catalogo-eventos-operacionais.md`, APROVADA E CONGELADA em 2026-09-16, commit `bd2ab47`): modelo híbrido de persistência (eventos imutáveis como fonte de transições e auditoria; tabelas de estado corrente como fonte dos valores pessoais e operacionais atuais — não é event sourcing integral); catálogo fechado de exatamente cinco eventos (`lote_criado`, `lote_congelado_d8`, `disparo_confirmado`, `correcao_registrada`, `tentativa_correcao_nao_resolvida`); proibição de valor pessoal bruto em qualquer evento; payload seguro da tentativa não resolvida; localização do checksum e natureza correlacionável do `payload_hash`; identidade técnica por `session_user`; matriz de papéis, incluindo a nova role `NOLOGIN` `nsi_congelamento`; idempotência determinística do congelamento.

**Nenhuma implementação de código, schema, migration ou role foi realizada nesta subetapa** — exclusivamente documental. Satisfaz integralmente a condição da Seção 9.

#### B4.2 — Migration `0004` — schema relacional de lotes, registros e eventos operacionais — CONCLUÍDA

**Objetos criados** (`migrations/versions/0004_lotes_registros_eventos_operacionais.py`, commit `41e49f9`), executando integralmente como `nsi_eventos_owner` (`SET LOCAL ROLE`, `RESET ROLE` explícito e autoverificação de `current_user`, mesmo padrão de `0002`/`0003`):

- `nsi_operacional.lotes` — estado corrente do lote: totais, `total_valido_congelado`, `status` (`aguardando_d8` | `sem_registros_validos` | `aguardando_confirmacao_disparo` | `disparo_confirmado`), `horario_conceitual_congelamento` (exatamente `recebido_em` + 691200 s), dados do congelamento e da confirmação, `versao_eventos_atual`; `CHECK`s de totais, de coerência por status, de congelamento nunca antecipado e de `atrasado` correto; índice único parcial `lotes_lote_id_legado_unico` e índice parcial `lotes_aguardando_congelamento`.
- `nsi_operacional.registros_coleta` — estado corrente do registro: `nome`, `produto`, `whatsapp`, `valido`, `motivos_invalidez` (vocabulário fechado de sete motivos, sem duplicata), `numero_versao_dados`, `versao_eventos_atual`; `CHECK` de coerência entre validade, valores e motivos; índices `registros_coleta_lote_id` e `registros_coleta_invalidos_por_lote`.
- `nsi_operacional.eventos_lote` — log imutável dos quatro eventos de agregado `lote`, com colunas relacionais tipadas e `CHECK` condicional de payload por tipo (nenhum `JSONB` genérico); `UNIQUE (aggregate_id, aggregate_version)`; índices únicos parciais `eventos_lote_criado_unico`, `eventos_lote_congelado_unico`, `eventos_lote_disparo_confirmado_unico`.
- `nsi_operacional.eventos_registro_coleta` — log imutável de `correcao_registrada`, com `resultado` (`aplicada_valida` | `aplicada_ainda_invalida` | `recusada_ja_valido` | `recusada_tardia`) e `numero_versao_dados` presente somente nos resultados de aplicação; `UNIQUE (aggregate_id, aggregate_version)`.
- Funções de trigger `fn_bloquear_alteracao_eventos_lote` e `fn_bloquear_alteracao_eventos_registro_coleta`, com as triggers `eventos_lote_bloqueia_alteracao` e `eventos_registro_coleta_bloqueia_alteracao` (`BEFORE UPDATE OR DELETE`, bloqueiam inclusive o owner).
- Ampliação aditiva do `CHECK` `ck_comandos_idempotentes_comando`, que passa a aceitar também `registrar_lote`, `registrar_congelamento`, `confirmar_disparo`, `registrar_correcao` e `registrar_tentativa_nao_resolvida` — nenhuma outra coluna de `comandos_idempotentes` é alterada.
- `REVOKE ALL` de `PUBLIC` e das três roles funcionais já existentes em cada tabela, e de `PUBLIC` em cada função de trigger. Nenhuma coluna de checksum. Não toca `lote.json`.

**Máquina de estados de `lotes.status` fixada pela `0004`:** criação sempre em `aguardando_d8`, inclusive com `total_valido = 0`; antes do congelamento, correções alteram `registros_coleta` e os totais do lote sem mudar o status; no congelamento, a contagem real do instante decide `sem_registros_validos` (terminal) ou `aguardando_confirmacao_disparo`; a confirmação leva a `disparo_confirmado`. `numero_versao_dados` (só avança em correção aplicada) e `versao_eventos_atual` (avança inclusive em recusa) são contadores independentes.

**Downgrade com preflight obrigatório:** `0004 → 0003` aborta a transação inteira, sem remover nenhum objeto, se existir qualquer recibo de um dos cinco comandos da B4 em `comandos_idempotentes`. Essa regra tem consequência direta sobre os testes da B4.3 (ver "Critérios de rollback", abaixo).

**Não criado nesta subetapa:** nenhuma função `SECURITY DEFINER`; nenhuma referência ou concessão a `nsi_congelamento`, que ainda não existe. Ambos pertencem à B4.3.

**Testes entregues no mesmo commit:** `test_migration_0004_upgrade_downgrade.py`, `test_schema_b4_constraints.py`, `test_schema_b4_unicidade_e_fk.py`, `test_trigger_imutabilidade_eventos_lote.py`, `test_trigger_imutabilidade_eventos_registro_coleta.py`, `test_comandos_idempotentes_compatibilidade_b4.py`, e ajustes em `test_alembic_postgres.py` e `test_migration_0002_upgrade_downgrade.py`.

**Registro de execução real não consolidado neste documento:** as contagens da suíte e a revisão corrente de `nsi_test` e `nsi_dev` após a `0004` não foram registradas aqui no encerramento da B4.2. Sua confirmação, por leitura, é pré-requisito da B4.3 (ver "Dependências", abaixo) — este documento não afirma números que não verificou.

#### B4.3 — Role `nsi_congelamento` e Migration `0005` — cinco funções `SECURITY DEFINER` — CONCLUÍDA

**Status:** concluída sobre a especificação técnica aprovada e congelada abaixo, que não foi reaberta. O texto das subseções "Objetivo" a "Critérios de rollback" é o da especificação; o resultado da implementação, as decisões tomadas dentro dela e a situação de cada critério de aceite estão em "Registro de implementação", ao final desta subetapa. Todos os onze critérios de aceite estão satisfeitos.

##### Objetivo

Tornar gravável, exclusivamente por função `SECURITY DEFINER`, o catálogo fechado de cinco eventos da ADR-009 sobre as tabelas já criadas pela `0004`: cada função grava o evento imutável e atualiza a projeção corrente na mesma transação, com idempotência persistente, identidade técnica por `session_user` e menor privilégio por role.

##### Escopo

**Dentro:**
- Provisionamento administrativo da role `nsi_congelamento` (`NOLOGIN`), no padrão de três fases da B3.1.
- Migration `0005`: exatamente cinco funções `SECURITY DEFINER`, seus `REVOKE EXECUTE ... FROM PUBLIC` e seus `GRANT EXECUTE` por role.
- Módulo Python de produção para o cálculo canônico de `payload_hash`.
- Testes unitários dos scripts administrativos e do módulo de `payload_hash`, e testes de integração PostgreSQL real das cinco funções.

**Fora, sem exceção:**
- Qualquer alteração em `0001`–`0004`, em tabelas, constraints, índices ou triggers já criados.
- Qualquer alteração em arquivo já existente de `adapters/`, `core/`, `app.py`, `integration/` ou `services/` — a troca do backend da aplicação não pertence à B4.3.
- Mecanismo de detecção automática do M0+192h (worker/cron) — Sprint D. A B4.3 entrega somente a função que o mecanismo futuro invocará.
- Funções de leitura/consulta e qualquer `GRANT SELECT`.
- Envio, `wamid`, webhook (Sprint C); autenticação, MFA, rotas e `operador_humano_id` preenchido (Sprint D); importação de dados legados (B5); ensaio e corte (B6/B7).
- Sexto evento, sexta função de negócio ou função auxiliar no banco — a especificação técnica não amplia o catálogo da ADR-009.
- Tabela de histórico de valores pessoais anteriores e qualquer coluna de checksum (ADR-009, Seções 5 e 9).

##### Dependências

1. ADR-009 aprovada e congelada (B4.1) — satisfeita.
2. Migration `0004` (B4.2) aplicada — **a confirmar por leitura**, antes de qualquer ação: revisão corrente de `nsi_test` e de `nsi_dev`, e suíte completa do projeto passando sobre a `0004`. *(Satisfeita: confirmada por leitura no início da implementação — ver "Registro de implementação".)*
3. B3.1 provisionada (`nsi_eventos_owner`, `nsi_aplicacao`, `nsi_expiracao`, `nsi_operador_restrito`; memberships dos migrators) — satisfeita.
4. Role `nsi_congelamento` existente **antes** da `0005` — a migration falha, sem criar nada, se a role não existir (mesmo tipo de pré-requisito que `0002`/`0003`/`0004` têm em relação a `nsi_eventos_owner`). A ordem interna da B4.3 é, portanto, fixa: provisionamento da role → migration `0005`.
5. Autorização humana própria para a implementação da B4.3 e, separadamente, para a execução real do provisionamento administrativo.

##### Arquivos previstos

Tabela da especificação, mantida como aprovada. Os nomes finais, todos já existentes, estão em "Registro de implementação".

| Arquivo | Natureza |
|---|---|
| `scripts/postgres_local/provisionar_b4_role_congelamento.sql` | novo — preflight somente leitura → convergência → pós-validação completa |
| `scripts/postgres_local/desprovisionar_b4_role_congelamento.sql` | novo — reversão administrativa, não executada na subetapa |
| `migrations/versions/0005_cinco_funcoes_eventos_operacionais.py` | novo — as cinco funções e sua matriz de `EXECUTE` |
| Módulo Python de produção para o cálculo canônico de `payload_hash` | novo — puro, sem acesso a banco, sem alterar nenhum arquivo existente |
| Teste unitário do módulo de `payload_hash` | novo |
| `tests/unit/test_scripts_b4_role_congelamento.py` | novo — testes estáticos de conteúdo, ordem e gates dos dois scripts |
| `tests/integration/test_provisionamento_b4_role_congelamento.py` | novo — somente leitura |
| `tests/integration/test_fn_registrar_lote.py` | novo |
| `tests/integration/test_fn_registrar_congelamento.py` | novo |
| `tests/integration/test_fn_confirmar_disparo.py` | novo |
| `tests/integration/test_fn_registrar_correcao.py` | novo |
| `tests/integration/test_fn_registrar_tentativa_nao_resolvida.py` | novo |
| `tests/integration/test_idempotencia_e_permissoes_b4_3.py` | novo |
| `tests/integration/test_migration_0005_upgrade_downgrade.py` | novo |
| `tests/integration/test_alembic_postgres.py`, `test_migration_0002_upgrade_downgrade.py`, `test_migration_0004_upgrade_downgrade.py` | ajuste — somente o necessário para o novo head `0005`, sem reabrir nenhuma regra já aprovada |
| Documento operacional próprio do procedimento manual destrutivo da role `nsi_congelamento` | novo — cenários destrutivos da role continuam exclusivamente manuais; este documento apenas o referencia, e `PROCEDIMENTO-MANUAL-B3-DESTRUTIVO.md` não é alterado |
| Este documento, `ROADMAP-SPRINTS-B-G.md`, `PROJECT_STATUS.md` | atualização de status ao encerramento |

`config.py` não é alterado: `nsi_congelamento` é `NOLOGIN` e não possui URL de conexão.

##### Role `nsi_congelamento`

Regida pela ADR-009 (Seção 11): a criação da role é administrativa, nunca responsabilidade automática de uma migration Alembic.

- **Atributos:** `NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`; sem senha; sem pertencer a nenhuma outra role.
- **Privilégios:** `USAGE` no schema `nsi_operacional`, nos dois bancos locais, e `EXECUTE` em `fn_registrar_congelamento`. Nenhum `CONNECT` próprio, nenhum `SELECT`/`INSERT`/`UPDATE`/`DELETE` em nenhuma tabela, nenhum `EXECUTE` em qualquer outra função, inclusive as seis de claim.
- **Membership:** `nsi_aplicacao` → `nsi_congelamento` com `INHERIT FALSE, SET TRUE, ADMIN FALSE`. `nsi_aplicacao` não tem `EXECUTE` direto na função de congelamento.
- **Uso:** a conexão `nsi_aplicacao` assume `nsi_congelamento` por `SET ROLE` com escopo de transação, invoca a função e o papel se desfaz ao fim da transação. Como `SET ROLE` não altera `session_user`, o evento registra `executado_por_login = nsi_aplicacao`; o que prova o caminho de autorização exercido é o próprio tipo do evento (ADR-009, Seção 10).
- **Script de provisionamento — três fases:**
  - Fase 1 é uma barreira global de validação: prova, antes de qualquer escrita em qualquer banco, que o estado inteiro é um dos estados previstos, e aborta sem corrigir nada silenciosamente.
  - Fase 2 é a única fase que escreve. Cada ação da Fase 2 confirma imediatamente, por leitura direta do servidor, o estado do objeto que irá alterar.
  - Fase 3 revalida tudo a partir do zero.
- **Fases autossuficientes:** nenhuma fase transmite estado, variáveis ou resultados para outra. A única informação propagada entre fases é que a fase anterior terminou com sucesso.
- **READ ONLY obrigatório:** as Fases 1 e 3 executam obrigatoriamente em modo somente leitura. Qualquer tentativa de escrita nessas fases interrompe imediatamente a execução.
- **Revisões aceitas pelo script:** `0004` e `0005`, a mesma em `nsi_dev` e em `nsi_test`.
- **Reexecução e efeito sobre a B3.1:** idempotente e seguro para reexecução. Não cria, altera nem remove nenhuma das quatro roles da B3.1, nem os migrators — o único efeito sobre uma role da B3.1 é a membership de `nsi_aplicacao` descrita acima.
- **Relação com a regra de membership da B3.1:** a regra geral da B3.1 — nenhuma role funcional pertence a outra role — permanece válida. A membership de `nsi_aplicacao` em `nsi_congelamento` é a única exceção, resultante da aplicação da ADR-009 e formalizada em sua Seção 21, para permitir a operação via `SET ROLE`. Por ocorrer sem herança automática (`INHERIT FALSE`), ela não altera o princípio de menor privilégio da B3.1.

**Divisão de responsabilidades entre o script administrativo e a `0005`.** A role `nsi_congelamento` é criada exclusivamente pelo script administrativo de provisionamento, que também concede o `USAGE` no schema e a membership de `nsi_aplicacao`. A `0005` assume que a role já existe e nunca a cria, altera ou remove. Todos os `REVOKE` e `GRANT EXECUTE` das cinco funções — inclusive o `GRANT EXECUTE` de `fn_registrar_congelamento` a `nsi_congelamento` — são aplicados dentro da própria `0005`, pelo owner, como a `0003` fez para as roles da B3.1, de modo que as permissões estejam completas ao final da migration, sem passo administrativo posterior. A comprovação exigida pela ADR-009 (Seção 11) é feita por inspeção somente leitura pós-migration (teste de integração de leitura e reexecução da Fase 3 do script).

##### Regras comuns às cinco funções

- **Forma:** `LANGUAGE plpgsql`, `SECURITY DEFINER`, owner `nsi_eventos_owner`, `SET search_path = pg_catalog, nsi_operacional, pg_temp`, toda referência interna qualificada por schema — mesmo padrão da `0003`. Todas retornam `JSONB`.
- **Identificadores:** `lote_id` e `registro_coleta_id` são fornecidos pelo chamador (o `registro_coleta_id` já nasce em Python desde a Sprint A1); `evento_id` é sempre gerado dentro da função (`gen_random_uuid()`).
- **Identidade:** `executado_por_login` = `session_user`, sempre. `current_user` nunca é usado como identidade do chamador. Nenhuma função recebe nome, rótulo ou identificador humano; nenhuma recebe parâmetro para `operador_humano_id`.
- **Tempo:** PostgreSQL é a autoridade temporal — `recebido_em`, `occurred_at`, `horario_real_execucao` e `disparo_confirmado_em` vêm de `now()`. Nenhuma função aceita parâmetro de relógio. Testes de fronteira usam o artifício da Seção 7 (setup e chamada na mesma transação).
- **Versão de evento:** obtida por `UPDATE ... SET versao_eventos_atual = versao_eventos_atual + 1 RETURNING versao_eventos_atual` na linha do agregado — nunca por `MAX(aggregate_version) + 1`. A `UNIQUE (aggregate_id, aggregate_version)` permanece como rede de segurança, não como mecanismo primário.
- **Atomicidade e imutabilidade:** evento e projeção são gravados na mesma transação. Nenhuma função executa `UPDATE` ou `DELETE` sobre evento já gravado.
- **Bloqueio:** toda função que toca `lotes` e `registros_coleta` adquire primeiro a linha do lote, depois a do registro. Correção e congelamento bloqueiam explicitamente a linha do lote no início da função — é o que serializa uma contra a outra e elimina deadlock. A `0003` dispensava bloqueio explícito por operar sobre uma única tabela; aqui, uma correção `aplicada_ainda_invalida` ou recusada não altera nenhuma coluna de `lotes` e, sem ele, não teria como serializar contra o congelamento.
- **Recusa e exceção:** recusa de negócio é retorno estruturado (`sucesso: false`, `motivo` de vocabulário fechado), nunca exceção. Exceção é reservada a três casos: conflito de idempotência (`SQLSTATE 22023`), violação estrutural da entrada, e estado impossível da arquitetura (ver `fn_registrar_congelamento`).
- **Violação de constraint:** o detalhe de erro nativo do PostgreSQL para uma `CHECK` violada inclui a linha inteira, com nome e WhatsApp. Toda violação de constraint em `lotes` ou `registros_coleta` é capturada dentro da função e relançada com mensagem fixa, sem detalhe e sem valor.

##### As cinco funções

Nomes derivados dos cinco valores de `comando` já fixados pela `0004`. Papéis, eventos e efeitos são os da ADR-009 (Seção 6) e não são reabertos. A chave de idempotência e o `payload_hash` de cada função estão nas duas subseções seguintes.

###### `fn_registrar_lote`

| | |
|---|---|
| **Comando / evento / agregado** | `registrar_lote` / `lote_criado` / `lote` |
| **Role** | `nsi_aplicacao` |
| **Parâmetros** | `p_lote_id UUID`, `p_lote_id_legado TEXT` (pode ser nulo), `p_registros JSONB` (lista; cada item: `registro_coleta_id`, `nome`, `whatsapp`, `produto`, `valido`, `motivos_invalidez`), `p_chave_idempotencia TEXT`, `p_payload_hash TEXT` |
| **Pré-condições** | nenhum lote com esse `lote_id`; nenhum `registro_coleta_id` repetido na lista ou já existente |
| **Pós-condições (sucesso)** | uma linha em `lotes` (`aguardando_d8`, `versao_eventos_atual = 1`); uma linha por registro em `registros_coleta`; um evento `lote_criado` de versão 1; recibo concluído |
| **Retorno (sucesso)** | `sucesso`, `lote_id`, `recebido_em`, `horario_conceitual_congelamento`, os três totais, `status`, `versao_eventos` |
| **Recusa de negócio** | `lote_ja_existe` — sem evento |

- Os totais (`total_recebido`, `total_valido`, `total_invalido`) são contados pela função a partir dos registros recebidos, nunca informados pelo chamador.
- A classificação de cada registro (`valido`, `motivos_invalidez`) e a normalização do WhatsApp continuam sendo responsabilidade da validação Python já existente (Sprint A2); as `CHECK`s de `registros_coleta` são a rede de segurança.
- Lote sem nenhum registro válido é criado normalmente, nunca recusado.
- `registro_coleta_id` repetido ou já existente é violação estrutural: a transação inteira é abortada, sem recibo.
- Como `recebido_em` é `now()`, esta função não serve para registrar lotes com M0 no passado — a importação de lotes legados é assunto da B5 e não é resolvida aqui.

###### `fn_registrar_congelamento`

| | |
|---|---|
| **Comando / evento / agregado** | `registrar_congelamento` / `lote_congelado_d8` / `lote` |
| **Role** | `nsi_congelamento` (via `SET ROLE` a partir de `nsi_aplicacao`) |
| **Parâmetros** | `p_lote_id UUID` — somente |
| **Pré-condições** | lote existente; `now() >= horario_conceitual_congelamento`; status `aguardando_d8` |
| **Pós-condições (sucesso)** | `total_valido_congelado`, `horario_real_congelamento` e `congelamento_atrasado` preenchidos; status `sem_registros_validos` (zero válidos) ou `aguardando_confirmacao_disparo`; um evento `lote_congelado_d8`; recibo concluído |
| **Retorno (sucesso)** | `sucesso`, `status`, `total_valido_congelado`, `horario_conceitual`, `horario_real_execucao`, `atrasado`, `versao_eventos` |
| **Recusas de negócio** | `lote_inexistente`, `instante_nao_atingido` — ambas sem evento e sem recibo |

- A contagem é a real do instante (`COUNT` de registros válidos do lote, com a linha do lote bloqueada), nunca a do upload.
- `atrasado` é verdadeiro somente quando o horário real é estritamente maior que o conceitual.
- As pré-condições são verificadas, com a linha do lote já bloqueada, **antes** de reservar o recibo: com chave determinística, um recibo de recusa persistido tornaria a recusa permanente e impediria o congelamento legítimo posterior.
- Lote já congelado devolve o resultado gravado na primeira execução (replay).

**Estado impossível da arquitetura — divergência entre a contagem real e `lotes.total_valido`.** Com a linha do lote bloqueada, a contagem real de registros válidos do lote e o valor de `lotes.total_valido` são, por construção, iguais: toda alteração de validade passa por `fn_registrar_correcao`, que ajusta os dois na mesma transação. Uma divergência entre eles **não é uma recusa de negócio nem uma condição operacional prevista** — é um estado que a arquitetura declara impossível e cuja ocorrência só pode significar defeito de implementação ou alteração de dados fora das funções. Ao detectá-la, a função:
- aborta imediatamente a transação inteira;
- não gera evento;
- não gera recibo de idempotência;
- não altera nenhum estado persistente — o lote permanece exatamente como estava, em `aguardando_d8`.

A função nunca corrige o total, nunca escolhe um dos dois números e nunca congela sobre dado inconsistente. O aborto é sinalizado por erro próprio de invariante violada, com mensagem fixa e sem valores, distinto do `SQLSTATE 22023` reservado ao conflito de idempotência. Como nada é persistido, uma nova tentativa encontra o mesmo estado e aborta da mesma forma, até que haja investigação e intervenção humanas — o congelamento desse lote não prossegue automaticamente em hipótese alguma.

###### `fn_confirmar_disparo`

| | |
|---|---|
| **Comando / evento / agregado** | `confirmar_disparo` / `disparo_confirmado` / `lote` |
| **Role** | `nsi_operador_restrito` |
| **Parâmetros** | `p_lote_id UUID`, `p_total_esperado INTEGER`, `p_chave_idempotencia TEXT`, `p_payload_hash TEXT` |
| **Pré-condições** | status `aguardando_confirmacao_disparo`; `p_total_esperado = total_valido_congelado` |
| **Pós-condições (sucesso)** | status `disparo_confirmado`; `disparo_confirmado_em`, `disparo_confirmado_por_login` e `total_confirmado_para_disparo` preenchidos; um evento `disparo_confirmado` com `operador_humano_id` nulo; recibo concluído |
| **Retorno (sucesso)** | `sucesso`, `lote_id`, `disparo_confirmado_em`, `total_confirmado`, `versao_eventos` |
| **Recusas de negócio** | `lote_inexistente`, `lote_nao_congelado`, `sem_registros_validos`, `disparo_ja_confirmado`, `total_divergente` |

- `p_total_esperado` é a precondição fornecida pelo chamador prevista pela ADR-009 (Seção 6): a confirmação só vale para a composição definitiva que foi apresentada.
- A função não envia, não agenda e não autoriza nenhum envio técnico — apenas registra o fato. O `occurred_at` do evento é o T0 da Coleta (ADR-005, Princípio 1).

###### `fn_registrar_correcao`

| | |
|---|---|
| **Comando / evento / agregado** | `registrar_correcao` / `correcao_registrada` / `registro_coleta` |
| **Role** | `nsi_aplicacao` |
| **Parâmetros** | `p_lote_id UUID`, `p_registro_coleta_id UUID`, `p_nome TEXT`, `p_whatsapp TEXT`, `p_produto TEXT`, `p_valido BOOLEAN`, `p_motivos_invalidez TEXT[]`, `p_chave_idempotencia TEXT`, `p_payload_hash TEXT` |
| **Pré-condição para gerar evento** | registro existente e pertencente a `p_lote_id` |
| **Retorno** | `sucesso`, `resultado`, `numero_versao_dados` (só quando aplicada), `versao_eventos` |
| **Recusas de negócio** | com evento: `recusada_ja_valido`, `recusada_tardia`; sem evento: `registro_nao_resolvido_neste_lote` |

Ordem de decisão, preservando a da Sprint A3 (`core/scheduler.py::processar_uma_correcao`):
1. registro já válido → `recusada_ja_valido`;
2. `now() >= horario_conceitual_congelamento` do lote, ou lote fora de `aguardando_d8` → `recusada_tardia`;
3. caso contrário, aplica: `aplicada_valida` ou `aplicada_ainda_invalida`, conforme a classificação recebida.

- **Fronteira:** correção exatamente na fronteira é tardia, mesmo que o congelamento técnico ainda não tenha sido executado. A regra do status cobre a correção que começou antes da fronteira mas ficou aguardando o bloqueio do lote enquanto o congelamento terminava.
- **Aplicação:** o valor anterior é sobrescrito (nenhum histórico de valores — ADR-009, Seção 5); `valido`, `motivos_invalidez`, `numero_versao_dados` e `versao_eventos_atual` do registro são atualizados; os totais do lote são ajustados na mesma transação, sem evento de lote e sem mudança de status.
- **Recusa com evento:** nenhum valor pessoal, total ou `numero_versao_dados` é alterado; apenas `versao_eventos_atual` do registro avança.
- **`p_lote_id` é obrigatório:** a resolução do registro é restrita ao lote informado, como na Sprint A3 — sem ele, uma correção apresentada em uma Operação poderia alterar um registro de outra.
- **Registro não resolvido:** registro inexistente, ou pertencente a outro lote, não gera `correcao_registrada`. A recusa `registro_nao_resolvido_neste_lote` vem acompanhada de um campo `diagnostico` (`codigo_inexistente` | `registro_de_outra_operacao`), feito pelo banco porque a aplicação não tem leitura direta; com ele, o chamador registra a tentativa por `fn_registrar_tentativa_nao_resolvida`.
- **`codigo_tecnico`:** o `codigo_tecnico` da ADR-009 é o próprio `registro_coleta_id` (o CSV de correção da Sprint A3 já o usa como código técnico), por isso `eventos_registro_coleta` o representa em `aggregate_id`, sem coluna separada.

###### `fn_registrar_tentativa_nao_resolvida`

| | |
|---|---|
| **Comando / evento / agregado** | `registrar_tentativa_nao_resolvida` / `tentativa_correcao_nao_resolvida` / `lote` |
| **Role** | `nsi_aplicacao` |
| **Parâmetros** | `p_lote_id UUID`, `p_motivo TEXT`, `p_codigo_tecnico_normalizado UUID` (pode ser nulo), `p_chave_idempotencia TEXT`, `p_payload_hash TEXT` |
| **Pré-condições** | lote existente; motivo dentro dos quatro valores da ADR-009 (Seção 8); código nulo se e somente se `motivo` ∈ {`codigo_ausente`, `codigo_invalido`}; código não resolve a registro deste lote; motivo conferido contra o banco |
| **Pós-condições (sucesso)** | um evento `tentativa_correcao_nao_resolvida`; `versao_eventos_atual` do lote avança; nenhum outro efeito na projeção; recibo concluído |
| **Retorno (sucesso)** | `sucesso`, `evento_id`, `versao_eventos` |
| **Recusas de negócio** | `lote_inexistente`, `motivo_invalido`, `motivo_incoerente_com_codigo`, `codigo_resolve_neste_lote`, `motivo_diverge_do_estado` |

- A coerência entre motivo e código é imposta pela função, porque a `CHECK` da tabela não a impõe.
- Conferência contra o banco: `codigo_inexistente` exige que o código não exista em nenhum lote; `registro_de_outra_operacao` exige que exista em outro lote.
- O parâmetro do tipo `UUID` torna impossível gravar um código bruto sintaticamente inválido. Não existe parâmetro de texto livre, nome, telefone ou produto.
- É aceita em qualquer status do lote, inclusive depois do congelamento.

##### Idempotência

Envelope idêntico ao da `0003`: reserva em `comandos_idempotentes` com `INSERT ... ON CONFLICT (comando, aggregate_id, chave_idempotencia) DO NOTHING`; mesma chave com mesmo `payload_hash` devolve o `resultado` persistido (replay), sem novo evento; mesma chave com `payload_hash` divergente levanta `conflito_de_idempotencia` com `SQLSTATE 22023` e mensagem fixa, sem interpolar chave, hash ou valor, e o recibo original permanece intocado.

| Função | Escopo da chave | Natureza |
|---|---|---|
| `fn_registrar_lote` | `(registrar_lote, lote_id, chave)` | por tentativa de upload |
| `fn_registrar_congelamento` | `(registrar_congelamento, lote_id, lote_id em texto)` | determinística, derivada dentro da função |
| `fn_confirmar_disparo` | `(confirmar_disparo, lote_id, chave)` | por tentativa de confirmação |
| `fn_registrar_correcao` | `(registrar_correcao, registro_coleta_id, chave)` | por tentativa de correção — nunca o próprio `registro_coleta_id` |
| `fn_registrar_tentativa_nao_resolvida` | `(registrar_tentativa_nao_resolvida, lote_id, chave)` | por tentativa |

- As quatro funções com chave fornecida reservam o recibo antes de qualquer efeito. Suas recusas de negócio também gravam recibo: a repetição com a mesma chave devolve a mesma recusa.
- Chave nova sobre fato que só pode ocorrer uma vez (segundo upload do mesmo lote, segunda confirmação) é recusa de negócio, nunca segundo evento.
- O congelamento é a exceção: pré-condições antes da reserva; recusa e estado impossível não deixam recibo; duas execuções do mesmo lote, mesmo concorrentes e em instantes diferentes, produzem um evento e um replay, nunca conflito (ADR-009, Seção 12).

##### `payload_hash`

- **Formato:** SHA-256 em hexadecimal minúsculo (64 caracteres, conforme `ck_comandos_idempotentes_payload_hash_sha256`) sobre a serialização canônica da entrada semântica do chamador: JSON com chaves ordenadas, UTF-8, sem espaços, com um discriminador do comando.
- **Composição por comando**, conforme a ADR-009 (Seção 6):
  - `registrar_lote`: `lote_id`, `lote_id_legado`, registros ordenados por `registro_coleta_id`, cada um com seus seis campos e os motivos ordenados;
  - `registrar_congelamento`: `lote_id`;
  - `confirmar_disparo`: `lote_id`, `total_esperado`;
  - `registrar_correcao`: `lote_id`, `registro_coleta_id`, `nome`, `whatsapp`, `produto`, `valido`, motivos ordenados;
  - `registrar_tentativa_nao_resolvida`: `lote_id`, `motivo`, código normalizado (ou nulo).
- **O que entra:** os valores exatamente como passados à função, já normalizados. Nenhum valor gerado pelo servidor e nunca a chave de idempotência.
- **Quem calcula:** o chamador, para as quatro funções com chave fornecida; a própria função, no congelamento (SHA-256 nativo do PostgreSQL, sem extensão).
- **Sem recálculo:** a função não recalcula o hash recebido — mesmo comportamento da `0003`. Um hash incorreto compromete apenas a idempotência do próprio chamador.
- **Módulo único de produção:** o cálculo canônico em Python é um módulo de produção novo e puro — sem acesso a banco e sem alterar nenhum arquivo existente —, usado também pelos testes, de modo que exista uma única implementação. O hash que `fn_registrar_congelamento` calcula internamente deve ser idêntico ao que esse módulo produz para o mesmo `lote_id`.
- **Correlação:** o hash de `registrar_lote` e de `registrar_correcao` cobre conteúdo pessoal e é, por isso, potencialmente correlacionável (ADR-009, Seção 9) — vive somente em `comandos_idempotentes`, nunca em evento.

##### Critérios de segurança

- `PUBLIC` sem `EXECUTE` em nenhuma das cinco funções (`REVOKE` explícito, obrigatório).
- Matriz de `EXECUTE` exatamente a dos contratos acima (ADR-009, Seção 11); `nsi_expiracao` em nenhuma das cinco.
- Nenhuma role funcional ganha DML ou leitura direta em `lotes`, `registros_coleta`, `eventos_lote`, `eventos_registro_coleta` ou `comandos_idempotentes` — o chamador conhece o estado exclusivamente pelo retorno das funções.
- A autorização decorre exclusivamente de `GRANT EXECUTE`; nenhum valor de parâmetro concede privilégio.
- Nenhum valor pessoal em evento, em `resultado` (retorno e recibo de idempotência), em mensagem ou detalhe de exceção, ou em saída de teste — apenas identificadores, enums, contadores e timestamps. Valores pessoais trafegam apenas como parâmetros vinculados, nunca interpolados em SQL.
- Nenhuma DSN, senha, token, segredo ou hash reutilizável em exceção, log, `repr`, `resultado` ou saída capturada — mesmo endurecimento dos testes da B3.
- Os scripts administrativos não contêm senha e verificam a identidade do servidor antes de qualquer escrita.
- Verificação de ambiente, fora das funções: a configuração de log do servidor não pode registrar os parâmetros das consultas, que carregam valores pessoais.

##### Estratégia de testes

Mesma separação da Seção 20: unitários em Python puro; integração somente contra PostgreSQL real (`pg_integration`), sem SQLite e sem mock; nenhum teste usa banco ou credencial de produção.

- **Scripts administrativos (unitários, estáticos):** ordem das três fases, gates, ausência de senha, ausência de comando destrutivo fora da reversão.
- **Provisionamento (integração, somente leitura):** atributos da role, ausência de membership inesperada, membership de `nsi_aplicacao` com `INHERIT FALSE`, `USAGE` no schema nos dois bancos.
- **`payload_hash` (unitários):** determinismo, ordenação, insensibilidade à ordem dos registros e dos motivos; e, em integração, igualdade entre o hash calculado por `fn_registrar_congelamento` e o do módulo para o mesmo `lote_id`.
- **Por função:** caminho de sucesso; cada recusa de negócio; conteúdo exato do evento gravado e da projeção resultante; `executado_por_login` igual ao `session_user` real.
- **Fronteira temporal, sem espera real:** congelamento e correção um microssegundo antes, exatamente em, e um microssegundo depois de `horario_conceitual_congelamento`.
- **Congelamento:** `atrasado` correto; contagem real do instante divergindo da contagem do upload após correções; lote sem válidos → `sem_registros_validos`; chamada prematura sem evento e sem recibo, seguida de chamada legítima bem-sucedida; dois workers concorrentes reais → um evento, o outro replay.
- **Estado impossível:** divergência entre a contagem real e `lotes.total_valido`, provocada artificialmente pelo próprio teste → a função aborta com o erro de invariante; nenhum evento, nenhum recibo, lote inalterado em `aguardando_d8`; nova tentativa aborta da mesma forma.
- **Diagnóstico de correção:** registro inexistente e registro de outro lote devolvem `registro_nao_resolvido_neste_lote` com o `diagnostico` correto, sem evento; a tentativa correspondente é aceita com o motivo coerente e recusada com o motivo divergente.
- **Concorrência real (duas conexões):** correção contra congelamento na fronteira; duas correções simultâneas ao mesmo registro, sem perda de atualização e com versões sem lacuna; dois uploads com o mesmo `lote_id`; duas confirmações do mesmo lote.
- **Idempotência:** replay sem novo evento, inclusive em nova conexão; mesma chave com payload diferente → `SQLSTATE 22023` com mensagem fixa; recibo original intocado.
- **Privacidade:** varredura das colunas de `eventos_lote` e `eventos_registro_coleta` e de `comandos_idempotentes.resultado`, confirmando ausência dos valores pessoais usados no teste; violação de constraint provocada com valores pessoais conhecidos, com mensagem e detalhe do erro inspecionados, sem nenhum desses valores.
- **Permissão:** cada role tentando cada função fora da sua matriz → falha; `nsi_aplicacao` chamando a função de congelamento sem `SET ROLE` → falha; DML direto por qualquer role funcional → falha; `PUBLIC` sem `EXECUTE`.
- **Imutabilidade:** nenhuma das cinco funções provoca `UPDATE`/`DELETE` em evento; triggers da `0004` continuam ativas.
- **Migration:** ciclo `0005 → 0004 → 0005` exclusivamente em `nsi_test`, com o gate obrigatório de identidade; inventário somente leitura confirmando exatamente cinco funções novas, owner, `SECURITY DEFINER`, `search_path` e matriz de `EXECUTE`.
- **Limpeza:** todo teste com commit real remove explicitamente os recibos que criou (ver "Critérios de rollback").
- **Regressão:** suíte completa do projeto, sem exclusões, sem falhas e sem pulados.

##### Critérios de aceite

1. Role `nsi_congelamento` provisionada pelo script de três fases, executado duas vezes, ambas concluindo com a pós-validação completa aprovada.
2. `0005` cria exatamente as cinco funções acima e nada mais — nenhuma tabela, coluna, constraint, índice, trigger ou função auxiliar.
3. As cinco funções têm owner `nsi_eventos_owner`, `SECURITY DEFINER` e `search_path` fixo, comprovados por inspeção somente leitura.
4. Matriz de `EXECUTE` idêntica à da ADR-009 (Seção 11), comprovada por inspeção somente leitura.
5. Cada um dos cinco eventos é gravado com o payload exato da ADR-009 e a projeção correspondente, na mesma transação.
6. Replay e conflito de idempotência comprovados para as cinco funções; replay do congelamento comprovado sob concorrência real.
7. Nenhum valor pessoal em evento, recibo, exceção ou saída de teste.
8. `0005` aplicada primeiro em `nsi_test`; depois em `nsi_dev`, somente por `upgrade`, com identidade confirmada antes de qualquer ação. Ambos terminam em `0005 (head)`.
9. Suíte específica da B4.3 e suíte completa do projeto aprovadas integralmente.
10. `0001`–`0004` e todo arquivo já existente de `adapters/`, `core/`, `app.py`, `integration/` e `services/` sem nenhuma alteração; o único arquivo novo de produção fora de `migrations/` e `scripts/` é o módulo de `payload_hash`.
11. Documentação de encerramento registrada neste documento, no `ROADMAP-SPRINTS-B-G.md` e no `PROJECT_STATUS.md`.

##### Critérios de rollback

- **Migration:** o `downgrade` da `0005` remove exatamente as cinco funções, na ordem inversa da criação, com `SET LOCAL ROLE`/`RESET ROLE` e autoverificação. Não toca tabelas, dados, recibos nem a role.
- **Onde o downgrade é permitido:** somente em `nsi_test`, com o gate de identidade (banco, servidor, porta, `nsi_test_migrator`) confirmado antes. Nenhum `downgrade` é executado em `nsi_dev` — mesma regra de toda a Sprint B3.
- **Dados não são revertidos:** eventos são imutáveis inclusive para o owner. Reverter a `0005` retira a capacidade de gravar novos eventos; nunca apaga os já gravados.
- **Recibos de teste e o preflight da `0004`:** qualquer recibo dos cinco comandos da B4 em `comandos_idempotentes` faz o downgrade `0004 → 0003` abortar. Por isso, cada teste com commit real remove explicitamente, ao final, os recibos que ele próprio criou — identificados pelas suas próprias chaves, nunca por remoção em massa —, e o teste de ciclo destrutivo confirma zero recibos da B4 antes do downgrade, falhando com mensagem clara se houver. A regra de preflight da `0004` não é reaberta nem enfraquecida. Linhas de `lotes`, `registros_coleta` e eventos deixadas por esses testes permanecem como resíduo sintético deliberado em `nsi_test`, nunca em `nsi_dev`, como na B3.
- **Role:** a reversão administrativa exige a função de congelamento já ausente (revisão exatamente `0004` nos dois bancos), verifica ausência de privilégios e objetos residuais antes de qualquer `DROP ROLE`, exige confirmação textual exata e não contém senha. Implementada e documentada, mas não executada na subetapa.
- **Critério de interrupção:** se a implementação revelar defeito na `0004` ou tensão com a ADR-009, a B4.3 para e o ponto é levado à decisão — nunca corrigido de forma silenciosa dentro da `0005`. `nsi_dev` só recebe a `0005` depois de a suíte completa passar em `nsi_test`.

##### Registro de implementação

**Commits** (todos em `main`): `0c82df1` (adaptação da validação de membership da B3.1 à exceção da ADR-009), `319e24f` (script de provisionamento da role e seus testes estáticos), `c5d7176` (script de desprovisionamento), `f3e51fd` (sincronização dos critérios de rollback para a revisão `0004`), `cfb57bc` (migration `0005`, módulo de `payload_hash` e suíte de testes) e `c665cda` (correção de um detector estático do teste do provisionamento).

**Arquivos entregues** — nomes finais dos candidatos de "Arquivos previstos":

| Arquivo | Natureza |
|---|---|
| `scripts/postgres_local/provisionar_b4_role_congelamento.sql` | novo |
| `scripts/postgres_local/desprovisionar_b4_role_congelamento.sql` | novo — não executado |
| `migrations/versions/0005_cinco_funcoes_eventos_operacionais.py` | novo |
| `core/payload_hash.py` | novo — o módulo de produção do `payload_hash`, puro, sem acesso a banco |
| `tests/unit/test_payload_hash.py`, `tests/unit/test_scripts_b4_role_congelamento.py` | novos |
| `tests/integration/test_provisionamento_b4_role_congelamento.py`, os cinco `test_fn_*.py`, `test_idempotencia_e_permissoes_b4_3.py`, `test_migration_0005_upgrade_downgrade.py` | novos |
| `tests/apoio_b4_3.py` | novo — apoio comum aos testes de integração da B4.3 (identificadores, registros sintéticos, criação de lote pela própria função, posicionamento na fronteira temporal e espera de bloqueio em concorrência real) |
| `tests/regra_membership_b3_1.py`, `tests/unit/test_regra_membership_b3_1.py` | novos — regra de membership da B3.1 com a exceção única da ADR-009, Seção 21 |
| `tests/integration/test_provisionamento_b3_roles.py` | ajuste — passa a aceitar somente a exceção da ADR-009 |
| `tests/integration/test_alembic_postgres.py`, `test_migration_0002_upgrade_downgrade.py`, `test_migration_0004_upgrade_downgrade.py` | ajuste — somente o novo head `0005` |
| `docs/implementation/PROCEDIMENTO-MANUAL-B4-ROLE-CONGELAMENTO-DESTRUTIVO.md` | novo — cenários destrutivos da role, exclusivamente manuais, não executados |

**Decisões tomadas dentro da especificação** — nenhuma amplia o catálogo, a matriz de papéis ou o contrato das cinco funções:

- **Contrato de erro.** Recusa de negócio continua sendo retorno estruturado. As exceções têm mensagem fixa, sem `DETAIL` e sem nenhum valor: `conflito_de_idempotencia` (`SQLSTATE 22023`); `entrada_estrutural_invalida` (`SQLSTATE 22000`); `violacao_de_constraint` (`SQLSTATE` nativo da classe 23); e `invariante_violada` (`SQLSTATE` próprio `NS001`, o erro de estado impossível do congelamento). A violação de constraint repassa o **nome** da constraint, para diagnóstico, e nunca a linha, cujo detalhe nativo traria nome e WhatsApp.
- **Validação da chave e do hash antes da reserva.** Chave de idempotência fora de 1 a 200 caracteres, ou `payload_hash` fora do formato SHA-256, é `entrada_estrutural_invalida` antes de qualquer escrita. Sem isso, a `CHECK` de `comandos_idempotentes` seria violada na reserva, e seu detalhe nativo exporia a linha com o hash.
- **Lote sem nenhum registro é recusado.** Lista de registros vazia é `entrada_estrutural_invalida` (`22000`), sem lote, evento ou recibo. Decisão humana da B4.3, que resolve a Seção 22, item 11. Não se confunde com o lote sem nenhum registro **válido**, que continua sendo criado normalmente.
- **`registro_coleta_id` já gravado por outro lote concorrente** também é `entrada_estrutural_invalida`: a mesma classificação do registro já existente detectado sem corrida.
- **Ordem de avaliação em `fn_registrar_lote`.** O PostgreSQL avalia as `CHECK`s de `lotes` antes do teste de conflito do `ON CONFLICT`. Um segundo upload do mesmo `lote_id` com `lote_id_legado` fora do formato recebe, por isso, `violacao_de_constraint`, e não `lote_ja_existe`. Comportamento documentado na migration e fixado por teste.
- **Nível de isolamento.** As cinco funções exigem `READ COMMITTED`, o padrão do PostgreSQL e do projeto: replay do congelamento concorrente, correção tardia pela regra do status e segunda confirmação recusada dependem de o `FOR UPDATE` reler a linha já confirmada pela transação concorrente. Sob `REPEATABLE READ` ou `SERIALIZABLE`, os mesmos cenários terminariam em falha de serialização (`40001`).
- **Serialização canônica do `payload_hash`.** `sha256` sobre o JSON com o discriminador `comando` e os campos da composição, chaves ordenadas, separadores sem espaço, UTF-8 sem escape, e UUIDs canônicos em minúsculas. O hash do congelamento calculado no SQL é idêntico ao do módulo, comprovado em integração.

**Execução real:**

- Dependência 2 confirmada por leitura antes de qualquer ação: `nsi_test` e `nsi_dev` em `0004`.
- Provisionamento administrativo da role executado pelo operador humano, com credencial própria do superusuário local (nunca acessada pela automação), concluindo com a pós-validação completa aprovada. Primeira execução reportada em 2026-10-03, com os dois bancos em `0004`. Segunda execução em 2026-10-03, já com os dois bancos em `0005`: a Fase 1 reconheceu o estado previsto, as quatro ações da Fase 2 responderam "ja presente, nada a fazer" (convergência idempotente, sem nenhuma alteração real) e a Fase 3 passou integralmente nos itens 3.1 a 3.7.
- `0005` aplicada primeiro em `nsi_test`, com o gate de identidade (banco, servidor local, porta 5432, `nsi_test_migrator`) confirmado antes de cada `downgrade`. O ciclo `0005 → 0004 → 0005` foi executado mais de uma vez em `nsi_test`, durante a implementação e após as correções da auditoria.
- `0005` aplicada em `nsi_dev` em 2026-10-03, **somente por `upgrade`**, depois da suíte completa aprovada em `nsi_test` e com a identidade confirmada antes (banco `nsi_dev`, servidor local, porta 5432, `nsi_dev_migrator`, revisão `0004`). Nenhum `downgrade` foi executado em `nsi_dev`.
- Inspeção somente leitura de `nsi_dev` após o upgrade: exatamente as cinco funções, com definição idêntica à de `nsi_test`; owner `nsi_eventos_owner`; `SECURITY DEFINER`; `search_path` fixo; `PUBLIC` sem `EXECUTE`; matriz de `EXECUTE` idêntica à da ADR-009; zero linhas nas tabelas operacionais e zero recibos da B4.
- `nsi_test` e `nsi_dev` terminam ambos em `0005 (head)`.
- O script de desprovisionamento não foi executado.

**Testes** (contagens na suíte final): 355 testes da B4.3, sendo 150 unitários (`test_scripts_b4_role_congelamento.py`: 111; `test_payload_hash.py`: 39) e 205 de integração real. Os de integração se distribuem assim:

| Arquivo | Testes |
|---|---|
| `test_fn_registrar_lote.py` | 34 |
| `test_fn_registrar_congelamento.py` | 15 |
| `test_fn_confirmar_disparo.py` | 15 |
| `test_fn_registrar_correcao.py` | 22 |
| `test_fn_registrar_tentativa_nao_resolvida.py` | 26 |
| `test_idempotencia_e_permissoes_b4_3.py` | 76 |
| `test_migration_0005_upgrade_downgrade.py` | 4 |
| `test_provisionamento_b4_role_congelamento.py` | 13 |

Suíte completa do projeto, com integração real obrigatória: **1013 de 1013 aprovados, nenhuma falha, nenhum pulado**. Sem `pg_integration`: 478 coletados, 535 desmarcados.

**Auditoria anterior ao commit.** Uma auditoria técnica crítica encontrou um bloqueador e seis pontos menores, todos corrigidos e cobertos por teste antes do commit, sem reabrir a especificação:

- O bloqueador: um `payload_hash` malformado atingia a `CHECK` de `comandos_idempotentes`, cujo detalhe nativo expunha o hash.
- Os pontos menores:
  - a corrida entre lotes com o mesmo `registro_coleta_id` era classificada como violação de constraint;
  - a violação de constraint não trazia o nome da constraint;
  - o lote com lista vazia não tinha decisão;
  - a ordem entre `CHECK` e `ON CONFLICT` não estava documentada;
  - o contrato de isolamento não estava documentado;
  - a folga de relógio real do único teste que depende dele estava curta.

**Resíduo de teste.** Os testes com commit real removem, ao final, os recibos que criaram, pelas próprias chaves e nunca por remoção em massa. Assim, o teste de ciclo confirma zero recibos da B4 antes do downgrade, e a regra de preflight da `0004` não foi enfraquecida. Lotes, registros e eventos desses testes ficam como resíduo sintético em `nsi_test`, nunca em `nsi_dev`, até o ciclo destrutivo da própria suíte (`downgrade base`) remover as tabelas da `0004`.

**Situação dos critérios de aceite:**

| # | Critério | Situação |
|---|---|---|
| 1 | Provisionamento executado duas vezes, ambas com pós-validação aprovada | satisfeito — duas execuções, ambas com "Fase 3 (pós-validação completa) passou integralmente" |
| 2 | Exatamente as cinco funções, nada mais | satisfeito |
| 3 | Owner, `SECURITY DEFINER` e `search_path` comprovados por leitura | satisfeito, nos dois bancos |
| 4 | Matriz de `EXECUTE` comprovada por leitura | satisfeito, nos dois bancos |
| 5 | Cinco eventos com payload exato e projeção na mesma transação | satisfeito |
| 6 | Replay e conflito nas cinco funções; replay do congelamento sob concorrência real | satisfeito |
| 7 | Nenhum valor pessoal em evento, recibo, exceção ou saída de teste | satisfeito |
| 8 | `nsi_test` primeiro; `nsi_dev` só por `upgrade`; ambos em `0005 (head)` | satisfeito |
| 9 | Suíte da B4.3 e suíte completa aprovadas | satisfeito — 1013 de 1013 |
| 10 | `0001`–`0004` e arquivos existentes de produção intocados; único arquivo novo de produção fora de `migrations/` e `scripts/` é o módulo de `payload_hash` | satisfeito — `core/payload_hash.py` |
| 11 | Documentação de encerramento neste documento, no ROADMAP e no `PROJECT_STATUS.md` | satisfeito por esta revisão |

### B4, B5, B6, B7 — resumo
- **B4:** B4.1 e B4.2 concluídas; B4.3 concluída (detalhamento acima).
- **B5:** script de importação em ambiente de teste/staging; validação de paridade contra os 213 cenários existentes; nunca toca produção.
- **B6:** ver Seção 19.
- **B7:** ver Seção 14; produção, autorização própria.

## 19. Regras do Ensaio de Corte (B6)

Dados sintéticos representativos são o padrão. Dados reais só quando estritamente necessários, mediante autorização humana explícita e específica; quando usados: minimização, anonimização/pseudonimização sempre que possível, ambiente isolado (nunca instância/credenciais de produção), criptografia em repouso e trânsito, controle de acesso restrito, prazo de retenção definido previamente, eliminação auditada ao final. Nunca reutilizar credenciais ou banco de produção informalmente. O ensaio não altera a fonte de verdade e não escreve em produção — executa os passos 1–4 da ADR-008 §16 inteiramente em ambiente controlado, sem o passo 5.

---

## 20. Plano de Testes

**Separação obrigatória:** unitários (Python puro — geração de token, hash, formatação de parâmetros, sem tocar banco) vs. integração (PostgreSQL real — transação, locks, concorrência, constraints, roles, `SECURITY DEFINER`, trigger, `TIMESTAMPTZ`, idempotência). **Nenhum SQLite, nenhum mock** para os itens de integração. **Nenhum teste usa credencial ou banco de produção.**

- Criação: primeira vez; após `liberado`; recusa com `ativo`/`expirado_pendente_revisao`; dois workers reais disputando.
- Heartbeat: um microssegundo antes/exatamente na/um microssegundo depois da fronteira (via transação com `now()` congelado, Seção 7); token/`claim_id` errados; nunca muda `numero_tentativa`.
- Liberação: sucesso; após expiração técnica (materializa em vez de liberar).
- Materialização: idempotência sob execução concorrente real repetida.
- Revisão: sempre gera evento, inclusive decidindo não reatribuir; projeção inalterada exceto versão.
- Reatribuição: exige revisão válida vinculada ao `claim_id` correto; recusa sem ela; recusa com revisão de geração antiga; concorrência entre duas reatribuições com a mesma revisão — uma única vencedora.
- Idempotência: mesma chave/mesmo pedido → mesmo resultado sem novo evento, inclusive após **nova conexão** (simulando reinício de processo); mesma chave/pedido diferente → conflito; `resultado` inspecionado, confirmando ausência de token/segredo.
- Permissão: `nsi_aplicacao` tentando `INSERT`/`UPDATE`/`DELETE` direto → falha; `nsi_expiracao` tentando `EXECUTE` em `fn_registrar_revisao_abandono`/`fn_reatribuir_claim` → falha; trigger defensiva confirmada.
- `session_user` corretamente usado como identidade, com `app.worker_id` forjado não concedendo privilégio.
- Token: `token_bruto` nunca aparece em nenhuma tabela/log de teste; comparação com token incorreto sempre falha; reatribuição invalida definitivamente o token anterior.
- Regressão completa da suíte atual (213 testes) sem quebra.

## 21. Riscos e Mitigação

Tensão de granularidade entre modelo atual (arquivo mutável inteiro) e modelo-alvo (linha por `registro_coleta_id`); janela de corte exigindo pausa real de todos os pontos de entrada de escrita hoje existentes; volume de dados em produção desconhecido; compatibilidade com fallbacks existentes (`_contar_validos`); testes de deadlock/concorrência da Sprint A3 precisam ser adaptados, não descartados, para validar as novas invariantes transacionais; limitação declarada de reentrega de token (Seção 4.2); identidade de worker/humano ainda fraca até a Sprint D (Seção 4.3).

## 22. Checklist de Decisões Humanas/Infraestruturais Pendentes

1. Decisão arquitetural formal do catálogo de eventos operacionais (Seção 9) — bloqueia B4.
2. Escolha final de isolamento de infraestrutura A/B/C (Seção 12).
3. Mecanismo de backup, responsável, retenção, RPO, RTO, comprovação de teste de restauração (Seção 14) — bloqueia B7.
4. Nome final da classificação de registros legados sem identidade técnica (Seção 10).
5. Retenção da tabela `comandos_idempotentes` (Seção 16).
6. Nomes físicos definitivos de coluna (candidatos nesta especificação) e prefixo de ambiente para as roles conceituais aprovadas (Seção 5).
7. Confirmação, subetapa a subetapa, de necessidade de dados reais em B6 (Seção 19).
8. Eventual evolução futura para HMAC com pepper no token (Seção 4.1) — não bloqueante, decisão técnica formal própria quando/se necessária.
9. B4.3 — local do `GRANT EXECUTE` da função de congelamento a `nsi_congelamento`: na própria `0005` ou em passo administrativo posterior (Seção 18).
10. B4.3 — confirmação, por leitura, da revisão corrente de `nsi_test`/`nsi_dev` e da suíte completa sobre a `0004`, antes de qualquer ação (Seção 18).
11. B4.3 — verificações anteriores à implementação: se o upload atual aceita CSV sem nenhuma linha de dados (define se `fn_registrar_lote` aceita lista vazia); e ausência de trigger que impeça remoção em `comandos_idempotentes` (premissa da limpeza de recibos de teste).
12. Registro de lotes legados com M0 no passado — não atendido por `fn_registrar_lote`; pertence à B5.

**Item 1 resolvido:** a decisão arquitetural do catálogo de eventos operacionais foi tomada pela ADR-009 (B4.1) e deixou de bloquear a B4.

**Item 9 resolvido:** a role `nsi_congelamento` é criada exclusivamente pelo script administrativo; a `0005` assume sua existência e aplica todos os `REVOKE` e `GRANT EXECUTE` das cinco funções, deixando as permissões completas ao final da migration (Seção 18).

**Item 10 resolvido:** `nsi_test` e `nsi_dev` foram confirmados por leitura em `0004` antes de qualquer ação da implementação da B4.3 (Seção 18, "Registro de implementação").

**Item 11 resolvido:** lote com lista de registros vazia é recusado por `fn_registrar_lote` como entrada estruturalmente inválida (`SQLSTATE 22000`), por decisão humana da B4.3. Nenhuma trigger impede remoção em `comandos_idempotentes`, e a limpeza dos recibos de teste pelas próprias chaves funciona como especificado (Seção 18, "Registro de implementação").

**Não são pendências da B4.3:** o contrato das cinco funções, o bloqueio da linha do lote, o módulo de `payload_hash`, a limpeza dos recibos de teste e o tratamento do estado impossível estão decididos e registrados na Seção 18.

**Não são mais pendências:** algoritmo de hash do token (decidido: SHA-256 simples, Seção 4.1); comportamento em caso de resposta perdida na criação/reatribuição (decidido: fail-safe, Seção 4.2); identidade do executor (decidido: `session_user` + rótulo informativo, Seção 4.3); nomes de schema/tabelas/funções/roles conceituais (decididos, Seção 5).

## 23. Status e Histórico de Revisão

**B1: CONCLUÍDA.** Consolida o texto integral de todas as rodadas de correção desta sessão de planejamento. Subordinada à ADR-008 (APROVADA E CONGELADA) e ao `ROADMAP-SPRINTS-B-G.md`. Nenhuma implementação de código, schema, migration ou dependência foi realizada por este documento.

**B2 (Infraestrutura, Conexão e Migrations): CONCLUÍDA.** Subetapas B2.1, B2.2 e B2.3 executadas e validadas integralmente (Seção 18) — dependências instaladas, esteira Alembic criada, PostgreSQL 17 local provisionado (`nsi_dev`, `nsi_test`, roles de migração, schema `nsi_operacional`), revisão `0001` aplicada em ambos os bancos (somente `alembic_version`, nenhuma tabela de negócio), suíte completa em 246/246, três testes de integração PostgreSQL real passando com zero pulados. Dois problemas reais de mecânica de conexão (dialeto SQLAlchemy; transação "autobegin") foram encontrados e corrigidos em `migrations/env.py` durante a validação — nenhuma decisão da ADR-008 foi alterada por isso. **Nenhuma implementação de tabela de negócio, evento, claim ou função `SECURITY DEFINER` foi realizada nesta subetapa — isso pertence integralmente às subetapas B3.2/B3.3, ainda não iniciadas.**

**B3.1 (Provisionamento administrativo, roles e isolamento): CONCLUÍDA.** A Sprint B3 foi dividida em quatro subetapas fixas (B3.1–B3.4, Seção 18) numa rodada de planejamento posterior a este documento ("Parte 1 da B3", aprovada e encerrada), agora incorporada aqui. Provisionamento idempotente em três fases (preflight completo → convergência → pós-validação completa), executado manualmente duas vezes contra o cluster PostgreSQL 17 local, ambas as execuções concluindo com "Fase 3 (pós-validação completa) passou integralmente" — comprovando a convergência segura, sem nenhuma alteração destrutiva, na segunda execução. As quatro roles funcionais criadas com atributos de segurança explícitos; isolamento de `CONNECT` por banco (`PUBLIC` sem `CONNECT`, cada migrator restrito ao próprio banco, as três roles funcionais nos dois bancos locais); `USAGE` no schema e propriedade do schema transferida para `nsi_eventos_owner` nos dois bancos, sem afetar `alembic_version` (permanece com o migrator). `config.py` estendido com `resolver_url_banco_papel()` para as seis variáveis funcionais, reaproveitando integralmente as proteções já validadas em B2.1. Senhas das três roles `LOGIN` definidas interativamente via `\password`; as seis URLs configuradas localmente no `.env`, fora do versionamento — nenhuma credencial exposta em nenhum artefato deste repositório. Reversão administrativa (`desprovisionar_b3_roles.sql`) implementada e documentada, mas não executada nesta subetapa. Testes de integração real, exclusivamente leitura: **20/20 aprovados**; suíte completa do projeto: **331/331 aprovados**, nenhuma falha, nenhum pulado. **Nenhuma tabela de negócio, evento, claim ou função `SECURITY DEFINER` foi criada nesta subetapa — isso pertence integralmente a B3.2/B3.3, ainda não iniciadas.**

**B3.2 (Migration `0002` — tabelas, constraints, índices e trigger defensiva): CONCLUÍDA.** Criadas `nsi_operacional.claims`, `nsi_operacional.eventos_claim`, `nsi_operacional.comandos_idempotentes`, com todas as `CHECK`s, a `PRIMARY KEY` composta e as `UNIQUE` normais já aprovadas; a FK composta diferível `claims_revisao_atual_fk`; os índices únicos parciais `eventos_claim_expirado_unico` e `eventos_claim_origem_claim_id_unica`; a função `fn_bloquear_alteracao_eventos_claim` e a trigger `eventos_claim_bloqueia_alteracao`; `REVOKE ALL` de `PUBLIC` e das três roles funcionais em cada tabela e na função da trigger — todos os nomes definitivos já aprovados fora desta migration, preservados sem alteração. Três defeitos foram encontrados e corrigidos **exclusivamente nos testes**, nunca na migration: suposição de estado inicial incompatível com o fluxo real; dado de teste incoerente (`concluido_em` anterior a `criado_em`) num caso de `comandos_idempotentes`; e `SET CONSTRAINTS` sem qualificação de schema, falhando por resolução via `search_path`. Um quarto ponto, também exclusivo dos testes, foi corrigido durante a validação real: o inventário estrutural usava `information_schema.tables` (filtrada por privilégio, ocultando as três tabelas do migrator, que não tem DML direto nelas) — corrigido para `pg_catalog.pg_tables`, sem esse filtro. Testes também endurecidos para nunca expor DSN em falha (obtenção via `request.getfixturevalue`, sem comparação direta contra saída capturada). Execução real: `0002` aplicada primeiro em `nsi_test` (suíte específica da B3.2: **97/97 aprovados**); ciclo `0002 → 0001 → 0002` comprovado em `nsi_test`, com o gate de identidade (`nsi_test`, servidor local, porta 5432, `nsi_test_migrator`) confirmado antes do único `downgrade`, terminando em `0002`; identidade de `nsi_dev` confirmada antes de qualquer ação, `0002` aplicada em `nsi_dev` **somente por `upgrade`** — nenhum `downgrade` executado em `nsi_dev`; `nsi_dev` termina em `0002`. Suíte completa do projeto, com integração real obrigatória: **428/428 aprovados, nenhuma falha, nenhum pulado**. **Nenhuma das seis funções `SECURITY DEFINER` nem a migration `0003` foram criadas nesta subetapa — pertencem integralmente a B3.3, ainda não iniciada.**

**B3.3 (Migration `0003` — seis funções `SECURITY DEFINER`): CONCLUÍDA.** Criadas exatamente as seis funções `SECURITY DEFINER` aprovadas na Seção 15 (`fn_criar_claim`, `fn_registrar_heartbeat`, `fn_liberar_claim`, `fn_materializar_expiracao`, `fn_registrar_revisao_abandono`, `fn_reatribuir_claim`), todas com owner `nsi_eventos_owner`, `search_path` fixo (`pg_catalog, nsi_operacional, pg_temp`) e `PUBLIC` sem `EXECUTE`; matriz de `EXECUTE` restrita por role conforme a Seção 8/15. Nenhum defeito real foi encontrado na migration — todas as correções desta subetapa foram exclusivamente de simulação temporal e desenho dos testes (Seção 18, detalhamento de B3.3). Execução real: `0003` aplicada primeiro em `nsi_test` (suíte específica da B3.3: **63/63 aprovados**; regressão completa compatível, excluindo deliberadamente `test_migration_0002_upgrade_downgrade.py`: **488/488 aprovados**), depois em `nsi_dev` **somente por `upgrade`** — nenhum `downgrade` executado em `nsi_dev` nesta subetapa; ambos terminam em `0003 (head)`. Dois testes deixam resíduo sintético deliberado e permanente em `nsi_test` (nunca em `nsi_dev`), por imutabilidade de `eventos_claim` combinada com FK não diferível para `claims`: concorrência real de reatribuição (1 `claims` + 1 `eventos_claim`) e persistência de idempotência sobrevivendo a reinício de processo (1 `claims` + 1 `eventos_claim` + 1 `comandos_idempotentes`).

**B3.4 (Testes finais e documentação de encerramento da Sprint B3): CONCLUÍDA.** `tests/integration/test_migration_0002_upgrade_downgrade.py` atualizado para o ciclo destrutivo compatível com o head atual (`0003 → 0001 → 0003`), exclusivamente contra `nsi_test`, preservando integralmente o piso `0001`, o gate obrigatório de identidade e as verificações de segurança já aprovados na B3.2 — nenhuma regra reaberta; teste de ciclo renomeado para `test_ciclo_downgrade_0001_upgrade_0003`. Execução real: suíte específica do ciclo — **3 passed em 3.82s**; suíte completa do projeto, sem exclusões ou filtros — **491 passed em 35.22s**, zero falhas. `nsi_test` terminou em `0003 (head)`; `nsi_dev` confirmado por leitura, também em `0003 (head)` — nenhum `downgrade` executado em `nsi_dev` em nenhum momento da Sprint B3. **Sprint B3 (B3.1–B3.4) integralmente CONCLUÍDA — nenhum item pendente.**

**B4.1 (Decisão arquitetural do catálogo de eventos operacionais): CONCLUÍDA.** ADR-009 aprovada e congelada em 2026-09-16 (commit `bd2ab47`): modelo híbrido, catálogo fechado de cinco eventos, privacidade, identidade técnica, papéis (incluindo a nova role `nsi_congelamento`) e idempotência determinística do congelamento. Exclusivamente documental — satisfaz a condição da Seção 9.

**B4.2 (Migration `0004` — schema relacional de lotes, registros e eventos operacionais): CONCLUÍDA.** Criadas `lotes`, `registros_coleta`, `eventos_lote` e `eventos_registro_coleta`, com suas `CHECK`s, índices, triggers defensivas de imutabilidade e `REVOKE`s; ampliado o `CHECK` de `comando` em `comandos_idempotentes` com os cinco comandos da B4 (commit `41e49f9`). Nenhuma função `SECURITY DEFINER` e nenhuma referência a `nsi_congelamento` — ambos pertencem à B4.3. As contagens de execução real e a revisão corrente dos bancos não foram consolidadas neste documento no encerramento da subetapa; sua confirmação por leitura é pré-requisito da B4.3 (Seção 18).

**B4.3 (Role `nsi_congelamento` e Migration `0005` — cinco funções `SECURITY DEFINER`): CONCLUÍDA.**

- A role `nsi_congelamento` foi provisionada pelo script administrativo de três fases, executado duas vezes, ambas aprovadas na pós-validação completa; a segunda comprovou a convergência idempotente, sem nenhuma alteração real.
- A `0005` foi aplicada primeiro em `nsi_test`, onde o ciclo `0005 → 0004 → 0005` passou com gate de identidade, e depois em `nsi_dev`, somente por `upgrade`. Ambos terminam em `0005 (head)`, com definições idênticas.
- Foram criadas exatamente as cinco funções `SECURITY DEFINER` da ADR-009, com owner `nsi_eventos_owner`, `search_path` fixo, `PUBLIC` sem `EXECUTE` e matriz de `EXECUTE` comprovada por leitura nos dois bancos.
- `core/payload_hash.py` é o único arquivo novo de produção fora de `migrations/` e `scripts/`. Nenhum arquivo existente de produção nem as migrations `0001`–`0004` foram alterados.
- A suíte completa aprovou **1013 de 1013**, sem falhas e sem pulados. Desses, 355 testes são da B4.3.
- O script de desprovisionamento foi implementado e não foi executado. Os cenários destrutivos da role seguem exclusivamente manuais, em `PROCEDIMENTO-MANUAL-B4-ROLE-CONGELAMENTO-DESTRUTIVO.md`.
- A Seção 22, itens 10 e 11, está resolvida.
- **Os onze critérios de aceite estão satisfeitos. B4.3 integralmente CONCLUÍDA — nenhum item pendente.**

Próxima revisão: ao início da B5.
