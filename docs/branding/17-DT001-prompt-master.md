# Prompt Master — Documentos Visuais do NSI

**Origem:** construído a partir de `DT-001`, mas projetado desde o início como o Prompt Master fixo e reaproveitável para toda a série de Documentos Visuais do NSI.
**Deriva de:** `docs/architecture/ADR-002-brand-foundation.md`, `docs/architecture/ADR-003-sistema-editorial-visual.md`, [`09-sistema-editorial-visual.md`](09-sistema-editorial-visual.md), [`10-componentes-visuais.md`](10-componentes-visuais.md), [`11-grid-e-zona-de-seguranca.md`](11-grid-e-zona-de-seguranca.md), [`12-sistema-modular-de-composicao.md`](12-sistema-modular-de-composicao.md), [`13-tipografia-oficial.md`](13-tipografia-oficial.md), [`14-paletas-oficiais.md`](14-paletas-oficiais.md), [`16-DT001-direcao-de-arte.md`](16-DT001-direcao-de-arte.md).
**Status:** Sprint 3 — APROVADO PROVISORIAMENTE. Arquitetura editorial oficialmente congelada; qualquer ajuste a este Prompt ocorrerá sobre a prática da produção real, não sobre revisão teórica adicional.
**Natureza:** Prompt de geração de imagem. Único bloco de texto fixo, com um único campo variável (`[TEXTO PRINCIPAL]`) para reuso em qualquer Documento Visual futuro.

---

## Como cada documento entra no Prompt

| Bloco do Prompt | Deriva de |
|---|---|
| Identidade Visual | `09-sistema-editorial-visual.md`, Capítulos 2, 4, 5, 6 |
| Arquitetura Editorial | `12-sistema-modular-de-composicao.md`, Capítulos 01, 02, 04, 09 |
| Grid e Zonas | `11-grid-e-zona-de-seguranca.md`, Capítulos 1–3, 8–10 |
| Hierarquia | `11-grid-e-zona-de-seguranca.md`, Capítulo 8; `13-tipografia-oficial.md`, Capítulo 1 |
| Ritmo e Silêncio Visual | `11-grid-e-zona-de-seguranca.md`, Capítulos 5–7; `16-DT001-direcao-de-arte.md`, Capítulos 4 e 7 |
| Componentes | `10-componentes-visuais.md`, todos os itens |
| Direção de Arte | `13-tipografia-oficial.md`, `14-paletas-oficiais.md`, `16-DT001-direcao-de-arte.md` |
| Critérios Negativos | `09-sistema-editorial-visual.md`, Capítulo 2; `16-DT001-direcao-de-arte.md`, Capítulo 9 |
| Consistência entre documentos | ADR-003, Princípio 6; `12-sistema-modular-de-composicao.md`, Capítulo 04 |

## Nota sobre o campo variável

A instrução é que exista **um único** campo variável, `[TEXTO PRINCIPAL]`, e que gerar `DT-002`, `DT-003` ou `DT-050` exija editar apenas esse campo. Para que isso seja literalmente verdadeiro — e não apenas a frase-âncora, deixando código e categoria hardcoded em `DT-001`/"Fundamentos" — defini `[TEXTO PRINCIPAL]` como um bloco de três linhas (Código Documental, Categoria, Frase-âncora). É essa decisão de escopo que torna possível trocar apenas um campo entre documentos, sem editar nenhuma regra acima dele. Sinalizo a decisão em vez de escondê-la: se a intenção era outra (por exemplo, código e categoria fixos e só a frase variando), ajusto.

Nenhum valor de cor (hex/RGB) ou nome de família tipográfica foi definido em `13-tipografia-oficial.md` e `14-paletas-oficiais.md` — ambos deliberadamente pararam na arquitetura, não na escolha concreta. O Prompt abaixo traduz essa arquitetura em linguagem descritiva e qualitativa (ex.: "tons neutros, baixa saturação"), não em uma cor ou fonte oficial nomeada. Quando uma paleta e uma tipografia concretas forem escolhidas — decisão futura, fora do escopo deste Prompt — este documento deve ser atualizado para referenciá-las explicitamente.

---

## Prompt Master

