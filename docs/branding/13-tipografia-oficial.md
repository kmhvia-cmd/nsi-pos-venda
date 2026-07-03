# Tipografia Oficial do NSI

**Deriva de:** [`09-sistema-editorial-visual.md`](09-sistema-editorial-visual.md), [`11-grid-e-zona-de-seguranca.md`](11-grid-e-zona-de-seguranca.md), [`12-sistema-modular-de-composicao.md`](12-sistema-modular-de-composicao.md), `docs/architecture/ADR-003-sistema-editorial-visual.md` (Bloco 03 — Tipografia).
**Status:** Sprint 2 — Rascunho para revisão. Não congelado. Corresponde ao Bloco 03 da ADR-003, Seção 4.
**Natureza:** Arquitetura tipográfica. Nenhuma fonte específica é escolhida aqui — apenas a lógica de hierarquia, ritmo, peso, espaçamento, escala e contraste que qualquer fonte futura terá que obedecer.

---

## Objetivo

Definir a arquitetura tipográfica do NSI — as regras que qualquer texto, em qualquer peça, vai obedecer — antes de escolher qualquer fonte. A tipografia é a camada construída sobre o Grid (`11-grid-e-zona-de-seguranca.md`) e organizada pelo Sistema Modular de Composição (`12-sistema-modular-de-composicao.md`): o grid decide onde o texto vive; este documento decide como o texto se comporta ali dentro. A escolha da família tipográfica em si é uma decisão posterior, concreta, fora do escopo deste documento.

---

## 1. Hierarquia Tipográfica

O sistema de níveis que orienta o olhar pela importância relativa de cada texto dentro de uma peça — título, subtítulo, corpo, legenda, identificador. Cada nível tem uma função exclusiva; nenhum nível assume a função de outro.

Esta hierarquia é a tradução, no plano do texto, da Hierarquia Espacial já registrada em `11-grid-e-zona-de-seguranca.md`, Capítulo 8: o texto de maior importância ocupa a posição de maior destaque dentro da Área Útil para Conteúdo, nunca o contrário.

## 2. Níveis de Leitura

Toda peça do NSI é lida em duas camadas: uma **leitura de varredura** (o que se apreende em poucos segundos — título, categoria, código documental) e uma **leitura de imersão** (o corpo do texto, para quem decide se aprofundar).

A leitura de varredura sozinha já deve entregar a ideia central da peça — aplicação direta do Princípio da Memorização (`08-principios-editoriais.md`). A leitura de imersão existe para sustentar essa ideia com profundidade, nunca para revelar uma ideia diferente da que a varredura já comunicou.

## 3. Ritmo Visual

O espaçamento entre linhas, parágrafos e blocos de texto segue a mesma lógica proporcional e relativa já estabelecida para o Ritmo Vertical e o Ritmo Horizontal (`11-grid-e-zona-de-seguranca.md`, Capítulos 5 e 6) — nunca um valor arbitrário escolhido peça a peça.

Um texto sem ritmo consistente cansa antes de convencer; um texto com ritmo prevé onde uma ideia termina e a próxima começa, mesmo antes de ser lido palavra por palavra.

## 4. Pesos

A hierarquia tipográfica se expressa, em parte, por variação de peso — não apenas de tamanho. Um nível pode se destacar por ser mais pesado, sem precisar ser maior.

A variação de pesos disponíveis é deliberadamente controlada: poucos pesos, usados com disciplina, comunicam mais hierarquia do que muitos pesos competindo entre si — aplicação direta do Princípio da Simplicidade (`09-sistema-editorial-visual.md`, Capítulo 3).

## 5. Espaçamentos

Espaçamento entre letras, entre linhas e entre parágrafos é sempre proporcional à escala tipográfica (Capítulo 6), nunca um valor fixo isolado.

O espaçamento tipográfico é a Área de Respiro (`10-componentes-visuais.md`, item 7; `11-grid-e-zona-de-seguranca.md`, Capítulo 7) aplicada dentro do próprio texto — um bloco de texto sem respiro interno satura tanto quanto uma peça sem respiro entre componentes.

## 6. Escala

Todo tamanho de texto deriva de uma **escala modular única** — uma relação matemática consistente entre os níveis de hierarquia (Capítulo 1), nunca tamanhos escolhidos avulsamente peça a peça.

A proporção exata dessa escala é uma decisão concreta futura, fora do escopo deste documento. O que se congela aqui é o princípio: existe uma única régua de escala, e todo nível tipográfico do NSI deriva dela — nunca uma exceção pontual "só desta vez".

## 7. Relação entre Títulos, Subtítulos e Corpo

O **título** ancora a única ideia central da peça — aplicação direta do Princípio da Singularidade (`08-principios-editoriais.md`) ao texto: uma peça, um título, uma ideia.

O **subtítulo** apoia o título; nunca compete com ele em peso ou destaque — aplicação do Princípio 5 da ADR-003 (a forma nunca compete com a mensagem).

O **corpo** carrega o desenvolvimento da ideia. É o nível com maior volume de texto e, ainda assim, o mais contido em destaque visual — sua função é ser lido com atenção, não ser notado primeiro.

## 8. Princípios de Legibilidade

Um texto do NSI é lido sem esforço, ou falhou como texto — aplicação direta do Princípio da Clareza (`09-sistema-editorial-visual.md`, Capítulo 3). Isso implica, independentemente da fonte que for escolhida no futuro:

- Extensão de linha controlada — nem tão longa que canse o olho, nem tão curta que quebre o raciocínio.
- Densidade controlada — bloco de texto denso demais é a mesma saturação já proibida em `09-sistema-editorial-visual.md`, Capítulo 2.
- Nenhum tratamento decorativo que compita com a leitura — legibilidade nunca é sacrificada por personalidade visual.

## 9. Princípios de Contraste

O contraste entre níveis de hierarquia (Capítulo 1) precisa ser suficiente para ser percebido instantaneamente — nem sutil a ponto de borrar a hierarquia, nem exagerado a ponto de parecer estar gritando (o que violaria diretamente `09-sistema-editorial-visual.md`, Capítulo 2 — nunca marketing agressivo).

Nesta fase, o contraste é construído pela combinação de peso (Capítulo 4), escala (Capítulo 6) e espaçamento (Capítulo 5) — não por cor, que ainda não foi definida (Bloco 04 — Paletas Oficiais).

---

## O que este documento deliberadamente não define

Nenhuma família tipográfica, nenhum tamanho em unidade concreta, nenhuma cor e nenhum layout foram definidos aqui — matéria de uma decisão concreta futura (escolha de fonte) e dos Blocos 04 (Paletas Oficiais) e 06 (Biblioteca de Composição) da ADR-003. Este documento define exclusivamente a lógica que qualquer fonte, tamanho e composição de texto terá que obedecer.
