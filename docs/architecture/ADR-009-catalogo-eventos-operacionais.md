# ADR-009 — Catálogo de Eventos Operacionais de Lote, Registro de Coleta e Correção

## Metadados

| Campo | Valor |
|---|---|
| Status | APROVADA E CONGELADA |
| Data | 2026-09-16 |
| Versão de referência do sistema | `v1.1.0-fonte-unica-webhook-motor` |
| Commit de referência | `19cfed3` |
| Branch | `master` |
| Escopo desta ADR | Arquitetura — nenhuma implementação de código, schema de banco de dados ou migration |

> **Nota de processo:** ADR aberta para cumprir a dependência formalmente registrada pela Especificação Técnica da Sprint B (`SPRINT-B-ESPECIFICACAO-TECNICA.md`, Seção 9 — "Modelo de Dados — Eventos Operacionais (B4) — NÃO Definido Aqui"): *"B4 permanece formalmente condicionada a uma decisão arquitetural própria (evolução da ADR-008 ou ADR complementar)"*. Esta ADR é essa decisão. Ela não reabre, não redefine e não contradiz nenhuma decisão já congelada na ADR-007 ou na ADR-008 — estende exclusivamente o modelo geral de evento imutável e projeção corrente já fixado na ADR-008 (§6) a um novo domínio (lote, registro de coleta e correção), exatamente como a própria ADR-008 (§11) previu que decisões futuras próprias poderiam fazer. Esta ADR foi precedida por múltiplas rodadas de verificação somente leitura — reconstrução de estado, privacidade de dados pessoais, menor privilégio e semântica correta de identidade no PostgreSQL — cada uma corrigindo a anterior, e está **APROVADA E CONGELADA** com essas correções já incorporadas (Seção 15).

---

## 1. Objetivo

Registrar o catálogo fechado de eventos imutáveis, o modelo híbrido de persistência e as regras de identidade técnica e de menor privilégio para os domínios de **lote**, **registro de coleta** e **correção** — a Subetapa B4.1 da Sprint B. Esta ADR define, antes de qualquer código: quais eventos existem para esses três domínios e nenhum outro; o que cada evento pode e não pode carregar; como o modelo híbrido evita\* colocar dado pessoal em uma estrutura que nunca pode ser editada ou apagada; qual identidade técnica cada evento registra; e quais papéis do PostgreSQL têm permissão de gerar cada evento.

Esta ADR não implementa nada. Ela define o que deve ser verdade antes que qualquer migration, tabela ou função `SECURITY DEFINER` deste domínio seja criada.

\* "Evita" no sentido de desenho arquitetural — não é uma garantia jurídica; ver Seção 7.

---

## 2. Escopo

### 2.1 Escopo desta decisão

- Modelo híbrido de persistência: eventos imutáveis como fonte de transições e auditoria; tabelas de estado corrente como fonte dos valores pessoais e operacionais atuais (Seção 5).
- Catálogo fechado de cinco eventos para os domínios de lote, registro de coleta e correção (Seção 6).
- Classificação de dados pessoais e limites de imutabilidade frente a obrigações jurídicas futuras (Seção 7).
- Payload seguro do evento de tentativa de correção não resolvida (Seção 8).
- Localização do checksum do CSV e do `payload_hash` de idempotência, e sua natureza potencialmente correlacionável (Seção 9).
- Regras de identidade técnica dentro de funções `SECURITY DEFINER` (Seção 10).
- Papéis (roles) do PostgreSQL autorizados a gerar cada evento, e a natureza administrativa da criação de uma nova role (Seção 11).
- Regra de idempotência determinística para o evento de congelamento M0+192h (Seção 12).

### 2.2 Fora do escopo desta decisão

- Eventos do ciclo de vida de claims — catálogo fechado já definido pela ADR-008 (§11), não reaberto por esta ADR.
- Envio efetivo, API ou webhook do WhatsApp — Sprint C.
- Eventos internos de execução do Motor NSI — fora do domínio operacional da ADR-008 (§5).
- Portal Executivo do Cliente — domínio da ADR-004/ADR-006, não relacionado.
- Autenticação e MFA reais do Operador Interno — Sprint D; esta ADR só define que a identidade humana não pode ser inventada enquanto essa autenticação não existir (Seção 10).
- Histórico completo e navegável de valores pessoais anteriores (ex.: uma eventual tabela de versões) — não criado nesta sprint (Seção 5).
- Política jurídica definitiva de retenção, anonimização ou expurgo de dados pessoais — a formalizar separadamente, nunca antecipada por esta ADR (Seção 7).
- Schema relacional concreto, migration, nomes de colunas/funções Python — especificação técnica futura (Seção 14).
- Mecanismo técnico concreto de detecção do congelamento M0+192h (cron/worker) e o script de provisionamento administrativo da nova role — também especificação técnica futura, nunca presumidos como responsabilidade automática de uma migration Alembic (Seção 14).

---

## 3. Contexto

