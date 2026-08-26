# ADR-006 — Jornada de Transformação Organizacional (Tela 03)

## Metadados

| Campo | Valor |
|---|---|
| Status | APROVADA E CONGELADA |
| Data | 2026-08-25 |
| Data de congelamento | 2026-08-26 |
| Versão de referência do sistema | `v1.1.0-fonte-unica-webhook-motor` |
| Commit de referência | `998387f` |
| Branch | `master` |
| Escopo desta ADR | Arquitetura — nenhuma implementação de código, frontend ou componente visual |

> **Nota de processo:** ADR aberta para cumprir a dependência registrada na ADR-004 ("Decisão Arquitetural — Encerramento da Jornada de Inteligência Organizacional"): *"Após o Sexto Cartão, inicia-se uma jornada conceitualmente independente, denominada Jornada de Transformação Organizacional... sua arquitetura será tratada em sessão futura."* Esta ADR é essa sessão futura. Registra os princípios fundacionais, o schema conceitual, a governança de autoria e correção, o acesso à Tela 03, o encerramento da relação com a NSI e o Pacote de Preservação Histórica — não define cartões, telas internas, layout, componentes visuais ou implementação técnica.
>
> **Esta ADR está APROVADA E CONGELADA (Seção 22).** Os princípios fundacionais descritos nas Seções 4 a 21 estão aprovados. As pendências registradas na Seção 14 (Pendências Técnicas, Visuais e Jurídicas Não Bloqueantes) são exclusivamente de implementação técnica ou visual, ou dependem de uma Política Jurídica futura já nomeada como tal — nenhuma delas representa lacuna conceitual, e nenhuma impede este congelamento (Seção 22). Mudanças futuras à arquitetura conceitual aqui congelada exigem evolução formalmente documentada, no mesmo padrão já usado nesta e nas demais ADRs do projeto.

---

## 1. Objetivo

Registrar os princípios fundacionais da Jornada de Transformação Organizacional — **Tela 03** do Portal Executivo do Cliente — a etapa que sucede o encerramento da Jornada de Inteligência Organizacional no Sexto Cartão (ADR-004). Esta ADR já define a Pergunta Cognitiva Fundadora (Seção 6), o modelo estrutural da jornada — Trajetória Contínua (Seção 7) —, a granularidade dos registros — Granularidade por Ato de Declaração (Seção 8) —, a transição conceitual de acesso entre o Sexto Cartão e a Tela 03 — Modelo Combinado (Seção 9) —, o modelo de autoria (Seção 10), referenciando a identidade do usuário definida pela ADR-004, e o schema conceitual da Trajetória Contínua — Registro Atômico Independente (Seção 11). A arquitetura visual, os componentes concretos de navegação e o armazenamento técnico concreto dos registros permanecem em arquitetura. Esta ADR não implementa nada e não altera nenhuma decisão já congelada nas ADRs anteriores.

---

## 2. Escopo

### 2.1 Escopo desta decisão

- Identidade da Tela 03 e sua posição na numeração do Portal Executivo do Cliente.
- Registro desta jornada em ADR própria, distinta da ADR-004.
- Princípio de autoria exclusivamente humana da transformação.
- Aplicação integral, sem exceção, do Princípio da Observabilidade e da Neutralidade Decisória (ADR-004, §7.9 e §7.17) à Jornada de Transformação.
- Unidade cognitiva e de registro da jornada: uma realidade recorrente por vez.
- Relação temporal entre a Tela 03 e o ciclo de coleta da ADR-005.
- Isolamento absoluto dos registros da Transformação em relação às leituras congeladas.
- Missão conceitual da jornada.
- Pergunta Cognitiva Fundadora e seus limites.
- Modelo estrutural da Tela 03 — Trajetória Contínua.
- Natureza cronológica e cumulativa dos registros.
- Preservação histórica por acréscimo, sem reescrita retroativa.
- Permanência aberta e ausência de conclusão obrigatória.
- Neutralidade estrutural da trajetória.
- Granularidade dos registros — Granularidade por Ato de Declaração.
- Indivisibilidade do conteúdo declarado em um mesmo ato.
- Organização exclusivamente cronológica dos registros, sem hierarquia ou agrupamento automático.
- Transição conceitual de acesso entre o Sexto Cartão e a Tela 03 — Modelo Combinado.
- Modelo de autoria (individual e institucional declarada), referenciando a identidade do usuário definida pela ADR-004.
- Schema conceitual da Trajetória Contínua — Registro Atômico Independente, incluindo a identidade própria do registro (`registro_id`).
- Fronteira epistemológica da jornada ("Limite pela Fonte da Afirmação").
- Regra de acesso independente à Tela 03 para cada realidade recorrente revelada pela Leitura de Excedência — sem comparação, identificação de equivalência ou vinculação automática com realidades reveladas pela Leitura Inicial.

### 2.2 Fora do escopo desta decisão

- Arquitetura visual e navegação dos registros, incluindo layout, botão, transição, rota, componentes, filtros de exibição, busca, paginação e agrupamento visual.
- KPIs e gráficos.
- Recomendações de qualquer natureza.
- Responsáveis e prazos.
- Planos de ação.
- Automações.
- Qualquer implementação de código, frontend, componente visual, schema de banco de dados ou API.
- Alteração ao Motor NSI.
- Alteração à ADR-004 ou à ADR-005.

---

## 3. Contexto

A ADR-004 (§7, Decisão Arquitetural — Encerramento da Jornada de Inteligência Organizacional) declarou que a Jornada de Inteligência Organizacional está completa e encerrada no Sexto Cartão, e que uma jornada subsequente e conceitualmente independente — a Jornada de Transformação Organizacional — ainda não estava arquitetada, ficando sua arquitetura reservada para sessão futura.

Esta ADR cumpre essa dependência, registrando os princípios fundacionais decididos em sessão de arquitetura própria, sem alterar o texto já congelado da ADR-004 ou da ADR-005.

---

## 4. Princípios Arquiteturais da Jornada de Transformação Organizacional

### Princípio 1 — Identidade e Domínio

A Jornada de Transformação Organizacional corresponde à **Tela 03 — Jornada de Transformação Organizacional**, do Portal Executivo do Cliente. Pertence ao Portal Executivo do Cliente (ADR-001, §4.2) — não cria uma nova plataforma do ecossistema NSI. Sucede numericamente a Tela 01 — Acesso ao Portal Executivo e a Tela 02 — Home (Painel Executivo do Portal), ambas registradas na ADR-004. Possui arquitetura própria nesta ADR — não é seção nem continuação interna da Tela 02.

