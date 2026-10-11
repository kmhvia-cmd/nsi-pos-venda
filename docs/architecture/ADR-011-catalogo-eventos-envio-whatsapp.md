# ADR-011 — Catálogo de Eventos do Domínio de Envio e de Eventos Técnicos do WhatsApp

## Metadados

| Campo | Valor |
|---|---|
| Status | APROVADA E CONGELADA |
| Data | 2026-10-11 |
| Versão de referência do sistema | `v1.1.0-fonte-unica-webhook-motor` |
| Commit de referência | `b3821ba` |
| Branch | `master` |
| Escopo desta ADR | Arquitetura — nenhuma implementação de código, schema de banco de dados, migration, role ou configuração |

> **Nota de processo:** ADR aberta como Subetapa C1 da Sprint C, para cumprir a dependência registrada no `ROADMAP-SPRINTS-B-G.md` (Sprint C, "Dependências"): *"aprovação arquitetural formal, própria e anterior à implementação, do catálogo de eventos do domínio de envio (`solicitado`, `aceito_api`, `falha_api_observada`, `resultado_desconhecido`, e qualquer outro evento deste domínio). Este roadmap não aprova esse catálogo sozinho."* Esta ADR é essa decisão. Ela não reabre, não redefine e não contradiz nenhuma decisão congelada nas ADR-005, ADR-007, ADR-008, ADR-009 e ADR-010 — estende o modelo geral de evento imutável e projeção corrente da ADR-008 (§6) a um novo domínio, exatamente como a ADR-008 (§11, §18) previu.

> **Escolhas entre alternativas:** os pontos em que esta ADR escolheu entre alternativas legítimas estão reunidos na Seção 16 (`P1` a `P8`), cada um com a alternativa descartada e a decisão tomada. Tudo o mais decorre de regra já congelada.

---

## 1. Objetivo

Registrar, antes de qualquer código: quais eventos imutáveis existem para o **envio de um convite de coleta pelo WhatsApp** e para os **fatos técnicos que a plataforma informa por webhook**; o que cada evento pode e não pode carregar; em que ordem um envio é registrado em relação à chamada à API; o que nunca pode ser repetido automaticamente; qual identidade técnica gera cada evento; e o que mantém o envio **desabilitado para clientes reais** durante toda a Sprint C.

Esta ADR não implementa nada.

---

## 2. Escopo

### 2.1 Escopo desta decisão

- Agregado e identidade técnica de uma tentativa de envio (Seção 5).
- Catálogo fechado de seis eventos (Seção 6).
- Ordem obrigatória entre registro e chamada à API, e a regra de não repetição (Seção 7).
- Relação com `numero_tentativa`, com o claim e com o T0 da Coleta (Seção 8).
- Fatos técnicos do webhook: `statuses`, `context` e mensagens recebidas (Seção 9).
- Privacidade: o que nunca entra em evento e o que não é persistido por este domínio (Seção 10).
- Papéis (roles) autorizados (Seção 11).
- Desabilitação do envio real (Seção 12).

### 2.2 Fora do escopo desta decisão

- Corte real e mudança da fonte de verdade — B7, primeiro item da Sprint C, com especificação própria e inalterada.
- Rotas HTTP, autenticação, MFA e a confirmação humana em dois atos na interface — Sprint D.
- Autorização humana de **nova tentativa** e o evento que a registra — Sprints D e G (Seção 8).
- Correlação determinística `registro de coleta → envio → resposta → produto`, quarentena de resposta sem vínculo e entrada no Motor NSI — Sprint E.
- Payload íntegro do webhook, criptografia temporária, retenção curta e eliminação auditada — Sprint F.
- Mapeamento dos códigos de erro da Meta para falha temporária, definitiva ou não classificada — Sprint G.
- Eventos de claim (ADR-008, §11) e de lote, registro de coleta e correção (ADR-009, §6) — catálogos fechados, não reabertos.
- Schema relacional, nomes de tabelas, colunas e funções, migration, contrato de erros, formato exato de chaves e de `payload_hash` — especificação técnica (Seção 14).
- Política jurídica de retenção, anonimização ou expurgo.

---

## 3. Contexto

