# Especificação Técnica — Sprint C: Envio, `wamid` e Webhook

**Natureza deste documento:** especificação técnica. **Não é uma ADR** — não fixa arquitetura nova. Traduz a ADR-011 em schema, funções, papéis, serviços e testes.

**Subordinação:** integral à ADR-011, à ADR-007 (§10, §16 a §22), à ADR-008, à ADR-009 e ao `ROADMAP-SPRINTS-B-G.md` (Sprint C), nessa ordem de precedência. Onde houver tensão, o documento superior prevalece e este é corrigido.

**Status:** DOCUMENTO VIVO — **C1 (ADR-011) CONCLUÍDA**; **C2 (esta especificação) CONGELADA** para os itens 1 a 12; C3 a C7 registradas na Seção 13 à medida que forem concluídas.

**Alcance:** esta especificação **não cobre a B7** (corte real), primeiro item da Sprint C, que permanece bloqueada e regida por `SPRINT-B-ESPECIFICACAO-TECNICA.md` (Seções 12, 14 e 18) e por `SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md` (Seção 50).

---

## 1. Regras invariáveis da sprint

1. **Nenhum envio real.** Nenhum teste, script ou rota envia mensagem à plataforma.
2. **Nenhum dado real e nenhuma credencial real** em teste, fixture ou arquivo versionado.
3. **Todo transporte HTTP é injetável.** Nenhum teste abre conexão de rede com a plataforma.
4. **Somente `nsi_dev` e `nsi_test`.** `downgrade` somente em `nsi_test`. Nenhuma migration anterior é alterada.
5. **Compatibilidade:** os 1993 testes existentes continuam passando sem alteração de comportamento. Um teste existente só é editado quando verifica literalmente um fato que a sprint muda por desenho (a revisão *head* e o inventário de objetos do schema).
6. **O caminho legado em `lote.json` não é substituído** (ADR-011, Seção 13): coexiste até o corte real.

## 2. Subetapas

| Subetapa | Conteúdo |
|---|---|
| **C1** | ADR-011 — concluída |
| **C2** | Esta especificação |
| **C3** | Roles `nsi_envio` e `nsi_webhook`: scripts administrativos e procedimento |
| **C4** | Migration `0007`: tabelas, triggers e funções |
| **C5** | Serviço de envio (`services/whatsapp.py`), configuração e bloqueio do caminho legado |
| **C6** | Webhook (`services/webhook_handler.py`, `app.py`) |
| **C7** | Auditoria final, documentação e encerramento |

## 3. Papéis (C3)

| Role | Atributos | Bancos | Privilégios |
|---|---|---|---|
| `nsi_envio` | `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`, sem senha no script | `CONNECT` em `nsi_dev` e `nsi_test` | `USAGE` em `nsi_operacional`; `EXECUTE` concedido somente pela `0007` |
| `nsi_webhook` | idem | idem | idem |

- Nenhuma das duas pertence a outra role nem tem membros.
- `provisionar_c3_roles_envio.sql` e `desprovisionar_c3_roles_envio.sql`, em `scripts/postgres_local/`, no padrão de três fases (preflight somente leitura → convergência → pós-validação), executados pelo operador com o superusuário. O provisionamento aceita `nsi_dev` e `nsi_test` em `0006` ou `0007`, na mesma revisão. O desprovisionamento exige confirmação textual exata (`CONFIRMO-DESPROVISIONAR-NSI-C3-ROLES-ENVIO`) e aborta se a `0007` estiver aplicada em qualquer dos bancos.
- Variáveis de conexão, no `.env` local, no formato `postgresql://`: `DATABASE_URL_NSI_ENVIO`, `TEST_DATABASE_URL_NSI_ENVIO`, `DATABASE_URL_NSI_WEBHOOK`, `TEST_DATABASE_URL_NSI_WEBHOOK`. `config.resolver_url_banco_papel` passa a aceitar os dois papéis em `development` e `test`; em `ensaio` continuam inválidos.
- Os testes somente leitura de provisionamento que consultam catálogos do cluster passam a reconhecer as duas roles.

