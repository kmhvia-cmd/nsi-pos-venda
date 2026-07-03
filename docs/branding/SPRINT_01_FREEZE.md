# Sprint 01 — Fundação da Marca

**Registro oficial de congelamento.** Este documento é o certificado de encerramento da Sprint 1 do módulo de branding do NSI — não um documento de conteúdo da marca, mas o registro de que a fundação está completa, revisada e congelada.

---

## Objetivo

Construir a fundação documental da marca NSI antes de qualquer peça de comunicação, seguindo a mesma metodologia já validada na arquitetura técnica do sistema: **arquitetura primeiro, implementação depois, congelamento somente após aprovação**.

A Sprint 1 não produziu identidade visual, layout, imagem ou post. Produziu o **Livro da Marca**: a fonte única de verdade sobre o que o NSI é, por que existe e como fala — derivada diretamente dos princípios já congelados do Motor (`contrato_motor_nsi.md`, Seção 0), não de uma narrativa de marketing construída à parte.

---

## Documentos criados

### Arquitetura
- [`docs/architecture/ADR-002-brand-foundation.md`](../architecture/ADR-002-brand-foundation.md) — decisão arquitetural que funda o módulo, revisada linha por linha (`Em Revisão` → `Aprovado`) e congelada.

### Livro da Marca (`docs/branding/`)
- [`README.md`](README.md) — índice e regras de uso do módulo.
- [`01-filosofia.md`](01-filosofia.md) — crenças fundamentais.
- [`02-manifesto.md`](02-manifesto.md) — declaração de convicção.
- [`03-proposito.md`](03-proposito.md) — por que o NSI existe.
- [`04-posicionamento.md`](04-posicionamento.md) — categoria, público, contraste competitivo.
- [`05-missao-visao-valores.md`](05-missao-visao-valores.md) — missão, visão e valores.
- [`06-diferenciais.md`](06-diferenciais.md) — o que distingue o NSI de alternativas.
- [`07-tom-de-voz.md`](07-tom-de-voz.md) — como o NSI fala.
- [`08-principios-editoriais.md`](08-principios-editoriais.md) — regras de escrita vinculantes, incluindo os Princípios da Singularidade e da Memorização.
- `SPRINT_01_FREEZE.md` — este documento, o registro de congelamento.

**Total: 10 documentos** (1 ADR + 9 documentos do Livro da Marca).

---

## Decisões arquiteturais congeladas

Todas as decisões abaixo estão registradas formalmente na ADR-002, Seção 8:

1. `docs/branding/` é a fonte única de verdade da marca NSI.
2. A Sprint 1 entrega exclusivamente documentação fundacional — nenhum layout, imagem ou post.
3. A filosofia de marca deriva dos princípios técnicos já congelados do Motor (Contrato Seção 0), não de uma narrativa de marketing independente.
4. Toda comunicação futura do NSI, em qualquer canal, deve ser coerente com os documentos de `docs/branding/`.
5. Alterações de conteúdo de marca seguem a mesma disciplina de versionamento em Git aplicada ao código.
6. O Branding do NSI é um ativo arquitetural do projeto, não uma iniciativa de campanha.
7. O objetivo do módulo é um Sistema Editorial Proprietário — não apenas identidade visual — composto por três camadas (Fundamentos da Marca, Design System, Sistema de Publicações).
8. Toda decisão de marca deve preservar a identidade do NSI por muitos anos (Consistência de Longo Prazo).
9. O NSI deve ser reconhecível mesmo sem o logotipo, pela repetição consistente de sua linguagem visual, editorial e conceitual (Identidade Única).
10. Uma sigla institucional nunca possui mais de um significado dentro do Livro da Marca (Unicidade de Sigla Institucional).
11. Tipo de Documento e Tema são eixos permanentemente separados; nenhuma sigla de Tipo pode representar um Tema.
12. O código `SEM` foi identificado como ambíguo durante a revisão arquitetural (confundia Tipo com Tema) e eliminado definitivamente da nomenclatura oficial. "Semântica" existe exclusivamente como Tema Editorial.
13. Nomenclatura oficial e fechada dos Tipos de Documento do Livro da Marca: `DT`, `ART`, `REL`, `MAN`, `EST`, `GUI`, `INS`.

Complementam essas decisões dois princípios editoriais nomeados, registrados em `08-principios-editoriais.md`:

- **Princípio da Singularidade** — cada publicação comunica apenas uma ideia central; temas profundos se dividem em sequência `DT-001`, `DT-002`, `DT-003`...
- **Princípio da Memorização** — toda publicação deve ser compreendida em poucos segundos e deixar uma única ideia gravada na mente de quem lê.

---

## O que deliberadamente NÃO faz parte desta Sprint

Por decisão explícita da ADR-002 (Seções 2.2 e 10), ficam **fora do escopo da Sprint 1** — não por esquecimento, mas por definição de fronteira:

- **Identidade visual**: logotipo, paleta de cores, tipografia, ícones, layouts, templates, grid, componentes, zonas de segurança.
- **Qualquer peça de comunicação**: posts, textos publicitários, roteiros, e-mails, imagens, fotografias, ilustrações.
- **Canais de publicação e calendário editorial**: nenhum canal ou cronograma foi definido.
- **Regras de numeração e formatos dos códigos documentais**: a lista de Tipos (`DT`, `ART`, `REL`, `MAN`, `EST`, `GUI`, `INS`) está fechada, mas como cada código se combina com Tema, sequência e formato de arquivo é decisão da Camada 3 (Sistema de Publicações), ainda não iniciada.
- **Camada 2 (Design System) e Camada 3 (Sistema de Publicações)** do Sistema Editorial: existem apenas como conceito registrado na ADR-002, Seção 5 — sem nenhuma decisão de conteúdo.
- **Qualquer alteração ao Motor, ao Operations Console ou ao Portal Executivo do Cliente** (ADR-001): o módulo de branding não toca em código, API ou lógica de produto.

Tudo isso pertence à Sprint 2 e sprints subsequentes.

---

## Próxima Sprint

### Sprint 2 — Design System

Objetivos previstos:

- Grid oficial
- Sistema de margens
- Zonas de segurança
- Componentes
- Paletas
- Tipografia
- Biblioteca oficial de layouts
- Prompt Master de geração de imagens
- Prompt Master de geração de conteúdo

Como em toda sprint do NSI, a Sprint 2 segue arquitetura primeiro: nenhuma decisão de Design System entra em vigor sem ADR própria, aprovada e congelada, antes de qualquer peça ser produzida.

---

## Estado

**CONGELADA**
