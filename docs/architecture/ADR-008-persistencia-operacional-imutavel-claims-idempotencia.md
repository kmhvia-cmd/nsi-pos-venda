# ADR-008 — Persistência Operacional Imutável, Claims e Idempotência

## Metadados

| Campo | Valor |
|---|---|
| Status | APROVADA E CONGELADA |
| Data | 2026-09-07 |
| Versão de referência do sistema | `v1.1.0-fonte-unica-webhook-motor` |
| Commit de referência | `8d0b2b1` |
| Branch | `master` |
| Escopo desta ADR | Arquitetura — nenhuma implementação de código, schema de banco de dados ou migration |

> **Nota de processo:** ADR aberta para cumprir a dependência técnica registrada na própria ADR-007 (§2.2 — "Fora do escopo desta decisão": *"Schema de banco de dados (...) para qualquer entidade desta ADR"*; §17 e §24 — idempotência persistente entre processos e workers, hoje resolvida apenas em memória de um único processo, limitação documentada literalmente em `adapters/storage.py::_obter_lock_lote`). Esta ADR não reabre, não redefine e não contradiz nenhuma decisão já congelada na ADR-007 — preenche exclusivamente os espaços que a própria ADR-007 declarou, por escrito, como fora de seu escopo. **Esta ADR foi revisada em quatro partes** (auditoria e distribuição documental; texto integral da ADR; texto integral do roadmap complementar das Sprints B–G; atualizações complementares), corrigida em múltiplas rodadas dentro de cada parte, aprovada explicitamente em cada uma delas, e está **APROVADA E CONGELADA** (Seção 25).

---

## 1. Objetivo

Registrar a arquitetura de persistência definitiva, do modelo de eventos imutáveis e do mecanismo de exclusão mútua entre processos e workers (claim) para o domínio operacional já delimitado pela ADR-007 — o ciclo entre o upload do CSV (M0) e a confirmação humana do primeiro disparo (T0 da Coleta), e o processamento subsequente do disparo.

Esta ADR define, antes de qualquer código: qual tecnologia de persistência definitiva é aprovada para este domínio, e com que escopo; o que é um evento imutável e o que é uma projeção corrente derivada dele; o que é um claim, sua granularidade e seu token de posse; os tempos operacionais aprovados de validade e renovação; os estados possíveis da projeção de um claim, distintos dos eventos imutáveis que os originam; a proibição de reatribuição automática; a exigência de transação e de idempotência persistente; e a estratégia de migração dos dados hoje existentes em JSON, com a preservação desses arquivos legados.

Esta ADR não implementa nada. Ela define o que deve ser verdade antes que qualquer registro de coleta seja processado por mais de um worker ao mesmo tempo, e antes que qualquer dado hoje em `lote.json` seja migrado para a persistência definitiva.

---

## 2. Escopo

### 2.1 Escopo desta decisão

- Aprovação de PostgreSQL como persistência definitiva do domínio operacional da ADR-007, com escopo estritamente delimitado (Seção 5).
- Definição de evento imutável e de projeção corrente como conceitos arquiteturais distintos (Seção 6).
- Definição do claim ("Reserva de Processamento"), sua granularidade por `registro_coleta_id` e seu token de posse (Seções 7-8).
- Tempos operacionais aprovados de validade inicial, intervalo de heartbeat e renovação, e a regra de que não podem ser alterados informalmente (Seção 9).
- Estados possíveis da projeção corrente de um claim, distintos do catálogo fechado de eventos imutáveis que os produzem (Seções 10-12).
- Regra de expiração, revisão de abandono e proibição de reatribuição automática (Seção 13).
- Fronteira explícita entre este mecanismo técnico e o `numero_tentativa` já regido pela ADR-007 (Seção 14).
- Exigência de transação e de idempotência persistente entre processos e workers (Seção 15).
- Estratégia de migração por corte controlado dos dados hoje existentes (Seção 16).
- Regra de preservação dos JSONs legados após a migração (Seção 17).
- Fronteira formal entre esta sprint (B) e as sprints subsequentes (C–G) (Seção 18).

### 2.2 Fora do escopo desta decisão

- Schema relacional concreto: tabelas, colunas, tipos de dado, índices, constraints, chaves estrangeiras, particionamento.
- Driver de banco de dados, versão, pool de conexões, ORM ou uso de SQL puro.
- Ferramenta e scripts concretos de migration; formato exato de manifesto e algoritmo de checksum dos JSONs legados.
- Infraestrutura de hospedagem do banco de dados.
- Nomes de módulos, funções ou assinaturas concretas de código Python.
- Mecanismo técnico concreto de renovação de heartbeat (thread, scheduler, cron, worker dedicado).
- Qualquer integração com a Meta/WhatsApp Cloud API: envio efetivo, `wamid`, eventos dependentes de resposta da Meta, processamento de status de webhook.
- Rotas HTTP, autenticação e MFA do Operador Interno, telas de relatório ou correção.
- Correlação determinística entre registro de coleta, envio, resposta e produto; quarentena; entrada no Motor NSI.
- Mapeamento de códigos de erro da Meta e regras finais de intervalo entre tentativas.
- Qualquer alteração à ADR-007, à ADR-001, à ADR-005 ou à ADR-006 — nenhuma delas é reaberta, redefinida ou contradita por esta ADR.

