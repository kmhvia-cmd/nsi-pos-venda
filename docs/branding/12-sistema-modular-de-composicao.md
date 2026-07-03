# Sistema Modular de Composição Visual do NSI

**Deriva de:** [`09-sistema-editorial-visual.md`](09-sistema-editorial-visual.md), [`10-componentes-visuais.md`](10-componentes-visuais.md), [`11-grid-e-zona-de-seguranca.md`](11-grid-e-zona-de-seguranca.md), `docs/architecture/ADR-003-sistema-editorial-visual.md`.
**Status:** Sprint 2 — Rascunho para revisão. Não congelado.
**Natureza:** Arquitetura de composição. Nenhum layout, grid visual, tipografia, cor, prompt ou exemplo gráfico é definido aqui — apenas as regras pelas quais componentes e zonas se combinam.

---

## Decisão Arquitetural

**O NSI não utilizará templates. O NSI utilizará um Sistema Modular de Composição Visual.**

Esta decisão substitui qualquer ideia de criação baseada em templates repetitivos e passa a reger toda publicação futura do NSI.

**Nota de governança:** esta decisão pertence ao Livro da Marca e ao Sistema Editorial Visual, e não exige uma ADR própria. Ela deriva integralmente de princípios já congelados — Princípio 1 da ADR-002/ADR-003 (Derivação Integral da Fundação da Marca) e Princípio 3 da ADR-003 (Derivação a partir dos Princípios Filosóficos Aprovados) — e não introduz nenhum princípio novo de governança, apenas uma regra de composição derivada dos que já existem. A ADR-003 permanece como a referência arquitetural única da Sprint 2; este documento é conteúdo sob sua governança, não uma decisão paralela.

**Justificativa:** templates produzem repetição — a mesma peça reaparecendo com o conteúdo trocado. O objetivo do NSI não é repetir layout, é construir uma linguagem visual própria. Toda publicação deve parecer pertencente ao mesmo sistema, mas nunca ser idêntica à anterior — assim como um livro tem páginas diferentes que compartilham a mesma identidade editorial sem serem cópias umas das outras.

---

## Capítulo 01 — O que é um Sistema Modular de Composição

Um sistema onde toda peça nasce da combinação de componentes reutilizáveis (`10-componentes-visuais.md`), organizados dentro das zonas estruturais do grid (`11-grid-e-zona-de-seguranca.md`), segundo regras de composição — nunca de um arquivo pronto que se preenche.

A diferença central em relação a um template: um template fixa a posição de cada elemento e se repete; um sistema modular fixa **regras** de combinação, e cada aplicação dessas regras produz uma composição nova, ainda assim reconhecível como parte da mesma família.

---

## Capítulo 02 — Por que o NSI não utiliza templates

Um template, por definição, produz repetição — a mesma peça reaparecendo com o conteúdo trocado, sinal de produção em série, não de linguagem viva. Isso contradiz diretamente o Princípio da Atemporalidade e o Princípio 6 da ADR-003: a identidade deve sobreviver ao tempo pela consistência das **regras**, não pela repetição de uma peça fixa.

Um acervo de peças idênticas com texto trocado também se aproxima do que a identidade visual do NSI nunca pode parecer: aparência de propaganda, estética repetitiva de anúncio (`09-sistema-editorial-visual.md`, Capítulo 2). O objetivo desta Sprint não é produzir peças rapidamente — é construir uma linguagem visual proprietária que se sustente por anos.

---

## Capítulo 03 — Princípio da Variabilidade Controlada

Toda publicação pode variar — a posição relativa de um componente, a ênfase de uma zona, o ritmo entre elementos, sempre dentro dos limites já definidos pelo Grid Mestre e pelos componentes aprovados.

A identidade jamais pode variar. Os Princípios Visuais (`09-sistema-editorial-visual.md`, Capítulo 3), os componentes (`10-componentes-visuais.md`) e as zonas estruturais (`11-grid-e-zona-de-seguranca.md`) são fixos. Variabilidade existe apenas na composição — nunca nas regras que a governam.

---

## Capítulo 04 — Princípio da Família Visual

Toda peça deve parecer pertencente à mesma família — reconhecível por compartilhar os mesmos componentes, zonas e regras de composição — mas nunca ser cópia da anterior.

Este princípio aplica, na prática de composição, o Princípio 7 da ADR-002 (Identidade Única): reconhecimento vem da repetição consistente da linguagem, nunca da repetição idêntica de uma peça específica.