A ADR-007 fixou o resultado obrigatório: um convite por registro de coleta; idempotência persistente entre processos (§17); até três tentativas, com confirmação humana a cada nova tentativa (§19); falhas classificadas (§20); e a regra de verdade observável — a aceitação pela API nunca significa recebimento, e eventos da plataforma são registrados como fatos técnicos, sem inferência de leitura ou atenção humana (§22). A ADR-008 (§18) deixou explicitamente para a Sprint C o envio efetivo, a captura de `wamid` e o processamento de status de webhook, e declarou o claim *"inteiramente agnóstico de Meta, WhatsApp, `wamid` ou webhook"*. A ADR-009 (§6.3) registra `disparo_confirmado` como a única decisão que autoriza o disparo, e seu timestamp como o T0 da Coleta.

O código atual não atende a nenhuma dessas regras:

- `services/whatsapp.py` envia sem timeout, sem registrar intenção antes da chamada, sem capturar o `wamid` da resposta e com normalização de telefone por `startswith("55")` — proibida desde a Sprint A2;
- `core/scheduler.py::disparar_lote` percorre o lote e marca envio em `lote.json`; uma interrupção no meio não deixa registro do que já foi aceito pela API;
- `services/webhook_handler.py` lê somente a primeira mensagem do primeiro `entry`, ignora `statuses` e `context`, e associa a resposta ao lote somente pelo telefone (não conformidade já declarada pela ADR-007, §10.3);
- `app.py` expõe `POST /api/lote/<lote_id>/disparar` sem autenticação e sem confirmação em dois atos, e contém um token de verificação de webhook fixo no código versionado.

A Sprint B entregou a fundação em PostgreSQL (claims, eventos operacionais, idempotência), mas **o backend da aplicação continua em `lote.json`** até o corte real (B7). O mecanismo desta ADR nasce, portanto, sem uso operacional.

---

## 4. Princípios Arquiteturais

### Princípio 1 — Registrar Antes de Agir

A intenção de enviar é gravada e confirmada no banco **antes** da chamada à API. Nenhuma chamada à API do WhatsApp ocorre sem um evento de solicitação já persistido.

### Princípio 2 — Na Dúvida, Não Reenviar

Quando o sistema não sabe se a plataforma aceitou um envio, ele registra que não sabe e **para**. Nenhum mecanismo automático repete um envio cujo resultado é desconhecido. Uma mensagem duplicada a um cliente é um dano que nenhum evento posterior desfaz.

### Princípio 3 — Fato Técnico, Nunca Interpretação

Um evento deste catálogo registra o que a API respondeu ou o que a plataforma informou — nunca o que isso significa para uma pessoa. "Lido" é um status informado pela plataforma; não é leitura humana, atenção nem intenção de resposta (ADR-007, §22).

### Princípio 4 — Eventos Nunca Carregam Valor Pessoal

Nenhum evento contém telefone, nome, produto, texto de mensagem ou texto livre devolvido pela plataforma. O payload limita-se a identificadores técnicos, enums fechados, códigos numéricos e timestamps (mesmo princípio da ADR-009, Princípio 2).

### Princípio 5 — Menor Privilégio por Papel Dedicado

Quem envia e quem recebe webhook são identidades técnicas distintas entre si e distintas das já existentes. O processo exposto à internet nunca possui privilégio de envio.

### Princípio 6 — Desabilitado por Padrão

O envio real a clientes é impossível por ausência de configuração, não por lembrança de desligar. Habilitá-lo é uma decisão humana explícita, posterior e cumulativa (Seção 12).

### Princípio 7 — Imutabilidade Operacional e Neutralidade Jurídica

Nenhum fluxo executa `UPDATE` ou `DELETE` sobre um evento gravado (ADR-008, §15; ADR-009, Princípio 6). A imutabilidade é regra operacional interna, não blindagem jurídica (ADR-009, Princípio 7).

---

## 5. Agregado e Identidade Técnica

- **Tentativa de envio:** uma única chamada pretendida à API do WhatsApp para entregar o convite de um registro de coleta. É o agregado dos eventos de envio.
- **`tentativa_envio_id`:** identificador técnico próprio (UUID), gerado pelo servidor. Cada tentativa pertence a exatamente um `registro_coleta_id` e carrega o `numero_tentativa` a que corresponde (Seção 8).
- **Uma tentativa por `(registro_coleta_id, numero_tentativa)`:** não existem duas tentativas de envio para o mesmo registro e o mesmo número de tentativa. Essa unicidade é a chave persistente de idempotência exigida pela ADR-007 (§17).
- **`wamid`:** identificador que a plataforma atribui a uma mensagem aceita. É a "identidade técnica do envio" da cadeia da ADR-007 (§10.1). Reside **somente na projeção corrente** da tentativa, com unicidade, e **nunca em evento imutável** — é um identificador vinculável a uma pessoa por meio da plataforma, e precisa permanecer alcançável por uma futura política jurídica sem edição de evento (mesmo raciocínio da ADR-009, §9, para o checksum do CSV).
- **Modelo híbrido:** como na ADR-009 (§5), os eventos provam as transições; a projeção corrente da tentativa guarda o estado atual, o `wamid` e os instantes observados. Não é event sourcing integral.