### Princípio 2 — Independência Conceitual

A Jornada de Transformação é uma jornada subsequente e conceitualmente independente, iniciada para uma realidade recorrente após a conclusão do Sexto Cartão daquela realidade. A sequência temporal não elimina essa independência conceitual.

### Princípio 3 — Autoria Exclusivamente Humana

Quem transforma a realidade é exclusivamente o gestor e a organização — nunca o NSI. O NSI nunca conduz a transformação.

### Princípio 4 — Observabilidade e Neutralidade Decisória (sem exceção)

O NSI pode: estruturar, registrar, contextualizar e tornar observável aquilo que os gestores humanos decidirem.

O NSI está proibido de:
- escolher ou recomendar ações;
- sugerir soluções;
- definir prioridades;
- indicar responsáveis;
- estabelecer prazos;
- montar planos automaticamente;
- executar ações;
- avaliar ou decidir em nome do gestor.

Esta decisão preserva integralmente a ADR-004 (§7.9, §7.17), o Livro dos Princípios e a regra de que a tecnologia serve, mas não decide — sem qualquer exceção.

### Princípio 5 — Unidade Cognitiva e de Registro: Uma Realidade Recorrente por Vez

A jornada opera sobre uma realidade recorrente por vez — mesma unidade da Jornada de Descoberta (ADR-004, "Decisão Arquitetural — Unidade da Jornada Cognitiva"). A Transformação não produz uma nova análise semântica da realidade — organiza e registra a trajetória de mudança referente a uma única realidade recorrente já revelada.

### Princípio 6 — Relação Temporal com o Ciclo de Coleta (ADR-005)

A Jornada de Transformação pode coexistir com a Leitura de Excedência ainda em coleta — não precisa aguardar as 336 horas nem o encerramento da janela definida na ADR-005.

### Princípio 7 — Isolamento dos Dados

A Jornada de Transformação gera registros próprios, em camada de dados separada. Esses registros nunca escrevem, recalculam, misturam, substituem ou invalidam a Leitura Inicial ou a Leitura de Excedência já congeladas — preservando integralmente o Princípio 4 da ADR-005 (Independência Entre Leituras).

### Princípio 8 — Acesso Independente à Tela 03 por Realidade e por Leitura

- Cada realidade recorrente revelada pela Leitura de Excedência permanece pertencente exclusivamente àquela leitura.
- Depois de concluir sua própria Jornada de Inteligência Organizacional até o Sexto Cartão, essa realidade recebe acesso próprio e independente à Tela 03.
- Esse acesso possui registros próprios e isolados de qualquer acesso originado pela Leitura Inicial.
- O NSI não compara, identifica equivalência, vincula, atualiza, complementa, reabre ou mistura automaticamente realidades ou registros entre as duas leituras — preservando integralmente o Princípio 6 da ADR-005 (Ausência de Comparação Automática), aplicado por esta ADR à camada de Transformação.
- Se um gestor humano declarar que percebe relação, semelhança ou continuidade entre realidades de leituras diferentes, essa percepção permanece apenas como declaração humana atribuída, subordinada ao "Limite pela Fonte da Afirmação" (Seção 12).
- Mesmo uma declaração humana de relação não produz fusão, recálculo, vinculação automática nem compartilhamento de registros entre os acessos à Tela 03.

---

## 5. Missão Conceitual

> "A missão da Jornada de Transformação Organizacional é tornar observável, ao longo do tempo, a trajetória de mudança que o gestor e a organização escolherem seguir diante da realidade já revelada — mantendo o NSI exclusivamente na função de estruturar, registrar e contextualizar essa trajetória, nunca de conduzi-la."

---

## 6. Pergunta Cognitiva Fundadora

> "Diante desta realidade, que posição o gestor e a organização escolhem assumir?"

**Limites desta pergunta:**

- A pergunta inaugura a jornada com uma posição declarada pelo gestor e pela organização.
- "Posição" não significa cargo, hierarquia ou localização — significa a postura humana escolhida diante da realidade.
- A pergunta não presume ação, correção ou mudança.
- Permite legitimamente agir, acompanhar, preservar a condição atual ou decidir não mudar.
- Essas alternativas não devem ser apresentadas pelo sistema como opções fechadas ou categorias.
- A pergunta não recomenda, prioriza, avalia nem conduz.
- A posição declarada permanece subordinada ao "Limite pela Fonte da Afirmação" (Seção 12).
- O NSI registra e torna observável a declaração, mas não a interpreta.
- A pergunta fundadora não define cartões, etapas, campos, fluxo ou layout.

---

## 7. Modelo Estrutural — Trajetória Contínua

**Natureza estrutural**

- A Tela 03 não utiliza cartões cognitivos.
- Não utiliza etapas fechadas.
- Não utiliza marcos obrigatórios.
- Sua estrutura é uma trajetória única, contínua e cronológica.

**Início**

- A trajetória começa com a declaração humana produzida em resposta à Pergunta Cognitiva Fundadora (Seção 6).
- Essa resposta é o primeiro registro da trajetória.
- Ela não é chamada de cartão, etapa ou marco.

**Registros posteriores**

- Cada nova declaração humana é acrescentada cronologicamente à mesma trajetória.
- Nenhum registro anterior é apagado, substituído ou reescrito.
- Uma correção, mudança de posição ou nova interpretação humana deve ser registrada por acréscimo posterior, preservando o histórico anterior.
- Cada registro permanece subordinado ao "Limite pela Fonte da Afirmação" (Seção 12).

**Permanência**

- A trajetória pode permanecer aberta por tempo indeterminado.
- Não existe conclusão obrigatória.
- Não existe cartão final.
- Não existe quantidade mínima ou máxima de registros.
- Ausência de novos registros não significa conclusão, abandono, fracasso ou ineficiência.

**Neutralidade estrutural**

- O NSI não transforma registros em etapas.
- Não cria hierarquia entre declarações.
- Não escolhe marcos.
- Não classifica avanço, atraso, mudança, sucesso ou fracasso.
- Não infere causalidade pela ordem cronológica.
- A ordem temporal demonstra apenas quando cada declaração foi registrada.

**Consequência arquitetural**

