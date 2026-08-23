# ADR-005 — Ciclo Temporal de Coleta e Leituras Independentes

## Metadados

| Campo | Valor |
|---|---|
| Status | Aprovada e congelada |
| Data | 2026-08-23 |
| Versão de referência do sistema | `v1.1.0-fonte-unica-webhook-motor` |
| Commit de referência | `53fd6b8` |
| Branch | `master` |
| Escopo desta ADR | Arquitetura — nenhuma implementação de código, frontend ou componente visual |

> **Nota de processo:** ADR aberta para registrar a regra temporal de coleta do Motor NSI — janela total de uma operação e as duas leituras independentes que a compõem — identificada como lacuna durante a continuidade da arquitetura da Tela 02 do Portal Executivo. A ADR-004 exclui explicitamente qualquer alteração ao Motor NSI do seu escopo (Seções 2.2 e 10); esta ADR preenche essa lacuna em documento próprio, seguindo a mesma metodologia já validada nas ADRs anteriores: arquitetura primeiro, implementação depois, congelamento somente após aprovação explícita.

---

## 1. Objetivo

Registrar a arquitetura do ciclo temporal de coleta de respostas do Motor NSI: toda operação de coleta possui uma janela total de 336 horas (14 dias), dividida em dois intervalos que não se sobrepõem e não deixam lacunas — a **Leitura Inicial** (T0 ≤ timestamp da resposta < T0 + 120 horas) e a **Leitura de Excedência** (T0 + 120 horas ≤ timestamp da resposta < T0 + 336 horas) — cada uma congelada e processada separadamente pelo Motor NSI, sem que uma altere, recalcule, misture, substitua ou invalide a outra.

Esta ADR não implementa nada. Ela define, antes de qualquer código, **quando uma resposta é aceita, quando uma leitura é congelada e o que acontece quando a janela se encerra**.

---

## 2. Escopo

### 2.1 Escopo desta decisão

- Definição da janela temporal total de uma operação de coleta (336 horas / 14 dias), contada a partir do timestamp exato do disparo do lote.
- Definição da Leitura Inicial (T0 ≤ timestamp da resposta < T0 + 120 horas) e da Leitura de Excedência (T0 + 120 horas ≤ timestamp da resposta < T0 + 336 horas) como intervalos que não se sobrepõem e não deixam lacunas entre si, com contagem em tempo exato — não em dias-calendário.
- Regra de que o encerramento da janela e o congelamento da Leitura de Excedência ocorrem de forma atômica, no mesmo instante (T0 + 336 horas), antes de qualquer processamento dessa leitura.
- Manutenção de "1º ao 5º dia" e "6º ao 14º dia" exclusivamente como linguagem simplificada voltada ao gestor, sem que isso altere a contagem exata em horas que rege o sistema.
- Regra de congelamento de cada leitura e de processamento separado pelo Motor NSI.
- Regra de encerramento definitivo da janela, exatamente 336 horas após o disparo: nenhuma resposta aceita após esse instante, nenhuma resposta enviada ao Motor NSI.
- Comportamento do canal de coleta após o encerramento da janela (mensagem de encerramento + orientação ao canal oficial da empresa).
- O princípio de que o Portal Executivo deve exibir as duas leituras separadamente, com identificação clara do período de cada uma — como regra de referência para a ADR-004, sem definir aqui sua apresentação visual.

### 2.2 Fora do escopo desta decisão

- Títulos definitivos do painel e das duas leituras — tratados em sessão própria, referenciando esta ADR quanto à regra temporal (ADR-004, Seção 7).
- Layout, cabeçalho, cards, KPIs, gráficos, filtros ou qualquer componente visual do Portal Executivo.
- Qualquer comparação automática de gravidade, importância ou prioridade entre as duas leituras.
- Soluções sugeridas, recomendações automáticas, comportamento consultivo ou qualquer mecanismo de IA para aconselhamento.
- Alterações a Processors, Models, Confidence Rules ou Outputs do Motor NSI além da regra de janela e leitura aqui definida.
- Definição de stack tecnológica, schema de banco de dados, API ou infraestrutura.
- Qualquer alteração ao Operations Console (ADR-001), à Fundação de Marca (ADR-002) ou ao Sistema Editorial Visual (ADR-003).

---

## 3. Contexto