---

## 6. Catálogo Fechado de Eventos

**O catálogo abaixo é fechado exclusivamente para o domínio de envio e de eventos técnicos do WhatsApp.** A introdução de um sétimo evento, ou a alteração de qualquer um dos seis, exige evolução arquitetural formal desta ADR — a especificação técnica não amplia este catálogo sozinha. Vale a regra geral de idempotência da ADR-009 (§6): a chave identifica a operação, o `payload_hash` cobre somente a entrada fornecida pelo chamador, mesma chave com mesmo hash é replay, mesma chave com hash divergente é conflito explícito.

### 6.1 `envio_solicitado`

| | |
|---|---|
| **Agregado** | tentativa de envio |
| **Finalidade** | Registrar a intenção de enviar o convite de um registro de coleta, antes de qualquer chamada à API |
| **Transição permitida** | Somente quando, cumulativamente: o lote do registro está em `disparo_confirmado`; o registro é válido; a janela total da coleta (ADR-005) está aberta; o chamador detém o claim ativo do registro (Seção 8); não existe tentativa anterior do mesmo registro que tenha sido aceita pela API, que esteja com resultado desconhecido ou que esteja solicitada sem resultado; e o `numero_tentativa` é o autorizado (Seção 8) |
| **Payload** | `tentativa_envio_id`, `registro_coleta_id`, `lote_id`, `numero_tentativa`, identificação do template e do idioma, `executado_por_login` |
| **Idempotência** | determinística: `(envio_solicitado, registro_coleta_id, numero_tentativa)` |
| **Papel autorizado** | `nsi_envio` |
| **Efeito na projeção** | cria a tentativa em estado `solicitado` |

### 6.2 `envio_aceito_api`

| | |
|---|---|
| **Agregado** | tentativa de envio |
| **Finalidade** | Registrar que a API respondeu com sucesso e devolveu um identificador de mensagem. **Não significa recebimento** (ADR-007, §22) |
| **Transição permitida** | Somente a partir de `solicitado`, uma única vez |
| **Payload** | `tentativa_envio_id`, código HTTP, `horario_da_resposta` (produzido pelo servidor), `executado_por_login`. **Nunca o `wamid`** |
| **Idempotência** | determinística por tentativa |
| **Papel autorizado** | `nsi_envio` |
| **Efeito na projeção** | estado `aceito_api`; grava o `wamid`. A partir daqui o registro **nunca** recebe nova tentativa (ADR-007, §19) |

### 6.3 `envio_falha_api_observada`

| | |
|---|---|
| **Agregado** | tentativa de envio |
| **Finalidade** | Registrar que a API respondeu, de forma inteligível, recusando o envio |
| **Transição permitida** | Somente a partir de `solicitado`, uma única vez |
| **Payload** | `tentativa_envio_id`, código HTTP, código numérico de erro informado pela plataforma (quando houver), `classificacao`, `executado_por_login`. **Nunca o texto da mensagem de erro** |
| **Idempotência** | determinística por tentativa |
| **Papel autorizado** | `nsi_envio` |
| **Efeito na projeção** | estado `falha_api` |

`classificacao` é o enum da ADR-007 (§20). **Nesta ADR ele admite um único valor: `nao_classificada`.** O mapeamento que permitiria `temporaria` ou `definitiva` pertence à Sprint G; até lá, toda falha é não classificada e, pela ADR-007 (§20), **não permite nova tentativa**.

### 6.4 `envio_resultado_desconhecido`

| | |
|---|---|
| **Agregado** | tentativa de envio |
| **Finalidade** | Registrar que o sistema **não sabe** se a plataforma aceitou o envio |
| **Transição permitida** | Somente a partir de `solicitado`, uma única vez |
| **Payload** | `tentativa_envio_id`, `motivo`, `executado_por_login` |
| **Idempotência** | determinística por tentativa |
| **Papel autorizado** | `nsi_envio` |
| **Efeito na projeção** | estado `resultado_desconhecido`; bloqueia qualquer nova tentativa do registro (Seção 7) |

