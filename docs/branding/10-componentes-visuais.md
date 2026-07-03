# Componentes Visuais do NSI

**Deriva de:** [`09-sistema-editorial-visual.md`](09-sistema-editorial-visual.md), `docs/architecture/ADR-002-brand-foundation.md` (Seção 4 — Tipo de Documento vs. Tema), `docs/architecture/ADR-003-sistema-editorial-visual.md`.
**Status:** Sprint 2 — CONGELADO. Aprovado e congelado, correspondente ao Bloco 05 (Componentes) da ADR-003, Seção 4, produzido antes dos Blocos 02–04 por decisão explícita desta sessão (ADR-003, Princípio 4, observação de exceção deliberada).
**Natureza:** Arquitetura dos componentes reutilizáveis do Sistema Editorial Visual. Nenhum componente possui aparência definida — nenhuma cor, tipografia, grid, dimensão ou prompt.

---

## Objetivo

Definir **quais componentes reutilizáveis existirão em qualquer publicação do NSI**, e a arquitetura de cada um — função, obrigatoriedade, objetivo, comportamento, quando usar e quando não usar. Este documento não decide a aparência de nenhum componente; decide **o que cada componente é responsável por fazer**, antes de qualquer decisão de grid, tipografia, cor ou layout (Blocos 02, 03, 04 e 06 da ADR-003).

Cada componente abaixo deriva de um princípio já registrado em `09-sistema-editorial-visual.md`. Um componente sem função rastreável a um princípio não entra neste sistema — aplicação direta do Princípio 3 da ADR-003 (Derivação a partir dos Princípios Filosóficos Aprovados).

---

## 1. Cabeçalho

- **Função:** identifica imediatamente que a peça pertence ao NSI e situa o leitor no que está prestes a ler.
- **Obrigatoriedade:** obrigatório em toda peça publicável.
- **Objetivo:** primeira aplicação do Princípio da Hierarquia — o topo estabelece contexto antes do conteúdo começar.
- **Comportamento:** fixo em posição, sempre no topo da peça; nunca carrega a mensagem central, apenas a contextualiza.
- **Quando utilizar:** sempre, sem exceção.
- **Quando não utilizar:** nunca é omitido. Não deve ser usado como espaço para conteúdo — se o cabeçalho cresce a ponto de competir com a Área de Conteúdo, ele viola o Princípio 5 da ADR-003 (a forma não compete com a mensagem).

---

## 2. Logo

- **Função:** elemento gráfico de identificação formal da marca.
- **Obrigatoriedade:** opcional, condicionado ao tipo de peça.
- **Objetivo:** funcionar como assinatura, não como fonte primária de reconhecimento — o NSI já se compromete (Princípio 7, ADR-002) a ser reconhecível mesmo sem ele.
- **Comportamento:** discreto; nunca dominante; nunca o elemento de maior destaque da peça.
- **Quando utilizar:** em peças formais e institucionais, onde a assinatura explícita da marca é apropriada.
- **Quando não utilizar:** como muleta para compensar uma peça que, sem o logo, não seria reconhecível como NSI — isso é sintoma de identidade fraca (Capítulo 7, `09-sistema-editorial-visual.md`), não algo que o logo deva resolver.

---

## 3. Código Documental

- **Função:** **único responsável pela identificação institucional da publicação** — Tipo de Documento (`DT`, `ART`, `REL`, `MAN`, `EST`, `GUI`, `INS` — ADR-002, Seção 4.1) mais sequência. Exemplos: `DT-001`, `ART-003`, `REL-002`, `MAN-004`.
- **Obrigatoriedade:** obrigatório em todas as peças, sem exceção.
- **Objetivo:** rastreabilidade institucional — permite localizar a peça dentro do Sistema Editorial, com a mesma exigência de evidência rastreável que já rege o Motor.
- **Comportamento:** presente de forma consistente e discreta; nunca é elemento de destaque visual; nunca delegado a outro componente — é a única fonte de identificação institucional do NSI.
- **Quando utilizar:** sempre, em qualquer peça.
- **Quando não utilizar:** não se aplica — é obrigatório em toda peça. Nunca é substituído ou duplicado pelo componente Numeração (item 9), que representa exclusivamente estrutura interna, não identificação institucional.

---

## 4. Categoria

- **Função:** comunica o Tema da peça (ADR-002, Seção 4.2) — o assunto tratado, independente do Tipo de Documento.
- **Obrigatoriedade:** obrigatório sempre que houver Código Documental.
- **Objetivo:** permitir que quem lê identifique do que se trata antes de consumir a peça inteira — aplicação do Princípio da Clareza.
- **Comportamento:** sempre exibida junto ao Código Documental; nunca aparece isolada, para não repetir a ambiguidade Tipo/Tema já eliminada na ADR-002 (Princípio 8).
- **Quando utilizar:** sempre que houver Código Documental.
- **Quando não utilizar:** não é repetida de forma redundante dentro do corpo da peça — a Categoria se declara uma vez, com clareza, não se reafirma por insegurança.

---

## 5. Linha Divisória