---

## 3. Contexto

A ADR-007 (APROVADA E CONGELADA) definiu a arquitetura conceitual completa do ciclo de preparação e disparo da coleta, mas declarou explicitamente, em seu próprio texto, que a persistência técnica desse domínio permanecia fora de seu escopo (§2.2) e que a idempotência do processamento de disparo entre processos e workers distintos — já um princípio arquitetural congelado (Princípio 10) — carecia de um mecanismo técnico concreto, apontando nominalmente a limitação hoje existente no código:

> "Essa idempotência funciona entre processos e workers distintos — não apenas em memória de um único processo, resolvendo a limitação hoje documentada no próprio código (`adapters/storage.py::_obter_lock_lote`: *"Não protege contra múltiplos processos/workers"*)." (ADR-007, §17)

Essa mesma limitação está registrada como pendência técnica não bloqueante ao congelamento conceitual da ADR-007, mas bloqueante à sua operação em ambiente com múltiplos workers (ADR-007, §24).

Paralelamente, o `PROJECT_STATUS.md` já registrava, de forma informal e sem decisão arquitetural própria, que "Persistência definitiva (PostgreSQL) permanece para a Sprint B". Esta ADR formaliza essa menção, sem se apoiar nela como fonte de autoridade — a autoridade desta decisão é o texto desta própria ADR.

A ADR-006 já aprovou PostgreSQL como armazenamento definitivo para outro domínio do sistema — os registros da Trajetória Contínua (Jornada de Transformação Organizacional, Tela 03) —, com escopo que a própria ADR-006 delimita como estrito:

> "Esta decisão é estritamente escopada aos registros da Trajetória Contínua (...). Ela não decide, amplia ou sugere que a empresa, a Operação, o usuário, o resultado semântico candidato do Motor NSI (...) já sejam ou venham a ser armazenados em PostgreSQL — cada uma dessas entidades depende de decisão arquitetural própria, ainda não tomada." (ADR-006, §18)

Essa decisão da ADR-006 funciona, para esta ADR, exclusivamente como precedente de redação, de tecnologia e de política de idempotência — nunca como extensão automática. Esta ADR toma sua própria decisão, para seu próprio domínio, sem depender normativamente da ADR-006.

---

## 4. Princípios Arquiteturais da Persistência Operacional

### Princípio 1 — Persistência Definitiva Escopada

PostgreSQL é aprovado como persistência definitiva exclusivamente para o domínio operacional já delimitado pela ADR-007. Esta decisão não decide, amplia ou sugere persistência definitiva para nenhum outro domínio do sistema.

### Princípio 2 — Evento Imutável como Fonte de Verdade

Todo fato ocorrido no processamento de um registro de coleta é registrado como um evento imutável, nunca alterado ou removido após gravado. O estado atual de um claim é sempre uma projeção derivada da sequência de eventos — nunca a própria fonte de verdade.

### Princípio 3 — Claim Individual por Registro de Coleta

A exclusão mútua entre workers opera na granularidade do registro de coleta — nunca do lote inteiro, nunca do telefone — consistente com a granularidade já congelada pela ADR-007 (Princípio 12; §19) para as tentativas de disparo.

### Princípio 4 — Heartbeat como Prova de Atividade, Nunca de Resultado

Um heartbeat prova exclusivamente que o worker detentor de um claim segue ativo. Não prova, sugere ou implica sucesso, falha, disparo ou qualquer resultado de negócio.

### Princípio 5 — Tempos Operacionais como Decisão Aprovada, Não como Configuração Livre

Os tempos operacionais de validade e renovação do claim (Seção 9) são um padrão aprovado por decisão arquitetural — nunca um valor de configuração ajustável silenciosamente por variável de ambiente, arquivo de configuração ou parâmetro de execução.

### Princípio 6 — Não Reatribuição Automática

Um claim expirado nunca é reatribuído automaticamente. A criação de um novo claim para o mesmo registro de coleta, após um claim anterior expirar, exige revisão explícita, registrada como evento imutável, e só ocorre por essa via — nunca por decisão silenciosa do sistema. A reatribuição é sempre um evento que dá origem a um novo claim no estado `ativo`; não é, em si, um estado da projeção corrente.

### Princípio 7 — Neutralidade do Mecanismo de Claim em Relação à Decisão de Negócio

Claim, heartbeat, expiração e reatribuição são mecanismos técnicos de exclusão mútua e continuidade de processamento. Nenhum deles autoriza disparo, nova tentativa, ou qualquer decisão que a ADR-007 já reserva à confirmação humana do Operador Interno (ADR-007, §16, §19) — reafirmando, sem exceção, o Capítulo 5 do Livro dos Princípios ("A tecnologia serve; não decide").

### Princípio 8 — Idempotência Persistente entre Processos e Workers

