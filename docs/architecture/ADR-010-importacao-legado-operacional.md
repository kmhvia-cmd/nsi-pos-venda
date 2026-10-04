# ADR-010 — Importação do Legado Operacional em JSON

## Metadados

| Campo | Valor |
|---|---|
| Status | APROVADA E CONGELADA |
| Data | 2026-10-03 |
| Versão de referência do sistema | `v1.1.0-fonte-unica-webhook-motor` |
| Commit de referência | `ae1071b` |
| Branch | `master` |
| Escopo desta ADR | Arquitetura — nenhuma implementação de código, schema de banco de dados, migration, role ou configuração |

> **Nota de processo:** ADR aberta como Subetapa B5.1, para cumprir as dependências que a Especificação Técnica da Sprint B deixou registradas e que nenhuma decisão anterior satisfez. As Seções 10 ("Registros Legados Sem Identidade Técnica") e 11 ("Migração de Estado Sem Fabricar História") condicionam o nome da classificação legada e o tratamento do registro técnico de importação "à decisão da Seção 9". Essa decisão foi tomada pela ADR-009, que tratou exclusivamente dos cinco eventos do fluxo novo e não mencionou importação nem legado. A Seção 22, item 12, atribui à B5 o registro de lotes com M0 no passado, que `fn_registrar_lote` não atende. Esta ADR é a decisão que faltava. Ela não reabre, não redefine e não contradiz nenhuma decisão congelada na ADR-007, na ADR-008 ou na ADR-009. Sua única consequência sobre a ADR-009 é uma seção aditiva de formalização (Seção 11).

---

## 1. Objetivo

Definir como o conteúdo operacional hoje mantido em `lote.json` entra na persistência definitiva (ADR-008) **sem fabricar história, sem inventar identidade e sem perder nada**. A decisão cobre:

- o que é preservado;
- o que pode voltar a operar no sistema novo, e sob qual prova;
- o que nunca opera;
- quem executa a importação;
- como a importação é auditada, repetida e validada.

## 2. Escopo

### 2.1 Escopo desta decisão

- Natureza da importação: registro técnico, nunca evento de negócio (Seção 5).
- Classificação do legado por geração de formato (Seção 6) e o nome oficial das classificações (Seção 7).
- Os três destinos de um lote legado (Seção 8) e a natureza do snapshot legado (Seção 9).
- Critérios e efeitos da promoção (Seções 10 e 11), incluindo a não promoção das gerações anteriores à A2 (Seção 12).
- Política de interpretação de horários legados sem fuso (Seção 13).
- Status legados (Seção 14) e invariante de claim (Seção 15).
- Papel autorizado a importar (Seção 16).
- Idempotência, manifesto, paridade, escopo de arquivos, dados de entrada e ambiente (Seções 17 a 21).

### 2.2 Fora do escopo desta decisão

- Pausa de escritas, backup, troca da fonte de verdade e corte real, que são os passos 1, 2 e 5 da ADR-008, Seção 16, e pertencem à B7. O ensaio completo pertence à B6.
- Escolha da infraestrutura definitiva entre as opções A, B e C da Especificação, Seção 12, e os requisitos de backup da Seção 14.
- Domínios fora da ADR-008 (Seção 5): saída do Motor NSI, respostas e webhook (Sprints C e E), PDFs.
- Destino final dos JSONs legados, que depende de Política Jurídica futura (ADR-008, Seção 17).
- Política jurídica de retenção, anonimização ou expurgo dos dados pessoais preservados (ADR-009, Seção 7).
- Schema concreto, nomes de colunas, funções e módulos Python, que pertencem à especificação técnica (Seção 23).

---

## 3. Contexto

O armazenamento provisório em JSON passou por quatro gerações de formato, definidas pelas Sprints da ADR-007:

| Geração | Origem | Marcas estruturais |
|---|---|---|
| Anterior à A1 | antes da identidade por linha | registros sem `registro_coleta_id`; campo de contato chamado `telefone`; status em vocabulário próprio (por exemplo `pendente`, `pronto_disparo`) ou um dicionário de etapas |
| A1 | identidade por linha | todo registro com `registro_coleta_id` (UUID4 gerado no upload, em M0); sem separação entre válidos e inválidos |
| A2 | validação de conteúdo | `clientes` e `clientes_invalidos` separados, com `total_recebido`, `total_valido`, `total_invalido` e motivos de invalidez |
| A3 | correção append-only | além da A2, `historico_versoes` por registro e tentativas recusadas em `data/correcoes_rejeitadas/` |

Fatos que condicionam esta decisão:

- **Ambiente local:** uma verificação somente leitura, sem exibir nenhum valor pessoal, encontrou 5 lotes e 420 registros, **todos da geração anterior à A1**. Esse conteúdo aparenta ser dado pessoal real. O volume e as gerações presentes em produção são desconhecidos (Especificação, Seção 21).
- **M0 sem fuso:** o M0 legado é `criado_em`, gravado pelo processo da aplicação como hora local **sem fuso horário**. A Sprint A3 já usa o mesmo campo como `recebido_em` do histórico.
- **Restrições da persistência definitiva** (`0001`–`0005`), que impedem uma importação ingênua:
  - `fn_registrar_lote` usa `now()` como M0;
  - `registros_coleta` exige `registro_coleta_id` como chave;
  - todo `lotes.status` pressupõe transições provadas por eventos do catálogo fechado da ADR-009;
  - `fn_criar_claim` não verifica a existência do registro em `registros_coleta`.

---

## 4. Princípios Arquiteturais

### Princípio 1 — Importação É Registro Técnico, Nunca Evento de Negócio

O ato de importar é um fato técnico do sistema, não um fato do ciclo operacional. Ele é registrado como **registro técnico de importação**, distinto e rotulado, nunca gravado em `eventos_lote` nem em `eventos_registro_coleta`, nunca como um sexto evento e nunca confundido com um dos cinco eventos da ADR-009 (Especificação, Seção 11, categoria 2).

### Princípio 2 — Nenhuma História Fabricada

A importação nunca atribui, retroativamente, evento, horário, operador, decisão, classificação ou transição que o legado não comprove. Na dúvida, o fato não é afirmado: o lote é preservado, e não promovido.

### Princípio 3 — Identidade Preservada, Nunca Inventada

Um `registro_coleta_id` que já existe no legado é preservado exatamente. Um registro sem `registro_coleta_id` nunca recebe um, porque uma identidade gerada hoje seria apresentada como nascida no passado (Especificação, Seção 10).

### Princípio 4 — Preservação Integral Antes de Qualquer Promoção

Todo lote legado aceito é preservado integralmente, como snapshot, antes e independentemente de qualquer promoção. A promoção é um efeito adicional, nunca um substituto da preservação.

### Princípio 5 — Operabilidade Somente com Prova

Um lote legado só volta a operar no sistema novo quando o próprio legado comprova tudo o que o fluxo novo exige. Faltando qualquer prova, ele permanece somente auditável. A continuidade de um trabalho não promovido ocorre por um ato novo e honesto, nunca por reconstrução presumida (Seção 12).

### Princípio 6 — Menor Privilégio e Separação de Funções

A importação é executada por um papel próprio, que não grava nenhum dos eventos das ADRs 008 e 009, não compartilha identidade com nenhum outro fluxo e só existe operacionalmente durante as janelas autorizadas de importação.

### Princípio 7 — Integridade Verificável sem Dado Pessoal Indelével

O que precisa ser permanente é a prova da importação, não o dado pessoal. O registro técnico é imutável e não contém dado pessoal. O snapshot contém dado pessoal e, por isso, não é tornado indelével, mas qualquer alteração nele é detectável (Seção 9).

---

## 5. Natureza da Importação

- Cada execução de importação gera um registro técnico próprio, com:
  - identificador da execução;
  - instante (do PostgreSQL);
  - identidade técnica (`session_user`, nunca uma pessoa);
  - fuso horário declarado (Seção 13);
  - SHA-256 do manifesto (Seção 18);
  - por lote: identificador legado, SHA-256 do arquivo bruto, geração e destino (preservado, promovido ou recusado) e, quando promovido, o `lote_id` gerado.
- O registro técnico **não contém valor pessoal** e é imutável depois de gravado, inclusive para o owner, no mesmo padrão dos logs de evento.
- O registro técnico não é evento: não tem agregado, versão de agregado nem papel no catálogo da ADR-009, e não prova nenhuma transição de negócio. Prova apenas que um conteúdo legado, identificado por checksum, foi recebido pelo sistema novo naquele instante, sob aquela identidade técnica e com aquela interpretação de fuso.

---

## 6. Classificação por Geração de Formato

- Antes de qualquer escrita, cada `lote.json` é classificado por geração exclusivamente a partir de sua estrutura, nunca de seus valores pessoais: anterior à A1, A1, A2, A3 ou **formato desconhecido**, para qualquer estrutura que não corresponda exatamente a uma das quatro gerações.
- Lote em formato desconhecido é **recusado**, sem nenhuma escrita: nem snapshot nem promoção. A recusa fica no relatório da importação, para tratamento humano.
- A importação nunca adivinha um formato, nunca completa um campo ausente e nunca corrige um valor.

---

## 7. Nomes Oficiais das Classificações

Resolve a Seção 22, item 4, da Especificação:

| Classificação | Aplica-se a |
|---|---|
| `legado_sem_identidade_tecnica` | registro sem `registro_coleta_id`, em qualquer geração |
| `legado_identificado_nao_promovido` | registro com `registro_coleta_id`, pertencente a lote preservado e não promovido |
| `legado_promovido` | registro de lote promovido (Seção 11), que passa a existir também na projeção operacional |

Essas classificações vivem exclusivamente no snapshot legado e no registro técnico de importação. Elas nunca são apresentadas como identidade técnica nascida no passado e nunca são confundidas com registros nativos do fluxo novo.

---

## 8. Os Três Destinos de um Lote Legado

1. **Recusado:** formato desconhecido (Seção 6), conflito de reimportação (Seção 17) ou violação estrutural. Nada é gravado além da recusa no relatório.
2. **Preservado:** todo lote aceito é gravado no snapshot legado (Seção 9).
3. **Promovido:** lote preservado que, além disso, satisfaz todos os critérios da Seção 10. Passa a existir também em `lotes` e `registros_coleta` e segue o fluxo operacional novo a partir dali.

---

## 9. Snapshot Legado — Conteúdo, Proteção e Mutabilidade

### 9.1 Conteúdo

Por lote:
- o identificador legado original;
- a geração;
- o documento bruto exatamente como estava no arquivo;
- o status legado literal (Seção 14).

Por registro:
- a posição original no arquivo;
- os valores brutos exatamente como estavam;
- o SHA-256 do conteúdo bruto do registro (Especificação, Seção 10);
- o `registro_coleta_id`, quando existir;
- a classificação da Seção 7.

O snapshot é **estado preservado, não evento**: retrata o legado tal como observado na importação (Especificação, Seção 11, categoria 3).

### 9.2 Proteção

- O snapshot é gravado uma única vez, exclusivamente pela função de importação.
- Nenhuma role funcional, inclusive `nsi_importacao`, tem `SELECT`, `INSERT`, `UPDATE` ou `DELETE` direto sobre ele.
- Nenhuma função de nenhuma ADR altera ou remove linhas do snapshot.
- `nsi_eventos_owner`, dono das tabelas, é `NOLOGIN` e nunca é usado por fluxo operacional.

### 9.3 Por que o snapshot não recebe a trigger de imutabilidade do owner

Os logs de evento das ADRs 008 e 009 têm trigger que bloqueia `UPDATE` e `DELETE` inclusive para o owner. O snapshot legado deliberadamente **não** tem, pelos motivos abaixo:

1. **Ele contém dado pessoal.** A ADR-009 (Seção 3 e Princípio 7) resolveu a tensão entre imutabilidade e obrigações jurídicas futuras mantendo todo dado pessoal fora de estruturas indeléveis. Um snapshot indelével reintroduziria exatamente o problema que a ADR-009 evitou.
2. **A imutabilidade das ADRs 008 e 009 é regra dos eventos**, fatos operacionais sem valor pessoal. O snapshot não é evento, e estender a ele a mesma garantia não está prescrito por nenhuma ADR.
3. **Uma trigger seria contornada exatamente quando importasse.** Diante de uma obrigação jurídica futura de eliminação, uma trigger de imutabilidade teria de ser desativada por DDL, o que é uma quebra operacional de garantia pior do que não prometê-la.
4. **A integridade continua verificável.** O registro técnico, que é imutável, guarda o SHA-256 do arquivo bruto de cada lote, e o snapshot guarda o documento bruto. Qualquer alteração posterior no snapshot é detectável recalculando o SHA-256 do documento preservado e comparando-o com o registro imutável. O snapshot é, portanto, **mutável apenas por ato privilegiado, e sempre de forma detectável**, nunca silenciosamente.

### 9.4 Limites

- Alteração ou eliminação do snapshot só pode ocorrer por política jurídica formal futura, executada por ato administrativo próprio, que registre o que foi feito. Esta ADR não cria esse mecanismo, apenas não o impede.
- Após uma eventual eliminação jurídica, o registro técnico permanece e continua provando que a importação ocorreu. Ele guarda apenas o SHA-256 de arquivos inteiros, que não revela conteúdo. Esse hash só permite confirmar a posse de uma cópia exata do arquivo: o mesmo tipo de correlação residual já declarado pela ADR-009 (Seção 9) para o checksum do CSV.

---

## 10. Critérios de Promoção

Um lote é promovido **somente se todos** os critérios abaixo forem comprovados pelo próprio legado:

1. geração A2 ou A3 (Seção 12);
2. todo registro, válido ou inválido, com `registro_coleta_id` UUID, sem repetição no lote e sem colisão com nenhum registro já existente no sistema novo;
3. **nenhuma evidência de disparo**: nenhum registro com envio, entrega ou resposta registrados, nenhuma data de envio, e status legado sem nenhuma indicação de disparo realizado;
4. identificador legado em formato válido e ainda não usado por outro lote do sistema novo;
5. M0 interpretável conforme a política da Seção 13.