A ADR-008 (§11) fechou o catálogo de eventos exclusivamente para o ciclo de vida de claims, e foi explícita ao declarar que eventos de outros domínios — citando nominalmente "envio, aceitação pela API, status de webhook, resposta, quarentena, execução do Motor NSI" — dependeriam de decisões arquiteturais próprias das Sprints C, E e G, "sem que esta ADR antecipe seus campos, seu significado ou sua nomenclatura", mas reaproveitando o mesmo modelo geral de evento imutável e projeção corrente já fixado em sua Seção 6.

A Especificação Técnica da Sprint B (Seção 9) identificou que um domínio adicional — eventos de **lote**, de **registro de coleta** e de **correção** — também carecia dessa decisão própria antes que a Subetapa B4 pudesse começar, e declarou textualmente: *"Sem essa decisão, B4 não pode iniciar."* O `ROADMAP-SPRINTS-B-G.md` já previa esse trabalho como entrega da própria Sprint B: *"log de eventos imutável e projeção corrente para lotes, registros de coleta e correções."*

Diferente do domínio de claims — onde nenhum evento carrega dado pessoal bruto (`registro_coleta_id` é um UUID pseudônimo, `token_hash` é um hash não reversível) —, o domínio de lote/registro/correção lida diretamente com o conteúdo do CSV original: nome, WhatsApp e produto do cliente. Uma verificação somente leitura, anterior a esta ADR, confirmou que aplicar ao pé da letra o mesmo modelo de claims — eventos que reconstroem integralmente a projeção — exigiria embutir esse dado pessoal bruto dentro de uma estrutura que a ADR-008 (§15) não autoriza operacionalmente editar ou apagar por nenhum fluxo comum ou excepcional. Um eventual mecanismo jurídico futuro de anonimização, eliminação ou exceção — se e quando necessário — dependeria de política formal própria, ainda não criada; nem a ADR-008 nem esta ADR-009 substituem ou impedem essa obrigação legal futura, apenas não a antecipam. Esta ADR resolve essa tensão adotando um modelo híbrido (Seção 5), nunca reabrindo a regra de imutabilidade da ADR-008.

---

## 4. Princípios Arquiteturais

### Princípio 1 — Modelo Híbrido, Não Event Sourcing Integral

A projeção corrente de lote e de registro de coleta não é, e não precisa ser, integralmente reconstruível apenas a partir do log de eventos. Os eventos provam que uma transição ocorreu; as tabelas de estado corrente são a fonte primária dos valores pessoais e operacionais atuais.

### Princípio 2 — Eventos Nunca Carregam Valor Pessoal Bruto

Nenhum evento desta ADR contém nome, WhatsApp, produto ou qualquer valor pessoal submetido em uma correção. O payload de cada evento se limita a identificadores, contadores, enums de resultado e timestamps.

### Princípio 3 — Identidade Técnica, Nunca Identidade Humana Inventada

Todo evento registra `executado_por_login`, a credencial `LOGIN` real da conexão (`session_user`) — nunca uma pessoa. Onde uma identidade humana autenticada seria semanticamente relevante (a confirmação de disparo), o campo correspondente permanece explicitamente ausente/nulo até que autenticação real exista (Sprint D) — nunca preenchido com um rótulo inventado ou fornecido livremente pelo chamador.

### Princípio 4 — Menor Privilégio por Papel Dedicado

Cada evento é gerado por exatamente um papel (role) autorizado, restrito ao mínimo necessário. Um mecanismo técnico automático (o worker de congelamento) nunca compartilha a mesma identidade de papel usada por ações requisitadas por humanos.

### Princípio 5 — Idempotência Proporcional à Natureza da Operação

Operações que só podem ocorrer legitimamente uma vez por agregado (o congelamento de um lote) usam uma chave de idempotência determinística, derivada do próprio agregado. Operações que podem ocorrer legitimamente mais de uma vez para o mesmo agregado (uma correção, uma confirmação de disparo) exigem uma chave de idempotência fornecida por tentativa, nunca derivada de um identificador permanente do agregado.

### Princípio 6 — Imutabilidade Operacional sem Exceção

Nenhum fluxo comum ou excepcional desta ADR executa `UPDATE` ou `DELETE` sobre um evento imutável já gravado — mesma regra já congelada pela ADR-008 (§15), agora estendida a este domínio. Esta é uma regra operacional interna do sistema.

### Princípio 7 — Neutralidade Jurídica

Esta ADR não decide, antecipa, nem pode decidir por si só, nenhuma obrigação jurídica futura de anonimização ou eliminação de dados pessoais. Ela organiza os dados de forma que uma futura política jurídica **possa** atuar sobre as tabelas de estado corrente sem exigir a edição de um evento imutável — mas essa organização é uma facilitação técnica, nunca uma barreira jurídica, e nunca substitui a política em si, que permanece a ser formalizada separadamente (Seção 7).

---

## 5. Modelo Híbrido — Eventos e Estado Corrente

