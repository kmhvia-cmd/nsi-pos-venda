# ADR-003 — Sistema Editorial Visual do NSI

## Metadados

| Campo | Valor |
|---|---|
| Status | Aprovado |
| Data | 2026-07-03 |
| Versão de referência do sistema | `v1.1.0-fonte-unica-webhook-motor` |
| Tag de referência da marca | `v1.0.0-branding-fundacao` |
| Commit de referência | `adf482e` |
| Branch | `master` |
| Escopo desta ADR | Abertura arquitetural da Sprint 2 — nenhuma cor, tipografia, grid, componente ou prompt é definido nesta ADR |

> **Nota de processo:** aprovado como documento de abertura da Sprint 2 — sem revisão detalhada linha por linha, por decisão explícita de quem aprova. As decisões da Seção 7 estão congeladas a partir desta versão.

---

## 1. Objetivo

Formalizar arquiteturalmente a abertura da **Sprint 2 — Sistema Editorial Visual do NSI**, mantendo exatamente a mesma metodologia já aplicada ao software e à Fundação da Marca (ADR-001 e ADR-002): **arquitetura primeiro, implementação depois, congelamento somente após aprovação**.

Esta ADR registra que o projeto entra agora na fase de construção da linguagem visual do NSI. Ela não define essa linguagem — define **as condições que qualquer decisão visual futura precisa satisfazer** para ser considerada legítima. O objetivo desta Sprint é construir uma **linguagem visual proprietária** para o NSI, não adotar tendências de mercado nem produzir peças isoladas sem arquitetura por trás.

---

## 2. Escopo

### 2.1 Escopo desta decisão

- Abertura formal da Sprint 2 — Sistema Editorial Visual do NSI.
- Divisão da Sprint em 8 blocos independentes e sequenciais (Seção 4).
- Registro dos princípios arquiteturais que regem toda decisão visual futura do NSI (Seção 5).
- Confirmação de que o Bloco 01 — Arquitetura Visual (`docs/branding/09-sistema-editorial-visual.md`) é a primeira entrega da Sprint, hoje em revisão.

### 2.2 Fora do escopo desta decisão

- Definição de cor, tipografia, grid, margens, componentes, layouts ou prompts — matéria dos Blocos 02 a 08, não iniciados.
- Qualquer peça de comunicação publicável.
- Qualquer alteração às decisões já congeladas na ADR-001 ou na ADR-002.
- Qualquer alteração ao Motor, ao Operations Console ou ao Portal Executivo do Cliente.

---

## 3. Contexto

A Sprint 1 — Fundação da Marca está congelada (ADR-002, commit `b437b55`, registro de encerramento em `docs/branding/SPRINT_01_FREEZE.md`, commit `adf482e`, tag `v1.0.0-branding-fundacao`). O Livro da Marca — filosofia, manifesto, propósito, posicionamento, missão/visão/valores, diferenciais, tom de voz, princípios editoriais — está estabelecido como fonte única de verdade sobre o que o NSI é e como fala.

O NSI agora precisa de uma linguagem visual que traduza essa fundação em forma, sem se tornar uma narrativa visual desconectada dela — o mesmo risco que a ADR-002 já preveniu para o texto se aplica agora à imagem. Por isso, antes de qualquer cor ou tipografia, foi produzido `docs/branding/09-sistema-editorial-visual.md` (Bloco 01 — Arquitetura Visual): a filosofia visual, os princípios arquiteturais de forma, a personalidade da marca, as sensações obrigatórias e proibidas, a estratégia de reconhecimento sem depender do logotipo, e um checklist de aprovação — tudo isso sem definir uma única cor ou fonte.

Esta ADR existe para registrar essa abertura como decisão arquitetural formal, não como início informal de produção visual.

---

## 4. Decisão — Estrutura da Sprint 2 em Blocos

A Sprint 2 é dividida em **8 blocos independentes e sequenciais**. Nenhum bloco se inicia antes do anterior estar aprovado — a mesma disciplina de fases já usada na implementação técnica do Motor (`plano_implementacao_nsi.md`), onde "uma fase só começa após a anterior estar validada".

| Bloco | Nome | Entrega | Status |
|---|---|---|---|
| 01 | Arquitetura Visual | `docs/branding/09-sistema-editorial-visual.md` | Concluído |
| 02 | Grid e Sistema de Margens | `docs/branding/11-grid-e-zona-de-seguranca.md` | Aprovado provisoriamente |
| 03 | Tipografia | `docs/branding/13-tipografia-oficial.md` | Aprovado |
| 04 | Paletas Oficiais | `docs/branding/14-paletas-oficiais.md` | Aprovado |
| 05 | Componentes | `docs/branding/10-componentes-visuais.md` | Concluído (antecipado — exceção deliberada, ver observação do Princípio 4) |
| 06 | Biblioteca de Composição (renomeado de "Biblioteca Oficial de Layouts") | `docs/branding/15-biblioteca-de-composicao.md` | Aprovado |
| 07 | Prompt Master de Geração | — | Fora do escopo documental desta etapa |
| 08 | Biblioteca Oficial de Conteúdo | — | Fora do escopo documental desta etapa |

Cada bloco aprovado gera seu próprio documento em `docs/branding/`, seguindo a numeração sequencial já estabelecida na Sprint 1 (mesma justificativa da ADR-002, Seção 4: cada tema evolui em ritmo próprio e mantém o histórico do Git limpo por tema).

---

## 5. Princípios Arquiteturais Aprovados

### Princípio 1 — Derivação Integral da Fundação da Marca

