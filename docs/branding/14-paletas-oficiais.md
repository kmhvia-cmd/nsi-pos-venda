# Paletas Oficiais do NSI

**Deriva de:** [`09-sistema-editorial-visual.md`](09-sistema-editorial-visual.md), [`11-grid-e-zona-de-seguranca.md`](11-grid-e-zona-de-seguranca.md), [`13-tipografia-oficial.md`](13-tipografia-oficial.md), `docs/architecture/ADR-003-sistema-editorial-visual.md` (Bloco 04 — Paletas Oficiais).
**Status:** Sprint 2 — Rascunho para revisão. Não congelado. Corresponde ao Bloco 04 da ADR-003, Seção 4.
**Natureza:** Arquitetura cromática. Nenhuma cor concreta — hex, RGB ou nome — é definida aqui, pela mesma disciplina já aplicada à Tipografia (`13-tipografia-oficial.md`): a lógica vem antes da escolha. Este documento define o papel, a hierarquia, a contenção e o contraste que qualquer paleta futura terá que obedecer.

---

## Objetivo

Definir como a cor vai funcionar no Sistema Editorial Visual do NSI — antes de escolher qualquer cor. A escolha concreta da paleta (os valores em si) é uma decisão posterior, tão concreta quanto a escolha de uma fonte específica em `13-tipografia-oficial.md`, e pertence à mesma fase futura, fora do escopo deste documento.

---

## 1. Papel da Cor no Sistema NSI

Cor não é decoração — é hierarquia e função, a mesma lógica já aplicada ao espaço (`11-grid-e-zona-de-seguranca.md`) e à tipografia (`13-tipografia-oficial.md`). Toda cor usada em uma peça existe para cumprir um papel identificável; nenhuma cor entra "porque ficou bonita".

Isso deriva diretamente da Personalidade Visual já registrada em `09-sistema-editorial-visual.md`, Capítulo 4: Inteligência, Precisão, Discrição. Um sistema cromático ruidoso contradiz essa personalidade antes mesmo de qualquer tom ser escolhido.

## 2. Hierarquia Cromática

Assim como nem todo espaço (Hierarquia Espacial, `11-grid-e-zona-de-seguranca.md`, Capítulo 8) e nem todo texto (Hierarquia Tipográfica, `13-tipografia-oficial.md`, Capítulo 1) têm a mesma importância, nem toda cor tem o mesmo protagonismo. Existe uma cor (ou tom) dominante, reservado ao que mais importa em cada peça, e cores de apoio, reservadas a papéis estruturais — nunca todas as cores competindo pela mesma atenção.

## 3. Paleta Institucional vs. Paleta de Conteúdo

A Área Institucional (`11-grid-e-zona-de-seguranca.md`, Capítulo 10 — Cabeçalho, Logo, Código Documental, Rodapé) usa um conjunto de cor deliberadamente mais restrito e estável do que a Área Útil para Conteúdo (Capítulo 9), que pode ter necessidade cromática própria conforme o que está sendo comunicado.

O princípio: a identidade institucional muda menos ao longo do tempo do que o conteúdo — logo, sua cor muda menos. Aplicação direta do Princípio 6 da ADR-003 (a identidade visual deve sobreviver ao tempo).

## 4. Princípio da Contenção Cromática

Poucas cores, usadas com disciplina, comunicam mais controle do que muitas cores competindo entre si — a mesma lógica já aplicada aos Pesos tipográficos (`13-tipografia-oficial.md`, Capítulo 4). Uma peça com excesso de cor viola diretamente o que a identidade visual do NSI nunca transmite (`09-sistema-editorial-visual.md`, Capítulo 2: visual poluído, excesso de elementos).

## 5. Contraste e Legibilidade

Toda combinação de cor usada sobre texto precisa garantir leitura sem esforço — aplicação cromática direta do Princípio da Clareza e dos Princípios de Legibilidade já registrados em `13-tipografia-oficial.md`, Capítulo 8. Contraste insuficiente entre texto e fundo é, na prática, uma falha de Clareza, não uma escolha estética válida.

## 6. Consistência entre Formatos

A mesma cor institucional precisa ser reconhecível como a mesma cor em qualquer canal — Instagram, PDF, apresentação, dashboard — mesmo que a renderização técnica varie entre tela e impressão. A paleta é definida de forma a permanecer consistente entre esses contextos, não otimizada para um único canal às custas dos demais.

## 7. Significado e Uso

Cor não é usada como atalho de julgamento — o mesmo princípio que já rege o Motor ("nunca score arbitrário, nunca +1/-1", `contrato_motor_nsi.md`, Seção 0) se estende à forma: o NSI não usa vermelho/verde como semáforo simplista de "bom/ruim" em dashboards ou peças, porque isso reproduziria exatamente a redução que o Motor recusa fazer com dado. Qualquer uso de cor com valor semântico precisa ser tão rastreável e justificado quanto uma classificação semântica do Motor.

## 8. Atemporalidade Cromática

Nenhuma cor é escolhida por estar em alta no momento. O critério de validação de qualquer paleta futura é o mesmo já registrado em `09-sistema-editorial-visual.md`, Capítulo 3 (Princípio da Atemporalidade): "ainda vai fazer sentido em anos?", nunca "está atual agora?".

---

## O que este documento deliberadamente não define

Nenhuma cor concreta — hex, RGB, CMYK ou nome — foi definida aqui, nem quantidade exata de cores na paleta final. Isso é decisão concreta futura, assim como a escolha de fonte em `13-tipografia-oficial.md`. Este documento define exclusivamente o papel, a hierarquia, a contenção, o contraste e o significado que qualquer paleta terá que obedecer quando for escolhida.