- **Evento imutável ("Evento Permanente"):** um fato ocorrido, registrado uma única vez, com identificador, tipo e timestamp próprios, nunca alterado nem removido após gravado — mesma definição geral já fixada pela ADR-008 (§6), aplicada aqui a um novo domínio. Um evento desta ADR prova **que** uma transição de negócio ocorreu, **quando**, sob qual identidade técnica e com qual resultado — nunca o valor pessoal em si.
- **Estado corrente ("Tabela de Projeção"):** a fonte de verdade dos valores pessoais e operacionais **atuais** de um lote ou de um registro de coleta — nome, WhatsApp, produto, validade, status. É mutável por natureza: uma correção substitui o valor anterior diretamente na tabela de estado, na mesma transação em que o evento correspondente é gravado.
- **Isto não é event sourcing integral.** Ao contrário do modelo de claims (onde a projeção é inteiramente derivada do log de eventos), a projeção de registro de coleta **não pode** ser reconstruída do zero apenas a partir dos cinco eventos desta ADR — os valores pessoais em si só existem nas tabelas de estado. Esta é uma diferença de contrato deliberada frente à ADR-008 (§6), justificada pela Seção 7 desta ADR.
- **Valores pessoais anteriores não são preservados nesta sprint.** Uma correção sobrescreve o valor corrente; o evento correspondente registra apenas que uma correção ocorreu (`numero_versao`, `resultado`), nunca o valor antigo nem o novo.
- **Nenhuma tabela de histórico de versões (`registros_coleta_versoes` ou equivalente) é criada por esta ADR.** Se uma necessidade futura de negócio ou uma exigência jurídica exigir histórico detalhado de valores pessoais anteriores, isso exige decisão arquitetural própria, futura, que pondere explicitamente essa necessidade contra o mesmo risco de imutabilidade descrito na Seção 7.

---

## 6. Catálogo Fechado de Eventos

**O catálogo abaixo é fechado exclusivamente para os eventos de lote, registro de coleta e correção definidos por esta ADR** — mesma disciplina já usada pela ADR-008 (§11) para o catálogo de claims. Não é o catálogo geral de eventos imutáveis do sistema NSI: eventos de claim pertencem exclusivamente à ADR-008; eventos de envio, webhook, Motor NSI e Portal Executivo pertencem a decisões arquiteturais próprias de outras sprints (Seção 13). A introdução de um sexto evento a este catálogo, ou a alteração de qualquer um dos cinco abaixo, exige evolução arquitetural formal desta ADR-009 — a especificação técnica não amplia este catálogo sozinha.

**Regra geral de idempotência, válida para os cinco eventos abaixo:** a chave de idempotência identifica a requisição ou operação que produziu o evento — nunca o valor de negócio que ela gera. O `payload_hash` representa exclusivamente a entrada semântica fornecida pelo chamador; nenhum valor gerado pelo servidor (timestamp, contador, versão produzida ou resultado calculado) entra nele. Mesma chave de idempotência com mesmo `payload_hash` retorna o resultado já persistido (**replay**), sem gravar novo evento; mesma chave com `payload_hash` divergente é recusada como conflito explícito (`SQLSTATE 22023`, mesmo padrão já usado pelas funções de claim). A própria chave de idempotência nunca é confundida com, nem incluída artificialmente dentro de, o conteúdo semântico que compõe o `payload_hash` — são dois valores independentes.

Composição conceitual do `payload_hash` de cada evento (implementação exata do algoritmo permanece para especificação técnica, Seção 14):

- `lote_criado`: entrada semântica canônica do upload — o hash fica somente em `comandos_idempotentes` e pode ser correlacionável (Seção 9).
- `lote_congelado_d8`: somente `lote_id` (Seção 12).
- `disparo_confirmado`: `lote_id` e a precondição/versão esperada fornecida pelo chamador, quando aplicável.
- `correcao_registrada`: `registro_coleta_id` e os valores corrigidos normalizados fornecidos pelo chamador — os valores em si nunca aparecem no evento, apenas o hash correspondente em `comandos_idempotentes`.
- `tentativa_correcao_nao_resolvida`: `lote_id`, `motivo` e `codigo_tecnico_normalizado` (ou seu valor nulo).

Nenhuma dessas composições inclui horário, versão produzida pela função, contador ou resultado — todos gerados pelo servidor, nunca pelo chamador.

### 6.1 `lote_criado`

| | |
|---|---|
| **Agregado** | `lote` |
| **Finalidade** | Registrar que um CSV foi recebido e estruturalmente validado, com seus registros de coleta já separados em válidos e inválidos (M0) |
| **Transição permitida** | Só ocorre quando não existe `lote_criado` anterior para o mesmo `lote_id` |
| **Payload** | `lote_id`, `recebido_em`, `total_recebido`, `total_valido`, `total_invalido`, `executado_por_login` |
| **Idempotência** | `(lote_criado, lote_id, id_requisicao_de_upload)` — chave fornecida pela tentativa de upload |
| **Papel autorizado** | `nsi_aplicacao` |
| **Efeito na projeção** | Cria a linha correspondente em `lotes` e uma linha por registro em `registros_coleta` — os valores pessoais de cada registro são escritos diretamente na projeção, nunca replicados no evento |