- A pendência "Estrutura interna: cartões ou outro formato" fica resolvida.
- A pendência "Quantidade e ordem de possíveis etapas" deixa de existir como formulação válida, pois não haverá etapas.
- A granularidade dos registros dentro da trajetória contínua é registrada na Seção 8 (Granularidade por Ato de Declaração).
- Permanece em aberto apenas a arquitetura visual e de navegação, e o armazenamento técnico concreto dos registros isolados (Seção 14).

---

## 8. Granularidade por Ato de Declaração

**Unidade de registro**

- Cada ato humano de envio confirmado de uma declaração constitui um único registro.
- O envio e sua confirmação pertencem ao mesmo ato de declaração e nunca geram dois registros.
- A confirmação não é um segundo registro — é a condição que torna aquele ato registrável.
- Conteúdos ainda não confirmados não integram a Trajetória Contínua.
- Um registro pertence exclusivamente a um acesso específico da Tela 03.

**Conteúdo indivisível**

- Depois da confirmação, conteúdo literal, autor e data/hora formam uma unidade indivisível.
- Se a pessoa declarar várias informações no mesmo ato de envio confirmado, elas permanecem no mesmo registro.
- O NSI não divide, fragmenta, resume, completa, reorganiza ou parafraseia o conteúdo.

**Registros posteriores**

- Qualquer declaração humana posterior, inclusive correção, mudança de posição, explicação adicional ou nova interpretação, gera novo ato de envio confirmado e novo registro.
- O registro anterior não é apagado, substituído ou reescrito.
- O NSI não decide que uma declaração posterior corrige, invalida ou supera uma anterior.
- Qualquer relação entre registros precisa ser declarada por uma pessoa e permanece subordinada ao "Limite pela Fonte da Afirmação" (Seção 12).

**Organização**

- Os registros são organizados exclusivamente pela ordem temporal dos atos.
- A ordem cronológica não representa importância, prioridade ou causalidade.
- Registros feitos na trajetória não são automaticamente agrupados por tema, tipo, relevância ou resultado.
- Nenhum registro recebe hierarquia automática.
- A trajetória cresce somente por acréscimo.

**Grande volume**

- Esta decisão de granularidade não define layout, filtros, busca, paginação, agrupamento visual ou navegação.
- A legibilidade de uma trajetória com muitos registros permanece pertencente à arquitetura visual e de navegação (Seção 14).
- Futuras soluções de navegação não poderão alterar, resumir ou reinterpretar os registros originais.

**Consequência arquitetural**

- A pendência "Granularidade e organização dos registros dentro da trajetória contínua" fica resolvida no nível conceitual.
- O armazenamento técnico concreto dos registros permanece pendente (Seção 14).
- Arquitetura visual e navegação permanecem pendentes (Seção 14).

---

## 9. Transição entre o Sexto Cartão e a Tela 03

**Modelo aprovado: Combinado — oferta no momento da conclusão + acesso permanente.**

- O acesso à Tela 03 é habilitado após a conclusão do Sexto Cartão daquela realidade.
- O Portal oferece a entrada nesse momento, mas não redireciona automaticamente.
- Entrar exige uma decisão humana explícita.
- Se o gestor não entrar, nada acontece:
  - não existe estado "pendente";
  - não existe atraso, incompletude ou abandono;
  - não existe avaliação negativa.
- O acesso permanece disponível posteriormente, dentro do contexto daquela realidade específica.
- Não existe prazo, expiração, pressão ou lembrete insistente.
- Entrar posteriormente possui a mesma validade arquitetural que entrar no momento da oferta.
- Cada acesso permanece independente por realidade e por leitura, conforme os Princípios 5 e 8 (Seção 4) já aprovados.
- O sistema não classifica entrar ou não entrar como avanço, atraso, sucesso ou fracasso.

**Esta decisão não define:**

- texto do convite ou botão;
- rota técnica;
- layout;
- posição;
- cores;
- dimensões;
- componentes visuais;
- mecanismo concreto de navegação.

---

## 10. Autoria

- Todo registro da Trajetória Contínua exige, obrigatoriamente, um `usuario_id` como autor — identidade técnica definida pela ADR-004 (Evolução Aprovada — Identidade Técnica do Usuário, Seção 12) — nunca a empresa isoladamente.
- O contexto da declaração pode ser marcado, pela própria pessoa, como pessoal ou institucional.
- O contexto institucional é uma escolha humana explícita, feita no ato da declaração — nunca inferida, presumida ou aplicada por padrão.
- Marcar uma declaração como institucional nunca substitui, transfere ou dilui a autoria técnica individual — o `usuario_id` permanece, sempre, o autor do registro.
- Não existe, nesta decisão, nenhuma definição de papéis, permissões ou níveis hierárquicos — quem está autorizado a declarar em nome da organização permanece pendente, pertencente ao futuro controle de acesso.

---

## 11. Schema Conceitual da Trajetória Contínua — Registro Atômico Independente

**Natureza da Trajetória**

- A Trajetória não possui identidade técnica própria — é inteiramente derivada da coleção de registros que compartilham o mesmo `realidade_id` (ADR-004, §7.26).
- Não existe evento de criação da Trajetória em si — ela passa a existir no momento em que o primeiro registro é feito (Seção 7, "Início").

**O registro**

- Cada ato humano de envio confirmado gera um registro independente, próprio e imutável (Seção 8, Granularidade por Ato de Declaração).
- `registro_id`: identificador técnico próprio, opaco, único e imutável, atribuído a cada registro no exato momento em que o ato de envio é confirmado e o registro é criado.
- Timestamp, posição cronológica e conteúdo **não compõem** a identidade do registro — são atributos associados a ela, nunca parte dela.
- Cada registro referencia `realidade_id` (vínculo à trajetória) e `usuario_id` (autor, identidade definida pela ADR-004) — as duas referências são paralelas e independentes entre si; `usuario_id` nunca é descendente de `realidade_id`, nem vice-versa.
- Cada registro preserva: o contexto declarado (pessoal | institucional, Seção 10), o conteúdo literal e indivisível, e o timestamp do ato confirmado.
- Registros nunca são reabertos, editados ou substituídos — cada correção ou nova posição gera um novo `registro_id`, preservando integralmente o registro anterior, que nunca é alterado.

**Isolamento**

- O armazenamento dos registros da Trajetória é fisicamente isolado de `lote.json` e de `saida_motor.json` — nenhum registro da Transformação escreve, recalcula ou altera qualquer leitura congelada (Princípio 7, Seção 4).