- **Função:** separa blocos de conteúdo, marcando uma transição real.
- **Obrigatoriedade:** opcional, aplicada conforme a hierarquia da peça exigir.
- **Objetivo:** reforçar Ordem e Hierarquia sem depender de texto explicativo para anunciar "aqui começa outra parte".
- **Comportamento:** neutra e discreta; nunca decorativa, nunca protagonista da peça.
- **Quando utilizar:** quando existe mudança real de assunto ou bloco lógico dentro da peça.
- **Quando não utilizar:** como preenchimento para simular estrutura em um conteúdo que não tem divisão real — isso viola o Princípio da Simplicidade.

---

## 6. Área de Conteúdo

- **Função:** espaço reservado exclusivamente para a mensagem central da peça.
- **Obrigatoriedade:** obrigatório — é a razão de existir de qualquer peça.
- **Objetivo:** garantir que a ideia central (Princípio da Singularidade, `08-principios-editoriais.md`) tenha espaço claro, sem disputa com componentes de apoio.
- **Comportamento:** recebe prioridade máxima de hierarquia; todo outro componente existe em função dela, nunca o contrário.
- **Quando utilizar:** sempre, em toda peça.
- **Quando não utilizar:** nunca é dividida para acomodar duas ideias centrais na mesma peça — se isso acontece, a peça viola a Singularidade e deve ser separada em duas (sequência `DT-001`, `DT-002`...).

---

## 7. Área de Respiro

- **Função:** espaço intencionalmente vazio entre e ao redor dos demais componentes.
- **Obrigatoriedade:** obrigatório — aplicação direta do Princípio do Respiro (`09-sistema-editorial-visual.md`, Capítulo 3).
- **Objetivo:** comunicar controle e calma; prevenir saturação visual.
- **Comportamento:** circunda a Área de Conteúdo e separa componentes entre si; não é um espaço "livre" a ser preenchido quando falta lugar para algo.
- **Quando utilizar:** sempre, entre todo par de componentes da peça.
- **Quando não utilizar:** nunca é reduzida ou eliminada para "caber mais conteúdo" — se o conteúdo não cabe respeitando a Área de Respiro, o conteúdo é reduzido ou dividido, nunca o respiro.

---

## 8. Rodapé Institucional

- **Função:** encerra formalmente a peça com informação de origem e contexto institucional.
- **Obrigatoriedade:** obrigatório em peças formais do Sistema de Publicações; opcional em peças internas pontuais.
- **Objetivo:** reforçar o pertencimento institucional da peça, fechando-a com a mesma sobriedade com que ela começou — sem repetir o Cabeçalho.
- **Comportamento:** discreto; posição sempre consistente (encerramento da peça); nunca compete com a Área de Conteúdo.
- **Quando utilizar:** em qualquer peça que representa o NSI formalmente perante um público externo ou institucional.
- **Quando não utilizar:** em peças efêmeras ou de uso interno rápido, onde um rodapé completo adicionaria peso desnecessário — violaria o Princípio da Simplicidade.

---

## 9. Numeração

- **Função:** representa **exclusivamente a estrutura interna da peça** — nunca a identificação institucional do documento, responsabilidade exclusiva do Código Documental (item 3). Exemplos: "Página 1 de 8", "Capítulo 02", "Seção 03", "Item 4.1", "Checklist 05", "Fluxo 02".
- **Obrigatoriedade:** obrigatório sempre que a peça possuir mais de uma unidade interna (páginas, capítulos, seções, itens, checklists, fluxos).
- **Objetivo:** orientar quem lê dentro da estrutura interna da peça — continuidade e navegação (Princípio da Continuidade), não rastreabilidade institucional.
- **Comportamento:** consistente em formato e posição dentro da peça; nunca assume o formato do Código Documental (`DT-00X`, `ART-00X`...) para se representar.
- **Quando utilizar:** sempre que houver estrutura interna real com mais de uma unidade.
- **Quando não utilizar:** nunca para representar `DT-001` ou qualquer outro código documental — essa identificação pertence exclusivamente ao Código Documental. Também não é usada em peça única e autocontida, sem divisão interna — numerar sem necessidade cria a falsa impressão de uma estrutura que não existe.

---

## 10. Identificadores

- **Função:** marcações que situam a peça dentro do sistema institucional maior — referência ao documento, ADR ou decisão de origem, e demais dados de rastreabilidade que não sejam o Código Documental ou a Categoria.
- **Obrigatoriedade:** obrigatório em qualquer peça formal do Sistema de Publicações.
- **Objetivo:** garantir rastreabilidade completa — a mesma exigência de evidência rastreável que o Motor aplica a uma classificação semântica, aplicada agora à origem de uma peça visual.
- **Comportamento:** sempre discretos, nunca centrais; agrupados de forma consistente, tipicamente próximos ao Código Documental.
- **Quando utilizar:** sempre que a peça precisar ser rastreável até uma decisão, documento ou processo de origem específico.
- **Quando não utilizar:** quando a informação já é coberta pelo Código Documental ou pela Categoria — Identificadores não repetem o que outro componente já declara.

---

## O que este documento deliberadamente não define

Nenhuma cor, tipografia, grid, dimensão, espaçamento em unidade concreta, ou prompt de geração foi definida para nenhum componente acima. Esta é matéria dos Blocos 02 (Grid e Sistema de Margens), 03 (Tipografia), 04 (Paletas Oficiais), 06 (Biblioteca Oficial de Layouts) e 07 (Prompt Master de Geração) da ADR-003 — ainda não iniciados. Este documento define exclusivamente **o que cada componente é e para que existe**, não como ele aparece.