## 4. Modelo de dados (C4 — migration `0007`)

Quatro tabelas em `nsi_operacional`, dono `nsi_eventos_owner`. `REVOKE ALL` de `PUBLIC` e de todas as roles funcionais em cada uma: nenhuma role tem DML direto.

### 4.1 `envios` — projeção corrente da tentativa de envio

| Coluna | Tipo | Regra |
|---|---|---|
| `tentativa_envio_id` | `UUID` | PK, gerado pelo servidor |
| `registro_coleta_id` | `UUID` | FK `registros_coleta` |
| `lote_id` | `UUID` | FK `lotes` |
| `numero_tentativa` | `INTEGER` | `CHECK (numero_tentativa = 1)` (ADR-011, Seção 8) |
| `estado` | `TEXT` | `solicitado` \| `aceito_api` \| `falha_api` \| `resultado_desconhecido` |
| `template_nome`, `template_idioma` | `TEXT` | identificação do template; formato restrito |
| `solicitado_em` | `TIMESTAMPTZ` | produzido pelo servidor |
| `desfecho_em` | `TIMESTAMPTZ` | nulo somente em `solicitado` |
| `wamid` | `TEXT` | `UNIQUE`; presente **se e somente se** `estado = 'aceito_api'` |
| `codigo_http` | `INTEGER` | presente em `aceito_api` e `falha_api` |
| `codigo_erro_plataforma` | `INTEGER` | opcional, somente em `falha_api` |
| `classificacao` | `TEXT` | `nao_classificada`, se e somente se `falha_api` |
| `motivo_desconhecido` | `TEXT` | enum da ADR-011 (§6.4), se e somente se `resultado_desconhecido` |
| `status_enviado_em`, `status_entregue_em`, `status_lido_em`, `status_falhou_em` | `TIMESTAMPTZ` | horário informado pela plataforma; nulos até observados |
| `status_falhou_codigo` | `INTEGER` | opcional, somente com `status_falhou_em` |
| `versao_eventos_atual` | `BIGINT` | versão do agregado |

`UNIQUE (registro_coleta_id, numero_tentativa)`. Um `CHECK` de coerência amarra as colunas a cada estado. Não existe coluna de "status atual".

### 4.2 `eventos_envio` — eventos imutáveis da tentativa

Colunas tipadas (nunca `JSONB` livre): `evento_id`, `aggregate_type` (`tentativa_envio`), `aggregate_id` (FK `envios`), `aggregate_version`, `tipo`, `occurred_at`, `executado_por_login`, `registro_coleta_id`, `lote_id`, `numero_tentativa`, `template_nome`, `template_idioma`, `codigo_http`, `codigo_erro_plataforma`, `classificacao`, `motivo`, `status`, `horario_informado_pela_plataforma`.

- `tipo` ∈ {`envio_solicitado`, `envio_aceito_api`, `envio_falha_api_observada`, `envio_resultado_desconhecido`, `status_whatsapp_observado`}.
- `UNIQUE (aggregate_id, aggregate_version)`; índice único parcial em `(aggregate_id, status)` para `status_whatsapp_observado`; índice único parcial em `(aggregate_id)` para os três eventos de desfecho — no máximo um desfecho por tentativa.
- Um `CHECK` por tipo define quais colunas são preenchidas. **Não existe coluna para `wamid`, telefone ou texto.**
- Trigger `BEFORE UPDATE OR DELETE` que bloqueia inclusive o dono.

### 4.3 `mensagens_recebidas` — registro técnico da mensagem recebida

`mensagem_recebida_id` (PK), `identificador_plataforma` (`TEXT`, `UNIQUE`), `tipo_mensagem`, `horario_informado_pela_plataforma`, `referencia` (enum da ADR-011, §6.6), `tentativa_envio_id` (FK `envios`, presente se e somente se `referencia = 'contexto_de_envio_conhecido'`), `registrada_em`. **Não existe coluna para texto nem para telefone.**