### 6.2 `lote_congelado_d8`

| | |
|---|---|
| **Agregado** | `lote` |
| **Finalidade** | Registrar, de forma auditável, o instante real em que o congelamento M0+192h foi tecnicamente aplicado — inclusive quando tardio (ADR-007, §12) |
| **Transição permitida** | Só ocorre quando o instante conceitual M0+192h já foi atingido e não existe `lote_congelado_d8` anterior para o mesmo `lote_id` |
| **Payload** | `lote_id`, `horario_conceitual` (M0+192h, calculado), `horario_real_execucao` (produzido pela função, nunca informado pelo chamador), `atrasado` (booleano), `executado_por_login` |
| **Idempotência** | `(lote_congelado_d8, lote_id, lote_id)` — chave determinística; ver Seção 12 |
| **Papel autorizado** | `nsi_congelamento` (via `SET ROLE`, a partir de uma conexão `nsi_aplicacao`) |
| **Efeito na projeção** | `lotes.status` → estado equivalente a "Aguardando confirmação de disparo" (ADR-007, §13) |

### 6.3 `disparo_confirmado`

| | |
|---|---|
| **Agregado** | `lote` |
| **Finalidade** | Registrar o segundo ato da Confirmação em Dois Atos (ADR-007, §16) — a única decisão que autoriza o disparo. O timestamp deste evento é o T0 que a ADR-005 (Princípio 1) já define como o timestamp exato do disparo do lote (ADR-007, §18) |
| **Transição permitida** | Só ocorre após `lote_congelado_d8`, com a contagem definitiva já calculada, e sem `disparo_confirmado` anterior para o mesmo `lote_id` |
| **Payload** | `lote_id`, `executado_por_login`, `operador_humano_id` (nulo até a Sprint D), `total_confirmado` |
| **Idempotência** | `(disparo_confirmado, lote_id, id_requisicao_de_confirmacao)` |
| **Papel autorizado** | `nsi_operador_restrito` |
| **Efeito na projeção** | `lotes.status` → `disparo_confirmado` |

### 6.4 `correcao_registrada`

| | |
|---|---|
| **Agregado** | `registro_coleta` |
| **Finalidade** | Registrar o resultado de uma tentativa de correção que resolveu a um registro de coleta existente neste lote — aceita como válida, aceita mas ainda inválida, ou recusada com um registro identificável |
| **Transição permitida** | Sempre grava, independentemente do resultado — mesmo princípio já aprovado para `revisao_de_abandono_registrada` (ADR-008, §13) |
| **Payload** | `registro_coleta_id`, `codigo_tecnico`, `numero_versao`, `resultado` (enum), `executado_por_login` |
| **Idempotência** | `(correcao_registrada, registro_coleta_id, id_da_tentativa)` — **nunca `codigo_tecnico`**, que identifica o alvo permanente da correção, não a tentativa |
| **Papel autorizado** | `nsi_aplicacao` |
| **Efeito na projeção** | Atualiza `registros_coleta` (valores pessoais atuais, validade, número de versão) somente quando `resultado` é uma aplicação; nenhuma alteração quando o resultado é uma recusa |

### 6.5 `tentativa_correcao_nao_resolvida`

| | |
|---|---|
| **Agregado** | `lote` |
| **Finalidade** | Registrar, de forma auditável e segura, uma tentativa de correção cujo código não resolveu a nenhum registro deste lote |
| **Transição permitida** | Ocorre quando o código técnico apresentado é ausente, sintaticamente inválido, sintaticamente válido mas inexistente neste lote, ou pertence a outra Operação |
| **Payload** | Ver Seção 8 (payload seguro, sem dado pessoal bruto) |
| **Idempotência** | `(tentativa_correcao_nao_resolvida, lote_id, id_da_tentativa)` |
| **Papel autorizado** | `nsi_aplicacao` |
| **Efeito na projeção** | Nenhum |

---

## 7. Privacidade e Dados Pessoais

- **Nome, WhatsApp, produto e valores corrigidos são dados pessoais.** Nome e WhatsApp identificam diretamente uma pessoa natural; produto é dado pessoal por associação a um registro identificável; valores corrigidos são dado pessoal atualizado. Nenhum dos quatro é classificado por esta ADR como dado operacional neutro. Esses valores residem exclusivamente nas tabelas de estado corrente (Seção 5) — nunca em um evento.
- **`lote_id`, `registro_coleta_id` e `codigo_tecnico` continuam sendo dados pessoais enquanto forem vinculáveis a uma pessoa identificável.** São identificadores pseudonimizados, não anonimizados — esta ADR não os classifica como "dados não pessoais" só por serem UUIDs; a pseudonimização reduz o risco de exposição direta, mas não remove a natureza pessoal do dado enquanto a vinculação a um registro real existir.
- **A imutabilidade definida por esta ADR é uma regra operacional interna, não uma blindagem jurídica.** Esta ADR não declara, e não pode declarar, que a imutabilidade dos eventos impede uma futura obrigação jurídica de anonimização ou eliminação de dados pessoais (direito ao esquecimento, ordem judicial ou equivalente) — mesma cautela já praticada pela ADR-008 (§15). O que esta ADR faz é **organizar** os dados de forma que essa obrigação, quando existir, possa ser cumprida atuando sobre as tabelas de estado corrente, sem exigir a edição de nenhum evento imutável.
- **Uma eventual política jurídica de retenção, anonimização ou expurgo de dados pessoais será formalizada separadamente**, no mesmo padrão já usado pela ADR-006 (§21) e pela ADR-008 (§17/§21) — esta ADR não a antecipa, não a desenha e não constitui autorização operacional para editar ou remover nenhum evento imutável.