A garantia de idempotência do processamento de disparo, já congelada pela ADR-007 (Princípio 10), passa a ser garantida pela persistência definitiva desta ADR — sobrevivendo a reinício de processo e valendo entre workers distintos, nunca apenas em memória de um único processo.

### Princípio 9 — Migração por Corte Controlado

A transição do armazenamento provisório em JSON para a persistência definitiva ocorre por um corte controlado e único — nunca por escrita dupla permanente entre os dois formatos.

### Princípio 10 — Preservação de Legado sem Prazo Presumido

Os arquivos JSON que hoje constituem o armazenamento provisório são preservados integralmente após a migração, sem que esta ADR presuma, defina ou insinue qualquer prazo de retenção ou de eliminação.

---

## 5. Armazenamento Definitivo — Escopo Estritamente Limitado ao Domínio Operacional da ADR-007

- PostgreSQL é o armazenamento arquitetural definitivo dos dados do domínio operacional já delimitado pela ADR-007: registros de coleta, suas versões de correção (ADR-007, §9), eventos de claim e heartbeat (Seções 6-12 desta ADR), e as chaves de idempotência do processamento de disparo (ADR-007, §17) — não haverá solução provisória oficial em JSON para esses dados após a conclusão da migração desta sprint.
- Esta decisão é estritamente escopada ao domínio operacional da ADR-007. Ela **não** decide, amplia ou sugere que qualquer outro domínio do sistema — incluindo, sem se limitar a, `saida_motor.json`, os candidatos do Motor NSI, ou qualquer entidade cuja persistência dependa de decisão arquitetural própria ainda não tomada — passe a ser armazenado em PostgreSQL por força desta ADR.
- Esta decisão também não altera, amplia ou reduz o escopo já aprovado pela ADR-006 §18 para os registros da Trajetória Contínua — os dois domínios permanecem arquiteturalmente distintos e independentes, ainda que compartilhem a mesma tecnologia de persistência por decisão própria de cada ADR.
- O schema relacional concreto (tabelas, colunas, chaves, constraints, índices) que implementará este armazenamento não é definido nesta ADR — permanece para especificação técnica (Seção 19).

---

## 6. Evento Imutável e Projeção Corrente — Definições Gerais

- **Evento imutável ("Evento Permanente"):** um fato ocorrido, registrado uma única vez, com identificador, tipo e timestamp próprios, nunca alterado nem removido após gravado pela aplicação comum (Seção 15).
- **Projeção corrente ("Estado Atual"):** o estado presente de uma entidade — nesta ADR, especificamente, o estado de um claim —, inteiramente derivado da sequência de eventos imutáveis já ocorridos. A projeção pode ser recalculada a qualquer momento a partir do log de eventos; o log de eventos que a origina nunca é reescrito.
- Um evento e uma mudança de estado da projeção não são a mesma coisa: nem todo evento imutável produz uma mudança de estado (Seção 12 trata explicitamente o caso do heartbeat, que gera evento sem mudar o estado).

---

## 7. Claim ("Reserva de Processamento") — Definição e Granularidade

- Claim ("Reserva de Processamento") é a posse temporária e exclusiva de um único `registro_coleta_id`, atribuída a um worker, para que esse worker processe aquele registro sem que outro worker o processe simultaneamente.
- A granularidade do claim é individual, por `registro_coleta_id` — nunca por telefone, nunca pelo lote inteiro. Esta granularidade é consistente com, e reforça, a mesma unidade já congelada pela ADR-007 para as tentativas de disparo (Princípio 12; §19: "cada registro de coleta — não cada telefone").
- Um `registro_coleta_id` só pode ter um claim ativo por vez. Uma tentativa de criar um novo claim para um registro que já possui claim ativo falha explicitamente — nunca substitui silenciosamente o claim existente.

---

## 8. Token de Posse

- Todo claim criado recebe um token de posse: um identificador técnico próprio, opaco e único, atribuído no momento da criação do claim.
- Somente quem detém o token de posse correspondente pode renovar (heartbeat) ou liberar o claim ao qual ele pertence.
- Uma operação de renovação ou liberação apresentada sem o token correto, ou com um token que não corresponde ao claim ativo daquele registro, é recusada.

---

## 9. Tempos Operacionais Aprovados

Os seguintes valores constituem o **padrão operacional inicial aprovado** por esta ADR:

- **Validade inicial do claim:** 5 (cinco) minutos, a partir da criação.
- **Intervalo de heartbeat:** 60 (sessenta) segundos.
- **Renovação por heartbeat válido:** estende a validade do claim por mais 5 (cinco) minutos a partir do momento da renovação.

Estes valores são uma decisão arquitetural, não um parâmetro de configuração operacional. Não podem ser alterados por variável de ambiente, arquivo de configuração, parâmetro de execução ou qualquer outro mecanismo que produza uma mudança silenciosa em produção. Qualquer alteração futura a estes valores exige evolução arquitetural formalmente documentada, no mesmo método já usado por esta e por todas as demais ADRs do projeto — nunca um ajuste de configuração.

---

## 10. Estados da Projeção Corrente do Claim