A ausência de qualquer prova impede a promoção. O lote continua preservado e, portanto, auditável.

---

## 11. Efeitos da Promoção e Relação com a ADR-009

### 11.1 Efeitos

- **Identificador do lote:** o `lote_id` UUID do sistema novo é gerado no momento da importação e assim registrado no registro técnico. O identificador legado original é preservado em `lote_id_legado`. O novo identificador é declaradamente da importação, e não inventa história.
- **Identificador do registro:** o `registro_coleta_id` é preservado exatamente (Princípio 3).
- **M0:** `recebido_em` é o M0 legado interpretado pela Seção 13. É uma reconstrução honesta com timestamp já existente (Especificação, Seção 11, categoria 1). `horario_conceitual_congelamento` é calculado a partir dele, pela regra da `0004`.
- **Valores correntes:** a projeção recebe os valores correntes do legado: a versão corrente de `historico_versoes`, quando existir, e os totais recontados a partir dos registros. Correções passadas **não** viram eventos `correcao_registrada`. O número da versão corrente de dados é preservado, e o histórico permanece no snapshot.
- **Status inicial:** o status do lote promovido é sempre `aguardando_d8`, porque o congelamento M0+192h nunca foi aplicado por mecanismo nenhum no legado. Se a fronteira já passou, o congelamento ocorrerá depois pelo fluxo normal (`fn_registrar_congelamento`) e será registrado como `atrasado`. Esse é o retrato verdadeiro do que aconteceu, nunca um congelamento retroativo.
- **Nenhum evento de negócio** é gravado pela importação. O log de eventos de um lote promovido começa no primeiro evento do fluxo novo. A origem do lote é provada pelo registro técnico de importação.

### 11.2 Relação com a ADR-009

A ADR-009 (Seção 6.1) descreve `lote_criado` como o evento que cria a linha do lote na projeção. Um lote promovido existe na projeção **sem** `lote_criado`: gravar esse evento afirmaria um upload que o sistema novo não presenciou, e criar um sexto evento ampliaria o catálogo fechado. Esta ADR não faz nenhum dos dois.

A exceção é formalizada na própria ADR-009 por uma seção aditiva (Seção 22 daquela ADR), no mesmo padrão já usado pela Seção 21:

- todo lote da projeção nasce de `lote_criado` (fluxo nativo) **ou** de uma promoção registrada por esta ADR (legado);
- o catálogo de cinco eventos, suas regras e seus papéis valem integralmente para o lote promovido a partir da promoção;
- nenhuma frase das Seções 1 a 21 da ADR-009 é alterada.

---

## 12. Gerações Anteriores à A2 Nunca São Promovidas

### 12.1 Decisão

Lotes da geração anterior à A1 e da geração A1 são preservados, nunca promovidos.

### 12.2 Fundamentos

- **Anterior à A1:** os registros não têm `registro_coleta_id`. Promovê-los exigiria inventar identidades (Princípio 3).
- **A1:** os registros têm identidade, mas o lote não tem classificação de validade, motivos de invalidez nem totais de válidos. O fluxo novo exige essa classificação desde a criação (`registros_coleta.valido`, `motivos_invalidez` e os totais de `lotes`). Ela só poderia ser obtida executando hoje a validação da Sprint A2 sobre dados de ontem. Isso seria **produzir agora uma classificação e apresentá-la como o estado do lote em M0**, o que é exatamente a fabricação que o Princípio 2 proíbe. E o resultado não é garantidamente o que teria sido produzido em M0, porque as regras de normalização e a lista de códigos válidos podem ter evoluído desde então.
- **Reclassificar seria uma decisão de negócio, não técnica.** Decidir que um registro de ontem é inválido por uma regra de hoje afeta quem será contatado. Esse tipo de decisão não pode ser tomado implicitamente por um importador.

### 12.3 Consequências, assumidas

1. Um lote anterior à A2 que esteja em andamento no momento do corte **não continua no sistema novo**. Ele não pode ser congelado, corrigido nem confirmado para disparo pelo fluxo novo.
2. Seus registros permanecem preservados e auditáveis no snapshot, com a classificação `legado_sem_identidade_tecnica` ou `legado_identificado_nao_promovido`, e nunca recebem claim (Seção 15).
3. **A continuidade, quando desejada, ocorre por um ato novo e honesto:** um novo upload do CSV pelo operador, no sistema novo, depois do corte. Esse upload gera um lote nativo, com `lote_criado`, M0 novo, prazo de congelamento novo e identidades novas, todos verdadeiros. O lote legado continua preservado, sem vínculo automático com o novo.
4. O mesmo conteúdo pessoal passa a existir em dois lugares, o snapshot do lote legado e a projeção do lote novo. Essa duplicidade fica registrada para a política jurídica futura (Seção 9.4).
5. **Quantificação antes do corte:** o ensaio da B6 mede, sobre os dados reais, quantos lotes de cada geração existem e quantos estão em andamento. A decisão operacional sobre esses lotes, inclusive o momento do corte, é tomada pela B7 com esse número em mãos, nunca presumida por esta ADR.