---

## 8. Payload Seguro — `tentativa_correcao_nao_resolvida`

**Permitido:**
- `lote_id`.
- `motivo`, enum fechado: `codigo_ausente` \| `codigo_invalido` \| `codigo_inexistente` \| `registro_de_outra_operacao`.
- `codigo_tecnico_normalizado`, presente **somente** quando o código apresentado é sintaticamente válido como UUID4 (`motivo` ∈ {`codigo_inexistente`, `registro_de_outra_operacao`}).
- `codigo_tecnico_normalizado` = `NULL` quando `motivo` ∈ {`codigo_ausente`, `codigo_invalido`}.

**Proibido, sem exceção:**
- O código bruto apresentado, quando sintaticamente inválido — nunca gravado, nem truncado, nem em nenhuma forma reversível.
- Nome, telefone, produto ou qualquer outro valor pessoal bruto.
- Texto livre de qualquer natureza vindo da tentativa.

**Fingerprint da entrada bruta:** permanece fora do escopo desta ADR e desligado por padrão. Uma eventual necessidade futura de detecção de abuso, que justifique um fingerprint não reversível e de tamanho limitado, exige avaliação e aprovação próprias — não é criada, habilitada ou presumida por este documento.

---

## 9. Checksum do CSV e `payload_hash` de Idempotência

- **O checksum do arquivo CSV original nunca aparece em nenhum evento imutável desta ADR.** É classificado como um artefato **potencialmente correlacionável**: mesmo não sendo reversível em nome/telefone, permite provar que um arquivo específico — com todo o seu conteúdo pessoal — corresponde a um `lote_id` determinado, para quem possuir uma cópia do arquivo original.
- Se um checksum for operacionalmente necessário (prova de integridade do arquivo recebido), ele fica **exclusivamente na tabela mutável `lotes`** — nunca em `eventos_lote` — precisamente para que uma futura política jurídica possa corrigi-lo ou removê-lo sem tocar em nenhum evento imutável.
- **O `payload_hash` usado pelo mecanismo de idempotência (`comandos_idempotentes`) também é um artefato operacional potencialmente correlacionável**, pelo mesmo motivo — um hash sobre conteúdo pessoal permite correlação por quem possuir o conteúdo original, mesmo sem conseguir revertê-lo.
- **`comandos_idempotentes` permanece sujeita a uma futura política formal de retenção ou expurgo**, no mesmo padrão de honestidade documental já praticado pela ADR-008 (§17/§21) para os JSONs legados — esta ADR não define esse prazo.
- **Nenhum horário ou valor gerado pelo servidor entra no `payload_hash` de entrada de nenhum evento.** O hash cobre exclusivamente os campos fornecidos pelo chamador; valores como `now()` ou `horario_real_execucao` nunca compõem o hash de comparação de idempotência — ver Seção 12 para a consequência direta disso no evento de congelamento.

---

## 10. Identidade Técnica

- **`executado_por_login` = `session_user`** representa a credencial `LOGIN` real da conexão que efetivamente executou a operação — nunca uma pessoa, nunca uma role assumida por `SET ROLE`.
- **`nsi_aplicacao`, `nsi_expiracao` e `nsi_operador_restrito` já são roles `LOGIN` existentes** (aprovadas na B3.1) — esta ADR não cria nenhuma delas, apenas reaproveita.
- **`current_user` nunca é usado como identidade do chamador dentro de uma função `SECURITY DEFINER`.** Dentro de uma função `SECURITY DEFINER`, `current_user` passa a ser o dono da função (`nsi_eventos_owner`) durante a execução — não identifica quem chamou. A identidade do chamador é sempre `session_user`, que `SET ROLE` e `SECURITY DEFINER` não alteram.
- **`operador_humano_id` permanece `NULL`** em `disparo_confirmado` até que autenticação humana real exista (Sprint D). Nenhuma função desta ADR recebe, hoje, um parâmetro para esse campo.
- **Nenhuma função aceita nome ou rótulo humano fornecido livremente pelo chamador.** Um rótulo não autenticado nunca é tratado como identidade confiável, sob nenhuma circunstância.
- **A autorização de quem pode gerar cada evento decorre exclusivamente dos `GRANT EXECUTE`** concedidos a cada role (Seção 11) — nunca do valor registrado no payload do evento. O próprio tipo do evento gravado já prova qual caminho de autorização foi exercido.