**Fora desta decisão**

- Mecanismo técnico concreto de armazenamento.
- Regra de geração e garantia concreta de unicidade de `registro_id`.
- Formato concreto da referência ao resultado candidato de origem de uma realidade (ADR-004, §7.26).
- Tratamento de concorrência entre múltiplos processos/workers.

---

## 12. Fronteira Epistemológica — Limite pela Fonte da Afirmação

**O que compõe a trajetória:** qualquer informação cuja origem seja uma declaração humana explícita (gestor ou organização): decisões tomadas, ações concluídas, status alcançados, datas e explicações — sempre atribuídas a quem declarou.

**O que precisa ser declarado por pessoas:** toda informação que estabeleça sentido, motivo, avaliação, relação de causa ou resultado. O sistema não pode originar, completar ou parafrasear esse conteúdo.

**O que o NSI pode tornar observável:** quais declarações existem, em que ordem foram feitas e seu conteúdo literal — sempre visivelmente atribuído a seu autor humano e à data. Nada afirmado pelo próprio sistema é apresentado como fato sobre a transformação.

**O que o NSI está proibido de inferir, concluir ou avaliar:** qualquer afirmação não atribuível, palavra por palavra, a uma declaração humana — incluindo vínculos causais entre entradas, julgamentos de sucesso, fracasso ou eficiência, ou qualquer frase de síntese gerada pelo sistema.

**Como se impede que sequência temporal seja apresentada como causa e efeito:** como o sistema só exibe declarações literais e suas datas, nunca gerando linguagem conectiva própria, nenhuma frase de autoria do sistema pode afirmar que um evento causou outro.

**Como se impede a classificação automática de sucesso, fracasso, eficiência ou ineficiência:** nenhum campo, ícone, cor ou rótulo gerado pelo sistema pode classificar mudança, ausência de mudança, conclusão ou atraso — repete, nesta jornada, a mesma fronteira já congelada para a Jornada de Inteligência Organizacional (ADR-004, §7.17): o sistema organiza evidências, a interpretação pertence ao gestor.

**Atribuição visível da fonte humana:** toda declaração exibida permanece visivelmente atribuída a seu autor humano e à data em que foi feita — nunca apresentada como afirmação neutra ou de autoria do sistema.

**Distinção entre declaração humana e conclusão do sistema:** tudo o que o sistema apresenta como fato é estritamente: (a) que uma declaração existe; (b) seu conteúdo literal; (c) sua data; (d) seu autor. Qualquer interpretação, julgamento ou vínculo causal só existe se for, ele próprio, uma declaração humana citada — nunca uma afirmação do sistema.

---

## 13. Decisões Aprovadas Nesta Sessão

As seguintes decisões são consideradas aprovadas como princípios fundacionais — **não como arquitetura completa da Tela 03**:

1. Identidade: Tela 03 — Jornada de Transformação Organizacional, do Portal Executivo do Cliente (Princípio 1).
2. Independência conceitual, sem ser descrita como "continuação natural" (Princípio 2).
3. Autoria exclusivamente humana da transformação (Princípio 3).
4. Observabilidade e Neutralidade Decisória, sem exceção, com a lista completa de capacidades e proibições do NSI (Princípio 4).
5. Unidade cognitiva e de registro: uma realidade recorrente por vez (Princípio 5).
6. Relação temporal: coexistência com a Leitura de Excedência em coleta, sem necessidade de aguardar 336 horas (Princípio 6).
7. Isolamento absoluto dos registros da Transformação em relação às leituras congeladas (Princípio 7).
8. Regra de acesso independente à Tela 03 por realidade e por leitura, sem comparação, equivalência ou vinculação automática entre a Leitura Inicial e a Leitura de Excedência (Princípio 8).
9. Missão conceitual (Seção 5).
10. Pergunta cognitiva fundadora, com seus limites de interpretação (Seção 6).
11. Modelo estrutural — Trajetória Contínua (Seção 7).
12. Granularidade por Ato de Declaração (Seção 8).
13. Transição entre o Sexto Cartão e a Tela 03 — Modelo Combinado (Seção 9).
14. Autoria (Seção 10), referenciando a identidade do usuário definida pela ADR-004 (Seção 12).
15. Schema Conceitual da Trajetória Contínua — Registro Atômico Independente, incluindo `registro_id` (Seção 11).
16. Fronteira epistemológica — Limite pela Fonte da Afirmação (Seção 12).

## 14. Pendências Técnicas, Visuais e Jurídicas Não Bloqueantes

Nenhuma das pendências abaixo é uma lacuna conceitual da arquitetura da Tela 03: são exclusivamente pendências de implementação técnica ou visual, ou dependem de uma Política Jurídica futura já nomeada como tal (Seção 21). Nenhuma delas reabre ou impede o congelamento conceitual desta ADR (Seção 22).

- Arquitetura visual e navegação: rota técnica, layout detalhado, posição, cores, dimensões, componentes visuais, mecanismo concreto de navegação — a transição conceitual de acesso e o texto do convite já estão definidos (Seções 9 e 20).
- Schema relacional concreto em PostgreSQL para os registros da Trajetória Contínua: tabelas, colunas, índices, constraints, row-level security, migrations, endpoints, infraestrutura (Seção 11; Seção 18 — Armazenamento).
- Constraints e garantia de unicidade persistida de `empresa_id` e `operacao_id` (ADR-001, Seção 17), `usuario_id`, `resultado_id` e `realidade_id` (ADR-004, Seção 13) e `registro_id` (Seção 18) — o formato UUID4 de cada identificador está definido, mas a garantia concreta de unicidade no banco de dados ainda não.
- Armazenamento técnico e preservação histórica dos resultados candidatos do Motor NSI e de seus eventuais reprocessamentos — inclusive se e como isso se relaciona com `saida_motor.json` (Seção 18 — Armazenamento). Esta pendência não é resolvida pela adoção de PostgreSQL para a Trajetória Contínua, cujo escopo é estritamente distinto.
- Distinção técnica persistida entre retry e reprocessamento intencional de uma execução do Motor — a política conceitual (Seção 18) estabelece a diferença de intenção, mas não define como ela é implementada ou armazenada.
- Tratamento de concorrência entre múltiplos processos/workers, além da garantia transacional já descrita para a Trajetória Contínua (Seção 18).
- Mecanismo técnico concreto de geração, empacotamento, criptografia e entrega do Pacote de Encerramento e Preservação Histórica (Seção 21): checksums, ZIP criptografado, link temporário e infraestrutura de envio.
- Destino técnico dos registros originais da Trajetória Contínua em PostgreSQL após o encerramento da relação (permanecem, são arquivados ou eliminados) — depende da Política Jurídica futura (Seção 21).
- Política Jurídica NSI própria — privacidade, retenção, atendimento a autoridades, exclusão ou anonimização exigida por lei, preservação para exercício ou defesa de direitos, acesso administrativo excepcional, prazos legais aplicáveis e auditoria das medidas jurídicas (Seção 21) — dependência externa nomeada, ainda não criada.
- Retenção das chaves de idempotência — prazo, mecanismo e critério de expurgo permanecem indefinidos (Seção 18).
- Implementação técnica da ADR-005 no Motor NSI (janelas, leituras, estados).

