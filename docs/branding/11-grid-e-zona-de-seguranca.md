# Grid e Zona de Segurança do NSI

**Deriva de:** [`09-sistema-editorial-visual.md`](09-sistema-editorial-visual.md) (Princípios Visuais, Capítulo 3), [`10-componentes-visuais.md`](10-componentes-visuais.md) (componentes organizados espacialmente por este grid), `docs/architecture/ADR-003-sistema-editorial-visual.md` (Bloco 02 — Grid e Sistema de Margens).
**Status:** Sprint 2 — APROVADO PROVISORIAMENTE. Sem revisão detalhada linha por linha; sujeito a ajuste durante a prototipação visual, caso a prática revele necessidade. Corresponde ao Bloco 02 da ADR-003, Seção 4.
**Natureza:** Arquitetura espacial invisível. Nenhuma cor, tipografia, layout, componente gráfico ou prompt é definido aqui — apenas as regras estruturais que todos eles vão obedecer.

---

## Objetivo

Este documento constrói o esqueleto invisível sobre o qual toda peça futura do NSI será organizada — o Bloco mais estrutural de todo o Sistema Editorial Visual, porque tudo o que vier depois (Tipografia, Paletas, Componentes gráficos, Biblioteca de Layouts, Prompt Master) será construído **sobre** este grid, nunca ao contrário.

Nenhuma cor, fonte ou layout é definida aqui. O que se define é **como o espaço se organiza** — em qualquer formato: Instagram, Facebook, LinkedIn, PDF, apresentação ou dashboard. Por isso, nenhuma regra deste documento é expressa em valor fixo (pixel, milímetro, coluna fixa). Toda regra é **proporcional e relativa ao formato**, para que a mesma lógica de grid seja reconhecível em um story vertical, em um slide widescreen e em uma página impressa — a mesma disciplina de Consistência (`09-sistema-editorial-visual.md`, Capítulo 3) aplicada ao espaço, não apenas à forma.

---

## 1. Grid Mestre do NSI

- **Função:** a estrutura proporcional que organiza todo o espaço de qualquer peça — o esqueleto sobre o qual tipografia, cor, componentes e layout serão construídos nos próximos blocos.
- **Lógica estrutural:** baseado em unidades proporcionais e relativas ao formato da peça, nunca em valores fixos absolutos.
- **Regra entre formatos:** não é um único grid fixo replicado em todo lugar — é um conjunto de regras proporcionais que cada formato (Instagram, Facebook, LinkedIn, PDF, apresentação, dashboard) instancia de forma consistente com sua própria proporção.
- **Relação com princípios:** aplica diretamente o Princípio da Ordem e o Princípio da Consistência (`09-sistema-editorial-visual.md`, Capítulo 3) — a mesma decisão estrutural, aplicada sempre da mesma forma.

---

## 2. Zona de Segurança

- **Função:** área de proteção que garante que nenhum elemento essencial da peça seja cortado, sobreposto ou perdido por interferência externa ao NSI — recorte de plataforma, interface de terceiros sobre um story, margem de impressão, corte automático de preview.
- **Lógica estrutural:** um buffer proporcional entre a borda real da peça e qualquer conteúdo essencial; escala junto com o Grid Mestre, nunca é um valor isolado e fixo.
- **Regra entre formatos:** cada formato impõe suas próprias interferências externas (Instagram sobrepõe interface sobre stories; LinkedIn recorta preview; PDF tem margem de impressão) — a Zona de Segurança é a regra que garante que o conteúdo essencial nunca dependa da ausência dessas interferências.
- **Relação com princípios:** aplicação defensiva do Princípio da Clareza — nada essencial pode se perder por uma circunstância que o NSI não controla.
- **Diferença em relação à Margem (Capítulo 3):** a Zona de Segurança protege contra o que o NSI **não controla** (a plataforma); a Margem é decisão editorial própria do NSI, independente de qualquer plataforma.

---

## 3. Margens

- **Função:** a moldura editorial intencional ao redor de toda peça — decisão de composição do NSI, não reação a uma limitação externa.
- **Lógica estrutural:** proporcional ao formato e ao Grid Mestre; aplicação do Princípio do Respiro (`09-sistema-editorial-visual.md`, Capítulo 3) na borda externa da peça.
- **Regra entre formatos:** não é um número fixo replicado em todo formato — é uma proporção que se adapta ao tamanho e à orientação de cada peça, preservando a mesma sensação de respiro em qualquer formato.
- **Relação com componentes:** contém integralmente a Área Útil para Conteúdo (Capítulo 9) e a Área Institucional (Capítulo 10) — nada do conteúdo relevante da peça existe fora da margem.
- **Diferença em relação à Zona de Segurança:** a margem é decisão de composição; a Zona de Segurança é defesa contra interferência externa. Uma peça pode ter margem generosa e ainda assim precisar de Zona de Segurança adicional quando a plataforma sobrepõe elementos.

---

## 4. Alinhamentos

- **Função:** a regra que decide onde cada componente se ancora dentro do grid — nunca posicionamento aleatório ou "onde couber".
- **Lógica estrutural:** todo elemento se alinha a uma referência do Grid Mestre (uma coluna, uma linha, um eixo); nenhum elemento flutua livre do sistema.
- **Regra entre formatos:** o eixo de alinhamento pode mudar conforme a orientação do formato (vertical, horizontal, quadrado), mas a disciplina de alinhar-se sempre a uma referência do grid nunca muda.
- **Relação com princípios:** aplicação direta do Princípio da Ordem — alinhamento consistente é o que permite ao olho prever onde encontrar cada tipo de informação, peça após peça.