A projeção corrente de um claim admite exatamente os seguintes estados, e nenhum outro:

- **`ativo`** ("Em Processamento"): claim válido, com token de posse válido e dentro do prazo de validade corrente (Seção 9). Um claim chega a este estado de duas formas: pela criação original (evento `claim_criado`) ou pela reatribuição de um claim anterior expirado (evento `claim_reatribuido`, Seção 13). Em ambos os casos, o estado resultante é o mesmo: `ativo`. Um heartbeat válido **não** produz um novo estado — o claim permanece `ativo` (Seção 12).
- **`liberado`** ("Processamento Liberado"): o próprio detentor do token de posse encerrou o claim antes de sua expiração.
- **`expirado_pendente_revisao`** ("Interrompido — Aguardando Revisão"): a validade do claim se esgotou sem renovação por heartbeat válido. Este estado não significa sucesso nem falha do processamento (Seção 13).

**Não existe um estado `reatribuido`.** A reatribuição é exclusivamente um evento imutável (`claim_reatribuido`, Seção 11) — seu efeito é a criação de um novo claim, cuja projeção corrente nasce diretamente em `ativo`. O histórico de eventos permite, a qualquer momento, reconstruir que um claim `ativo` específico se originou de uma reatribuição, e a partir de qual claim anterior — sem que isso exija ou justifique um quarto estado de projeção.

Também não existe um estado "renovado" — a renovação por heartbeat é igualmente um evento (Seção 12), não um estado.

A projeção corrente de um claim admite, portanto, **três estados**: `ativo`, `liberado`, `expirado_pendente_revisao`.

---

## 11. Eventos Imutáveis do Claim

**O catálogo abaixo é fechado exclusivamente para os eventos do ciclo de vida de claims definidos por esta ADR.** Ele não é o catálogo geral de eventos imutáveis do sistema NSI: eventos de outros domínios — envio, aceitação pela API, status de webhook, resposta, quarentena, execução do Motor NSI — não pertencem a este catálogo. Esses eventos futuros serão definidos pelas decisões arquiteturais próprias das Sprints C, E e G, reaproveitando o modelo geral de evento imutável e projeção corrente já fixado na Seção 6, sem que esta ADR antecipe seus campos, seu significado ou sua nomenclatura.

Os seis eventos do ciclo de vida de um claim são:

- **`claim_criado`**: registrado no momento em que um claim é criado para um `registro_coleta_id`, contendo o `registro_coleta_id`, o token de posse, o worker solicitante e o timestamp de criação.
- **`heartbeat_registrado`**: registrado a cada renovação válida (Seção 12), contendo o token de posse apresentado, o timestamp do heartbeat e a nova validade calculada.
- **`claim_liberado`**: registrado quando o detentor do token de posse libera o claim antes da expiração.
- **`claim_expirado`**: registrado quando a validade do claim se esgota sem renovação — este evento, por si só, não classifica o processamento como bem-sucedido ou malsucedido (Seção 13).
- **`revisao_de_abandono_registrada`**: registrado quando um claim em `expirado_pendente_revisao` é formalmente revisado, com o resultado dessa revisão e quem a realizou — inclusive quando a revisão conclui por *não* reatribuir.
- **`claim_reatribuido`**: registrado exclusivamente quando uma revisão de abandono autoriza explicitamente a retomada. Este evento sempre acompanha, na mesma operação, a criação de um novo claim com novo token de posse, cuja projeção corrente nasce em `ativo` (Seção 10) — `claim_reatribuido` é o evento; `ativo` é o estado do novo claim resultante. O evento referencia o claim anterior e o `registro_coleta_id` comum, preservando no histórico a rastreabilidade de que aquele claim ativo se origina de uma reatribuição.

Nenhum evento fora deste catálogo fechado de seis é definido por esta ADR para o ciclo de vida de claims. **A introdução de um novo tipo de evento de claim exige evolução arquitetural formal desta ADR-008.** Isso não impede — e esta ADR reconhece explicitamente — que as Sprints C–G definam, em suas próprias decisões arquiteturais, outros eventos imutáveis para seus próprios domínios (por exemplo, eventos de envio ou de resposta da Meta), sustentados pelo mesmo modelo geral de evento imutável e projeção corrente aqui estabelecido (Seção 6), sem que este catálogo os restrinja, defina ou antecipe.

---

## 12. Heartbeat ("Sinal de Atividade") — Evento, Nunca Estado

- O heartbeat é a renovação periódica de um claim ativo pelo worker que o detém, comprovando que esse worker segue ativo e trabalhando naquele registro de coleta.
- Um heartbeat válido produz exatamente um evento imutável `heartbeat_registrado` (Seção 11) e atualiza dois campos da projeção corrente do claim: `ultimo_heartbeat_em` e `expira_em` (recalculado conforme os tempos aprovados na Seção 9).
- Um heartbeat válido **nunca** produz uma mudança de estado da projeção — o claim permanece `ativo` antes e depois de cada heartbeat.
- O evento `heartbeat_registrado` anterior nunca é alterado, substituído ou removido pelo heartbeat seguinte — cada renovação é um novo evento, acrescentado ao log, nunca uma correção do evento anterior.
- Um heartbeat só é aceito quando acompanhado do token de posse correto do claim ativo correspondente (Seção 8).
- O heartbeat, por si só, nunca comprova sucesso do processamento, nunca comprova envio, nunca comprova qualquer resultado de negócio — comprova exclusivamente que o worker detentor segue ativo (Princípio 4).