A ADR-006 está APROVADA E CONGELADA (Seção 22); estas pendências serão tratadas em sessões de arquitetura técnica futuras, registradas como evolução desta ADR quando necessário.

---

## 15. Dependências

- Depende da ADR-001 (Seção 4.2), que define o Portal Executivo do Cliente como plataforma.
- Depende da ADR-001, Seção 16 (Evolução Aprovada — Identidade Técnica da Empresa e da Operação), para o `operacao_id` — que compõe, junto ao tipo, a identidade da Leitura (ADR-005) e, transitivamente, da realidade recorrente — e para o `empresa_id`, que ancora a propriedade e o isolamento de cada `operacao_id` e de cada `usuario_id`, sem integrar a identidade da Leitura.
- Depende da ADR-004 (Decisão Arquitetural — Encerramento da Jornada de Inteligência Organizacional; §7.9; §7.17; "Decisão Arquitetural — Unidade da Jornada Cognitiva"), que originou esta ADR e cujos princípios de Observabilidade e Neutralidade Decisória são aqui reafirmados sem exceção.
- Depende da ADR-004, §7.26 (Identidade Técnica da Realidade Recorrente), para o `realidade_id`, que funciona como chave de agrupamento dos registros que formam a Trajetória Contínua — a Trajetória, por si só, não possui identidade técnica própria (Seção 11).
- Depende da ADR-004, Seção 12 (Evolução Aprovada — Identidade Técnica do Usuário), para o `usuario_id` exigido como autor de todo registro (Seção 10).
- Depende da ADR-005 (Princípio 4 — Independência Entre Leituras; Princípio 6 — Ausência de Comparação Automática; ciclo temporal de coleta), quanto à relação temporal, ao isolamento dos dados e à proibição de comparação automática entre leituras, aplicada por esta ADR à camada de Transformação.
- Depende da ADR-005, Seção 16 (Evolução Aprovada — Identidade Técnica da Leitura), para a identidade composta referenciada por cada realidade recorrente.
- Depende do Livro dos Princípios do NSI, especialmente "a tecnologia serve; não decide" (Capítulo 5) e "Compreensão Antes de Automação" (Princípio 3).
- A ADR-004 referencia esta ADR, por meio de suas Seções 14 e 15, quanto aos perfis autorizados a acessar a Jornada de Transformação, à autoria institucional e aos eventos de auditoria relacionados às declarações e correções da Tela 03.
- Depende de uma Política Jurídica NSI futura e própria (Seção 21), ainda não criada, para privacidade, retenção, atendimento a autoridades e demais obrigações legais — esta ADR fixa apenas os princípios; os detalhes jurídicos pertencem a esse documento futuro.

---

## 16. Itens Fora do Escopo

Ver Seção 2.2.

---

## 17. Referências

- `docs/architecture/ADR-001-operations-console.md` — define o Portal Executivo do Cliente como plataforma (Seção 4.2); Seção 16, identidade técnica da Empresa e da Operação (`empresa_id`, `operacao_id`).
- `docs/architecture/ADR-004-portal-executivo-cliente.md` — origem da Jornada de Transformação Organizacional (Decisão Arquitetural — Encerramento da Jornada de Inteligência Organizacional) e princípios reafirmados (§7.9; §7.17; "Decisão Arquitetural — Unidade da Jornada Cognitiva"); §7.26, Identidade Técnica da Realidade Recorrente; Seção 12, Identidade Técnica do Usuário.
- `docs/architecture/ADR-005-ciclo-temporal-coleta-leituras-independentes.md` — Princípio 4 (Independência Entre Leituras) e Princípio 6 (Ausência de Comparação Automática), quanto ao ciclo temporal de coleta, ao isolamento dos dados desta jornada e à proibição de comparação automática entre leituras, aplicada por esta ADR à camada de Transformação; Seção 16, identidade técnica da Leitura.
- `docs/principios/livro-dos-principios.md` — fundação filosófica: "a tecnologia serve; não decide" (Capítulo 5); "Compreensão Antes de Automação" (Princípio 3).

---

## 18. Evolução Aprovada — Formato de Identificadores, Armazenamento Definitivo e Política de Idempotência da Trajetória Contínua (2026-08-26)

Esta seção documenta uma evolução aprovada da ADR-006, complementando a Seção 11 (Schema Conceitual da Trajetória Contínua) e a Seção 14 (Pendências Técnicas, Visuais e Jurídicas Não Bloqueantes, atualizada nesta mesma data). Nenhuma decisão anteriormente aprovada nas Seções 1 a 17 é alterada; apenas a lista viva de pendências da Seção 14 é atualizada.

### Formato dos identificadores

Os seis identificadores técnicos da cadeia da Trajetória Contínua usam UUID4 completo, canônico, opaco, estável e imutável como formato técnico:

- `empresa_id` (ADR-001, Seção 17);
- `operacao_id` (ADR-001, Seção 17);
- `usuario_id` (ADR-004, Seção 13);
- `resultado_id` (ADR-004, Seção 13);
- `realidade_id` (ADR-004, Seção 13);
- `registro_id` (definido nesta ADR, Seção 11).

Este formato define representação e geração probabilisticamente única — não define, por si só, a garantia de unicidade persistida. Constraints de banco de dados, tratamento de colisão e o schema relacional concreto continuam pendentes (Seção 14).

### Ausência de identidade própria da Trajetória