O Sistema Editorial Visual deriva integralmente da Fundação da Marca (ADR-002). Nenhuma decisão visual desta Sprint nasce isolada; toda escolha remonta a um documento já registrado em `docs/branding/01` a `08`.

### Princípio 2 — Não Contradição com a ADR-002

Nenhuma decisão visual pode contrariar qualquer decisão já congelada na ADR-002. Em caso de conflito aparente entre uma escolha visual e uma decisão da Fundação da Marca, é a escolha visual que é revisada — a ADR-002 não é reaberta por conveniência estética.

### Princípio 3 — Derivação a partir dos Princípios Filosóficos Aprovados

Todo componente visual — cor, tipografia, grid, layout, componente, prompt — é derivado explicitamente de um princípio filosófico já registrado em `docs/branding/09-sistema-editorial-visual.md`. Nenhum componente visual entra no sistema por preferência estética isolada de quem o produz.

### Princípio 4 — Construção por Blocos Independentes e Sequenciais

A Sprint 2 avança pelos 8 blocos definidos na Seção 4, em ordem, sem paralelismo e sem pular etapa. Um bloco começa somente depois que o anterior está aprovado.

> **Observação:** a ordem de implementação dos blocos poderá ser ajustada durante a Sprint quando houver dependência arquitetural entre eles, desde que nenhuma decisão congelada seja violada. Essa flexibilidade existe apenas para facilitar a construção do Sistema Editorial Visual e reduzir retrabalho. A sequência lógica da Seção 4 permanece a referência oficial; antecipações de bloco são exceções deliberadas, registradas como tal quando ocorrerem — não uma reordenação da arquitetura.

### Princípio 5 — A Forma Nunca Compete com a Mensagem

Toda decisão visual existe para reforçar o conteúdo que acompanha — nunca para chamar mais atenção do que ele. Uma peça visualmente impressionante que ofusca a mensagem que carrega é uma peça reprovada, independentemente da qualidade estética isolada da forma.

### Princípio 6 — A Identidade Visual Deve Sobreviver ao Tempo

Toda decisão de identidade visual é avaliada pela pergunta "isso ainda vai parecer elegante daqui a cinco anos?" — nunca por "isso está atual agora?". Consistente com o Princípio 6 da ADR-002 (Consistência de Longo Prazo) e com o Princípio da Atemporalidade já registrado em `docs/branding/09-sistema-editorial-visual.md`, Capítulo 3.

---

## 6. Governança

- Nenhum bloco (Seção 4) se inicia sem que o bloco anterior esteja formalmente aprovado.
- Toda decisão visual produzida em qualquer bloco desta Sprint deve ser rastreável até um dos seis princípios da Seção 5.
- Conflito entre uma decisão visual proposta e qualquer decisão já congelada nas ADR-001 ou ADR-002 é resolvido a favor da decisão já congelada, sem exceção.
- Alterações a qualquer documento produzido nesta Sprint seguem o mesmo processo de revisão do restante do repositório.
- Qualquer nova decisão estrutural que surja durante a Sprint 2 e não esteja coberta por esta ADR é registrada como ADR subsequente, mantendo a numeração sequencial.

---

## 7. Decisões Congeladas

As decisões abaixo estão congeladas e aprovadas a partir desta versão do ADR.

1. A Sprint 2 — Sistema Editorial Visual do NSI está formalmente aberta.
2. O Sistema Editorial Visual deriva integralmente da Fundação da Marca (ADR-002); nenhuma decisão visual pode contrariá-la.
3. Todo componente visual é derivado explicitamente de um princípio filosófico já aprovado (`docs/branding/09-sistema-editorial-visual.md`).
4. A Sprint 2 é dividida em 8 blocos independentes e sequenciais (Seção 4); nenhum bloco se inicia antes do anterior estar aprovado.
5. A forma nunca pode competir com a mensagem — toda decisão visual existe para reforçar o conteúdo, nunca para se sobrepor a ele.
6. A identidade visual deve sobreviver ao tempo — nenhuma decisão visual persegue tendência momentânea.
7. A Sprint 2 não produz apenas layouts: produz um **Sistema Editorial Visual Proprietário** do NSI.

---

## 8. Dependências

- Depende da Fundação da Marca congelada (ADR-002; registro de encerramento `docs/branding/SPRINT_01_FREEZE.md`; tag `v1.0.0-branding-fundacao`).
- Depende da aprovação do Bloco 01 (`docs/branding/09-sistema-editorial-visual.md`) antes de iniciar o Bloco 02.
- Cada bloco subsequente (03 a 08) depende da aprovação formal de todos os blocos anteriores.

---

## 9. Itens Fora do Escopo

- Definição de cor, tipografia, grid, margens, componentes, layouts ou prompts — matéria dos Blocos 02 a 08.
- Qualquer peça de comunicação publicável.
- Qualquer alteração às decisões já congeladas na ADR-001 ou na ADR-002.
- Qualquer alteração em `engine/`, `processors/`, `models/`, `outputs/`, `confidence/` ou nas plataformas definidas na ADR-001.

---

## 10. Referências

- `docs/architecture/ADR-002-brand-foundation.md` — Fundação da Marca, da qual este Sistema Editorial Visual deriva integralmente.
- `docs/branding/09-sistema-editorial-visual.md` — Bloco 01, Arquitetura Visual, em revisão.
- `docs/branding/SPRINT_01_FREEZE.md` — registro de encerramento da Sprint 1.

---

> **Registro final:** a Sprint 2 não produzirá apenas layouts. Ela produzirá um **Sistema Editorial Visual Proprietário** do NSI — uma linguagem visual própria, derivada da Fundação da Marca, construída para permanecer reconhecível e consistente por muitos anos, não para atender a uma campanha ou tendência pontual.