---

## 13. Expiração, Revisão de Abandono e Proibição de Reatribuição Automática

- Quando a validade de um claim se esgota sem heartbeat válido, é registrado o evento imutável `claim_expirado`, e a projeção corrente desse claim passa ao estado `expirado_pendente_revisao`.
- A expiração de um claim **não significa**, por si só, sucesso do processamento, nem significa falha do processamento — é, estritamente, a ausência de prova de que o processamento continuou.
- Nenhum claim em `expirado_pendente_revisao` é automaticamente reatribuído a qualquer worker, incluindo o próprio worker original.
- A retomada do processamento de um registro de coleta cujo claim está em `expirado_pendente_revisao` exige, obrigatoriamente:
  1. uma revisão explícita, registrada como o evento imutável `revisao_de_abandono_registrada`;
  2. somente se essa revisão autorizar a retomada: o registro do evento imutável `claim_reatribuido` e, na mesma operação, a criação de um novo claim, com um **novo** token de posse (Seção 8), para o mesmo `registro_coleta_id`.
- A projeção corrente desse novo claim é `ativo` — **não existe um estado `reatribuido`** (Seção 10). O que fica registrado como reatribuição é o evento `claim_reatribuido`; o estado do claim resultante é `ativo`, indistinguível estruturalmente de qualquer outro claim ativo, exceto pela sua origem, reconstruível a partir do histórico de eventos.
- Uma revisão de abandono pode concluir por **não** reatribuir — nesse caso, apenas o evento `revisao_de_abandono_registrada` é gravado, e o claim permanece em `expirado_pendente_revisao`, sem gerar `claim_reatribuido` nem novo claim.
- A reatribuição, como qualquer evento desta ADR, nunca autoriza disparo e nunca altera `numero_tentativa` (Seção 14).
- O mecanismo técnico concreto e o papel responsável por realizar essa revisão permanecem para especificação técnica (Seção 19) — esta ADR fixa apenas a obrigação de que a revisão exista e seja explícita, nunca automática.

---

## 14. Relação entre Claim/Heartbeat e `numero_tentativa` — Fronteira com a ADR-007

- O `numero_tentativa` de um registro de coleta é um conceito de negócio já definido e regido integralmente pela ADR-007 (Princípio 12; §19): cada nova tentativa exige confirmação explícita do Operador Interno, dentro dos limites e intervalos ali já congelados. Esta ADR não redefine, não substitui e não altera essa regra.
- Claim, heartbeat, expiração e reatribuição são mecanismos técnicos de exclusão mútua e continuidade de processamento entre workers — nunca mecanismos de decisão de negócio.
- Por isso, de forma explícita e sem exceção: a criação de um claim nunca autoriza um disparo; um heartbeat nunca comprova sucesso de um disparo; a expiração de um claim nunca conta como uma tentativa nem como uma falha; e a reatribuição de um claim nunca gera, por si só, uma nova tentativa.
- `numero_tentativa` só avança por confirmação humana explícita do Operador Interno, exatamente como já exigido pela ADR-007 — nenhuma sequência de eventos de claim, isoladamente, jamais o altera.

---

## 15. Transações e Idempotência Persistente

- A criação de um claim ("se não existe outro claim ativo para este `registro_coleta_id`, crie; senão, recuse") é uma operação que deve ser atômica na camada de persistência — nunca resolvida apenas em memória de aplicação.
- A gravação de um evento imutável e a atualização correspondente da projeção corrente ocorrem dentro do mesmo limite transacional, sempre que a tecnologia de persistência escolhida oferecer transação — para nunca deixar o log de eventos e a projeção divergentes após uma falha no meio da escrita.
- **Nenhum fluxo comum ou excepcional do NSI executa UPDATE ou DELETE sobre um evento imutável já gravado.** Esta regra não admite exceção operacional de nenhuma natureza.
- Uma eventual correção a um fato já registrado gera um novo evento, compensatório ou de retificação, vinculado ao evento original — nunca a edição ou a remoção do evento original, que permanece intacto e íntegro. Esta ADR fixa apenas o princípio append-only acima e **não cria, nesta etapa, nenhum evento de retificação para o ciclo de vida de claims**. Como o catálogo de eventos de claim (Seção 11) é fechado, a criação futura de um novo tipo de evento pertencente a esse ciclo de vida — incluindo um eventual evento de retificação — exige, obrigatoriamente, evolução arquitetural formal desta ADR-008; **a especificação técnica (Seção 19) não tem autoridade para ampliar, sozinha, esse catálogo fechado.**
- Obrigações jurídicas futuras de eliminação ou anonimização de dados (ex.: direito ao esquecimento, ordem judicial) serão tratadas por uma política jurídica própria, ainda não criada. Esta ADR não a antecipa, não a desenha e, em particular, **não constitui autorização operacional para editar ou remover eventos imutáveis** — qualquer mecanismo de exceção legal, quando existir, será definido exclusivamente por aquela política futura.
- A garantia de idempotência entre processos e workers, já exigida pela ADR-007 (Princípio 10; §17), passa a ser garantida por esta persistência definitiva — uma operação repetida é verificada contra o armazenamento definitivo antes de agir, nunca contra estado em memória de um único processo.
- O mecanismo técnico concreto de transação (isolamento, locking otimista ou pessimista, constraints de unicidade) permanece para especificação técnica (Seção 19).