- Reafirma-se, sem alterar a substância já registrada na Seção 11 ("Natureza da Trajetória"): a Trajetória Contínua não possui `trajetoria_id` nem qualquer outra identidade técnica própria. Ela é inteiramente derivada da coleção de registros que compartilham o mesmo `realidade_id`.

### Armazenamento definitivo — escopo estritamente limitado à Trajetória Contínua

- PostgreSQL é o armazenamento arquitetural definitivo dos registros da Trajetória Contínua (Seção 11) — não haverá solução provisória oficial em JSON ou SQLite para esses registros.
- Esta decisão é estritamente escopada aos registros da Trajetória Contínua (`registro_id`, e sua referência a `realidade_id` e `usuario_id`). Ela **não** decide, amplia ou sugere que a empresa, a Operação, o usuário, o resultado semântico candidato do Motor NSI (`resultado_id`) ou a saída do Motor NSI (`saida_motor.json`) já sejam ou venham a ser armazenados em PostgreSQL — cada uma dessas entidades depende de decisão arquitetural própria, ainda não tomada. `saida_motor.json` permanece exatamente como está.
- O schema relacional concreto (tabelas, colunas, chaves, constraints) que implementará este armazenamento em PostgreSQL não é definido nesta seção — permanece pendente (Seção 14).

### Regra de aplicação — Append-Only

- A aplicação comum aos registros da Trajetória Contínua é append-only: toda correção, mudança de posição ou nova declaração gera um novo registro, nunca a edição ou remoção de um registro existente — reafirmando, para a aplicação como um todo, o que a Seção 8 já estabelece por ato de declaração.
- Esta regra rege a operação normal do sistema. Uma eventual exceção decorrente de obrigação legal (ex.: direito ao esquecimento, ordem judicial de exclusão) não é decidida, autorizada nem desenhada por esta seção — permanece inteiramente pendente, junto às demais questões de privacidade, retenção e exclusão legal (Seção 14).

### Política de Idempotência

**Natureza e escopo lógico da chave**

- A chave de idempotência identifica uma intenção técnica de criação — nunca a entidade criada. Ela é explícita, opaca e estritamente separada do ID da entidade.
- O escopo lógico de uma chave é composto por: o contexto de empresa (`empresa_id`), quando aplicável; o tipo de operação de criação (ex.: cadastro de empresa, criação de Operação, cadastro de usuário, execução do Motor, ato humano confirmado, revelação); e a própria chave opaca daquela intenção. Este escopo é conceitual — não define schema, tabela ou coluna concreta.
- Conteúdo, nome, e-mail, telefone, slug, `codigo_catalogo`, timestamp ou hash nunca são usados para inferir duplicidade — apenas a chave de idempotência, comparada dentro do seu escopo.

**Comportamento geral sob retry e conflito**

- No mesmo escopo, a mesma chave acompanhada da mesma solicitação retorna o resultado originalmente persistido.
- A mesma chave acompanhada de conteúdo ou parâmetros diferentes é rejeitada como conflito.
- Uma nova intenção legítima usa uma nova chave, mesmo que o conteúdo seja idêntico ao de uma intenção anterior — nenhuma deduplicação por conteúdo jamais ocorre.

**Aplicação às seis criações da cadeia**

*Empresa*
- Um retry do mesmo cadastro retorna o mesmo `empresa_id`.
- Uma nova empresa usa uma nova chave, mesmo com nome idêntico ao de uma empresa já cadastrada.

*Operação*
- Um retry da mesma criação retorna o mesmo `operacao_id`.
- Uma nova Operação usa uma nova chave.

*Usuário*
- Um retry do mesmo cadastro retorna o mesmo `usuario_id`.
- Um novo usuário usa uma nova chave.
- Nome, e-mail ou telefone não determinam duplicidade — apenas a chave de idempotência.

*Motor (execução de processamento)*
- Uma solicitação de processamento possui uma única chave de idempotência e pode produzir vários `resultado_id`.
- Um retry técnico da mesma execução retorna exatamente o mesmo conjunto de `resultado_id` já produzido.
- Um reprocessamento intencional usa uma nova chave e produz um novo conjunto de `resultado_id`.
- A persistência técnica dessa idempotência e o histórico das execuções e reprocessamentos do Motor continuam pendentes (Seção 14) — esta seção não define onde ou como esse histórico é armazenado, nem afirma que PostgreSQL garante a idempotência do Motor: a garantia transacional descrita adiante é escopada exclusivamente aos registros da Trajetória Contínua.

*Realidade (revelação)*
- Um retry da revelação retorna o mesmo `realidade_id` já existente.
- Mesmo que a revelação seja tentada novamente com uma chave de idempotência nova, a cardinalidade `resultado_id` → 0..1 `realidade_id` (ADR-004, Seção 13) prevalece: uma chave nova nunca autoriza a criação de um segundo `realidade_id` a partir do mesmo `resultado_id`. A invariante de domínio tem precedência sobre a semântica técnica de idempotência.

*Registro*
- Um retry do mesmo ato humano confirmado (Seção 8) retorna o mesmo `registro_id` já criado.
- Uma nova confirmação humana cria um novo `registro_id`, mesmo com texto idêntico ao de um registro anterior — consistente com a Seção 8 ("O NSI não decide que uma declaração posterior corrige, invalida ou supera uma anterior").

**Reprocessamento do Motor — o que esta seção não decide**

- O reprocessamento intencional de uma execução do Motor cria uma nova execução e novos `resultado_id` — não altera nem apaga os candidatos produzidos por execuções anteriores.
- A preservação histórica de candidatos de execuções anteriores, o critério de seleção do conjunto aplicável quando existir mais de um, e a eventual designação de uma versão canônica entre múltiplos conjuntos de `resultado_id` permanecem inteiramente pendentes (Seção 14) — esta seção não declara que os conjuntos antigos e novos simplesmente coexistem como solução já definida; apenas que nenhum deles é apagado.

**Garantia transacional**

- PostgreSQL garante persistência e idempotência exclusivamente para os registros da Trajetória Contínua, dentro do escopo aprovado nesta seção (Armazenamento definitivo).
- Esta garantia não se estende aos candidatos do Motor NSI, nem decide, por si só, que empresa, Operação, usuário ou resultado candidato já serão armazenados em PostgreSQL — cada uma dessas entidades depende de decisão arquitetural própria, ainda não tomada.

### O que não mudou