`motivo`, enum fechado: `tempo_esgotado` \| `falha_de_conexao` \| `resposta_ininteligivel` \| `processamento_interrompido`.

### 6.5 `status_whatsapp_observado`

| | |
|---|---|
| **Agregado** | tentativa de envio |
| **Finalidade** | Registrar um status que a plataforma informou, por webhook, sobre uma mensagem enviada |
| **Transição permitida** | Somente quando o `wamid` informado pertence a uma tentativa em `aceito_api` ou em `resultado_desconhecido` (Seção 9). No máximo um evento por `(tentativa, status)` |
| **Payload** | `tentativa_envio_id`, `status`, `horario_informado_pela_plataforma`, código numérico de erro (somente para `falhou`), `executado_por_login` |
| **Idempotência** | determinística: `(status_whatsapp_observado, tentativa_envio_id, status)` — a plataforma reenvia notificações, e a repetição é replay |
| **Papel autorizado** | `nsi_webhook` |
| **Efeito na projeção** | grava o instante observado daquele status. **Não existe "status atual"** (Seção 9) |

`status`, enum fechado: `enviado` \| `entregue` \| `lido` \| `falhou`. Qualquer outro valor informado pela plataforma não gera evento.

### 6.6 `mensagem_recebida_observada`

| | |
|---|---|
| **Agregado** | mensagem recebida |
| **Finalidade** | Registrar o fato técnico de que uma mensagem chegou pelo webhook, e se ela faz referência a um envio conhecido |
| **Transição permitida** | Uma única vez por mensagem recebida |
| **Payload** | identificador técnico próprio da mensagem recebida, `tipo` da mensagem, `horario_informado_pela_plataforma`, `referencia` (enum), `tentativa_envio_id` referida (somente quando a referência é a um envio conhecido), `executado_por_login` |
| **Idempotência** | determinística pelo identificador que a plataforma atribui à mensagem recebida — que reside somente na projeção |
| **Papel autorizado** | `nsi_webhook` |
| **Efeito na projeção** | cria o registro técnico da mensagem recebida |

`referencia`, enum fechado: `sem_contexto` \| `contexto_de_envio_conhecido` \| `contexto_desconhecido`.

**O que este evento não faz:** não associa a mensagem a um registro de coleta para fins de coleta; não decide em qual Leitura ela entra; não a entrega ao Motor NSI; não a coloca em quarentena. Tudo isso é da Sprint E. O evento registra apenas o que foi observado.

---

## 7. Ordem Obrigatória e Regra de Não Repetição

1. **`envio_solicitado` é gravado e confirmado (`COMMIT`) antes da chamada à API.**
2. **A chamada à API ocorre fora de qualquer transação de banco.** Nenhuma transação fica aberta enquanto se espera a plataforma.
3. **O desfecho é gravado depois**, por exatamente um dos três eventos: `envio_aceito_api`, `envio_falha_api_observada` ou `envio_resultado_desconhecido`.
4. **Uma tentativa em `solicitado` sem desfecho nunca é reenviada.** Se o processo foi interrompido entre o passo 1 e o passo 3, a chamada pode ou não ter sido feita. A tentativa só deixa esse estado por `envio_resultado_desconhecido`, com motivo `processamento_interrompido`. A especificação técnica define quem a materializa e quando; nunca o reenvio.
5. **`resultado_desconhecido` bloqueia o registro.** Nenhuma nova tentativa do mesmo registro de coleta é possível enquanto houver uma tentativa nesse estado. O desbloqueio é uma decisão humana, por evento que **não pertence a este catálogo** e exige evolução arquitetural própria (Sprints D e G).
6. **Um status de webhook pode esclarecer, nunca reenviar.** Se chegar um `status_whatsapp_observado` para uma tentativa em `resultado_desconhecido` — o que só é possível quando o `wamid` chegou a ser conhecido —, o status é registrado como fato; o estado da tentativa não é reescrito por ele.

Esta ADR não pressupõe que a plataforma ofereça, na chamada de envio, uma chave de idempotência que permita repetir com segurança — premissa a confirmar na documentação oficial da Meta durante a especificação técnica. A segurança contra duplicidade está inteiramente nesta ordem e nesta regra, e não depende do resultado dessa confirmação.

---

