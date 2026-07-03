# Direção de Arte — DT-001

**Código Documental:** `DT-001`
**Categoria (Tema):** Fundamentos
**Frase-âncora:** "Antes de analisar dados, é preciso aprender a ouvir."
**Deriva de:** `docs/architecture/ADR-002-brand-foundation.md`, `docs/architecture/ADR-003-sistema-editorial-visual.md`, [`09-sistema-editorial-visual.md`](09-sistema-editorial-visual.md), [`10-componentes-visuais.md`](10-componentes-visuais.md), [`11-grid-e-zona-de-seguranca.md`](11-grid-e-zona-de-seguranca.md), [`12-sistema-modular-de-composicao.md`](12-sistema-modular-de-composicao.md), [`13-tipografia-oficial.md`](13-tipografia-oficial.md), [`14-paletas-oficiais.md`](14-paletas-oficiais.md), [`15-biblioteca-de-composicao.md`](15-biblioteca-de-composicao.md).
**Status:** Sprint 3 — APROVADO PROVISORIAMENTE. Sem revisão textual completa; sujeito a ajuste durante a prototipação visual. Nenhum prompt, imagem, cor específica, fonte específica ou layout definitivo é definido aqui — apenas a direção conceitual que orienta o Prompt Master (`17-DT001-prompt-master.md`).

> **Nota:** a instrução que originou este documento listou os documentos da Sprint 2 a aplicar sem incluir `12-sistema-modular-de-composicao.md`. Apliquei este documento mesmo assim — é ele que estabelece que o NSI não usa templates, o requisito mais citado nesta Direção de Arte ("aparência de template" está na lista do que nunca deve aparecer). Sinalizo a omissão sem presumir que foi intencional.

---

## 1. Objetivo Emocional da Peça

Antes de ler qualquer palavra, quem vir DT-001 deve sentir que está diante de algo escrito com rigor — não de um post tentando capturar atenção. O objetivo não é gerar engajamento por impulso (curtida, compartilhamento reativo); é gerar reconhecimento de autoridade silenciosa: isto foi escrito por quem entende profundamente o assunto e não precisa provar isso gritando.

A frase-âncora é a primeira aplicação pública da Filosofia fundacional do NSI (`01-filosofia.md`, crença 1 — "feedback real não cabe em um score"). O objetivo emocional é que ela pareça uma convicção arquitetural registrada, não uma frase de efeito de marketing.

## 2. Sensação que Deve Transmitir

Tecnologia, inteligência, organização, elegância, precisão, confiança — os seis traços exigidos nesta instrução são os mesmos já congelados em `09-sistema-editorial-visual.md`, Capítulo 2 (Filosofia Visual). Nenhuma sensação nova foi inventada para esta peça; DT-001 aplica exatamente o que já está aprovado, sem exceção nem adição:

Confiança, Controle, Clareza, Competência técnica, Calma, Precisão, Seriedade (`09-sistema-editorial-visual.md`, Capítulo 5).

## 3. Hierarquia da Leitura

- **Nível 1 — a frase-âncora.** Ocupa a Área Útil para Conteúdo (`11-grid-e-zona-de-seguranca.md`, Capítulo 9). Sozinha, precisa entregar a ideia inteira na leitura de varredura (`13-tipografia-oficial.md`, Capítulo 2) — ninguém deveria precisar de mais nada para entender do que DT-001 trata.
- **Nível 2 — Categoria ("Fundamentos").** Discreta, posicionada junto ao Código Documental (`10-componentes-visuais.md`, item 4).
- **Nível 3 — Código Documental, Identificadores, Rodapé Institucional.** Área Institucional (`11-grid-e-zona-de-seguranca.md`, Capítulo 10) — presentes para quem procura rastreabilidade, nunca para competir com a leitura.

## 4. Ritmo Visual

Poucos elementos, espaçamento generoso entre eles — a Área de Respiro domina a composição, não o texto. Cadência vertical: Cabeçalho mínimo → respiro amplo → frase-âncora → respiro amplo → Categoria + Código Documental → Rodapé Institucional. O ritmo é deliberadamente lento, com poucas "batidas" visuais — aplicação direta do Ritmo Vertical (`11-grid-e-zona-de-seguranca.md`, Capítulo 5) à escala de uma peça de ideia única.

## 5. Fluxo dos Olhos