```
Crie um Documento Visual institucional pertencente a um Sistema Editorial Proprietário — nunca um post de rede social, nunca uma peça publicitária, nunca um template genérico preenchido.

IDENTIDADE VISUAL
A peça deve transmitir, de forma imediatamente perceptível: inteligência, precisão, ciência, tecnologia, organização, elegância, sofisticação, clareza e discrição. Nunca: marketing agressivo, aparência de propaganda, clickbait, visual poluído, estética de "guru", excesso de elementos. A personalidade é a de um instituto técnico — uma sala de instrumentos de precisão, não uma agência de publicidade: competência silenciosa, nada ali por decoração.

ARQUITETURA EDITORIAL
Esta peça é um Documento Visual, não um post — uma página pertencente a um manual técnico institucional, parte de uma família de documentos que compartilham a mesma linguagem sem nunca serem cópias idênticas entre si. Nenhum elemento é um template preenchido; a composição nasce de regras fixas aplicadas a um conteúdo variável, podendo reposicionar componentes dentro dessas regras sem quebrar a identidade.

GRID E ZONAS
Organize o espaço em zonas proporcionais, nunca em posições arbitrárias: uma Zona de Segurança que protege todo conteúdo essencial de corte ou sobreposição; Margens generosas e proporcionais ao redor de toda a peça; uma Área Institucional pequena e discreta; e uma Área Útil para Conteúdo dominante, que recebe a maior proporção do espaço disponível e hospeda exclusivamente a ideia central da peça.

HIERARQUIA
Estabeleça três níveis claros: (1) a mensagem central — máximo contraste, máximo destaque, é a primeira coisa que o olho encontra; (2) a categoria temática — peso médio-baixo, discreta, junto à identificação institucional; (3) identificação institucional (código do documento, identificadores, rodapé) — peso mínimo, quase sussurrado, nunca competindo com a mensagem central.

RITMO E SILÊNCIO VISUAL
Poucos elementos, espaçamento generoso entre eles. O espaço vazio deve dominar visualmente mais do que qualquer elemento presente — comunicando controle e calma, nunca saturação. O ritmo entre os blocos é lento e espaçado, nunca denso ou apressado.

COMPONENTES
Utilize apenas: um cabeçalho mínimo; opcionalmente um logotipo discreto, nunca dominante; um código documental discreto, no formato "DT-XXX"; uma categoria temática discreta, ao lado do código; um rodapé institucional discreto. Não inclua linha divisória nem numeração de página — não há mais de um bloco de conteúdo real a separar nesta peça.

DIREÇÃO DE ARTE
A mensagem central deve parecer uma convicção registrada, não uma frase de efeito publicitária. Tipografia sóbria, sem serifa decorativa, geométrica e precisa — sem ornamento, sem caligrafia, sem estilo manuscrito. Paleta extremamente contida: tons neutros e de baixa saturação, sem cor vibrante isolada, contraste aplicado apenas onde a hierarquia exigir, nunca por decoração. Nenhuma ilustração figurativa, nenhum ícone decorativo, nenhuma textura, nenhuma sombra pesada.

CRITÉRIOS NEGATIVOS — NUNCA INCLUIR
Marketing agressivo; aparência de propaganda ou anúncio; excesso de elementos; visual chamativo ou vibrante sem função; estética de template genérico; ícones decorativos sem justificativa; ilustrações figurativas; textura ou efeito de sombra pesado; qualquer chamada para ação ("clique aqui", "saiba mais", "arraste"); emoji; hashtag; qualquer marca de linguagem de rede social; métrica ou estatística fictícia; qualquer elemento sem função rastreável a um componente aprovado.

CONSISTÊNCIA ENTRE DOCUMENTOS FUTUROS
Este é o Prompt Master fixo e reaproveitável de toda a série de Documentos Visuais do NSI — DT-001, DT-002, DT-003, até DT-050 e além. Nenhuma regra acima muda de um documento para outro. O único elemento que varia entre documentos é o bloco abaixo.

[TEXTO PRINCIPAL]
Código Documental: DT-001
Categoria: Fundamentos
Frase-âncora: "Antes de analisar dados, é preciso aprender a ouvir."
```

---

## O que este documento não define

Nenhuma imagem foi gerada a partir deste Prompt. Este documento entrega o Prompt Master em si — a geração da primeira imagem de `DT-001` é a etapa seguinte, após aprovação.