---

## 13. Política de Interpretação de Horários Legados

### 13.1 Alcance

A única informação temporal legada **interpretada** é o M0 (`criado_em`) dos lotes candidatos à promoção. Todos os demais horários legados (correções, tentativas recusadas, datas de disparo, datas informativas do lote) são preservados como texto bruto no snapshot e nunca são interpretados.

### 13.2 Fonte do fuso horário

- O fuso é o da máquina que executava a aplicação legada quando os arquivos foram gravados. Ele é **atestado por declaração humana explícita** em cada execução de importação.
- O fuso nunca é inferido a partir dos dados, nunca é tomado do relógio ou da configuração da máquina que executa a importação, e nunca tem valor padrão. Uma execução sem declaração explícita não promove nenhum lote.
- A declaração é sempre um **identificador de fuso da base IANA** (por exemplo, `America/Sao_Paulo`), nunca um deslocamento fixo. Só a base IANA representa corretamente as regras históricas, inclusive horário de verão.

### 13.3 Uniformidade

- Uma execução usa um único fuso declarado para todos os lotes que processa. Esse fuso é gravado no registro técnico (Seção 5).
- O fuso nunca varia por lote dentro de uma execução.
- Se o operador não puder atestar um fuso único para o conjunto legado (por exemplo, porque a aplicação rodou em máquinas com fusos diferentes em períodos indistinguíveis), **nenhum lote é promovido**: todos são preservados.

### 13.4 Formas aceitas e casos de recusa da promoção

- **Forma aceita:** um M0 no formato ISO 8601 produzido pela aplicação legada, sem fuso, com ou sem fração de segundo. É interpretado no fuso declarado, preservando a precisão existente.
- Um M0 que, no fuso declarado, cai num **horário inexistente** (lacuna de início de horário de verão) ou **ambíguo** (repetição de fim de horário de verão) não é interpretável. O lote é preservado, e não promovido.
- Um M0 que já traga deslocamento ou fuso próprio não corresponde ao que a aplicação legada produzia. É anomalia: o lote é preservado, e não promovido.
- Um M0 ausente, vazio ou fora do formato impede a promoção. O lote é preservado, se o restante da estrutura for válido.

### 13.5 Auditabilidade

- O texto bruto do M0 permanece intacto no snapshot.
- O valor interpretado existe somente na projeção do lote promovido.
- A paridade (Seção 19) recalcula a interpretação a partir do texto bruto e do fuso gravado no registro técnico, e exige igualdade exata com a projeção.
- Uma declaração de fuso errada é erro humano rastreável: o registro técnico mostra qual fuso foi declarado, por qual identidade técnica e em qual execução.

### 13.6 Por que a declaração precisa ser humana

O fuso desloca M0 e, com ele, a fronteira M0+192h, que decide a janela de correção e o congelamento (ADR-007, Seção 12). Um erro de poucas horas muda quais correções são aceitas. Por isso o fuso não pode ser uma suposição silenciosa do software: é uma afirmação sobre o passado que só um humano responsável pela operação legada pode fazer, e que fica registrada como tal.

---

## 14. Status Legados

- O status legado, seja texto ou dicionário de etapas, é preservado **literalmente** no snapshot, como dado bruto.
- Ele nunca é convertido em status da projeção, nunca é traduzido em evento e nunca é interpretado como prova de congelamento, de confirmação humana ou de disparo.
- Um lote legado já disparado foi disparado sem a Confirmação em Dois Atos da ADR-007 (Seção 16), que não existia. Por isso ele nunca é promovido (Seção 10, critério 3), e nenhum `disparo_confirmado` é gravado para ele.

---

## 15. Invariante de Claim

- Nenhum registro `legado_sem_identidade_tecnica` ou `legado_identificado_nao_promovido` recebe claim, em nenhuma hipótese (Especificação, Seção 10). Esses registros nunca existem em `registros_coleta`.
- Registros `legado_promovido` têm identidade nascida em M0 pela Sprint A1 e seguem as regras nativas, inclusive de claim, a partir da promoção.
- Hoje, `fn_criar_claim` não verifica a existência do registro em `registros_coleta`, e `claims` não referencia `registros_coleta` por chave estrangeira. A invariante acima é um **requisito obrigatório** que a especificação técnica (B5.2) precisa tornar garantido e verificável por teste. Se isso exigir alterar a `0003` ou `fn_criar_claim`, a alteração é decidida explicitamente na B5.2, nunca feita de forma silenciosa.