### 4.4 `eventos_mensagem_recebida` — evento imutável

`evento_id`, `aggregate_type` (`mensagem_recebida`), `aggregate_id` (FK, `UNIQUE`), `aggregate_version` (`= 1`), `tipo` (`mensagem_recebida_observada`), `occurred_at`, `executado_por_login`, `tipo_mensagem`, `horario_informado_pela_plataforma`, `referencia`, `tentativa_envio_id`. Sem o identificador da plataforma. Mesma trigger de imutabilidade.

### 4.5 Formatos

- `wamid` e `identificador_plataforma`: 1 a 512 caracteres ASCII imprimíveis, sem espaço.
- `template_nome`: `^[a-z0-9_]{1,64}$`; `template_idioma`: `^[a-z]{2}(_[A-Z]{2})?$`.
- `tipo_mensagem`: `^[a-z_]{1,40}$`.
- Códigos numéricos: inteiros não negativos; `codigo_http` entre 100 e 599.

### 4.6 Downgrade

Remove, na ordem inversa, concessões, funções, triggers e tabelas, e nada além. Não toca nenhum objeto das revisões `0001` a `0006`.

## 5. Funções (C4)

Todas `SECURITY DEFINER`, dono `nsi_eventos_owner`, `search_path = pg_catalog, nsi_operacional, pg_temp`, retorno `JSONB`, `REVOKE ALL ... FROM PUBLIC`. Identidade registrada: `session_user`.

**Contrato de erros** (o mesmo da `0006`): `22000 entrada_estrutural_invalida` para entrada malformada; `22023 conflito_de_idempotencia` para repetição com entrada divergente; `NS001 invariante_violada` para estado impossível. Mensagens fixas, sem interpolar entrada. Recusas de negócio **não** são exceção: retornam `{"sucesso": false, "motivo": "<enum>"}`.

**Idempotência:** todas as chaves da ADR-011 são determinísticas e derivadas do agregado; a repetição é resolvida pelas constraints de unicidade das próprias tabelas, comparando a entrada com o que está gravado. **Nenhum recibo é gravado em `comandos_idempotentes`** — não há chave fornecida pelo chamador, e evita-se criar mais um artefato correlacionável (ADR-009, §9).

### 5.1 `fn_solicitar_envio(p_registro_coleta_id UUID, p_claim_id UUID, p_token_hash TEXT, p_numero_tentativa INTEGER, p_template_nome TEXT, p_template_idioma TEXT)`

1. Valida a forma da entrada (`22000`).
2. **Repetição primeiro:** se já existe tentativa para `(registro, numero_tentativa)`: template divergente → `22023`; idêntico → `{"sucesso": true, "repeticao": true, "tentativa_envio_id", "estado"}`, **sem os dados do destinatário**.
3. Recusas, nesta ordem: `numero_tentativa_nao_autorizado` (≠ 1); `registro_inexistente`; `registro_invalido`; `lote_sem_disparo_confirmado`; `janela_encerrada` (`now() >= disparo_confirmado_em + 336 horas`); `claim_invalido` (não existe claim `ativo`, não expirado, com aquele `claim_id` e `token_hash`).
4. Cria a tentativa em `solicitado`, grava `envio_solicitado` e retorna `{"sucesso": true, "repeticao": false, "tentativa_envio_id", "estado": "solicitado", "destinatario": {"whatsapp", "nome", "produto"}}`.

Os dados do destinatário saem **somente** na criação. Uma repetição nunca os devolve: um processo que perdeu o resultado da própria solicitação **não tem como reenviar** (ADR-011, Seção 7, item 4). A corrida entre dois chamadores é resolvida pela unicidade: um cria, o outro recebe a repetição.

### 5.2 `fn_registrar_envio_aceito(p_tentativa_envio_id UUID, p_wamid TEXT, p_codigo_http INTEGER)`