---

## 11. Papéis (Roles) Autorizados

| Role | Eventos autorizados | Natureza |
|---|---|---|
| `nsi_aplicacao` | `lote_criado`, `correcao_registrada`, `tentativa_correcao_nao_resolvida` | `LOGIN`, já existente (B3.1) |
| `nsi_operador_restrito` | `disparo_confirmado` | `LOGIN`, já existente (B3.1) |
| `nsi_congelamento` | `lote_congelado_d8`, exclusivamente | **Nova**, `NOLOGIN` |
| `nsi_eventos_owner` | Dona de todas as tabelas e funções deste domínio | `NOLOGIN`, já existente (B3.1) |
| `nsi_expiracao` | Nenhum evento deste domínio | `LOGIN`, já existente (B3.1) — não utilizada aqui |

`nsi_congelamento` é aprovada nesta ADR como uma role `NOLOGIN` de propósito único, seguindo o mesmo princípio de menor privilégio já aplicado às quatro roles funcionais da B3.1: uma conexão `LOGIN` já existente (`nsi_aplicacao`) assume `nsi_congelamento` via `SET ROLE` explícito antes de invocar a função de congelamento — nunca automaticamente.

`nsi_congelamento` opera sob privilégio estritamente mínimo, sem exceção:
- nenhum `SELECT`, `INSERT`, `UPDATE` ou `DELETE` direto em nenhuma tabela;
- nenhum `EXECUTE` em qualquer outra função além da função de congelamento;
- `PUBLIC` sem `EXECUTE` na função de congelamento;
- somente `USAGE` no schema `nsi_operacional` e `EXECUTE` na função específica são concedidos a `nsi_congelamento`;
- toda escrita em `eventos_lote`/`lotes` decorrente do congelamento ocorre exclusivamente dentro da função `SECURITY DEFINER`, dona `nsi_eventos_owner` — nunca por DML direto de `nsi_congelamento`.

**A criação real da role `nsi_congelamento` pertence ao provisionamento administrativo**, seguindo o mesmo padrão seguro já aprovado e executado na B3.1 (`scripts/postgres_local/provisionar_b3_roles.sql`: preflight somente leitura → convergência → pós-validação completa) — **nunca deve ser presumida como responsabilidade automática de uma migration Alembic** sem que os privilégios exatos necessários (Seção 10; `USAGE` no schema, `EXECUTE` na função específica, `GRANT` de membership com `INHERIT FALSE`) tenham sido comprovados e revisados pelo mesmo processo de preflight/pós-validação já validado.

---

## 12. Idempotência do Congelamento (M0+192h)

- A chave de idempotência de `lote_congelado_d8` é **determinística por lote** — `(lote_congelado_d8, lote_id, lote_id)` — porque esta operação só pode ocorrer legitimamente uma vez por lote, disparada pelo tempo, nunca por uma requisição humana repetível com variação de conteúdo.
- `horario_real_execucao` é um resultado **produzido pela função no momento da execução** (via `now()`), nunca um valor de entrada fornecido pelo chamador.
- `horario_real_execucao` **nunca entra no `payload_hash` de entrada** deste comando (Seção 9) — o hash é calculado exclusivamente sobre `lote_id`.
- **Consequência direta e obrigatória:** a repetição da mesma operação — por exemplo, dois workers concorrentes detectando o mesmo marco M0+192h — deve retornar o resultado já gravado na primeira execução (**replay**), nunca um conflito de idempotência (`SQLSTATE 22023`) causado apenas pela diferença de horário entre as duas tentativas. Uma nova tentativa legítima sobre o mesmo lote nunca pode ser rejeitada só porque ocorreu em um instante diferente da primeira.

---

## 13. Fronteira — Sprint B4 / Sprints C, D, E, F, G e Outros Domínios

Esta ADR rege exclusivamente o catálogo de eventos de lote, registro de coleta e correção da Subetapa B4. Ficam explicitamente fora, e pertencem a outras decisões, já tomadas ou ainda futuras:

- Eventos do ciclo de vida de claims — catálogo fechado, já definido e congelado pela ADR-008 (§11); esta ADR não o reabre.
- Envio efetivo pelo WhatsApp, captura de `wamid`, processamento de status de webhook — Sprint C.
- Eventos internos de execução do Motor NSI (classificação semântica) — fora do domínio operacional da ADR-008 (§5); esta ADR não os antecipa.
- Portal Executivo do Cliente — domínio da ADR-004/ADR-006, arquiteturalmente distinto.
- Autenticação e MFA reais do Operador Interno, rotas HTTP, telas de confirmação — Sprint D. Esta ADR só define a regra de identidade técnica que a Sprint D deverá respeitar ao introduzir `operador_humano_id` (Seção 10).
- Histórico completo e navegável de valores pessoais anteriores — não criado nesta sprint (Seção 5).
- Política jurídica definitiva de retenção, anonimização ou expurgo de dados pessoais — a formalizar separadamente (Seção 7).

---

## 14. O Que Permanece para Especificação Técnica