## 8. `numero_tentativa`, Claim e T0 da Coleta

- **`numero_tentativa` continua regido pela ADR-007 (§19) e pela ADR-008 (§14).** Esta ADR não cria nenhum evento que o avance.
- **A primeira tentativa (`numero_tentativa = 1`) é autorizada por `disparo_confirmado`** (ADR-009, §6.3), que já é a decisão humana do segundo ato.
- **As tentativas 2 e 3 não são alcançáveis por este catálogo.** Elas exigem, cumulativamente, uma falha classificada como temporária (Sprint G) e uma confirmação humana explícita por tentativa (Sprint D). O evento que registrará essa confirmação será definido por evolução formal desta ADR. Até lá, `envio_solicitado` só é aceito com `numero_tentativa = 1`.
- **O claim é pré-condição de `envio_solicitado`, e nada mais.** Deter o claim ativo de um registro (ADR-008, §7) garante que um único worker processa aquele registro por vez. O claim não autoriza o envio — quem autoriza é `disparo_confirmado` —, e nenhum evento desta ADR cria, renova, libera ou expira claim. A neutralidade da ADR-008 (§14) é preservada nos dois sentidos.
- **O T0 da Coleta não é tocado.** Continua sendo o timestamp de `disparo_confirmado` (ADR-007, §18; ADR-009, §6.3). Nenhum evento de envio, aceitação ou status altera, reinicia ou amplia a janela.
- **A janela fecha o envio.** Encerrada a janela total da coleta (ADR-005), `envio_solicitado` é recusado.

---

## 9. Fatos Técnicos do Webhook

- **Nada é processado sem assinatura válida.** Uma notificação cuja assinatura não confere não gera evento, não gera registro e não é interpretada.
- **A notificação inteira é percorrida.** Todos os `entry`, todos os `changes`, todos os `statuses` e todas as mensagens — nunca apenas o primeiro elemento.
- **Não existe "status atual" de um envio.** A plataforma não garante ordem: `lido` pode chegar antes de `entregue`, e notificações se repetem. A projeção guarda, para cada status, se foi observado e quando; nenhum campo afirma em que estado a mensagem "está".
- **Nenhuma inferência.** `lido` não vira "o cliente leu"; `entregue` não vira "o cliente recebeu"; ausência de status não vira falha. O sistema afirma apenas "a plataforma informou este status neste instante".
- **`context` é registrado como observado.** Quando uma mensagem recebida traz referência a uma mensagem anterior, o evento diz se essa referência aponta para um envio conhecido. Isso **não é** a correlação determinística da ADR-007 (§10): é o insumo que a Sprint E usará para decidi-la.
- **Status de `wamid` desconhecido não gera evento.** Não há agregado ao qual vinculá-lo. A especificação técnica define a contagem técnica desses casos, sem dado pessoal.
- **A resposta à plataforma não depende do resultado do processamento.** Uma notificação com assinatura válida é confirmada à plataforma mesmo quando nada nela gera evento, para não provocar reenvios em cadeia. O contrato exato é da especificação técnica.

---

## 10. Privacidade e Dados Pessoais

- **Telefone:** aparece nas notificações (`recipient_id`, `from`). **Nunca entra em evento e não é persistido por este domínio.** O telefone do registro de coleta já reside na projeção `registros_coleta` (ADR-009).
- **Texto de mensagem recebida:** dado pessoal de conteúdo livre. **Não é persistido em PostgreSQL por esta ADR**, nem em evento nem em projeção. Sua guarda é decidida pelas Sprints E (resposta vinculada) e F (payload íntegro, criptografia, retenção curta).
- **Texto de erro devolvido pela plataforma:** pode ecoar telefone ou conteúdo. Nunca é persistido; somente códigos numéricos.
- **`wamid` e o identificador de mensagem recebida:** identificadores pseudonimizados, vinculáveis por meio da plataforma. Residem somente em projeção corrente, nunca em evento (Seção 5).
- **`tentativa_envio_id`, `registro_coleta_id` e `lote_id`:** continuam dados pessoais enquanto vinculáveis (ADR-009, §7).
- **Credenciais:** o token de acesso à API, o segredo de assinatura e o token de verificação do webhook nunca aparecem em evento, projeção, log, mensagem de erro ou arquivo versionado.
- **Logs:** nenhuma mensagem de log deste domínio contém telefone, nome, produto, texto de mensagem, `wamid` ou credencial.

---