---

## 5. Ritmo Vertical

- **Função:** a cadência de espaçamento entre elementos ao longo do eixo vertical da peça.
- **Lógica estrutural:** intervalos proporcionais e repetíveis entre blocos empilhados — Cabeçalho, Área de Conteúdo, Rodapé Institucional (`10-componentes-visuais.md`) se sucedem sempre com a mesma lógica de distância relativa entre si.
- **Regra entre formatos:** peças altas (stories, PDFs de múltiplas páginas) e peças baixas (posts quadrados) aplicam a mesma proporção de ritmo, apenas em escalas diferentes — nunca um ritmo arbitrário por peça.
- **Relação com princípios:** aplicação do Princípio da Continuidade — cada peça nova "soa" como parte da mesma sequência de decisões, nunca como uma composição improvisada.

---

## 6. Ritmo Horizontal

- **Função:** a cadência de espaçamento entre elementos ao longo do eixo horizontal da peça.
- **Lógica estrutural:** mesma lógica proporcional do Ritmo Vertical, aplicada ao eixo horizontal — colunas, blocos lado a lado, distância entre elementos de uma mesma linha.
- **Regra entre formatos:** em formatos largos (apresentações, dashboards, LinkedIn horizontal) o ritmo horizontal ganha mais protagonismo estrutural do que em formatos estreitos e altos (stories) — a proporcionalidade da regra nunca muda, apenas sua ênfase relativa.
- **Relação com princípios:** mesma base do Ritmo Vertical — Continuidade e Consistência.

---

## 7. Área de Respiro

- **Função:** o espaço estrutural vazio que este grid reserva entre e ao redor de todo componente — a implementação geométrica do componente já registrado em `10-componentes-visuais.md`, item 7.
- **Lógica estrutural:** proporção mínima obrigatória entre qualquer par de elementos do grid; nunca reduzida para caber mais conteúdo — mesma regra já congelada no componente.
- **Regra entre formatos:** a proporção de respiro é relativa ao tamanho da peça — um dashboard tem mais área disponível que um story, mas a sensação de respiro (nunca saturado) é a mesma em ambos.
- **Nota de rastreabilidade:** este capítulo não redefine o componente Área de Respiro — define a lógica de grid que garante sua aplicação consistente em qualquer peça e formato.

---

## 8. Hierarquia Espacial

- **Função:** a regra que decide o tamanho e a posição relativa de cada área do grid conforme sua importância.
- **Lógica estrutural:** a Área Útil para Conteúdo (Capítulo 9) sempre recebe a maior proporção de espaço disponível; a Área Institucional (Capítulo 10) ocupa proporção deliberadamente menor — o grid nunca distribui espaço igualitariamente entre conteúdo e apoio.
- **Regra entre formatos:** a proporção entre área de conteúdo e área institucional se mantém como regra (conteúdo sempre dominante), mesmo quando o espaço total disponível muda drasticamente entre um story e um PDF.
- **Relação com princípios:** aplicação espacial direta do Princípio da Hierarquia (`09-sistema-editorial-visual.md`, Capítulo 3) e do Princípio 5 da ADR-003 (a forma nunca compete com a mensagem) — mais espaço para a mensagem, nunca para o que apenas a envolve.

---

## 9. Área Útil para Conteúdo

- **Função:** a região do grid reservada à mensagem central da peça — a implementação espacial do componente Área de Conteúdo (`10-componentes-visuais.md`, item 6).
- **Lógica estrutural:** delimitada pela Margem (Capítulo 3) e pela Zona de Segurança (Capítulo 2); recebe a maior proporção de espaço por força da Hierarquia Espacial (Capítulo 8).
- **Regra entre formatos:** seu tamanho absoluto muda radicalmente entre um slide de apresentação e um post de Instagram, mas sua função — abrigar exclusivamente a ideia central da peça (Princípio da Singularidade, `08-principios-editoriais.md`) — nunca muda.
- **Nota de rastreabilidade:** este capítulo não redefine o componente Área de Conteúdo — define onde e com que proporção ele existe dentro do grid.

---

## 10. Área Institucional

- **Função:** a região do grid reservada aos componentes de identificação e rastreabilidade da peça — Cabeçalho, Logo, Código Documental, Categoria, Rodapé Institucional, Numeração e Identificadores (`10-componentes-visuais.md`).
- **Lógica estrutural:** ocupa proporção deliberadamente pequena do grid, por força da Hierarquia Espacial (Capítulo 8); nunca compete espacialmente com a Área Útil para Conteúdo.
- **Regra entre formatos:** sua posição pode variar (topo, base, lateral, conforme o formato exigir), mas sua proporção reduzida em relação à Área Útil para Conteúdo é regra fixa em qualquer formato.
- **Relação com princípios:** aplicação espacial do Princípio 7 da ADR-002 (Identidade Única) — é essa área, aplicada com consistência peça após peça, que ajuda a tornar qualquer publicação reconhecível como NSI.

---

## O que este documento deliberadamente não define

Nenhuma cor, tipografia, layout completo, componente gráfico ou prompt foi definido aqui — matéria dos Blocos 03 (Tipografia), 04 (Paletas Oficiais), 06 (Biblioteca Oficial de Layouts) e 07 (Prompt Master de Geração) da ADR-003, ainda não iniciados. Este documento define exclusivamente a arquitetura invisível do espaço — a lógica que todo layout futuro vai obedecer, nunca a aparência desse layout.
