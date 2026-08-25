# ADR-006 — Jornada de Transformação Organizacional (Tela 03)

## Metadados

| Campo | Valor |
|---|---|
| Status | EM ARQUITETURA |
| Data | 2026-08-25 |
| Versão de referência do sistema | `v1.1.0-fonte-unica-webhook-motor` |
| Commit de referência | `998387f` |
| Branch | `master` |
| Escopo desta ADR | Arquitetura — nenhuma implementação de código, frontend ou componente visual |

> **Nota de processo:** ADR aberta para cumprir a dependência registrada na ADR-004 ("Decisão Arquitetural — Encerramento da Jornada de Inteligência Organizacional"): *"Após o Sexto Cartão, inicia-se uma jornada conceitualmente independente, denominada Jornada de Transformação Organizacional... sua arquitetura será tratada em sessão futura."* Esta ADR é essa sessão futura. Registra exclusivamente os princípios fundacionais já decididos — não define cartões, telas internas, layout, fluxos ou funcionalidades.
>
> **Esta ADR não está congelada.** Os princípios fundacionais descritos nas Seções 4, 5, 6 e 7 foram aprovados nesta sessão de decisão. A arquitetura completa da Tela 03 permanece **EM ARQUITETURA** — as pendências registradas na Seção 9 continuam abertas e serão tratadas em sessão futura, mediante aprovação própria.

---

## 1. Objetivo

Registrar os princípios fundacionais da Jornada de Transformação Organizacional — **Tela 03** do Portal Executivo do Cliente — a etapa que sucede o encerramento da Jornada de Inteligência Organizacional no Sexto Cartão (ADR-004), sem implementar, sem definir estrutura interna e sem alterar nenhuma decisão já congelada nas ADRs anteriores.

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
- Fronteira epistemológica da jornada ("Limite pela Fonte da Afirmação").
- Regra de acesso independente à Tela 03 para cada realidade recorrente revelada pela Leitura de Excedência — sem comparação, identificação de equivalência ou vinculação automática com realidades reveladas pela Leitura Inicial.

### 2.2 Fora do escopo desta decisão

- Criação de cartões ou etapas da Jornada de Transformação.
- Layout e componentes visuais.
- KPIs, gráficos e filtros.
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
- Se um gestor humano declarar que percebe relação, semelhança ou continuidade entre realidades de leituras diferentes, essa percepção permanece apenas como declaração humana atribuída, subordinada ao "Limite pela Fonte da Afirmação" (Seção 7).
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
- A posição declarada permanece subordinada ao "Limite pela Fonte da Afirmação" (Seção 7).
- O NSI registra e torna observável a declaração, mas não a interpreta.
- A pergunta fundadora não define cartões, etapas, campos, fluxo ou layout.

---

## 7. Fronteira Epistemológica — Limite pela Fonte da Afirmação

**O que compõe a trajetória:** qualquer informação cuja origem seja uma declaração humana explícita (gestor ou organização): decisões tomadas, ações concluídas, status alcançados, datas e explicações — sempre atribuídas a quem declarou.

**O que precisa ser declarado por pessoas:** toda informação que estabeleça sentido, motivo, avaliação, relação de causa ou resultado. O sistema não pode originar, completar ou parafrasear esse conteúdo.

**O que o NSI pode tornar observável:** quais declarações existem, em que ordem foram feitas e seu conteúdo literal — sempre visivelmente atribuído a seu autor humano e à data. Nada afirmado pelo próprio sistema é apresentado como fato sobre a transformação.

**O que o NSI está proibido de inferir, concluir ou avaliar:** qualquer afirmação não atribuível, palavra por palavra, a uma declaração humana — incluindo vínculos causais entre entradas, julgamentos de sucesso, fracasso ou eficiência, ou qualquer frase de síntese gerada pelo sistema.

**Como se impede que sequência temporal seja apresentada como causa e efeito:** como o sistema só exibe declarações literais e suas datas, nunca gerando linguagem conectiva própria, nenhuma frase de autoria do sistema pode afirmar que um evento causou outro.