Durante a continuidade da arquitetura da Tela 02 do Portal Executivo (ADR-004, Seção 7), foi definida a necessidade de o Painel apresentar duas leituras independentes do mesmo lote — uma referente às respostas recebidas nos primeiros dias da coleta, outra às respostas recebidas em um período de excedência subsequente. Essa necessidade ainda não estava registrada na ADR-004: a própria ADR-004 exclui explicitamente do seu escopo qualquer alteração ao Motor NSI (Seções 2.2 e 10), e a regra de quando uma resposta é aceita, quando uma leitura é congelada e quando a janela se encerra é uma regra de ingestão do Motor, não uma regra de apresentação do Portal.

Esta ADR registra essa regra no domínio a que ela pertence — o Motor NSI. A ADR-004 passa a referenciar esta ADR ao tratar da exibição das duas leituras no Painel, sem duplicar nem redefinir a regra temporal aqui estabelecida.

---

## 4. Princípios Arquiteturais do Ciclo Temporal de Coleta

### Princípio 1 — Janela Total de 336 Horas (14 dias)

Cada operação de coleta possui uma janela total de 336 horas (14 dias), contada a partir do timestamp exato do disparo do lote. Este é o limite absoluto de vida útil de uma operação de coleta, medido em tempo exato, não em dias-calendário.

### Princípio 2 — Leitura Inicial (T0 ≤ timestamp da resposta < T0 + 120 horas)

Pertencem à **Leitura Inicial** as respostas cujo timestamp seja maior ou igual ao do disparo (T0) e estritamente menor que T0 + 120 horas. Uma resposta recebida exatamente ao completar 120 horas não pertence à Leitura Inicial — pertence à Leitura de Excedência. Ao completar 120 horas, a Leitura Inicial é congelada e processada pelo Motor NSI. Para o gestor, esse período é comunicado como "1º ao 5º dia" — linguagem simplificada que não altera a contagem exata em horas que rege o sistema.

### Princípio 3 — Leitura de Excedência (T0 + 120 horas ≤ timestamp da resposta < T0 + 336 horas)

Pertencem à **Leitura de Excedência** as respostas cujo timestamp seja maior ou igual a T0 + 120 horas e estritamente menor que T0 + 336 horas. Uma resposta recebida exatamente ao completar 120 horas pertence à Leitura de Excedência, não à Leitura Inicial. Ao completar 336 horas, o encerramento da janela e o congelamento da Leitura de Excedência ocorrem de forma atômica, antes de ela ser processada separadamente pelo Motor NSI, como um segundo e distinto ciclo de processamento. Para o gestor, esse período é comunicado como "6º ao 14º dia" — linguagem simplificada que não altera a contagem exata em horas que rege o sistema.

### Princípio 4 — Independência Entre Leituras

A Leitura de Excedência não altera, não recalcula, não mistura, não substitui e não invalida a Leitura Inicial. Cada leitura, uma vez congelada e processada, é definitiva em si mesma.

### Princípio 5 — Unidade da Operação, Pluralidade de Recortes

As duas leituras pertencem à mesma operação e ao mesmo contexto de coleta — mas representam recortes temporais independentes daquela operação, não duas operações distintas.

### Princípio 6 — Ausência de Comparação Automática

Não existe comparação automática de gravidade, importância ou prioridade entre a Leitura Inicial e a Leitura de Excedência. Qualquer leitura comparativa entre elas, se um dia existir, pertence a uma decisão arquitetural futura e própria — nunca a uma inferência automática do Motor.

### Princípio 7 — Encerramento Definitivo da Janela

A janela está encerrada para todo timestamp de resposta maior ou igual a T0 + 336 horas. Uma resposta recebida exatamente ao completar 336 horas já está fora da janela e não é aceita. O encerramento da janela e o congelamento da Leitura de Excedência (Princípio 3) ocorrem de forma atômica — não existe instante em que a janela esteja indefinida entre um e outro. Nenhuma nova resposta é aceita como manifestação daquela operação, e nenhuma resposta é enviada ao Motor NSI, a partir desse instante. O encerramento é absoluto, medido em tempo exato, e não admite exceção por atraso, justificativa ou insistência do respondente.

### Princípio 8 — Comunicação de Encerramento ao Respondente

Quando uma resposta chega após o encerramento da janela, o canal deve informar que a coleta foi encerrada e orientar a pessoa a procurar o canal oficial da empresa. O silêncio do sistema diante de uma tentativa de resposta tardia não é uma opção arquitetural válida.

### Princípio 9 — Exibição Separada no Portal (regra de referência)

O Portal Executivo deve apresentar as duas leituras separadamente, com identificação clara do período de cada uma. Este princípio é a regra de referência para a arquitetura de exibição tratada na ADR-004 (Seção 7) — esta ADR não define layout, títulos ou componentes visuais para essa exibição.