A partir de `solicitado`: estado `aceito_api`, grava `wamid` e o evento. Repetição com o mesmo `wamid` → repetição; com outro → `22023`. Recusas: `tentativa_inexistente`; `desfecho_ja_registrado` (outro desfecho); `wamid_em_uso` (já vinculado a outra tentativa). `codigo_http` precisa estar entre 200 e 299.

### 5.3 `fn_registrar_envio_falha(p_tentativa_envio_id UUID, p_codigo_http INTEGER, p_codigo_erro_plataforma INTEGER)`

A partir de `solicitado`: estado `falha_api`, `classificacao = 'nao_classificada'`. `codigo_http` fora de 200–299. Repetição idêntica → repetição; divergente → `22023`.

### 5.4 `fn_registrar_envio_desconhecido(p_tentativa_envio_id UUID, p_motivo TEXT)`

A partir de `solicitado`: estado `resultado_desconhecido`. `p_motivo` ∈ {`tempo_esgotado`, `falha_de_conexao`, `resposta_ininteligivel`}; `processamento_interrompido` **não** é aceito aqui (`22000`).

### 5.5 `fn_materializar_envios_interrompidos()`

Marca como `resultado_desconhecido`, motivo `processamento_interrompido`, **toda** tentativa em `solicitado` há pelo menos **10 minutos** — o dobro da validade de um claim (ADR-008, §9), de modo que nenhum worker ainda a detenha. Retorna `{"materializados": n}`. Idempotente e segura sob concorrência (`FOR UPDATE SKIP LOCKED`). É o único caminho para `processamento_interrompido`.

### 5.6 `fn_registrar_status_whatsapp(p_wamid TEXT, p_status TEXT, p_horario TIMESTAMPTZ, p_codigo_erro INTEGER)`

`p_status` ∈ {`enviado`, `entregue`, `lido`, `falhou`}; `p_codigo_erro` só é admitido com `falhou`. `wamid` sem tentativa → `{"registrado": false, "motivo": "wamid_desconhecido"}`, sem gravar nada. Primeiro registro daquele status → grava o instante e o evento. Repetição do mesmo status → `{"registrado": false, "motivo": "repeticao"}`, **mantendo o primeiro horário**: a plataforma reenvia notificações, e a repetição nunca é conflito. O estado da tentativa nunca é alterado por status.

### 5.7 `fn_registrar_mensagem_recebida(p_identificador_plataforma TEXT, p_tipo_mensagem TEXT, p_horario TIMESTAMPTZ, p_wamid_contexto TEXT)`

Calcula `referencia`: `sem_contexto` (contexto nulo); `contexto_de_envio_conhecido` (o contexto é o `wamid` de uma tentativa); `contexto_desconhecido`. Grava o registro e o evento. Repetição do mesmo identificador → `{"registrado": false, "motivo": "repeticao"}`.

### 5.8 Concessões

| Role | `EXECUTE` |
|---|---|
| `nsi_envio` | 5.1 a 5.5; e `fn_criar_claim`, `fn_registrar_heartbeat`, `fn_liberar_claim` (deter o claim é pré-condição do envio) |
| `nsi_webhook` | 5.6 e 5.7 |

Nenhuma outra role recebe `EXECUTE` em função desta migration. `nsi_webhook` não recebe nenhuma função de envio nem de claim.

## 6. Serviço de envio (C5)

`services/whatsapp.py`:

- **Transporte injetável.** `enviar_convite(conexao, ..., transporte)` recebe o transporte como argumento; ele devolve código HTTP e corpo, ou levanta `TempoEsgotado` / `FalhaDeConexao`. O transporte real usa `requests` com tempo limite explícito.
- **Habilitação que falha fechada.** `envio_real_habilitado()` é verdadeira somente quando `NSI_ENVIO_REAL` vale exatamente `habilitado`. Ausente, vazia ou qualquer outro valor: desabilitado. O transporte real **recusa** qualquer chamada enquanto desabilitado (`EnvioDesabilitado`), antes de montar a requisição. Transportes simulados não dependem da habilitação.
- **Ordem da ADR-011 (Seção 7):** `fn_solicitar_envio` e `COMMIT`; chamada ao transporte fora de transação; desfecho e `COMMIT`.
- **Interpretação da resposta:** 2xx com exatamente um identificador de mensagem válido → aceito; 2xx sem identificador utilizável, ou corpo que não é JSON → `resposta_ininteligivel`; não 2xx com corpo inteligível → falha, com o código numérico da plataforma quando houver; tempo esgotado e falha de conexão → resultado desconhecido.
- **Repetição não envia.** Se `fn_solicitar_envio` devolver repetição, o serviço não chama o transporte.
- **Destino:** o `whatsapp` devolvido pela função já está normalizado pela regra da Sprint A2; o serviço só confere que são dígitos e não reaplica heurística de prefixo.
- **`empresa`:** parâmetro do template que não existe na projeção em PostgreSQL. É informado pelo chamador e não é persistido por este domínio (pendência registrada para a B7 e a Sprint D).
- **Sem vazamento:** nenhuma exceção, retorno ou log contém token, telefone, nome, produto, `wamid` ou corpo da resposta.
- **Caminho legado (ADR-011, `P7`):** `enviar_template_d8` passa a exigir a habilitação e levanta `EnvioDesabilitado` antes de qualquer chamada de rede; a rota `POST /api/lote/<lote_id>/disparar` responde `403` enquanto o envio estiver desabilitado, sem chamar `disparar_lote`. Nenhuma rota nova é criada.

## 7. Webhook (C6)

`services/webhook_handler.py`:

- **`extrair_fatos(payload)`** — função pura. Percorre todos os `entry`, `changes`, `statuses` e `messages`, e devolve os status e as mensagens em forma técnica: identificadores, tipos, horários, códigos e o identificador de contexto. **Nunca devolve telefone nem texto.** Estrutura inesperada é ignorada elemento a elemento, com contagem; nunca derruba o processamento.
- **Mapa de status:** `sent` → `enviado`; `delivered` → `entregue`; `read` → `lido`; `failed` → `falhou`. Qualquer outro valor é contado como ignorado.
- **`registrar_fatos_tecnicos(conexao, fatos)`** — chama as funções 5.6 e 5.7 como `nsi_webhook`, uma transação por fato, e devolve somente contagens: registrados, repetições, `wamid` desconhecido, ignorados.
- **`processar_webhook(payload)`** — a gravação de resposta em `lote.json` permanece **inalterada** (ADR-011, `P8`).
- **`app.py`:** depois da assinatura válida, o registro técnico é executado **em paralelo e sem poder afetar** a resposta legada: qualquer falha dele é contida e registrada com mensagem fixa. Ele só é tentado quando a variável de conexão de `nsi_webhook` do ambiente ativo está configurada.
- **Token de verificação:** sai do código versionado e passa a `WEBHOOK_VERIFY_TOKEN`, lido do ambiente, sem valor padrão. Ausente, a verificação `GET /webhook` responde sempre `403`. A comparação é em tempo constante.

**Ação exigida do operador ao implantar:** definir `WEBHOOK_VERIFY_TOKEN` no ambiente e **trocar o valor na plataforma**, porque o valor antigo permanece no histórico do repositório.

## 8. Privacidade

Valem integralmente as regras da ADR-011 (Seção 10). Verificação obrigatória por teste: nenhuma coluna das quatro tabelas admite telefone ou texto; nenhum evento contém `wamid`; nenhum retorno, exceção ou log dos dois serviços contém valor pessoal ou credencial.

## 9. Plano de testes

Separação obrigatória, como na Sprint B: unitários em Python puro; integração contra PostgreSQL real, sem SQLite e sem mock de banco.