O olho pousa primeiro na frase-âncora — não no cabeçalho, não em qualquer marca institucional. Só depois desce até Categoria e Código Documental, que confirmam "isto é Fundamentos, isto é DT-001" — a assinatura vem depois da mensagem, nunca antes (ADR-003, Princípio 5 — a forma nunca compete com a mensagem). Por último, se houver interesse adicional, o olho encontra o Rodapé Institucional.

## 6. Peso dos Elementos

A frase-âncora recebe o maior contraste tipográfico da peça (`13-tipografia-oficial.md`, Capítulo 9). Categoria recebe peso médio-baixo. Código Documental, Identificadores e Rodapé recebem o peso mínimo do sistema — presentes, quase sussurrados, nunca competindo com a leitura principal.

## 7. Uso do Silêncio Visual

O silêncio (Área de Respiro) é o segundo protagonista da peça, depois da frase — deve ocupar visualmente mais espaço do que qualquer elemento presente. Isso não é apenas aplicação do Princípio do Respiro (`09-sistema-editorial-visual.md`, Capítulo 3): é coerência direta com o próprio conteúdo da frase. Uma peça que afirma "é preciso aprender a ouvir" não pode ser visualmente ruidosa sem se contradizer.

## 8. Justificativa de Cada Componente

| Componente | Presente? | Justificativa |
|---|---|---|
| Cabeçalho | Sim, mínimo | Obrigatório sem exceção (`10-componentes-visuais.md`, item 1). |
| Logo | Sim, discreto | Peça institucional formal — presença apropriada (item 2), nunca como fonte primária de reconhecimento. |
| Código Documental | Sim — `DT-001` | Obrigatório em toda peça, sem exceção (item 3). |
| Categoria | Sim — "Fundamentos" | Obrigatório sempre que há Código Documental (item 4). |
| Linha Divisória | Não | Não há dois blocos de conteúdo distintos a separar; usá-la aqui seria simular estrutura que não existe (item 5, "quando não utilizar"). |
| Área de Conteúdo | Sim | Abriga integralmente a frase-âncora (item 6). |
| Área de Respiro | Sim, dominante | Ver Capítulo 7 acima (item 7). |
| Rodapé Institucional | Sim, discreto | Peça formal do Sistema de Publicações (item 8). |
| Numeração | Não | Representa estrutura interna com múltiplas unidades (item 9) — DT-001 é peça única, sem páginas ou seções internas. Não se aplica. |
| Identificadores | Sim, discretos | Rastreabilidade até esta Direção de Arte e as ADRs de origem (item 10). |

## 9. O que NÃO Deve Aparecer

- Ícone decorativo ou ilustração figurativa sem função.
- Cor vibrante ou isolada sem papel definido (`14-paletas-oficiais.md`, Capítulo 4 — Contenção Cromática).
- Textura, efeito de sombra pesado, ou qualquer ornamento sem justificativa.
- Chamada para ação ("clique aqui", "saiba mais", "arraste para o lado").
- Emoji, hashtag ou qualquer marca de linguagem de rede social.
- Métrica, número ou estatística fictícia (`08-principios-editoriais.md`, Regra 2).
- Qualquer elemento que faça a peça parecer um anúncio ou um template reaproveitado (`09-sistema-editorial-visual.md`, Capítulo 2; `12-sistema-modular-de-composicao.md`, Capítulo 02).

## 10. Critérios Objetivos de Aprovação

Adaptação, para esta peça específica, do checklist já congelado em `09-sistema-editorial-visual.md`, Capítulo 8:

- [ ] A frase-âncora é a primeira coisa que o olho encontra — antes de logo, cabeçalho ou código documental?
- [ ] A peça seria reconhecida como NSI mesmo sem o logotipo visível?
- [ ] Existe mais espaço vazio do que elemento presente?
- [ ] Cada componente presente está justificado no Capítulo 8 deste documento — nenhum está ali "porque ficou bonito"?
- [ ] A peça poderia ser confundida com propaganda, anúncio ou template? Se sim, está reprovada.
- [ ] A peça comunica exatamente uma ideia — a frase-âncora, sem concorrência de nenhuma outra mensagem?
- [ ] A peça seria reconhecível como NSI daqui a cinco anos?
- [ ] Toda decisão desta Direção de Arte está rastreável a um documento já congelado da Sprint 2?

---

## O que este documento deliberadamente não define

Nenhuma cor específica, fonte específica, prompt de geração de imagem ou layout definitivo foi definido aqui. Esta é matéria do Prompt Master — próxima etapa, iniciada somente após esta Direção de Arte estar aprovada.
