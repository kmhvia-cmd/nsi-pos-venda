# Especificação Técnica — Sprint B: Persistência Imutável, Claims e Idempotência

**Natureza deste documento:** especificação técnica de implementação. **Não é uma ADR** — não fixa arquitetura nova, não redefine nem amplia nada já congelado na ADR-008. Traduz as decisões arquiteturais já aprovadas em desenho técnico concreto, mantendo explicitamente rastreadas as decisões que ainda dependem de aprovação humana ou de infraestrutura externa a este repositório.

**Subordinação:** integral à ADR-008 (APROVADA E CONGELADA) e ao `ROADMAP-SPRINTS-B-G.md`. Nenhuma frase deste documento pode contradizer a ADR-008; onde houver aparente tensão, a ADR-008 prevalece e este documento deve ser corrigido.

**Status:** DOCUMENTO VIVO — **B1 (esta especificação) CONCLUÍDA**; **B2 (Infraestrutura, Conexão e Migrations) CONCLUÍDA** (Seção 18). B3–B7 pendentes, cada uma com autorização própria e separada.

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
| **B3** | Log imutável de claims + projeção + funções + testes | pendente — **não iniciada**; detalhada abaixo |
| **B4** | Catálogo de eventos operacionais e projeções de negócio | **condicionada** à decisão arquitetural formal (Seção 9) |
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

### Detalhamento de B3 — NÃO INICIADA
- Criação de `nsi_operacional.claims`, `nsi_operacional.eventos_claim`, `nsi_operacional.comandos_idempotentes` via migration Alembic.
- Implementação das seis funções (Seção 15), com todas as regras de identidade (Seção 4.3), token (Seção 4.1), versão (Seção 6/15), idempotência (Seção 16) e fronteira temporal (Seção 7).
- Aplicação integral do modelo de permissão (Seção 8): `REVOKE`/`GRANT` mínimos, `search_path` fixo, qualificação por schema, trigger defensiva `BEFORE UPDATE OR DELETE` em `eventos_claim`.
- Não toca `lote.json` — mecanismo isolado, testável por si.
- Critério de aceite: todos os testes da Seção 20 passando; suíte completa (213 + novos) sem regressão.

### B4, B5, B6, B7 — resumo
- **B4:** aguarda decisão da Seção 9.
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

**Não são mais pendências:** algoritmo de hash do token (decidido: SHA-256 simples, Seção 4.1); comportamento em caso de resposta perdida na criação/reatribuição (decidido: fail-safe, Seção 4.2); identidade do executor (decidido: `session_user` + rótulo informativo, Seção 4.3); nomes de schema/tabelas/funções/roles conceituais (decididos, Seção 5).

## 23. Status e Histórico de Revisão

**B1: CONCLUÍDA.** Consolida o texto integral de todas as rodadas de correção desta sessão de planejamento. Subordinada à ADR-008 (APROVADA E CONGELADA) e ao `ROADMAP-SPRINTS-B-G.md`. Nenhuma implementação de código, schema, migration ou dependência foi realizada por este documento.

**B2 (Infraestrutura, Conexão e Migrations): CONCLUÍDA.** Subetapas B2.1, B2.2 e B2.3 executadas e validadas integralmente (Seção 18) — dependências instaladas, esteira Alembic criada, PostgreSQL 17 local provisionado (`nsi_dev`, `nsi_test`, roles de migração, schema `nsi_operacional`), revisão `0001` aplicada em ambos os bancos (somente `alembic_version`, nenhuma tabela de negócio), suíte completa em 246/246, três testes de integração PostgreSQL real passando com zero pulados. Dois problemas reais de mecânica de conexão (dialeto SQLAlchemy; transação "autobegin") foram encontrados e corrigidos em `migrations/env.py` durante a validação — nenhuma decisão da ADR-008 foi alterada por isso. **Nenhuma implementação de tabela de negócio, evento, claim ou função `SECURITY DEFINER` foi realizada nesta subetapa — isso pertence integralmente à Sprint B3, ainda não iniciada.**

Próxima revisão: ao final da subetapa B3, ou mediante nova decisão arquitetural (Seção 9).