---

## 16. Migração — Corte Controlado

A transição do armazenamento provisório em JSON para a persistência definitiva desta ADR segue, obrigatoriamente, a sequência abaixo, por corte controlado — nunca por escrita dupla permanente entre os dois formatos:

1. **Pausa temporária de escritas** no armazenamento provisório em JSON.
2. **Backup integral** dos dados existentes, previamente à migração.
3. **Importação** dos dados para a persistência definitiva.
4. **Validação** da importação, confirmando integridade e completude antes de qualquer uso operacional da nova persistência.
5. **Mudança da fonte de verdade** para a persistência definitiva, somente após a aprovação explícita da validação do passo anterior.

**Cancelamento do corte:** se a importação (passo 3) ou a validação (passo 4) falhar, o corte é cancelado integralmente. O sistema continua operando com os JSONs originais como fonte de verdade, exatamente como antes da tentativa de migração — nenhuma mudança de fonte de verdade ocorre sem validação aprovada.

**Após a mudança da fonte de verdade (passo 5):** a persistência definitiva passa a ser a única fonte de verdade operacional, recebendo novos eventos. A partir desse momento, os JSONs congelados ficam necessariamente defasados frente a qualquer evento novo — seu tratamento posterior é regido integralmente pela Seção 17.

Nenhum passo desta sequência pode ser omitido ou reordenado. O mecanismo técnico concreto de cada passo (ferramenta de backup, formato de importação, critério exato de validação) permanece para especificação técnica (Seção 19).

---

## 17. Preservação dos JSONs Legados

- Após a conclusão da migração (Seção 16), os arquivos JSON que constituíam o armazenamento provisório são: congelados; tornados somente leitura; fisicamente separados do armazenamento operacional corrente; e acompanhados por um manifesto e por checksums que comprovem sua integridade.
- Esta ADR não define, presume ou insinua nenhum prazo de exclusão para esses arquivos. Eles permanecem preservados sem prazo definido por esta sprint.
- A eventual retenção definitiva ou eliminação futura desses arquivos depende de uma Política Jurídica futura e de evolução arquitetural formal — no mesmo padrão já adotado pela ADR-006 (§21) para o destino dos registros originais da Trajetória Contínua após o encerramento da relação com uma empresa.
- **Limite do uso dos JSONs congelados após o corte:** uma vez que a persistência definitiva se torna fonte de verdade e passa a receber novos eventos (Seção 16), os JSONs congelados ficam defasados em relação a qualquer evento posterior ao corte. **Eles não podem, isoladamente, voltar a ser fonte operacional** — servem exclusivamente como auditoria e como prova do estado do sistema no momento da migração.
- Uma eventual necessidade de recuperação posterior ao corte deve ser resolvida por backup e restauração da própria persistência definitiva (PostgreSQL), combinada com os eventos gravados após o corte — **nunca pelo retorno isolado aos JSONs congelados**. Qualquer rollback realizado após o corte precisa preservar integralmente todos os eventos gravados desde então, sem regressão nem perda de dado.

---

## 18. Fronteira Sprint B / Sprints C–G

Esta ADR rege exclusivamente a fundação de persistência, eventos, claims e idempotência da Sprint B. Ficam explicitamente fora, e pertencem a sprints futuras e a decisões humanas próprias, ainda não tomadas por esta ADR:

- Envio efetivo pelo WhatsApp, captura e persistência de `wamid`, eventos dependentes de resposta da Meta, processamento de status de webhook (Sprint C).
- Autenticação e MFA do Operador Interno, rotas HTTP, telas de relatório e correção, confirmação humana em dois atos na interface (Sprint D — os princípios de confirmação humana em si já estão congelados pela ADR-007, §16; esta ADR não os implementa).
- Correlação determinística entre registro de coleta, envio, resposta e produto; quarentena de resposta sem vínculo; entrada no Motor NSI (Sprint E).
- Teste controlado da Meta, payload íntegro temporário criptografado, retenção curta e eliminação auditada (Sprint F).
- Mapeamento oficial dos códigos de erro da Meta e regras finais de intervalo entre tentativas (Sprint G).

O mecanismo de claim, heartbeat e evento imutável definido nesta ADR é inteiramente agnóstico de Meta, WhatsApp, `wamid` ou webhook — não guarda "o que a Meta respondeu", guarda exclusivamente "quem está processando qual registro de coleta, e desde quando".