## 11. Papéis (Roles) Autorizados

| Role | Eventos autorizados | Natureza |
|---|---|---|
| `nsi_envio` | `envio_solicitado`, `envio_aceito_api`, `envio_falha_api_observada`, `envio_resultado_desconhecido` | **Nova**, `LOGIN`, credencial própria |
| `nsi_webhook` | `status_whatsapp_observado`, `mensagem_recebida_observada` | **Nova**, `LOGIN`, credencial própria |
| `nsi_eventos_owner` | Dona de todas as tabelas e funções deste domínio | `NOLOGIN`, já existente |
| `nsi_aplicacao`, `nsi_expiracao`, `nsi_operador_restrito`, `nsi_congelamento`, `nsi_importacao` | Nenhum evento deste domínio | já existentes — não utilizadas aqui |

- **As duas roles novas não pertencem a nenhuma role e não têm membros.** Nenhuma nova exceção à regra de membership da B3.1 é criada; a exceção única da ADR-009 (§21) continua única.
- **Privilégio estritamente mínimo:** `CONNECT`, `USAGE` no schema e `EXECUTE` somente nas funções dos seus eventos. Nenhum `SELECT`, `INSERT`, `UPDATE` ou `DELETE` direto em nenhuma tabela; `PUBLIC` sem `EXECUTE`.
- **`nsi_webhook` nunca envia.** O processo que recebe notificações da internet não possui `EXECUTE` em nenhuma função de envio, de claim, de lote ou de correção.
- **`nsi_envio` precisa deter o claim do registro** (Seção 8), o que exige o `EXECUTE` correspondente nas funções de claim que a especificação técnica indicar — e somente nelas.
- **Identidade registrada:** `executado_por_login = session_user`, como em todo o sistema (ADR-009, §10).
- **A criação das duas roles pertence ao provisionamento administrativo**, no padrão de três fases já usado desde a B3.1 — nunca a uma migration. As roles são criadas sem senha.

---

## 12. Desabilitação do Envio Real

- **Durante toda a Sprint C nenhum envio real a cliente ocorre** — nem em teste, nem em execução manual, nem por rota HTTP.
- **Desabilitado é o estado padrão.** A ausência de configuração de habilitação, ou qualquer valor que não seja o explicitamente previsto, significa envio desabilitado. Não existe valor padrão que habilite.
- **O transporte é substituível.** O componente que fala com a API recebe o transporte por injeção. Os testes usam exclusivamente transporte simulado ou fixtures; nenhum teste abre conexão com a plataforma.
- **A habilitação é cumulativa e humana.** Depende, sem dispensa isolada, das Sprints D (confirmação em dois atos e autenticação), E (correlação determinística), F (teste controlado da Meta) e G (classificação de falhas), nos termos do ROADMAP.
- **Nenhum claim, heartbeat ou evento técnico autoriza disparo** — desta ou de qualquer sprint.

**Caminho legado.** A rota `POST /api/lote/<lote_id>/disparar` e `core/scheduler.py::disparar_lote` enviam hoje sobre `lote.json`, sem autenticação. Esta ADR declara esse caminho **incompatível** com a ADR-007 (§16) e com esta seção. Durante a Sprint C ele é **desabilitado** pelo mesmo mecanismo de habilitação que falha fechado (ponto `P7` da Seção 16): nenhuma rota e nenhuma chamada direta envia enquanto o envio não for explicitamente habilitado.

---

## 13. Fronteira com as Demais Sprints e Domínios

| Assunto | Onde é decidido |
|---|---|
| Corte real; troca do backend de `adapters/storage.py` | B7 (Sprint C, primeiro item) |
| Confirmação de nova tentativa; desbloqueio de `resultado_desconhecido`; rotas e MFA | Sprint D |
| Vínculo resposta → registro → produto; quarentena; Motor NSI | Sprint E |
| Payload íntegro, criptografia, retenção curta | Sprint F |
| Classificação `temporaria` / `definitiva`; intervalo entre tentativas | Sprint G |
| Eventos de claim | ADR-008 |
| Eventos de lote, registro e correção | ADR-009 |

Até o corte real, o mecanismo desta ADR opera somente em `nsi_dev` e `nsi_test`, com dados sintéticos, e **coexiste** com o caminho legado em JSON sem substituí-lo.

---

## 14. O Que Permanece para Especificação Técnica

