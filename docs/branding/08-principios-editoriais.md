# Princípios Editoriais NSI

**Deriva de:** [`07-tom-de-voz.md`](07-tom-de-voz.md).
**Status:** Fundação Sprint 1.
**Natureza:** Regras vinculantes — não sugestões — para qualquer conteúdo futuro do NSI.

---

## Princípios Fundamentais

Os dois princípios abaixo governam a forma de qualquer publicação do NSI, antes de qualquer regra tática de escrita. As regras numeradas que seguem (1 a 9) implementam esses dois princípios — não os substituem.

### PRINCÍPIO DA SINGULARIDADE

Cada publicação comunica **apenas uma ideia central**.

Uma publicação. Uma mensagem. Um conceito.

Nunca ensinar vários assuntos em uma única peça — mesmo que estejam relacionados, mesmo que caibam no mesmo espaço. Se uma peça precisa de "e também" para ser descrita, ela tem mais de uma ideia e precisa ser dividida.

Quando um tema exigir profundidade além do que uma única publicação suporta, ele é dividido em uma **sequência de Documentos Técnicos** — `DT-001`, `DT-002`, `DT-003`, `DT-004`... — cada um ainda respeitando a Singularidade (um documento, uma ideia), preservando entre si a ordem e a progressão do raciocínio completo. `DT` identifica exclusivamente o **Tipo de Documento** (Documento Técnico, ver ADR-002, Seção 4.1); o assunto tratado pela sequência é o **Tema**, um eixo separado (ver Regra 10 abaixo). A numeração é sequencial e nunca reaproveitada, no mesmo espírito da numeração de ADRs.

### PRINCÍPIO DA MEMORIZAÇÃO

Toda publicação deve ser compreendida em poucos segundos e deixar **uma única ideia gravada na mente de quem lê**.

O objetivo não é transmitir o máximo de informação possível. O objetivo é transmitir a informação certa, com a máxima clareza possível.

Uma publicação que exige releitura para ser entendida falhou — não porque o leitor não se esforçou o suficiente, mas porque a peça carregou mais do que uma pessoa consegue reter num primeiro contato. Precisão (Filosofia, crença 1) e memorização não competem entre si: o corte de uma publicação está em *quantas ideias* ela carrega, nunca em reduzir o rigor da ideia única que ela carrega.

---

## 1. Toda afirmação precisa ser sustentável

Nenhuma frase publicável afirma algo que não possa ser demonstrado por um dado real, um fato verificável ou uma decisão já documentada neste repositório. Uma frase de efeito que não resiste à pergunta "prove isso" não é publicada.

## 2. Nenhuma métrica fictícia

Números de exemplo (uma taxa de resposta, um percentual de confiança) só aparecem em conteúdo explicitamente identificado como exemplo ilustrativo — nunca apresentados como se fossem um resultado real não identificado como tal.

## 3. Termos evitados

Os termos abaixo não aparecem em comunicação do NSI, por serem jargão que não carrega informação verificável:

`revolucionário` · `disruptivo` · `cutting-edge` · `na vanguarda` · `sinergia` · `empoderar` · `game changer` · `de última geração` · `solução completa` · `sem esforço` (aplicado a algo que exige esforço real)

Exceção: uso em citação direta de terceiros, claramente atribuída.

## 4. Clareza antes de impacto

Uma frase de efeito nunca é escolhida em troca de precisão. Se simplificar uma explicação a torna imprecisa, a explicação fica mais longa — não mais vaga.

## 5. Contexto antes de conclusão

Nenhum número aparece sozinho. Um percentual, uma taxa, uma variação sempre vêm acompanhados do que os sustenta: período, tamanho de amostra, ou nível de confiança — do mesmo jeito que o Motor nunca apresenta uma classificação sem confiança e ocorrências.

## 6. Ausência de dado é declarada, não preenchida

Quando uma informação não existe ou não pode ser verificada, o texto diz isso explicitamente (`"ainda não medido"`, `"não se aplica"`) em vez de ser reescrito para parecer completo.

## 7. Terminologia consistente

| Usar | Evitar (em material voltado a cliente/mercado) |
|---|---|
| Experiência comercial | Sentimento |
| Operação | Lote *(termo técnico interno — ver ADR-001)* |
| Evidência / confiança | Score, nota, insight mágico |
| Camada | Módulo *(reservar para contexto técnico)* |

Este glossário é vivo: qualquer novo termo de domínio adotado pelo produto deve ser adicionado aqui antes de aparecer em material de marca.

## 8. Toda alteração de conteúdo é uma mudança versionada

Texto de marca não é editado "por cima" sem registro. Segue commit descritivo e, quando aplicável, revisão — a mesma disciplina usada para qualquer alteração de código neste repositório.

## 9. Revisão obrigatória contra os documentos-fonte

Antes de publicar qualquer peça, quem escreve confirma coerência com [`01-filosofia.md`](01-filosofia.md), [`07-tom-de-voz.md`](07-tom-de-voz.md) e este documento. Divergência não é resolvida ajustando a peça isoladamente — é resolvida revisando a fonte, se a fonte estiver desatualizada, ou revisando a peça, se a fonte estiver certa.

## 10. Tipo de Documento é diferente de Tema

Toda publicação do NSI é identificada por dois eixos independentes, que nunca se confundem:

- **Tipo de Documento** — a estrutura institucional da peça. Lista fechada (ADR-002, Seção 4.1): `DT` Documento Técnico, `ART` Artigo, `REL` Relatório, `MAN` Manual, `EST` Estudo, `GUI` Guia, `INS` Insight.
- **Tema** — o assunto tratado, independente do tipo (ex.: Fundamentos, Experiência do Cliente, Semântica, Linguagem, Dados, Cultura, Inteligência Artificial).

Uma sigla institucional nunca representa mais de um significado dentro do Livro da Marca (ADR-002, Princípio 8 — Unicidade de Sigla Institucional). `DT` significa exclusivamente Documento Técnico — nunca "Documento Temático" ou qualquer variação que confunda Tipo com Tema. Pelo mesmo motivo, o código `SEM` foi eliminado da nomenclatura oficial: "Semântica" existe exclusivamente como Tema, nunca como Tipo. A nomenclatura completa que combina Tipo + Tema + sequência é definida pelo Design System (ADR-002, Seção 5, Camada 3).
