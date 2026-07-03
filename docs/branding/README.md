# Branding NSI — Fundação de Marca

## O que é este diretório

`docs/branding/` é a **fonte única de verdade** sobre o que o NSI é, por que existe e como fala. Toda comunicação futura do NSI — site, redes sociais, materiais comerciais, apresentações, e-mails, interface de produto — deriva do que está registrado aqui.

Esta fundação foi formalizada pela [ADR-002 — Fundação de Marca NSI](../architecture/ADR-002-brand-foundation.md), seguindo a mesma metodologia usada na arquitetura técnica do sistema (ADR-001): **arquitetura primeiro, implementação depois**. Nesta Sprint 1, o módulo entrega exclusivamente documentação. Identidade visual, peças de comunicação e calendário editorial pertencem a sprints futuras.

---

## Como este módulo se relaciona com o produto

A filosofia de marca do NSI não é uma narrativa de marketing construída à parte. Ela deriva diretamente dos princípios já congelados do Motor (`contrato_motor_nsi.md`, Seção 0) — rigor, evidência rastreável, recusa de reduzir uma resposta humana a um score. Quem escreve sobre o NSI deve conhecer esses princípios tanto quanto quem escreve código para ele.

---

## Índice

| Documento | Conteúdo |
|---|---|
| [`01-filosofia.md`](01-filosofia.md) | As crenças fundamentais por trás do NSI — o porquê por trás do porquê |
| [`02-manifesto.md`](02-manifesto.md) | Declaração de convicção — o registro público da postura do NSI |
| [`03-proposito.md`](03-proposito.md) | Por que o NSI existe — o problema que motivou sua criação |
| [`04-posicionamento.md`](04-posicionamento.md) | Categoria, público-alvo e contraste com alternativas do mercado |
| [`05-missao-visao-valores.md`](05-missao-visao-valores.md) | Missão, visão e os valores que governam decisões |
| [`06-diferenciais.md`](06-diferenciais.md) | O que distingue o NSI de qualquer alternativa existente |
| [`07-tom-de-voz.md`](07-tom-de-voz.md) | Como o NSI fala — e como não fala |
| [`08-principios-editoriais.md`](08-principios-editoriais.md) | Regras de escrita vinculantes para qualquer conteúdo futuro |

---

## Regras de uso

1. **Nada diverge sem alterar a fonte primeiro.** Se uma peça de comunicação precisar dizer algo que não está coerente com estes documentos, o documento é revisado antes — não a peça, isoladamente.
2. **Toda alteração é uma mudança versionada.** Segue a mesma disciplina de revisão do código: commit descritivo, revisão antes de consolidar.
3. **Tom de voz e princípios editoriais são vinculantes**, não sugestões. Ver [`07-tom-de-voz.md`](07-tom-de-voz.md) e [`08-principios-editoriais.md`](08-principios-editoriais.md) antes de escrever qualquer conteúdo publicável.
4. **Decisões estruturais novas viram ADR.** Introdução de identidade visual, nova plataforma de comunicação ou qualquer mudança que altere a arquitetura da marca (não apenas sua execução) é registrada como ADR subsequente em `docs/architecture/`.

---

## Status

**Sprint 1 — Fundação documental: concluída.** Nenhum layout, imagem ou post foi produzido nesta sprint, por decisão explícita (ADR-002, Seção 2.2).