- **Estáticos:** scripts da C3 (fases, somente leitura, escritas exatas, ausência de senha, frase de confirmação); migration `0007` (encadeamento, objetos, `REVOKE`/`GRANT`, ausência de colunas pessoais).
- **Migration:** inventário de objetos; ciclo `upgrade`/`downgrade` somente em `nsi_test`; catálogos de `nsi_dev` e `nsi_test` idênticos.
- **Funções:** cada transição, cada recusa, cada erro estrutural; repetição e conflito; fronteira exata da janela e dos 10 minutos; imutabilidade dos eventos inclusive para o dono; coerência de estado imposta por constraint.
- **Concorrência real:** dois chamadores solicitando o mesmo envio (um cria, um recebe repetição); desfechos concorrentes (um vence); status repetidos em paralelo.
- **Permissões:** DML direto negado a todas as roles; `nsi_webhook` sem nenhuma função de envio ou de claim; `nsi_aplicacao` sem nenhuma função deste domínio; `PUBLIC` sem `EXECUTE`.
- **Serviço de envio:** transporte simulado para aceito, falha, tempo esgotado, falha de conexão e resposta ininteligível; repetição nunca chama o transporte; transporte real recusa sem habilitação, sem tocar a rede; ausência de vazamento.
- **Webhook:** notificações com vários `entry`, `changes`, `statuses` e mensagens; ordem trocada; repetição; `context` conhecido e desconhecido; estrutura malformada; assinatura; token de verificação.
- **Legado:** rota de disparo recusada sem habilitação; gravação de resposta em `lote.json` inalterada.
- **Regressão:** suíte completa no modo de aceite, sem falha e sem pulado.

Testes de integração terminam em `ROLLBACK` sempre que possível; os que exigem `COMMIT` (concorrência, e o serviço de envio, que confirma por desenho) usam somente lotes sintéticos criados pelo próprio teste.

## 10. Critérios de aceite

1. ADR-011 aprovada antes de qualquer implementação.
2. Roles provisionadas pelo operador, com a pós-validação aprovada.
3. `0007` aplicada em `nsi_test` e em `nsi_dev` (esta, somente por `upgrade`), catálogos idênticos.
4. Suíte cobrindo `wamid`, `statuses` e `context`, usando somente transporte simulado e fixtures.
5. Nenhum envio real em nenhum teste; transporte real comprovadamente bloqueado sem habilitação.
6. Nenhuma inferência de leitura ou atenção humana em código, retorno ou nome de campo.
7. Nenhum valor pessoal em evento; nenhum telefone ou texto nas tabelas do domínio.
8. Caminho legado de disparo bloqueado; gravação de resposta em `lote.json` inalterada.
9. Suíte completa aprovada, sem pulados; os 1993 testes anteriores preservados.
10. Nenhuma ADR e nenhuma migration anterior alteradas.

## 11. Riscos

| Risco | Mitigação |
|---|---|
| Envio real acidental | transporte real bloqueado por padrão; testes só com transporte simulado |
| Duplicidade de mensagem | solicitação confirmada antes da chamada; repetição sem dados do destinatário; desconhecido bloqueia |
| Notificação repetida ou fora de ordem | unicidade por `(tentativa, status)`; sem "status atual" |
| Falha do registro técnico derrubar o webhook em operação | execução contida, opcional por configuração |
| `0007` exigir roles inexistentes | preflight da migration aborta com mensagem clara; C3 antes de C4 |
| Troca do token de verificação interromper a verificação da plataforma | ação do operador documentada na Seção 7 |

## 12. Pendências que esta sprint não resolve

- B7 (corte real) e seus pré-requisitos.
- Confirmação de nova tentativa e desbloqueio de `resultado_desconhecido` (Sprints D e G).
- Origem persistida do nome da empresa para o template (B7 e Sprint D).
- Correlação de respostas, quarentena e Motor NSI (Sprint E).
- Payload íntegro e retenção (Sprint F); classificação de falhas (Sprint G).
- Confirmação, na documentação oficial da plataforma, da inexistência de chave de idempotência na chamada de envio (ADR-011, Seção 7) — não altera nenhuma regra desta especificação.

## 13. Registro de implementação

**C1 (ADR-011): CONCLUÍDA** — commit `521cad9`.

**C2 (especificação técnica): CONCLUÍDA** — este documento.
