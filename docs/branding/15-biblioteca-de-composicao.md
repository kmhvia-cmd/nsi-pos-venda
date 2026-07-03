# Biblioteca de Composição do NSI

**Deriva de:** [`10-componentes-visuais.md`](10-componentes-visuais.md), [`11-grid-e-zona-de-seguranca.md`](11-grid-e-zona-de-seguranca.md), [`12-sistema-modular-de-composicao.md`](12-sistema-modular-de-composicao.md), `docs/architecture/ADR-003-sistema-editorial-visual.md` (Bloco 06 — renomeado de "Biblioteca Oficial de Layouts" para "Biblioteca de Composição", por coerência com a decisão de não usar templates registrada em `12-sistema-modular-de-composicao.md`).
**Status:** Sprint 2 — Aprovado. Corresponde ao Bloco 06 da ADR-003, Seção 4. Último documento estrutural desta etapa da Sprint 2.
**Natureza:** Arquitetura de catálogo. Nenhum layout, exemplo gráfico, cor ou tipografia concreta é definido aqui — apenas a estrutura que organiza os padrões de composição válidos.

---

## Objetivo

Definir o que é a Biblioteca de Composição do NSI e como ela se organiza — não seu conteúdo visual, que só existirá quando as primeiras peças reais forem produzidas na fase de prototipação. Este é o último documento estrutural antes de o NSI parar de documentar e começar a construir.

---

## 1. O que é a Biblioteca de Composição

Um catálogo de **padrões de composição válidos** — nunca uma coleção de arquivos prontos para reaproveitar. Cada padrão é uma forma reconhecida de organizar componentes (`10-componentes-visuais.md`) dentro das zonas do grid (`11-grid-e-zona-de-seguranca.md`), seguindo as regras do Sistema Modular de Composição (`12-sistema-modular-de-composicao.md`).

## 2. Diferença entre Biblioteca de Composição e Biblioteca de Templates

Um template é um arquivo fixo que se reaproveita, produzindo repetição — exatamente o que a ADR-003 e `12-sistema-modular-de-composicao.md` já recusaram. Um padrão de composição é uma **regra reaproveitável**: aplicada de novo, produz um resultado novo, ainda assim reconhecível como parte da mesma família visual (`12-sistema-modular-de-composicao.md`, Capítulo 04). A Biblioteca cataloga regras, nunca arquivos finais.

## 3. Categorias de Composição

A Biblioteca organiza padrões em categorias amplas, derivadas do Princípio do Documento (`12-sistema-modular-de-composicao.md`, Capítulo 09) — cada Documento Visual do NSI cumpre um de poucos propósitos estruturais:

- **Composição de Abertura** — apresenta uma ideia central pela primeira vez.
- **Composição de Desenvolvimento** — aprofunda uma ideia já apresentada.
- **Composição de Evidência** — apresenta um dado, uma citação, uma frase-evidência isolada.
- **Composição de Síntese** — fecha uma sequência `DT-00X`, resumindo o que foi construído ao longo dela.

Cada categoria é um **padrão de propósito**, não um layout — a aparência de cada uma será construída na fase de prototipação, nunca definida antecipadamente aqui.

## 4. Regra de Composição por Categoria

Toda categoria, sem exceção, obedece integralmente ao Sistema Modular de Composição (`12-sistema-modular-de-composicao.md`): mesmas zonas, mesmos componentes reutilizáveis, mesma hierarquia espacial e tipográfica, mesma Variabilidade Controlada (Capítulo 03). Nenhuma categoria cria uma exceção às regras já congeladas — categorias organizam propósito, não reescrevem arquitetura.

## 5. Rastreabilidade

Toda entrada da Biblioteca é identificada pelo Código Documental e pela Numeração da peça real que a originou (`10-componentes-visuais.md`, itens 3 e 9). A Biblioteca nunca contém exemplo anônimo, hipotético ou fictício — cataloga peças reais, publicadas, rastreáveis até sua origem.

## 6. Extensibilidade

Um padrão de composição só entra na Biblioteca depois de se repetir — uma composição usada uma única vez é apenas uma composição; só se torna padrão de biblioteca quando sua repetição confirma que pertence à família visual do NSI, não a uma necessidade pontual de uma peça isolada. Todo padrão novo deriva das regras já congeladas (`12-sistema-modular-de-composicao.md`, Princípio 3 da ADR-003) — nunca é criado por conveniência de uma peça específica.

---

## O que este documento deliberadamente não define

Nenhum layout, exemplo gráfico, cor ou tipografia concreta foi definido aqui. A Biblioteca nasce vazia — suas entradas reais só existirão quando as primeiras peças forem produzidas na fase de prototipação visual, a partir do primeiro Documento Visual Oficial do NSI (`DT-001`).

---

## Encerramento da etapa documental

Com este documento, encerra-se o escopo documental definido para esta etapa da Sprint 2 — Grid e Zona de Segurança, Tipografia Oficial, Paletas Oficiais e Biblioteca de Composição. Nenhum documento estrutural novo é criado a partir daqui. A partir deste ponto, a prática guia a arquitetura, não o contrário: o próximo passo é gerar `DT-001`, o primeiro Documento Visual Oficial do NSI.