---

## 19. O que Permanece para Especificação Técnica

Fora desta ADR, a resolver em especificação técnica futura, sem necessidade de nova ADR salvo se a decisão envolver novo princípio arquitetural:

- Schema relacional concreto (tabelas, colunas, tipos, índices, constraints, chaves estrangeiras, particionamento).
- Driver de banco de dados e sua versão; uso de ORM ou SQL puro; estratégia de pool de conexões.
- Ferramenta e scripts concretos de migration; formato exato de manifesto e algoritmo de checksum dos JSONs legados (Seção 17).
- Infraestrutura de hospedagem do banco de dados.
- Nomes de módulos, funções e assinaturas concretas de código Python.
- Mecanismo técnico concreto de renovação de heartbeat (thread, scheduler, cron, worker dedicado).
- Papel ou mecanismo técnico responsável por realizar a revisão de abandono (Seção 13).
- Mecanismo técnico concreto de transação e de locking (Seção 15).

---

## 20. Decisões Aprovadas e Congeladas

As decisões a seguir constituem a arquitetura aprovada e congelada desta ADR:

1. PostgreSQL como persistência definitiva, exclusivamente para o domínio operacional da ADR-007, sem extensão automática a outros domínios (Princípio 1; Seção 5).
2. Evento imutável como fonte de verdade; projeção corrente como estado derivado, nunca fonte de verdade (Princípio 2; Seção 6).
3. Claim individual por `registro_coleta_id`, nunca por telefone nem por lote (Princípio 3; Seção 7).
4. Token de posse como condição exclusiva para renovar ou liberar um claim (Seção 8).
5. Tempos operacionais aprovados — 5 minutos de validade inicial, heartbeat a cada 60 segundos, renovação por mais 5 minutos — como decisão arquitetural, nunca como configuração ajustável informalmente (Princípio 5; Seção 9).
6. Três estados possíveis da projeção corrente de um claim — `ativo`, `liberado`, `expirado_pendente_revisao` — sem um estado "renovado" e sem um estado "reatribuido" (Seção 10).
7. Catálogo fechado exclusivamente para os seis eventos do ciclo de vida de claims desta ADR (Seção 11) — não restringe a criação, por decisões arquiteturais próprias das Sprints C–G, de eventos imutáveis de outros domínios, sob o mesmo modelo geral de evento imutável (Seção 6).
8. Heartbeat como evento imutável (`heartbeat_registrado`), nunca como estado da projeção; nunca prova de sucesso, envio ou qualquer resultado de negócio (Princípio 4; Seção 12).
9. Proibição de reatribuição automática de um claim expirado, sob qualquer circunstância (Princípio 6; Seção 13).
10. Exigência de revisão explícita de abandono para qualquer claim em `expirado_pendente_revisao`, sempre registrada como evento imutável (`revisao_de_abandono_registrada`), inclusive quando a revisão conclui por não reatribuir (Seção 13).
11. `claim_reatribuido` como evento imutável — nunca como estado — que, quando a revisão autoriza a retomada, cria um novo claim com novo token de posse, cuja projeção corrente nasce em `ativo` (Seções 10 e 13).
12. Neutralidade absoluta de claim, heartbeat, expiração e reatribuição em relação a disparo e a `numero_tentativa`: nenhum deles autoriza disparo, comprova sucesso ou altera `numero_tentativa`, que permanece regido exclusivamente pela confirmação humana já exigida pela ADR-007 (Princípio 7; Seção 14).
13. Exigência de transação atômica para criação de claim e para a gravação conjunta de evento e projeção; exigência de idempotência persistente entre processos e workers, sobrevivendo a reinício de processo (Princípio 8; Seção 15).
14. Imutabilidade sem exceção: nenhum fluxo comum ou excepcional executa UPDATE ou DELETE sobre evento imutável; correção futura, se necessária, gera novo evento vinculado ao original, que permanece intacto; esta ADR não cria evento de retificação de claim, e qualquer novo tipo de evento do ciclo de vida de claims exige evolução formal da ADR-008 — a especificação técnica não amplia o catálogo fechado sozinha; obrigações jurídicas futuras de eliminação/anonimização não constituem autorização operacional para editar eventos (Seção 15).
15. Migração por corte controlado, sem escrita dupla permanente; falha de importação ou validação cancela o corte e mantém os JSONs como fonte operacional (Princípio 9; Seção 16).
16. Limite do rollback: após a mudança da fonte de verdade, qualquer rollback exige restauração da persistência definitiva preservando todos os eventos posteriores ao corte — nunca reversão isolada para os JSONs congelados (Seções 16 e 17).
17. Preservação dos JSONs legados sem prazo de exclusão presumido por esta sprint, servindo como auditoria e prova da migração, dependente de Política Jurídica futura para retenção ou eliminação definitiva (Princípio 10; Seção 17).
18. Fronteira formal entre a Sprint B e as Sprints C–G, com o mecanismo de claim/heartbeat/evento inteiramente agnóstico de Meta, WhatsApp, `wamid` ou webhook (Seção 18).