1. Schema relacional: tabelas de eventos e de projeção, constraints, índices, triggers de imutabilidade.
2. Funções `SECURITY DEFINER`, parâmetros, contrato de erros e mensagens fixas.
3. Formato exato das chaves de idempotência e do `payload_hash`.
4. Quem materializa `processamento_interrompido`, e a partir de que condição.
5. Quais funções de claim `nsi_envio` pode executar.
6. Scripts de provisionamento e de reversão das duas roles.
7. Contrato do transporte injetável; tempos limite; tratamento de resposta ininteligível.
8. Mecanismo concreto de habilitação que falha fechado.
9. Contrato da resposta HTTP do webhook e a contagem técnica de notificações sem evento.
10. Normalização do telefone para a API, usando a regra da Sprint A2.
11. Plano de testes e critérios de aceite.

---

## 15. Decisões Aprovadas e Congeladas

1. Agregado "tentativa de envio", com `tentativa_envio_id` e unicidade por `(registro_coleta_id, numero_tentativa)`.
2. Catálogo fechado de exatamente seis eventos: `envio_solicitado`, `envio_aceito_api`, `envio_falha_api_observada`, `envio_resultado_desconhecido`, `status_whatsapp_observado`, `mensagem_recebida_observada`.
3. `envio_solicitado` confirmado no banco antes da chamada à API; chamada fora de transação.
4. Tentativa sem desfecho nunca é reenviada; `resultado_desconhecido` bloqueia o registro até decisão humana futura.
5. Envio aceito pela API nunca é repetido.
6. `classificacao` com o único valor `nao_classificada` até a Sprint G.
7. Somente `numero_tentativa = 1` é alcançável por este catálogo.
8. Claim como pré-condição de exclusão mútua, nunca como autorização.
9. T0 da Coleta intocado por qualquer evento deste domínio.
10. Status de webhook registrados como fatos independentes, sem "status atual" e sem inferência.
11. `context` registrado como observado; correlação final somente na Sprint E.
12. `wamid` e identificador de mensagem recebida somente em projeção, nunca em evento.
13. Telefone, texto de mensagem e texto de erro nunca persistidos por este domínio.
14. Duas roles novas, `nsi_envio` e `nsi_webhook`, com `LOGIN` próprio, sem membership, privilégio mínimo; criadas por provisionamento administrativo.
15. Envio real desabilitado por padrão durante toda a Sprint C; habilitação cumulativa das Sprints D a G.
16. O caminho legado de disparo (`POST /api/lote/<lote_id>/disparar` e `core/scheduler.py::disparar_lote`) fica sujeito ao mesmo mecanismo de habilitação que falha fechado (`P7`).
17. A gravação de resposta em `lote.json` pelo webhook permanece inalterada até a Sprint E e o corte real; os eventos deste catálogo são registrados em paralelo (`P8`).

---

## 16. Escolhas entre Alternativas

| # | Decisão | Alternativa descartada | Motivo |
|---|---|---|---|
| `P1` | `wamid` só na projeção, nunca em evento | `wamid` no payload de `envio_aceito_api` | permite que uma futura política jurídica atue sem editar evento |
| `P2` | Um evento `status_whatsapp_observado` com enum de quatro valores | quatro eventos, um por status | mesma informação, catálogo menor; o enum continua fechado |
| `P3` | `mensagem_recebida_observada` existe já na Sprint C, sem texto e sem vínculo de coleta | deixar toda mensagem recebida para a Sprint E | o ROADMAP exige `context` processado na Sprint C; sem o evento, a referência se perderia |
| `P4` | Texto da mensagem recebida não vai para o PostgreSQL nesta ADR | gravar o texto em projeção | retenção e criptografia são da Sprint F; a resposta vinculada é da Sprint E |
| `P5` | Roles novas com `LOGIN` próprio | roles `NOLOGIN` assumidas por `SET ROLE` a partir de `nsi_aplicacao` | evita uma segunda exceção à regra de membership e isola o processo exposto à internet |
| `P6` | Tentativas 2 e 3 fora do catálogo | incluir já o evento de confirmação de nova tentativa | sem classificação de falha (Sprint G) e sem autenticação (Sprint D), o evento não teria uso legítimo |
| `P7` | Caminho legado de disparo desabilitado na Sprint C, pelo mecanismo que falha fechado | mantê-lo como está até a Sprint D | ver abaixo |
| `P8` | Gravação de resposta em `lote.json` mantida inalterada até a Sprint E e o corte real | removê-la já | ver abaixo |