### Princípio 10 — Fronteira Epistemológica do Motor

O ciclo temporal de coleta não altera a natureza do que o Motor NSI faz: organizar e evidenciar recorrências semânticas observáveis. O Motor não atravessa, em nenhuma das duas leituras, a fronteira entre evidência estatística e decisão humana — princípio já congelado na ADR-004 (Seção 7.17, Princípio da Observabilidade) e aqui reafirmado como válido para ambos os recortes temporais, sem exceção.

### Princípio 11 — Precisão dos Limites Temporais

Os limites das duas leituras e do encerramento da janela são intervalos que não se sobrepõem e não deixam lacunas entre si, medidos a partir do timestamp exato do disparo (T0):

- Leitura Inicial: T0 ≤ timestamp da resposta < T0 + 120 horas.
- Leitura de Excedência: T0 + 120 horas ≤ timestamp da resposta < T0 + 336 horas.
- Janela encerrada: timestamp da resposta ≥ T0 + 336 horas.

Esta é a definição formal e vinculante dos limites temporais desta ADR. A linguagem simplificada ("1º ao 5º dia", "6º ao 14º dia") é subordinada a esta definição, nunca o contrário.

---

## 5. Fluxo — Ciclo Temporal da Operação de Coleta

```
Disparo do lote (timestamp T0)
  ↓
T0 ≤ resposta < T0+120h — recebimento de respostas, Leitura Inicial ("1º ao 5º dia")
  ↓
T0+120h — Leitura Inicial congelada (resposta recebida exatamente aqui já pertence à Excedência)
  ↓
Leitura Inicial processada pelo Motor NSI
  ↓
T0+120h ≤ resposta < T0+336h — recebimento de respostas, Leitura de Excedência ("6º ao 14º dia")
  ↓
T0+336h — encerramento da janela e congelamento da Leitura de Excedência (atômico; resposta recebida exatamente aqui já está fora da janela)
  ↓
Leitura de Excedência processada separadamente pelo Motor NSI
  ↓
Nenhuma nova resposta é aceita como manifestação desta operação
```

---

## 6. Leitura Inicial (T0 ≤ timestamp da resposta < T0 + 120 horas)

- Compreende exclusivamente as respostas cujo timestamp seja maior ou igual ao do disparo (T0) e estritamente menor que T0 + 120 horas — comunicado ao gestor como "1º ao 5º dia".
- Uma resposta recebida exatamente ao completar 120 horas não integra a Leitura Inicial — pertence à Leitura de Excedência (Seção 7).
- Ao completar 120 horas, esta leitura é congelada: seu conjunto de respostas para fins de processamento não se altera mais.
- É processada pelo Motor NSI como um ciclo completo e definitivo.

---

## 7. Leitura de Excedência (T0 + 120 horas ≤ timestamp da resposta < T0 + 336 horas)

- Compreende exclusivamente as respostas cujo timestamp seja maior ou igual a T0 + 120 horas e estritamente menor que T0 + 336 horas — comunicado ao gestor como "6º ao 14º dia".
- Uma resposta recebida exatamente ao completar 120 horas pertence a esta leitura, não à Leitura Inicial.
- Uma resposta recebida exatamente ao completar 336 horas não pertence a esta leitura — já está fora da janela (Seção 8).
- Ao completar 336 horas, o encerramento da janela e o congelamento desta leitura ocorrem de forma atômica, **antes de ela ser processada** separadamente pelo Motor NSI, como um segundo ciclo de processamento, distinto do primeiro.
- Não recalcula, não mescla e não substitui os resultados já produzidos pela Leitura Inicial.
- Existe porque o gestor se beneficia de conhecer manifestações tardias — mas essas manifestações nunca contaminam a leitura já congelada.

---

## 8. Encerramento da Janela e Comunicação ao Respondente

- A janela está encerrada para todo timestamp de resposta maior ou igual a T0 + 336 horas. Uma resposta recebida exatamente ao completar 336 horas já está fora da janela.
- O encerramento da janela e o congelamento da Leitura de Excedência (Seção 7) ocorrem de forma atômica, no mesmo instante T0 + 336 horas, antes de qualquer processamento dessa leitura.
- Nenhuma resposta com timestamp maior ou igual a T0 + 336 horas é aceita como manifestação daquela operação.
- Nenhuma resposta com timestamp maior ou igual a T0 + 336 horas é enviada ao Motor NSI.
- Se uma pessoa tentar responder após o encerramento, o canal deve informar que a coleta foi encerrada e orientar a pessoa a procurar o canal oficial da empresa — nunca ignorar a tentativa silenciosamente, nunca fingir que a resposta foi recebida.