---

## 16. Papel Autorizado — `nsi_importacao`

### 16.1 Decisão

A importação é executada exclusivamente por uma role nova e dedicada, **`nsi_importacao`**, com `LOGIN` próprio.

### 16.2 Privilégio mínimo

- `EXECUTE` somente nas funções de importação.
- Nenhum `EXECUTE` em nenhuma das onze funções das ADRs 008 e 009.
- Nenhuma leitura nem DML direto em nenhuma tabela, inclusive o snapshot e o registro técnico.
- Sem membership em nenhuma role e sem nenhum membro.
- `CONNECT` somente nos bancos em que a importação está autorizada na subetapa corrente: na B5, **somente `nsi_test`** (Seção 21).

### 16.3 Por que uma role nova é necessária

As funções de importação têm uma característica única no sistema: **são as únicas que aceitam M0 fornecido pelo chamador**. Todas as demais usam o relógio do PostgreSQL como autoridade temporal (Especificação, Seções 3 e 7). Quem pode importar pode, portanto, criar lotes com prazo de congelamento no passado, ou seja, com a janela de correção já encerrada. Esse poder precisa ficar isolado de qualquer outro.

| Alternativa | Por que foi rejeitada |
|---|---|
| `nsi_aplicacao` | É a credencial de uso contínuo da aplicação. Um comprometimento dela permitiria forjar lotes com M0 arbitrário, contornando a autoridade temporal do banco. Também viola a separação entre fluxo rotineiro e operação excepcional (ADR-009, Princípio 4) |
| `nsi_operador_restrito` | Já concentra as decisões humanas excepcionais (revisão e reatribuição de claim, confirmação de disparo). Somar a importação daria a uma única credencial o poder de criar o lote e confirmar seu disparo, sem separação de funções |
| `nsi_expiracao` ou `nsi_congelamento` | São papéis de propósito único, definidos por ADR, e ampliá-los quebraria esse desenho |
| Migrators (`nsi_dev_migrator`, `nsi_test_migrator`) | São identidades de mudança de schema. Usá-las para gravar dados misturaria autoridade de DDL com escrita operacional, e o registro técnico atribuiria a importação a uma identidade de migration |
| Role `NOLOGIN` assumida por `SET ROLE` | Exigiria uma segunda exceção à regra de membership da B3.1, que a ADR-009 (Seção 21) declara única e fechada. Além disso, o membro escolhido passaria a carregar permanentemente a capacidade de importar |

### 16.4 Por que `LOGIN` próprio

- O registro técnico atribui cada importação a uma identidade técnica inequívoca (`session_user = nsi_importacao`), distinguível de qualquer outro fluxo.
- A credencial pode existir somente durante as janelas autorizadas, sem afetar nenhuma outra role.
- A capacidade de importar pode ser retirada por completo, desabilitando o `LOGIN` dessa única role, sem tocar a aplicação.

### 16.5 Ciclo de vida

- A role é criada administrativamente, no padrão de três fases da B3.1 e da B4.3, nunca por migration.
- Sua credencial é configurada fora do versionamento e usada somente durante execuções autorizadas.
- Ao fim da importação definitiva (B7) e de sua validação, a role é desabilitada (`NOLOGIN`) por ato administrativo, e permanece existente para que a identidade gravada nos registros técnicos continue reconhecível.
- Uma nova importação depois disso exige nova autorização explícita.

---

## 17. Idempotência e Reimportação

- A unidade de importação é o arquivo de lote, identificado pelo par (identificador legado, SHA-256 do arquivo bruto). A garantia é persistente, na mesma transação da escrita.
- Reimportar o mesmo arquivo, com o mesmo checksum, devolve o resultado original (replay), sem nenhuma nova linha.
- Reimportar um identificador legado já importado com checksum diferente é **conflito explícito, recusado**. O legado mudou depois de uma importação, e isso exige tratamento humano, nunca sobrescrita.
- A importação de um lote é atômica: snapshot, promoção e registro técnico gravam tudo ou nada.

---

## 18. Manifesto e Checksum

Resolve, no nível arquitetural, a pendência da ADR-008 (Seções 17, 19 e 21) sobre manifesto e checksum:

- **Algoritmo:** SHA-256 sobre os bytes brutos de cada arquivo, sem nenhuma normalização prévia.
- **Manifesto:** um documento por execução, que lista para cada arquivo do escopo (Seção 20):
  - o caminho relativo;
  - o tamanho;
  - o SHA-256;
  - a geração (Seção 6);
  - o destino (Seção 8).
  
  Ele não contém valor pessoal. O SHA-256 do próprio manifesto é gravado no registro técnico da execução.