**`P7` — caminho legado de disparo.** Opções: (a) desabilitá-lo na Sprint C, pelo mesmo mecanismo de habilitação que falha fechado, de modo que nenhuma rota envie; (b) mantê-lo como está até a Sprint D. A opção (a) altera `app.py` ou `core/scheduler.py`, que o ROADMAP reserva à Sprint D quanto a rotas; a opção (b) mantém um envio real sem autenticação acessível durante uma sprint cuja condição é "nenhum envio real". **Decisão: (a).** A alteração limita-se ao bloqueio do envio; nenhuma rota nova, autenticação ou tela é criada — isso continua sendo da Sprint D.

**`P8` — resposta em `lote.json`.** O webhook atual grava o texto da resposta no `lote.json`, vinculando-o por telefone. Opções: (a) manter esse comportamento inalterado até a Sprint E e o corte real, acrescentando os eventos novos em paralelo; (b) removê-lo já. A opção (b) interrompe a coleta de respostas da aplicação em operação. **Decisão: (a)**, com a não conformidade da ADR-007 (§10.3) permanecendo declarada.

---

## 17. Pendências Técnicas Não Bloqueantes

- Evento de confirmação de nova tentativa e de desbloqueio de `resultado_desconhecido` — evolução desta ADR, nas Sprints D e G.
- Valores `temporaria` e `definitiva` de `classificacao` — Sprint G.
- Política de retenção das projeções deste domínio e de `comandos_idempotentes`.
- Tratamento de status informados pela plataforma fora do enum de quatro valores, se algum se mostrar relevante.
- Disponibilidade de ambiente de teste da Meta: a Sprint C é aceita com transporte simulado e fixtures; um ambiente controlado da plataforma é opcional aqui e obrigatório somente na Sprint F.

---

## 18. Dependências

- ADR-005 — janela total da coleta e T0.
- ADR-007 — §10, §16 a §22.
- ADR-008 — §6, §7, §11, §14, §15 e §18.
- ADR-009 — §5 a §7, §9 a §11 e §21.
- Sprint B encerrada: `nsi_dev` e `nsi_test` em `0006`.
- Provisionamento administrativo das duas roles, pelo operador, com o superusuário.

---

## 19. Itens Fora do Escopo

Todos os da Seção 2.2. Em particular: esta ADR **não habilita envio**, **não autoriza a B7**, **não cria rota** e **não decide a correlação de respostas**.

---

## 20. Referências

- `docs/architecture/ADR-005-ciclo-temporal-coleta-leituras-independentes.md`
- `docs/architecture/ADR-007-ciclo-operacional-preparacao-disparo-coleta.md`
- `docs/architecture/ADR-008-persistencia-operacional-imutavel-claims-idempotencia.md`
- `docs/architecture/ADR-009-catalogo-eventos-operacionais.md`
- `docs/architecture/ADR-010-importacao-legado-operacional.md`
- `docs/implementation/ROADMAP-SPRINTS-B-G.md` — Sprint C
- `docs/implementation/SPRINT-B-ESPECIFICACAO-TECNICA.md`
- Código de referência: `services/whatsapp.py`, `services/webhook_handler.py`, `core/scheduler.py`, `app.py`

---

## 21. Status Final e Congelamento (2026-10-11)

**APROVADA E CONGELADA.** Aprovada pelo operador em 2026-10-11, na autorização de execução integral da Sprint C, com as escolhas `P1` a `P6` como propostas e os pontos `P7` e `P8` decididos conforme a recomendação (Seção 16).

### O que o congelamento significa

- O catálogo de seis eventos (Seção 6), a ordem obrigatória e a regra de não repetição (Seção 7), as regras de `numero_tentativa`, claim e T0 (Seção 8), o tratamento dos fatos do webhook (Seção 9), as regras de privacidade (Seção 10), os papéis autorizados (Seção 11) e a desabilitação do envio real (Seção 12) não são alterados por especificação técnica nem por implementação.
- Qualquer evento novo, qualquer valor novo de enum fechado e qualquer habilitação de envio real exigem evolução arquitetural formal desta ADR.
- O congelamento **não autoriza a B7**, **não habilita envio** e não dispensa a autorização própria de cada subetapa da Sprint C.

**Origem desta decisão:** dependência registrada no `ROADMAP-SPRINTS-B-G.md` (Sprint C, "Dependências") e na ADR-008 (§11 e §18).
