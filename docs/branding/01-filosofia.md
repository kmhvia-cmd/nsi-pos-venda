# Filosofia NSI

**Deriva de:** `contrato_motor_nsi.md`, Seção 0 — Princípios do Motor.
**Status:** Fundação Sprint 1.

---

## O princípio de origem

Antes de existir uma linha de código, o Motor NSI já tinha uma convicção:

> "O NSI não mede sentimento. O NSI mede **experiência comercial**."

Essa frase não nasceu como copy de marca. Nasceu como decisão de arquitetura, escrita para orientar como um `processor.py` deveria classificar uma resposta de cliente. Mas é, também, a frase mais precisa que existe sobre o que o NSI acredita. Este documento existe para tornar explícito que a filosofia da marca **é** a filosofia do produto — não uma narrativa construída em paralelo a ela.

---

## O que acreditamos

### 1. Feedback real não cabe em um score

Uma resposta como "gostei muito do atendimento, mas a entrega demorou" carrega duas informações opostas na mesma frase. Reduzi-la a um número único — um NPS, um -1/+1, um "positivo" — apaga exatamente a parte que a empresa precisa para agir. Acreditamos que a informação que importa está na estrutura da frase, não na média dela.

### 2. Contexto decide o significado, não o tom

Uma resposta pode soar positiva e esconder uma oportunidade de melhoria. Pode soar negativa e esconder uma força real do negócio. Por isso nenhuma camada do NSI classifica por polaridade isolada — toda categoria é avaliada pelo contexto em que aparece. Julgar pelo tom é julgar rápido; julgar pelo contexto é julgar certo.

### 3. Nada é descartado como ruído

Emoji, pontuação, caixa alta, gíria, silêncio, tempo de resposta, ortografia — tudo é dado de entrada para alguma camada do Motor. A mesma atenção se aplica à marca: nenhum detalhe de como o NSI se comunica é irrelevante o suficiente para ser tratado com descuido.

### 4. Confiança se declara, nunca se finge

Toda conclusão do Motor carrega um percentual de confiança **e** a quantidade de ocorrências que a sustentam. Incerteza não é escondida — é informação. A marca segue a mesma regra: o NSI não afirma com a certeza de quem tem 100 evidências quando tem três, e não finge não saber quando sabe.

### 5. Nenhuma métrica sem fonte real

Se um indicador não pode ser calculado com confiabilidade a partir do que o sistema efetivamente coleta, ele fica fora — não entra como estimativa especulativa disfarçada de dado. Aplicado à comunicação: o NSI não anuncia o que ainda não construiu, e não usa número que não pode mostrar de onde vem.

### 6. Rigor é o produto, não um adjetivo sobre o produto

`engine/`, `processors/`, `contrato_motor_nsi.md` — toda a arquitetura técnica do NSI existe para que uma conclusão sobre um cliente nunca seja um palpite bem-arrumado. Essa é a mesma disciplina que rege como a marca fala: precisão antes de impacto, evidência antes de afirmação.

---

## O que essa filosofia exige de quem fala pelo NSI

- Não inventar métrica, estatística ou caso de uso que não exista de fato.
- Não prometer uma capacidade que o Motor não sustenta hoje.
- Não usar linguagem que sugira certeza absoluta onde há apenas indício.
- Tratar cada detalhe de comunicação — uma palavra, uma vírgula, um exemplo escolhido — com o mesmo cuidado que o Motor trata cada palavra de uma resposta de cliente.

Esta filosofia se desdobra em convicção pública no [Manifesto](02-manifesto.md) e em regras concretas de escrita nos [Princípios Editoriais](08-principios-editoriais.md).