---

## 9. Relação com o Portal Executivo (ADR-004)

- O Portal Executivo deve apresentar a Leitura Inicial e a Leitura de Excedência separadamente, com identificação clara do período de cada uma.
- A regra temporal que origina essa separação — o que é cada leitura, quando ela é congelada, por que existem duas — pertence exclusivamente a esta ADR.
- A ADR-004 (Seção 7) é responsável por definir *como* essas duas leituras aparecem no Painel — títulos, posição, componentes visuais — sem jamais redefinir a regra temporal aqui registrada.
- Os títulos definitivos do painel e das duas leituras estão, neste momento, em definição — fora do escopo desta ADR (Seção 2.2).

---

## 10. Relação com a Filosofia do NSI

- O Motor NSI organiza e evidencia recorrências semânticas observáveis — em ambas as leituras, sem exceção.
- A existência de duas leituras não introduz nenhuma nova capacidade de julgamento, comparação de mérito ou recomendação ao Motor.
- O Motor não atravessa, em nenhum momento do ciclo temporal, a fronteira entre evidência estatística e decisão humana — reafirmando o Princípio da Observabilidade (ADR-004, Seção 7.17): *"O NSI organiza evidências. A interpretação pertence ao gestor."*

---

## 11. Decisões Aprovadas e Congeladas

1. Cada operação de coleta possui uma janela total de 336 horas (14 dias), contada a partir do timestamp exato do disparo (T0).
2. Pertencem à Leitura Inicial ("1º ao 5º dia") as respostas com T0 ≤ timestamp < T0 + 120 horas.
3. Ao completar 120 horas, a Leitura Inicial é congelada e processada pelo Motor NSI; uma resposta recebida exatamente nesse instante já pertence à Leitura de Excedência.
4. Pertencem à Leitura de Excedência ("6º ao 14º dia") as respostas com T0 + 120 horas ≤ timestamp < T0 + 336 horas.
5. Ao completar 336 horas, o encerramento da janela e o congelamento da Leitura de Excedência ocorrem de forma atômica, antes de ela ser processada separadamente pelo Motor NSI; uma resposta recebida exatamente nesse instante já está fora da janela.
6. A Leitura de Excedência não altera, recalcula, mistura, substitui ou invalida a Leitura Inicial.
7. As duas leituras pertencem à mesma operação e ao mesmo contexto de coleta, mas representam recortes temporais independentes, sem sobreposição e sem lacunas entre si.
8. Não existe comparação automática de gravidade, importância ou prioridade entre as duas leituras.
9. Para todo timestamp de resposta maior ou igual a T0 + 336 horas, nenhuma resposta é aceita como manifestação daquela operação, e nenhuma resposta é enviada ao Motor NSI.
10. O canal informa o encerramento da coleta e orienta a pessoa a procurar o canal oficial da empresa.
11. O Portal Executivo apresenta as duas leituras separadamente, com identificação clara do período de cada uma.

---

## 12. Dependências

- Depende da continuidade da arquitetura da Tela 02 do Portal Executivo (ADR-004, Seção 7), que motivou a necessidade das duas leituras exibidas separadamente no Painel Executivo — necessidade que esta ADR agora registra e formaliza no domínio do Motor NSI.
- Depende da ADR-004 (Seção 7.17, Princípio da Observabilidade), reafirmado aqui como válido para ambas as leituras.
- A ADR-004 passa a depender desta ADR quanto à regra temporal das duas leituras, mediante o ajuste de referência aplicado na própria ADR-004.

---

## 13. Itens Fora do Escopo

- Títulos definitivos do painel e das duas leituras.
- Layout, componentes visuais, cards, KPIs, gráficos, filtros ou arquitetura visual do Portal.
- Comparação automática entre as duas leituras.
- Soluções sugeridas, recomendações automáticas, comportamento consultivo ou mecanismo de IA para aconselhamento.
- Implementação de código, API, schema de dados ou infraestrutura.
- Qualquer alteração à ADR-001, à ADR-002 ou à ADR-003.

---

## 14. Referências

- `docs/architecture/ADR-004-portal-executivo-cliente.md` — Seção 7 (origem da necessidade das duas leituras) e Seção 7.17 (Princípio da Observabilidade, reafirmado nesta ADR).
- `docs/architecture/ADR-001-operations-console.md` — define o Motor NSI como componente invisível às plataformas do ecossistema (Seção 4.3).