- O mesmo formato de manifesto serve à preservação dos JSONs congelados no corte (ADR-008, Seção 17). O layout exato do documento pertence à especificação técnica.

---

## 19. Critério de Paridade

- A validação da importação, que é o passo 4 da ADR-008 (Seção 16), é **paridade campo a campo**, como o `ROADMAP-SPRINTS-B-G.md` já define.
- Para todo lote aceito, o documento bruto e cada valor bruto de cada registro no snapshot são idênticos aos do arquivo de origem, comprovado também por SHA-256.
- Para todo lote promovido:
  - cada valor corrente na projeção é idêntico ao valor corrente do legado;
  - os totais são iguais à recontagem;
  - o M0 interpretado é igual à reinterpretação do texto bruto no fuso gravado (Seção 13.5).
- Não há perda: todo arquivo do escopo aparece no manifesto com um destino explícito.
- Os "213 cenários" citados no resumo da B5 na Especificação correspondem ao tamanho da suíte de testes existente na B1, e não a um conjunto de cenários de dados. A exigência correspondente é a regressão completa da suíte do projeto, sem falhas e sem pulados, que se soma à paridade campo a campo e não a substitui.

---

## 20. Arquivos no Escopo

| Arquivo | Tratamento |
|---|---|
| `lote.json` de cada lote | classificado, preservado e, se elegível, promovido |
| Tentativas recusadas da A3 (`data/correcoes_rejeitadas/`) | incluídas no manifesto (checksum), **não** importadas e nunca convertidas em `tentativa_correcao_nao_resolvida`, porque seria evento fabricado |
| Saída do Motor (`saida_motor.json`), logs de resposta, PDFs, CSVs originais | **fora do escopo** (ADR-008, Seção 5; Sprints C e E). Nem importados nem incluídos no manifesto desta ADR. Sua preservação no corte é assunto da B7 |

---

## 21. Dados de Entrada e Ambiente da B5

- A B5 usa **exclusivamente fixtures sintéticas**, que reproduzem a estrutura das quatro gerações e dos formatos observados, nunca valores copiados de `data/`. Nenhum teste nem execução da B5 lê `data/`.
- Dado real só no ensaio da B6, sob as regras da Especificação, Seção 19.
- A B5 executa somente em `nsi_test`, com gate de identidade. `nsi_dev` não recebe importação na B5, e `nsi_importacao` não tem `CONNECT` em `nsi_dev` durante a B5. Nenhuma produção é tocada.
- O ambiente de staging e a infraestrutura definitiva continuam sendo decisões da Especificação, Seção 12, exigíveis antes da B6 e da B7, não da B5.

---

## 22. Fronteira B5 / B6 / B7

| Subetapa | Faz | Nunca faz |
|---|---|---|
| B5 | importação e validação de paridade em `nsi_test`, com dados sintéticos | pausar escritas, trocar a fonte de verdade, usar dado real, tocar produção |
| B6 | ensaio completo dos passos 1 a 4 da ADR-008 (Seção 16) em ambiente controlado, incluindo a quantificação por geração (Seção 12.3) | o passo 5 |
| B7 | corte real, com autorização própria, após a Especificação, Seção 14; desabilitação de `nsi_importacao` ao final (Seção 16.5) | escrita dupla permanente, retorno isolado aos JSONs |

---

## 23. O Que Permanece para Especificação Técnica (B5.2)

- O schema concreto do registro técnico de importação e do snapshot legado, e a migration correspondente.
- As funções de importação, seus parâmetros e o contrato de erro.
- A representação exata da versão de eventos de um lote promovido sem `lote_criado`.
- O mecanismo que garante a invariante de claim (Seção 15).
- O layout do manifesto e os nomes de módulos e scripts.
- O script administrativo da role `nsi_importacao` e a configuração de sua URL.
- A lista exata de marcas estruturais por geração e de evidências de disparo.
- A forma da declaração de fuso na execução.
- A estratégia de testes, os critérios de aceite e de rollback, e a limpeza compatível com os preflights de downgrade.

---

## 24. Pendências Técnicas Não Bloqueantes

- Mecanismo da invariante de claim (Seção 15), a decidir explicitamente na B5.2.
- Volume e gerações presentes em produção, medidos na B6 (Seção 12.3).
- Retenção de `comandos_idempotentes` e do registro técnico de importação, pendente no mesmo padrão da ADR-009 (Seção 9).

---

## 25. Decisões Aprovadas e Congeladas