Fora desta ADR, a resolver em especificação técnica futura, sem necessidade de nova ADR salvo se envolver novo princípio arquitetural:

- Schema relacional concreto: tabelas, colunas, tipos, índices, constraints, chaves estrangeiras.
- Script de migration Alembic para as tabelas e funções `SECURITY DEFINER` deste catálogo.
- Script de provisionamento administrativo da role `nsi_congelamento`, seguindo o padrão da B3.1 — nunca incluído dentro de uma migration Alembic.
- Mecanismo técnico concreto de detecção do congelamento M0+192h (cron, worker ou equivalente).
- Formato exato e implementação concreta do cálculo de `payload_hash` para cada evento.
- Nomes de módulos, funções e assinaturas concretas de código Python.

---

## 15. Decisões Aprovadas e Congeladas

1. Modelo híbrido de persistência: eventos imutáveis como fonte de transições e auditoria; tabelas de estado corrente como fonte dos valores pessoais e operacionais atuais — não se trata de event sourcing integral (Princípio 1; Seção 5).
2. Catálogo fechado de exatamente cinco eventos — `lote_criado`, `lote_congelado_d8`, `disparo_confirmado`, `correcao_registrada`, `tentativa_correcao_nao_resolvida` — para os domínios de lote, registro de coleta e correção (Seção 6).
3. Nenhum evento carrega nome, WhatsApp, produto ou valores corrigidos brutos; esses valores residem exclusivamente nas tabelas de estado corrente (Princípio 2; Seção 7).
4. `lote_id`, `registro_coleta_id` e `codigo_tecnico` permanecem dados pessoais enquanto vinculáveis — nunca classificados como dado não pessoal só por serem identificadores técnicos (Seção 7).
5. A imutabilidade definida por esta ADR é uma regra operacional interna, nunca uma barreira jurídica; obrigações futuras de anonimização/eliminação serão tratadas por política jurídica própria, ainda não criada (Princípio 7; Seção 7).
6. Nenhuma tabela de histórico detalhado de valores anteriores é criada nesta sprint (Seção 5).
7. Payload seguro de `tentativa_correcao_nao_resolvida`: código normalizado só quando sintaticamente válido; nunca código bruto inválido, nome, telefone, produto ou texto livre; fingerprint fora do escopo e desligado (Seção 8).
8. Checksum do CSV nunca em evento imutável; se necessário, só na tabela mutável `lotes`; classificado como potencialmente correlacionável, assim como o `payload_hash` de idempotência (Seção 9).
9. `comandos_idempotentes` permanece sujeita a uma futura política formal de retenção/expurgo (Seção 9).
10. `executado_por_login = session_user` é a identidade técnica registrada por todo evento; `current_user` nunca é usado como identidade do chamador dentro de `SECURITY DEFINER`; nenhuma função aceita rótulo humano livre; `operador_humano_id` permanece `NULL` até a Sprint D (Princípio 3; Seção 10).
11. Autorização de cada evento decorre exclusivamente do `GRANT EXECUTE` concedido à role correspondente, nunca de um valor registrado no payload (Seção 10).
12. Cinco papéis autorizados, com `nsi_congelamento` como nova role `NOLOGIN` de propósito único para `lote_congelado_d8`; sua criação real pertence ao provisionamento administrativo, no padrão da B3.1, nunca presumida como parte automática de uma migration Alembic (Princípio 4; Seção 11).
13. Idempotência do congelamento M0+192h é determinística por lote; `horario_real_execucao` é produzido pela função e nunca entra no `payload_hash`; a repetição da operação retorna replay, nunca conflito causado por diferença de horário (Princípio 5; Seção 12).
14. Imutabilidade sem exceção para todos os eventos deste catálogo: nenhum fluxo comum ou excepcional executa `UPDATE` ou `DELETE` sobre um evento já gravado (Princípio 6).
15. Fronteira formal entre a Subetapa B4 e as Sprints C, D, E, F, G e os domínios de claim, Motor NSI e Portal Executivo do Cliente (Seção 13).

---

## 16. Pendências Técnicas Não Bloqueantes

Nenhuma das pendências abaixo é lacuna conceitual desta ADR — são exclusivamente pendências de especificação técnica futura (Seção 14) ou de decisão jurídica/de negócio própria, no mesmo padrão já usado pela ADR-007 e pela ADR-008:

- Schema relacional concreto das tabelas e funções deste catálogo.
- Mecanismo técnico concreto de detecção do congelamento M0+192h.
- Script de provisionamento administrativo da role `nsi_congelamento`.
- Necessidade futura, se houver, de um histórico detalhado e navegável de valores pessoais anteriores.
- Política jurídica definitiva de retenção, anonimização ou expurgo de dados pessoais, incluindo o destino de `comandos_idempotentes` no longo prazo.

---

## 17. Dependências