---

## Capítulo 05 — Sistema de Componentes

Toda publicação do NSI é construída exclusivamente a partir dos componentes reutilizáveis já registrados em `10-componentes-visuais.md`. Nenhuma peça introduz um elemento visual que não seja um desses componentes, ou uma composição deles.

Aplicação direta do Princípio 3 da ADR-003 (Derivação a partir dos Princípios Filosóficos Aprovados): um componente sem função rastreável não entra no sistema — e, por extensão, nenhuma peça pode conter um elemento que não seja um componente já aprovado.

---

## Capítulo 06 — Sistema de Zonas

Todo documento visual do NSI é dividido em zonas estruturais — Área Institucional, Área Útil para Conteúdo, Zona de Segurança, Margens (`11-grid-e-zona-de-seguranca.md`). A composição de qualquer peça é sempre a organização de componentes dentro dessas zonas, nunca a criação de uma área nova fora delas.

As proporções e posições concretas de cada zona, por formato (Instagram, PDF, apresentação, dashboard), serão detalhadas posteriormente pelo Grid Mestre, à medida que o Bloco 02 avançar da arquitetura já registrada para a especificação visual. Este capítulo confirma apenas que a zona é a unidade estrutural sobre a qual toda composição modular opera.

---

## Capítulo 07 — Sistema de Combinações

Um mesmo componente pode ocupar posições diferentes conforme a composição de cada peça — o Código Documental pode estar mais próximo do Cabeçalho em uma peça e do Rodapé Institucional em outra, conforme a necessidade daquela composição específica.

A identidade não é preservada pela posição fixa de um elemento. É preservada pelas regras de composição — Zonas (Capítulo 06), Hierarquia Espacial e Ritmo (`11-grid-e-zona-de-seguranca.md`) — que governam qualquer posição escolhida. É exatamente isso que distingue um sistema modular de um template: o template fixa posição; o sistema modular fixa regra.

---

## Capítulo 08 — Regras de Consistência

- Todos os documentos pertencem à mesma família visual.
- Nenhuma publicação pode parecer isolada — sua estrutura deve remeter a todas as demais peças do NSI.
- Nenhuma publicação pode parecer um anúncio comum — violaria diretamente o que a identidade visual do NSI nunca transmite (`09-sistema-editorial-visual.md`, Capítulo 2: marketing agressivo, aparência de propaganda).
- Toda peça deve transmitir continuidade — aplicação do Princípio da Continuidade (`09-sistema-editorial-visual.md`, Capítulo 3).

---

## Capítulo 09 — Princípio do Documento

O NSI não publica "posts". **O NSI publica Documentos Visuais.**

Cada publicação deve parecer uma página pertencente a um manual técnico institucional — a mesma Personalidade Visual já registrada em `09-sistema-editorial-visual.md`, Capítulo 4 ("um instituto técnico", "uma sala de instrumentos de precisão"), agora aplicada à própria natureza de cada peça publicada. Assim como o Código Documental e a Numeração (`10-componentes-visuais.md`) já tratam cada peça como unidade rastreável de um sistema maior, toda publicação — em qualquer canal — é tratada como um documento do acervo do NSI, nunca como uma peça avulsa de campanha.

---

## Capítulo 10 — Princípio da Biblioteca

Quando alguém acessa o Instagram — ou qualquer outro canal — do NSI, deve sentir que está navegando por uma **biblioteca técnica**, não por um feed tradicional de rede social.

Essa sensação é a consequência direta, na experiência de quem navega, de todos os princípios anteriores deste documento: Documento em vez de post (Capítulo 09), Família Visual (Capítulo 04), Sistema de Zonas (Capítulo 06), Regras de Consistência (Capítulo 08). O critério de sucesso do Sistema Modular de Composição não é "esta peça, isoladamente, ficou boa" — é "o conjunto, visto em sequência, parece um acervo coerente, construído por anos, não uma sucessão de posts".

---

## O que este documento deliberadamente não define

Nenhum layout, grid visual concreto, tipografia, cor, prompt ou exemplo gráfico foi definido aqui — matéria dos Blocos 03 (Tipografia), 04 (Paletas Oficiais), 06 (Biblioteca Oficial de Layouts) e 07 (Prompt Master de Geração) da ADR-003, ainda não iniciados. Este documento define exclusivamente as regras de composição — como os componentes e zonas já aprovados se combinam — nunca a aparência do resultado dessa combinação.