---

## 21. Pendências Técnicas Não Bloqueantes

Nenhuma das pendências abaixo é lacuna conceitual desta ADR — são exclusivamente pendências de especificação técnica futura (Seção 19), no mesmo padrão já usado pela ADR-006 e pela ADR-007:

- Schema relacional concreto.
- Driver, ORM e infraestrutura de conexão.
- Ferramenta de migration e formato de manifesto/checksum dos JSONs legados.
- Mecanismo técnico concreto de heartbeat e de revisão de abandono.
- Destino final dos JSONs legados, dependente de Política Jurídica futura (Seção 17).

---

## 22. Dependências

- Depende da ADR-001 (Princípio 1 — Registro Permanente; §7 — Operação como unidade de exposição, `lote_id` como componente técnico interno).
- Depende da ADR-007 (§2.2 — exclusão de schema de banco de dados do seu escopo; Princípio 6 e §9 — correção append-only; Princípio 10 e §17 — idempotência entre processos e workers; Princípio 12 e §19 — granularidade por registro de coleta; §16 — confirmação humana em dois atos; §24 — pendências técnicas não bloqueantes) — esta ADR não redefine nenhuma dessas regras, apenas fornece a fundação técnica que a ADR-007 já previu como pendência.
- Depende da ADR-006 (§18), exclusivamente como precedente de redação, tecnologia e política de idempotência — nunca como autorização automática (Seção 5).
- Depende do Livro dos Princípios do NSI, Capítulo 5 ("A tecnologia serve; não decide"), para a fronteira entre mecanismo técnico e decisão de negócio (Princípio 7; Seção 14).

---

## 23. Itens Fora do Escopo

Ver Seção 2.2.

---

## 24. Referências

- `docs/architecture/ADR-001-operations-console.md` — Princípio 1 (Registro Permanente); Seção 7.
- `docs/architecture/ADR-006-jornada-de-transformacao-organizacional.md` — Seção 18 (Armazenamento definitivo, escopo estritamente limitado; política de idempotência).
- `docs/architecture/ADR-007-ciclo-operacional-preparacao-disparo-coleta.md` — Seções 2.2, 9, 12, 16, 17, 19, 24.
- `docs/principios/livro-dos-principios.md` — Capítulo 5 ("A tecnologia serve; não decide").
- `PROJECT_STATUS.md` — origem da nota informal formalizada por esta ADR.
- `docs/implementation/ROADMAP-SPRINTS-B-G.md` — sequenciamento de implementação das Sprints B a G, subordinado a esta ADR e à ADR-007.

---

## 25. Status Final e Congelamento (2026-09-07)

Com a arquitetura completa registrada nas Seções 1 a 24, revisada em quatro partes — auditoria e distribuição documental; texto integral da ADR; texto integral do roadmap complementar (`ROADMAP-SPRINTS-B-G.md`); atualizações complementares — e corrigida em múltiplas rodadas dentro de cada parte, com aprovação explícita em cada uma delas, a ADR-008 é registrada diretamente como **APROVADA E CONGELADA**.

### O que o congelamento significa

- Os princípios arquiteturais (Seção 4), o armazenamento definitivo escopado (Seção 5), o modelo de evento imutável e projeção corrente (Seção 6), o claim e sua granularidade (Seção 7), o token de posse (Seção 8), os tempos operacionais aprovados (Seção 9), os três estados da projeção (Seção 10), o catálogo fechado de seis eventos de claim (Seção 11), o heartbeat como evento (Seção 12), a expiração e a revisão de abandono (Seção 13), a fronteira com `numero_tentativa` (Seção 14), as transações e a idempotência persistente, incluindo a imutabilidade sem exceção (Seção 15), a migração por corte controlado (Seção 16), a preservação dos JSONs legados (Seção 17), e a fronteira Sprint B / Sprints C–G (Seção 18) estão aprovados e estáveis.
- A arquitetura conceitual desta ADR está congelada. Mudanças futuras a qualquer decisão aqui congelada só poderão ocorrer por evolução arquitetural formalmente documentada — no mesmo método já usado por esta e por todas as demais ADRs do projeto: preservação do texto histórico, registro explícito do que muda e do que não muda, e aprovação própria.
- As pendências registradas na Seção 21 não reabrem, não contradizem e não impedem este congelamento — são, por natureza, posteriores a ele: dizem respeito a como a arquitetura aqui aprovada será implementada, nunca ao que ela decide.
- Nenhuma implementação de código, schema de banco de dados, migration, endpoint ou configuração foi criada, modificada ou autorizada por este documento.
- A ADR-001, a ADR-005, a ADR-006 e a ADR-007 permanecem intocadas por esta ADR — nenhuma de suas seções, decisões ou pendências foi alterada, referenciada como dependência normativa reversa ou reaberta.

**Origem desta decisão:**
- Consolidação aprovada da fundação de persistência operacional imutável, claims e idempotência para o domínio da ADR-007 (2026-09-07), após revisão e aprovação explícita das quatro partes desta proposta.