- Depende da ADR-005 (`docs/architecture/ADR-005-ciclo-temporal-coleta-leituras-independentes.md`, Princípio 1 — "o timestamp exato do disparo do lote") — o evento `disparo_confirmado` (Seção 6.3) estabelece, com seu próprio timestamp, o T0 que ancora as janelas temporais da Leitura Inicial e da Leitura de Excedência já definidas por aquela ADR; esta ADR-009 não redefine nenhuma dessas janelas, apenas fornece o evento que as inicia.
- Depende da ADR-007 (§6 — M0; §11 — contagem definitiva; §12 — D+8 e congelamento; §13 — estado de espera; §14 — identificação na interface; §15 — Operador Interno; §16 — confirmação em dois atos; §18 — T0 da Coleta; §19 — tentativas de disparo) — esta ADR não redefine nenhuma dessas regras, apenas fornece a fundação de eventos que a Seção 9 da Especificação Técnica da Sprint B já previu como pendência.
- Depende da ADR-008 (§6 — definição geral de evento imutável e projeção corrente, aqui estendida a um novo domínio; §11 — catálogo fechado de claims, não reaberto; §15 — imutabilidade sem exceção e sua neutralidade frente a obrigações jurídicas futuras, aqui reafirmada; §18 — fronteira entre Sprint B e Sprints C–G) — esta ADR não amplia o catálogo de claims, nem redefine nenhuma decisão já congelada pela ADR-008.
- Depende da Especificação Técnica da Sprint B (Seção 9), cuja lacuna esta ADR preenche integralmente.
- Depende da B3.1 (`scripts/postgres_local/provisionar_b3_roles.sql`) como precedente de provisionamento administrativo seguro de roles, reaproveitado para `nsi_congelamento` (Seção 11).
- Depende da ADR-006 (§18), exclusivamente como precedente de redação e de política de idempotência — nunca como autorização automática, mesmo padrão já seguido pela ADR-008.

---

## 18. Itens Fora do Escopo

Ver Seção 2.2.

---

## 19. Referências

- `docs/architecture/ADR-005-ciclo-temporal-coleta-leituras-independentes.md` — Princípio 1 (T0 da Coleta, ancorado por `disparo_confirmado`).
- `docs/architecture/ADR-007-ciclo-operacional-preparacao-disparo-coleta.md` — Seções 6, 11, 12, 13, 14, 15, 16, 18, 19.
- `docs/architecture/ADR-008-persistencia-operacional-imutavel-claims-idempotencia.md` — Seções 6, 11, 13, 14, 15, 17, 18, 21.
- `docs/implementation/SPRINT-B-ESPECIFICACAO-TECNICA.md` — Seção 9 (lacuna preenchida por esta ADR), Seções 15-17 (padrão de funções `SECURITY DEFINER` e idempotência já aprovado para claims), Seção 18 (divisão em subetapas B3.1-B3.4).
- `docs/implementation/ROADMAP-SPRINTS-B-G.md` — entrega de "log de eventos imutável e projeção corrente para lotes, registros de coleta e correções" (Sprint B).
- `PROJECT_STATUS.md` — histórico de conclusão das Subetapas B3.1-B3.4.
- `scripts/postgres_local/provisionar_b3_roles.sql` — precedente de provisionamento administrativo seguro, reaproveitado para `nsi_congelamento`.

---

## 20. Status Final e Congelamento (2026-09-16)

Com a arquitetura completa registrada nas Seções 1 a 19 — precedida por múltiplas rodadas de verificação somente leitura sobre reconstrução de estado, privacidade e menor privilégio, cada uma corrigindo a anterior, com aprovação explícita ao final — a ADR-009 é registrada como **APROVADA E CONGELADA**.

### O que o congelamento significa

- O modelo híbrido de eventos e estado corrente (Seção 5), o catálogo fechado de cinco eventos (Seção 6), a classificação de dados pessoais e o limite de neutralidade jurídica (Seção 7), o payload seguro de tentativa não resolvida (Seção 8), a localização e a natureza correlacionável do checksum e do `payload_hash` (Seção 9), as regras de identidade técnica (Seção 10), os papéis autorizados e a natureza administrativa de `nsi_congelamento` (Seção 11), e a idempotência determinística do congelamento (Seção 12) estão aprovados e estáveis.
- A arquitetura conceitual desta ADR está congelada. Mudanças futuras a qualquer decisão aqui congelada só poderão ocorrer por evolução arquitetural formalmente documentada — mesmo método já usado por todas as demais ADRs do projeto.
- As pendências registradas na Seção 16 não reabrem, não contradizem e não impedem este congelamento — são, por natureza, posteriores a ele.
- Nenhuma implementação de código, schema de banco de dados, migration, role ou configuração foi criada, modificada ou autorizada por este documento.
- A ADR-001, a ADR-005, a ADR-006, a ADR-007 e a ADR-008 permanecem intocadas por esta ADR — nenhuma de suas seções, decisões ou pendências foi alterada, referenciada como dependência normativa reversa ou reaberta.

**Origem desta decisão:**
- Consolidação aprovada do catálogo de eventos operacionais de lote, registro de coleta e correção para a Subetapa B4.1 (2026-09-16), após múltiplas rodadas de verificação somente leitura e aprovação explícita de cada correção.