- Nenhuma decisão anteriormente aprovada nas Seções 1 a 17 é alterada; apenas a lista viva de pendências da Seção 14 é atualizada.
- Nenhuma definição de schema relacional, tabela, coluna, constraint ou endpoint — apenas política conceitual de idempotência e de formato de identificador.
- Nenhuma decisão sobre concorrência entre múltiplos processos/workers além da garantia transacional já descrita.
- O armazenamento e o histórico técnico das execuções, dos resultados candidatos e dos reprocessamentos do Motor NSI permanecem pendentes.
- A retenção das chaves de idempotência (prazo, mecanismo, critério de expurgo) permanece pendente, junto à política de privacidade e retenção (Seção 14) — nenhum prazo numérico é definido nesta seção.

**Origem desta decisão:**
- Consolidada nesta sessão (2026-08-26), a partir da arquitetura já aprovada do schema conceitual da Trajetória Contínua (Seção 11) e da identidade técnica registrada em ADR-001 (Seção 17) e ADR-004 (Seção 13).

---

## 19. Evolução Aprovada — Autoria Institucional e Correção de Registros (2026-08-26)

Esta seção documenta uma evolução aprovada da ADR-006, a partir da consolidação de governança, acesso, auditoria e encerramento do Portal NSI. Esta seção não substitui os princípios de autoria, granularidade, preservação e correção definidos nas Seções 7, 8, 10 e 11; resolve a autorização institucional e detalha o caminho excepcional posterior a uma tentativa bloqueada.

### Autorização institucional

- Gestores e Administradores ativos (ADR-004, Seção 14) podem declarar em nome da organização por consequência do próprio perfil — não por autorização concedida caso a caso.
- Usuários Comuns não declaram em nome da organização.
- Esta regra resolve, especificamente, a pendência da Seção 10 quanto a "quem está autorizado a declarar em nome da organização" — nenhuma outra frase da Seção 10 é alterada: a marcação institucional continua explícita, opcional e nunca automática; o `usuario_id` continua, sempre, o autor técnico do registro.
- O NSI não presume representação, intenção ou deliberação tácita como fato observável. O sistema registra apenas atos humanos efetivamente praticados.

### Correção, contestação e tentativa de alteração

- Nenhum Usuário Comum, Gestor ou Administrador pode editar ou excluir uma declaração já confirmada — reafirmando, sem exceção, as Seções 7, 8 e 11.
- **Caminho normal de correção:** uma correção, contestação, explicação adicional ou mudança de posição gera um novo registro, livremente, sem necessidade de autorização de terceiro — exatamente como já definido nas Seções 7 e 8. O registro anterior permanece intacto.
- **Caminho excepcional — tentativa de alteração ou exclusão do original:** se alguém tentar editar ou excluir um registro já confirmado, essa tentativa é bloqueada e auditada (ADR-004, Seção 15), e os Administradores são notificados.
- Depois de uma tentativa bloqueada, a criação de um novo registro de correção ou contestação associado a esse incidente específico exige a autorização de um Administrador.
- Essa autorização nunca permite modificar ou excluir o registro original — apenas libera a criação de um novo registro, pelo mesmo mecanismo de acréscimo já congelado.
- A aprovação ou a recusa dessa autorização também fica auditada.
- O gatilho de autorização do Administrador se aplica exclusivamente ao caminho excepcional (tentativa de alteração ou exclusão do original) — nunca ao caminho normal de correção por acréscimo, que permanece livre.

### Verdade e observabilidade

- Nenhuma declaração, decisão, correção, tentativa ou evento relevante é ocultado, suavizado, reescrito ou apagado na operação normal.
- O NSI não julga se alguém agiu bem ou mal, com eficiência ou ineficiência, boa-fé ou má-fé, e não atribui culpa. Avaliações, julgamentos e responsabilizações pertencem exclusivamente à empresa, a seus representantes humanos e às autoridades competentes — reafirmando a Fronteira Epistemológica já congelada (Seção 12).
- Exceções exigidas por lei ao regime de preservação serão executadas formalmente, de maneira restrita e auditável, conforme a Política Jurídica futura (Seção 21) — nunca como uma exceção genérica ou discricionária.

### O que não mudou

- Esta seção não substitui os princípios de autoria, granularidade, preservação e correção definidos nas Seções 7, 8, 10 e 11; resolve a autorização institucional e detalha o caminho excepcional posterior a uma tentativa bloqueada.
- O caminho normal de correção continua sendo, para todo autor, a simples criação de um novo registro — nunca uma aprovação prévia.

**Origem desta decisão:**
- Consolidação aprovada de governança, acesso, auditoria e encerramento do Portal NSI (2026-08-26).

---

## 20. Evolução Aprovada — Detalhamento do Acesso à Tela 03 (2026-08-26)

Esta seção documenta uma evolução aprovada da ADR-006, detalhando um item específico que a Seção 9 (Transição entre o Sexto Cartão e a Tela 03 — Modelo Combinado) explicitamente deixou para decisão futura: o texto do convite de acesso. Nenhuma outra frase da Seção 9 é alterada.

- Depois da conclusão do Sexto Cartão daquela realidade, o Portal oferece o acesso com o texto: "Acessar Jornada de Transformação".
- O texto não presume mudança, plano ou obrigação de agir.
- Não há redirecionamento automático — entrar exige decisão humana explícita, exatamente como já definido na Seção 9.
- O gestor decide se e quando entra.
- O acesso permanece disponível: no Sexto Cartão concluído; e na Home, dentro da área da realidade correspondente.
- Cada realidade e cada Leitura mantêm acesso próprio e independente — restatement do Princípio 8 (Seção 4) e do Princípio 6 da ADR-005, já congelados; esta seção não redefine essa regra, apenas a reafirma no contexto do convite de acesso.
- A ausência de entrada não representa atraso, abandono, fracasso ou ineficiência — reafirmando a Seção 9.

### Escopo desta evolução em relação à Seção 9

- Esta seção resolve, especificamente, o item "texto do convite ou botão" da lista "Esta decisão não define" da Seção 9.
- Todos os demais itens dessa lista continuam indefinidos: rota técnica; layout; posição; cores; dimensões; componentes visuais; mecanismo concreto de navegação.

**Origem desta decisão:**
- Consolidação aprovada de governança, acesso, auditoria e encerramento do Portal NSI (2026-08-26).

---

## 21. Evolução Aprovada — Encerramento da Relação e Pacote de Preservação Histórica (2026-08-26)