**Como se impede a classificação automática de sucesso, fracasso, eficiência ou ineficiência:** nenhum campo, ícone, cor ou rótulo gerado pelo sistema pode classificar mudança, ausência de mudança, conclusão ou atraso — repete, nesta jornada, a mesma fronteira já congelada para a Jornada de Inteligência Organizacional (ADR-004, §7.17): o sistema organiza evidências, a interpretação pertence ao gestor.

**Atribuição visível da fonte humana:** toda declaração exibida permanece visivelmente atribuída a seu autor humano e à data em que foi feita — nunca apresentada como afirmação neutra ou de autoria do sistema.

**Distinção entre declaração humana e conclusão do sistema:** tudo o que o sistema apresenta como fato é estritamente: (a) que uma declaração existe; (b) seu conteúdo literal; (c) sua data; (d) seu autor. Qualquer interpretação, julgamento ou vínculo causal só existe se for, ele próprio, uma declaração humana citada — nunca uma afirmação do sistema.

---

## 8. Decisões Aprovadas Nesta Sessão

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
11. Fronteira epistemológica — Limite pela Fonte da Afirmação (Seção 7).

## 9. Pendências Ainda em Arquitetura

- Estrutura interna: se haverá cartões ou outro formato.
- Quantidade e ordem de possíveis etapas.
- Arquitetura visual e navegação (layout, botão, transição, rota, componentes).
- Schema técnico dos registros isolados (Princípio 7).

Nenhuma dessas pendências foi decidida nesta ADR. A arquitetura completa da Tela 03 permanece EM ARQUITETURA até que cada uma delas seja tratada e aprovada em sessão futura.

---

## 10. Dependências

- Depende da ADR-001 (Seção 4.2), que define o Portal Executivo do Cliente como plataforma.
- Depende da ADR-004 (Decisão Arquitetural — Encerramento da Jornada de Inteligência Organizacional; §7.9; §7.17; "Decisão Arquitetural — Unidade da Jornada Cognitiva"), que originou esta ADR e cujos princípios de Observabilidade e Neutralidade Decisória são aqui reafirmados sem exceção.
- Depende da ADR-005 (Princípio 4 — Independência Entre Leituras; Princípio 6 — Ausência de Comparação Automática; ciclo temporal de coleta), quanto à relação temporal, ao isolamento dos dados e à proibição de comparação automática entre leituras, aplicada por esta ADR à camada de Transformação.
- Depende do Livro dos Princípios do NSI, especialmente "a tecnologia serve; não decide" (Capítulo 5) e "Compreensão Antes de Automação" (Princípio 3).
- A ADR-004 passará a referenciar esta ADR minimamente quanto à existência da Tela 03 — apenas depois que esta ADR for aprovada; nenhuma alteração é feita agora.

---

## 11. Itens Fora do Escopo

Ver Seção 2.2.

---

## 12. Referências

- `docs/architecture/ADR-001-operations-console.md` — define o Portal Executivo do Cliente como plataforma (Seção 4.2).
- `docs/architecture/ADR-004-portal-executivo-cliente.md` — origem da Jornada de Transformação Organizacional (Decisão Arquitetural — Encerramento da Jornada de Inteligência Organizacional) e princípios reafirmados (§7.9; §7.17; "Decisão Arquitetural — Unidade da Jornada Cognitiva").
- `docs/architecture/ADR-005-ciclo-temporal-coleta-leituras-independentes.md` — Princípio 4 (Independência Entre Leituras) e Princípio 6 (Ausência de Comparação Automática), quanto ao ciclo temporal de coleta, ao isolamento dos dados desta jornada e à proibição de comparação automática entre leituras, aplicada por esta ADR à camada de Transformação.
- `docs/principios/livro-dos-principios.md` — fundação filosófica: "a tecnologia serve; não decide" (Capítulo 5); "Compreensão Antes de Automação" (Princípio 3).