1. A importação é registro técnico, nunca evento de negócio e nunca sexto evento (Princípio 1; Seção 5).
2. Nenhuma história fabricada e nenhuma identidade inventada (Princípios 2 e 3).
3. A classificação por geração de formato é estrutural, e formato desconhecido é recusado (Seção 6).
4. Os nomes oficiais das classificações legadas são os da Seção 7.
5. Há três destinos, e a preservação integral sempre precede a promoção (Seção 8).
6. O snapshot é estado preservado: gravado uma única vez, sem acesso direto por role funcional, sem trigger de imutabilidade do owner, e com integridade verificável pelo registro técnico imutável (Seção 9).
7. A promoção ocorre somente para as gerações A2 e A3, com prova completa e sem evidência de disparo (Seção 10).
8. O lote promovido tem `lote_id` novo e declarado, `registro_coleta_id` e M0 preservados, status `aguardando_d8` e nenhum evento de negócio gravado (Seção 11.1).
9. A exceção à Seção 6.1 da ADR-009 é formalizada por seção aditiva naquela ADR, sem tocar o catálogo (Seção 11.2).
10. As gerações anteriores à A2 nunca são promovidas. A continuidade ocorre por novo upload nativo, e a quantificação é feita na B6 (Seção 12).
11. O M0 legado é interpretado em fuso IANA declarado por humano, uniforme por execução e gravado no registro técnico. Horários ambíguos, inexistentes ou anômalos impedem a promoção (Seção 13).
12. O status legado é preservado literalmente e nunca é convertido nem interpretado (Seção 14).
13. Legado não promovido nunca recebe claim. A garantia é requisito obrigatório da B5.2 (Seção 15).
14. A importação é executada pela role dedicada `nsi_importacao`, com `LOGIN` próprio, privilégio mínimo, `CONNECT` restrito e desabilitação ao final da B7 (Seção 16).
15. A reimportação é idempotente, e um checksum divergente para o mesmo identificador legado é conflito recusado (Seção 17).
16. O manifesto é por execução, com SHA-256 sobre os bytes brutos (Seção 18).
17. A paridade é campo a campo, e os "213" correspondem à regressão completa da suíte (Seção 19).
18. O escopo é `lote.json` importado e tentativas recusadas só no manifesto. Motor, respostas, PDFs e CSVs ficam fora (Seção 20).
19. A B5 usa somente dados sintéticos e somente `nsi_test` (Seção 21).

---

## 26. Dependências

- ADR-007 (Seções 9, 12, 13 e 16): correção append-only, congelamento M0+192h, status, Confirmação em Dois Atos.
- ADR-008 (Seções 5, 6, 15, 16 e 17): escopo, modelo de evento, imutabilidade, corte controlado, preservação.
- ADR-009 (Seções 3, 5, 6, 7, 9, 10, 11 e 21): tensão entre imutabilidade e dado pessoal, modelo híbrido, catálogo fechado, privacidade, correlação de checksum, identidade técnica, papéis, exceção de membership.
- Especificação Técnica da Sprint B (Seções 3, 7, 10, 11, 12, 19, 21 e 22).

## 27. Referências

- `docs/architecture/ADR-007-ciclo-operacional-preparacao-disparo-coleta.md`
- `docs/architecture/ADR-008-persistencia-operacional-imutavel-claims-idempotencia.md`
- `docs/architecture/ADR-009-catalogo-eventos-operacionais.md`
- `docs/implementation/SPRINT-B-ESPECIFICACAO-TECNICA.md`
- `docs/implementation/ROADMAP-SPRINTS-B-G.md`

---

## 28. Status Final e Congelamento (2026-10-03)

Com a arquitetura completa registrada nas Seções 1 a 27, revisada em rodadas sucessivas com aprovação humana explícita ao final, a ADR-010 é registrada como **APROVADA E CONGELADA**.

### O que o congelamento significa

- As decisões da Seção 25 estão aprovadas e estáveis.
- Mudanças futuras a qualquer decisão aqui congelada só poderão ocorrer por evolução arquitetural formalmente documentada, mesmo método das demais ADRs do projeto.
- As pendências da Seção 24 não reabrem nem impedem este congelamento.
- Nenhuma implementação de código, schema, migration, role ou configuração foi criada, modificada ou autorizada por este documento. A implementação depende da especificação técnica da B5.2 e de autorização própria.
- A única consequência desta ADR sobre outra ADR é a Seção 22 da ADR-009, de formalização aditiva (Seção 11.2). A ADR-001, a ADR-005, a ADR-006, a ADR-007 e a ADR-008 permanecem intocadas.

**Origem desta decisão:**
- Subetapa B5.1 da Sprint B (2026-10-03): decisão de arquitetura da importação do legado operacional, aberta para satisfazer as Seções 10, 11 e 22 (itens 4 e 12) da Especificação Técnica da Sprint B.