Esta seção documenta uma evolução aprovada da ADR-006. Ela define: o fechamento do acesso ao Portal ao final da relação comercial com a empresa; a entrega do Pacote de Encerramento e Preservação Histórica; os prazos operacionais de download e reemissão desse pacote; e a dependência de uma Política Jurídica futura para a retenção e o destino definitivo dos registros originais. Ela não altera nenhuma decisão já congelada — introduz um evento novo, posterior a todos os já descritos.

### Distinção conceitual

- O encerramento da relação com a NSI é um evento contratual e administrativo de fechamento de acesso ao Portal — não é uma conclusão cognitiva da Jornada de Transformação. A Trajetória Contínua (Seção 7) continua sem conclusão obrigatória; o encerramento da relação não declara nenhuma trajetória como "concluída", "bem-sucedida" ou "malsucedida".

### Pacote de Encerramento e Preservação Histórica

Ao encerrar a relação, a empresa recebe o "Pacote de Encerramento e Preservação Histórica NSI", contendo: relatório completo em PDF/A; auditoria completa em CSV; dados estruturados em JSON; declarações, leituras e arquivos gerados; PDFs anteriormente produzidos; manifesto de integridade; checksums; comprovante de entrega; pacote ZIP criptografado.

### Prazo de download

- A empresa terá 30 dias corridos para baixar o pacote, com o prazo visível no Portal.
- Se o download integral ocorrer antes do final dos 30 dias, o Portal será fechado imediatamente.
- O simples clique no botão não conta como download — somente a transferência integral, concluída e tecnicamente validada fecha o Portal.
- Download interrompido ou incompleto não fecha o Portal.

### Comprovante

- Após o download integral, é gerado automaticamente um comprovante contendo: empresa; usuário que realizou o download; data e hora; identificação do pacote; código de integridade; confirmação do fechamento do Portal.
- O comprovante é enviado ao e-mail institucional da empresa e a todos os Administradores ativos.

### Ausência de download

- Se o pacote não for baixado nos 30 dias, o Portal é fechado.
- A NSI envia automaticamente um link criptografado e temporário, com validade de sete dias corridos, ao e-mail institucional e a todos os Administradores ativos.
- Depois do vencimento, um Administrador autenticado pode solicitar novo link. Toda reemissão fica auditada.
- A NSI não mantém o Portal operacional apenas porque a empresa não realizou o download.

### Reemissão e retenção do pacote completo

- O pacote completo fica disponível para reemissão por 90 dias após o encerramento.
- Depois dos 90 dias, o pacote completo é eliminado.
- Permanece somente o conjunto estritamente necessário para: obrigações legais ou regulatórias; exercício ou defesa de direitos; atendimento a autoridades competentes; comprovação da entrega; comprovação da integridade do material.
- Esse conjunto fica isolado, com acesso restrito — sem reutilização comercial, nova análise ou reaproveitamento operacional.
- Ao final do prazo legal aplicável, os dados são eliminados ou anonimizados conforme obrigação jurídica.

### O que esta seção não define

- O destino dos registros originais da Trajetória Contínua em PostgreSQL após o encerramento — se permanecem, são arquivados ou são eliminados — não é definido por esta seção. Este ponto depende da Política Jurídica futura, abaixo, e essa indefinição não impede o congelamento conceitual desta ADR (Seção 22): o princípio de preservação e o tratamento da exceção legal já estão fixados; o mecanismo concreto de retenção dos dados originais é, por natureza, um detalhe de implementação subordinado a essa política.

### Dependência — Política Jurídica futura

Será criada uma Política Jurídica própria, externa a esta ADR, para: privacidade; retenção; atendimento a autoridades; exclusão ou anonimização exigida por lei; preservação para exercício ou defesa de direitos; acesso administrativo excepcional; prazos legais aplicáveis; auditoria das medidas jurídicas.

Esta ADR fixa somente os princípios de verdade, preservação, rastreabilidade, acesso controlado e cumprimento legal (Seção 19). Não define nenhum prazo jurídico além dos prazos operacionais expressamente aprovados nesta seção (sete, trinta e noventa dias).

**Origem desta decisão:**
- Consolidação aprovada de governança, acesso, auditoria e encerramento do Portal NSI (2026-08-26).

---

## 22. Congelamento da ADR-006 (2026-08-26)

Com as Seções 19, 20 e 21 aprovadas, e com a auditoria de consistência registrada nesta sessão (verificação de contradições, distinção entre regra arquitetural e detalhe de implementação futura, preservação da autoria humana visível e do regime append-only, e tratamento das obrigações legais como exceção formal, restrita e auditável), a ADR-006 passa do status EM ARQUITETURA para APROVADA E CONGELADA.

### Verificação de ausência de pendência conceitual

Todas as pendências remanescentes, listadas na Seção 14 (Pendências Técnicas, Visuais e Jurídicas Não Bloqueantes), são de uma das duas naturezas seguintes — nenhuma delas é uma lacuna conceitual da arquitetura da Tela 03:

- **Implementação técnica ou visual:** rota técnica; layout detalhado; componentes visuais; dimensões; cores; tabelas SQL; colunas; índices; constraints; row-level security; infraestrutura; migrations; endpoints; implementação do Portal; implementação técnica da ADR-005 no Motor NSI; mecanismo técnico concreto de geração e entrega do Pacote de Preservação Histórica.
- **Dependência de uma Política Jurídica futura, já nomeada como tal** (Seção 21): privacidade, retenção, exclusão legal e demais obrigações jurídicas.

### O que o congelamento significa

- Os princípios fundacionais, o schema conceitual, a governança de perfis e autoria (referenciando a ADR-004), o mecanismo de correção, a transição de acesso à Tela 03, e o encerramento da relação com o Pacote de Preservação Histórica estão aprovados e estáveis.
- Mudanças futuras a qualquer decisão conceitual já congelada nesta ADR só poderão ocorrer por evolução arquitetural formalmente documentada — no mesmo método já usado por esta e por todas as demais ADRs do projeto: preservação do texto histórico, registro explícito do que muda e do que não muda, e aprovação própria.
- Sessões de arquitetura técnica futuras (schema relacional concreto, componentes visuais, implementação do Portal, Política Jurídica) serão registradas como evoluções desta ADR, sem reabrir sua arquitetura conceitual.

**Origem desta decisão:**
- Consolidação aprovada de governança, acesso, auditoria e encerramento do Portal NSI (2026-08-26).
