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

> **Nota de evolução (2026-08-23):** esta ADR recebeu uma evolução arquitetural aprovada, incorporando o convite de coleta como unidade de participação, os gatilhos de encerramento da Leitura de Excedência (antecipado e obrigatório), a ordem atômica na fronteira de 120 horas e os dois cenários distintos sem relatório (sem população pendente e zero respostas na excedência). O teto de 336 horas permanece o limite máximo absoluto. Ver Seção 15 para o registro completo da evolução.

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
- Definição do convite de coleta como unidade de participação e da regra de resposta única válida por convite de coleta durante toda a operação.
- Regra de que a primeira resposta válida de um convite de coleta encerra sua participação e move o convite para o estado "Respondido", tornando irrelevantes quaisquer mensagens posteriores daquele convite.
- Definição dos gatilhos de encerramento da Leitura de Excedência — antecipado (todos os convites de coleta pendentes respondidos) e obrigatório (T0 + 336 horas) —, preservando 336 horas como teto absoluto.
- Declaração explícita de que não existe critério amostral, percentual mínimo ou decisão por maioria para o encerramento antecipado.
- Registro do estado "Sem respostas de excedência", que ocorre apenas quando todos os convites de coleta já haviam respondido com timestamp estritamente anterior a T0 + 120 horas e nenhuma resposta é classificada na Leitura de Excedência na fronteira.
- Definição da ordem atômica das operações na fronteira T0 + 120 horas: congelamento da Leitura Inicial, início da Leitura de Excedência e só então verificação de população pendente.
- Registro do cenário em que havia população pendente ao iniciar a Leitura de Excedência, mas nenhuma resposta foi recebida até o encerramento obrigatório em T0 + 336 horas.

### 2.2 Fora do escopo desta decisão

- Títulos definitivos do painel e das duas leituras — tratados em sessão própria, referenciando esta ADR quanto à regra temporal (ADR-004, Seção 7).
- Layout, cabeçalho, cards, KPIs, gráficos, filtros ou qualquer componente visual do Portal Executivo.
- Qualquer comparação automática de gravidade, importância ou prioridade entre as duas leituras.
- Soluções sugeridas, recomendações automáticas, comportamento consultivo ou qualquer mecanismo de IA para aconselhamento.
- Alterações a Processors, Models, Confidence Rules ou Outputs do Motor NSI além da regra de janela e leitura aqui definida.
- Definição de stack tecnológica, schema de banco de dados, API ou infraestrutura.
- Estados visuais, barra de andamento e demais elementos de exibição da Segunda Leitura durante a coleta — tratados na ADR-004.
- Critérios técnicos que definem o que constitui uma resposta válida versus inválida.
- Definição do que a barra de andamento representa (tempo decorrido, quantidade de respostas ou percentual) — permanece em arquitetura para decisão futura.
- Qualquer alteração ao Operations Console (ADR-001), à Fundação de Marca (ADR-002) ou ao Sistema Editorial Visual (ADR-003).

---

## 3. Contexto

Durante a continuidade da arquitetura da Tela 02 do Portal Executivo (ADR-004, Seção 7), foi definida a necessidade de o Painel apresentar duas leituras independentes do mesmo lote — uma referente às respostas recebidas nos primeiros dias da coleta, outra às respostas recebidas em um período de excedência subsequente. Essa necessidade ainda não estava registrada na ADR-004: a própria ADR-004 exclui explicitamente do seu escopo qualquer alteração ao Motor NSI (Seções 2.2 e 10), e a regra de quando uma resposta é aceita, quando uma leitura é congelada e quando a janela se encerra é uma regra de ingestão do Motor, não uma regra de apresentação do Portal.

Esta ADR registra essa regra no domínio a que ela pertence — o Motor NSI. A ADR-004 passa a referenciar esta ADR ao tratar da exibição das duas leituras no Painel, sem duplicar nem redefinir a regra temporal aqui estabelecida.

---

## 4. Princípios Arquiteturais do Ciclo Temporal de Coleta

### Princípio 1 — Janela Total de 336 Horas (14 dias)

Cada operação de coleta possui uma janela total de, no máximo, 336 horas (14 dias), contada a partir do timestamp exato do disparo do lote. Este é o teto absoluto de vida útil de uma operação de coleta, medido em tempo exato, não em dias-calendário — a janela pode se encerrar antes desse teto por encerramento antecipado (Princípio 15) ou por ausência de população pendente (Princípio 17), mas nunca depois.

### Princípio 2 — Leitura Inicial (T0 ≤ timestamp da resposta < T0 + 120 horas)

Pertencem à **Leitura Inicial** as respostas cujo timestamp seja maior ou igual ao do disparo (T0) e estritamente menor que T0 + 120 horas. Uma resposta recebida exatamente ao completar 120 horas não pertence à Leitura Inicial — pertence à Leitura de Excedência. Ao completar 120 horas, a Leitura Inicial é congelada e processada pelo Motor NSI. Para o gestor, esse período é comunicado como "1º ao 5º dia" — linguagem simplificada que não altera a contagem exata em horas que rege o sistema.

### Princípio 3 — Leitura de Excedência (T0 + 120 horas ≤ timestamp da resposta < T0 + 336 horas)

Pertencem à **Leitura de Excedência** as respostas cujo timestamp seja maior ou igual a T0 + 120 horas e estritamente menor que o instante efetivo de encerramento, limitado no máximo a T0 + 336 horas. Uma resposta recebida exatamente ao completar 120 horas pertence à Leitura de Excedência, não à Leitura Inicial — classificada nessa ordem antes de qualquer verificação de população pendente (Princípio 18). No instante efetivo de encerramento (Princípio 15), a Leitura de Excedência é congelada de forma atômica, antes de ser processada separadamente pelo Motor NSI, como um segundo e distinto ciclo de processamento — exceto nos dois cenários sem coleta ou sem resultado (Princípios 17 e 19), em que não há relatório semântico vazio. Quando há processamento, a Leitura de Excedência fica disponível ao gestor ao final dele. Para o gestor, esse período é comunicado como "6º ao 14º dia" — linguagem simplificada que não altera a contagem exata em horas nem os gatilhos de encerramento que regem o sistema.

### Princípio 4 — Independência Entre Leituras

A Leitura de Excedência não altera, não recalcula, não mistura, não substitui e não invalida a Leitura Inicial. Cada leitura, uma vez congelada e processada, é definitiva em si mesma.

### Princípio 5 — Unidade da Operação, Pluralidade de Recortes

As duas leituras pertencem à mesma operação e ao mesmo contexto de coleta — mas representam recortes temporais independentes daquela operação, não duas operações distintas.

### Princípio 6 — Ausência de Comparação Automática

Não existe comparação automática de gravidade, importância ou prioridade entre a Leitura Inicial e a Leitura de Excedência. Qualquer leitura comparativa entre elas, se um dia existir, pertence a uma decisão arquitetural futura e própria — nunca a uma inferência automática do Motor.

### Princípio 7 — Encerramento Definitivo da Janela

A janela se encerra no instante efetivo de encerramento — o primeiro entre o encerramento antecipado (Princípio 15), a ausência de população pendente (Princípio 17) e o encerramento obrigatório em T0 + 336 horas. T0 + 336 horas é o teto absoluto: a janela nunca permanece aberta além desse instante, mesmo que existam convites de coleta sem resposta. A partir do instante efetivo de encerramento, nenhuma nova resposta é aceita como manifestação daquela operação, e nenhuma resposta é enviada ao Motor NSI. O encerramento da janela e o congelamento da Leitura de Excedência (Princípio 3) ocorrem de forma atômica, no mesmo instante — não existe intervalo em que a janela esteja indefinida entre um e outro. O encerramento é absoluto, medido em tempo exato, e não admite exceção por atraso, justificativa ou insistência do respondente.

### Princípio 8 — Comunicação de Encerramento ao Respondente

Quando uma resposta chega após o encerramento da janela, o canal deve informar que a coleta foi encerrada e orientar a pessoa a procurar o canal oficial da empresa. O silêncio do sistema diante de uma tentativa de resposta tardia não é uma opção arquitetural válida.

Este princípio trata do encerramento da janela como um todo; a comunicação a um convite de coleta individual já respondido, independentemente do estado da janela, é tratada pelo Princípio 14.

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

O limite superior da Leitura de Excedência (T0 + 336 horas nesta definição) é o teto absoluto da janela. Quando o instante efetivo de encerramento (Princípio 15) ocorrer antes desse teto — por encerramento antecipado ou por ausência de população pendente (Princípio 17) —, o limite superior efetivo da Leitura de Excedência passa a ser esse instante — nunca um instante posterior a T0 + 336 horas.

### Princípio 12 — Convite de Coleta como Unidade de Participação

Cada convite de coleta válido de uma operação é a unidade de participação do respondente. Um convite de coleta aceita, no máximo, uma resposta válida durante toda a operação — nunca mais de uma, independentemente de quantas mensagens o respondente enviar.

### Princípio 13 — Encerramento Individual da Participação

A primeira resposta válida recebida para um convite de coleta encerra individualmente a participação daquele convite. A partir desse instante, o convite de coleta assume o estado "Respondido" e permanece nesse estado até o encerramento da operação. Este princípio se aplica a qualquer momento da operação, inclusive durante a Leitura Inicial (Seção 6).

### Princípio 14 — Irrelevância de Mensagens Posteriores ao Convite de Coleta Já Respondido

Uma vez que um convite de coleta esteja no estado "Respondido", qualquer mensagem posterior daquele mesmo convite: não integra a coleta; não altera a resposta já registrada; não reabre a participação; não é enviada novamente ao Motor NSI. O canal pode confirmar ao respondente: "Sua resposta já foi registrada. Agradecemos sua participação."

### Princípio 15 — Gatilhos de Encerramento da Leitura de Excedência

A Leitura de Excedência encerra no primeiro dos gatilhos a se cumprir:

- **Encerramento antecipado:** depois da classificação de eventuais respostas na fronteira T0 + 120 horas (Princípio 18) ou a qualquer momento posterior, não resta nenhum convite de coleta pendente. Se, nesse momento, a Leitura de Excedência já contiver uma ou mais respostas válidas — incluindo respostas classificadas exatamente em T0 + 120 horas —, elas integram a leitura, que é congelada e processada normalmente pelo Motor NSI, ficando disponível ao gestor ao final do processamento. Se, nesse mesmo momento, a Leitura de Excedência não contiver nenhuma resposta — o que só é possível quando todos os convites já haviam sido respondidos por respostas anteriores a T0 + 120 horas —, aplica-se o Princípio 17 ("Sem respostas de excedência"), sem coleta nem processamento.
- **Encerramento obrigatório:** o instante T0 + 336 horas é atingido, mesmo que existam convites de coleta ainda sem resposta.

O limite de 336 horas (Princípio 1) permanece o teto absoluto: o encerramento antecipado pode ocorrer antes desse instante, nunca depois. O cenário de população pendente sem nenhuma resposta até o encerramento obrigatório é tratado no Princípio 19.

### Princípio 16 — Ausência de Critério Amostral ou Majoritário

Não existe percentual mínimo, amostragem suficiente ou decisão automática baseada em 80%, maioria ou relevância estatística para encerrar a Leitura de Excedência antes do prazo. O único critério de encerramento antecipado é a resposta de 100% dos convites de coleta pendentes (Princípio 15) — qualquer outro critério pertence a uma decisão arquitetural futura e própria, se um dia existir.

### Princípio 17 — Sem Respostas de Excedência

O estado "Sem respostas de excedência" ocorre exclusivamente quando, após a ordem atômica da fronteira T0 + 120 horas (Princípio 18):

- todos os convites de coleta da operação já estavam no estado "Respondido" por respostas com timestamp estritamente menor que T0 + 120 horas; e
- nenhuma resposta válida foi classificada na Leitura de Excedência no instante T0 + 120 horas.

Nesse cenário — e somente nele — não existe população pendente, não existe resposta de excedência, a Leitura de Excedência não é coletada nem processada, e nenhum relatório semântico vazio é produzido pelo Motor NSI. Este cenário não representa erro, insuficiência ou falha do sistema.

Este princípio não se aplica quando uma ou mais respostas válidas forem classificadas na Leitura de Excedência exatamente em T0 + 120 horas, ainda que essas respostas completem o estado "Respondido" de todos os convites — esse é o cenário de encerramento antecipado do Princípio 15, que exige processamento.

Se, após a fronteira, existirem convites de coleta ainda sem resposta, a coleta da Leitura de Excedência continua normalmente e segue os gatilhos do Princípio 15, até que todos os pendentes respondam ou até T0 + 336 horas, o que ocorrer primeiro.

### Princípio 18 — Ordem Atômica na Fronteira de T0 + 120 Horas

No instante T0 + 120 horas, as seguintes operações ocorrem nesta ordem exata:

1. A Leitura Inicial é congelada, compreendendo exclusivamente as respostas com timestamp estritamente menor que T0 + 120 horas.
2. A Leitura de Excedência é aberta. Todas as respostas válidas com timestamp exatamente igual a T0 + 120 horas são classificadas nela, nunca na Leitura Inicial.
3. Somente depois dessa classificação, verifica-se a população pendente e o conteúdo já classificado na Leitura de Excedência (Princípios 15 e 17).

Esta ordem é vinculante: nenhuma resposta recebida exatamente em T0 + 120 horas pode ser tratada como inexistente ou descartada apenas porque, após sua classificação, não resta nenhum convite de coleta pendente. Nesse caso, o cenário aplicável é sempre o encerramento antecipado com processamento (Princípio 15) — nunca o estado "Sem respostas de excedência" (Princípio 17), que exige que a Leitura de Excedência esteja vazia após a classificação.

### Princípio 19 — Leitura de Excedência com População Pendente e Zero Respostas

Quando, após a ordem atômica da fronteira T0 + 120 horas (Princípio 18), restarem convites de coleta pendentes — havendo ou não respostas já classificadas na Leitura de Excedência nesse instante —, a coleta segue o Princípio 15 até o encerramento obrigatório em T0 + 336 horas, caso o encerramento antecipado não ocorra antes. Se, ao final da janela, a Leitura de Excedência não contiver nenhuma resposta válida, o Motor NSI não processa um relatório semântico vazio, e o Portal apresenta o estado "Nenhuma resposta recebida no período de excedência" — distinto do estado "Sem respostas de excedência" (Princípio 17), que só pode ocorrer na fronteira T0 + 120 horas, nunca em T0 + 336 horas. Este cenário não representa erro, insuficiência ou falha do sistema.

Havendo pelo menos uma resposta válida na Leitura de Excedência ao final da janela — classificada na fronteira (Princípio 18) ou recebida posteriormente —, a leitura é congelada, processada e disponibilizada normalmente (Princípio 3), independentemente de o encerramento ter sido antecipado ou obrigatório.

---

## 5. Fluxo — Ciclo Temporal da Operação de Coleta

```
Disparo do lote (timestamp T0)
  ↓
T0 ≤ resposta < T0+120h — recebimento de respostas, Leitura Inicial ("1º ao 5º dia")
  ↓
T0+120h — ordem atômica (Princípio 18):
  1. Leitura Inicial congelada (timestamp < T0+120h)
  2. Leitura de Excedência aberta; toda resposta válida com timestamp = T0+120h é classificada nela
  3. verificação de população pendente e do conteúdo já classificado, somente após essa classificação
  ↓
Leitura Inicial processada pelo Motor NSI
  ↓
Após a classificação da fronteira: resta convite de coleta pendente?
  (i) NÃO e Leitura de Excedência contém ≥1 resposta → encerramento antecipado (Princípio 15): leitura congelada e processada normalmente
  (ii) NÃO e Leitura de Excedência contém 0 respostas → estado "Sem respostas de excedência" (Princípio 17): sem coleta, sem processamento
  (iii) SIM → segue abaixo
  ↓ (somente cenário iii)
T0+120h ≤ resposta < instante efetivo de encerramento — recebimento de respostas adicionais, Leitura de Excedência ("6º ao 14º dia")
  ↓
Instante efetivo de encerramento — o que ocorrer primeiro:
  (a) todos os convites de coleta pendentes respondidos (encerramento antecipado, Princípio 15)
  (b) T0+336h (encerramento obrigatório, teto absoluto)
  ↓
Leitura de Excedência congelada no instante efetivo de encerramento (atômico)
  ↓
A Leitura de Excedência contém ao menos uma resposta válida? (Princípio 19)
  (i) NÃO (só possível via gatilho b) → Motor não processa relatório vazio → estado "Nenhuma resposta recebida no período de excedência"
  (ii) SIM → processada separadamente pelo Motor NSI → disponível ao gestor
  ↓
Nenhuma nova resposta é aceita como manifestação desta operação
```

---

## 6. Leitura Inicial (T0 ≤ timestamp da resposta < T0 + 120 horas)

- Compreende exclusivamente as respostas cujo timestamp seja maior ou igual ao do disparo (T0) e estritamente menor que T0 + 120 horas — comunicado ao gestor como "1º ao 5º dia".
- Uma resposta recebida exatamente ao completar 120 horas não integra a Leitura Inicial — pertence à Leitura de Excedência (Seção 7).
- Ao completar 120 horas, esta leitura é congelada: seu conjunto de respostas para fins de processamento não se altera mais.
- É processada pelo Motor NSI como um ciclo completo e definitivo.
- Aplica-se aqui, como em toda a operação, o Princípio 12 (Convite de Coleta como Unidade de Participação): a primeira resposta válida de um convite de coleta encerra sua participação, ainda que recebida durante a Leitura Inicial.

---

## 7. Leitura de Excedência (T0 + 120 horas ≤ timestamp da resposta < T0 + 336 horas)

- Compreende exclusivamente as respostas cujo timestamp seja maior ou igual a T0 + 120 horas e estritamente menor que o instante efetivo de encerramento, limitado no máximo a T0 + 336 horas — comunicado ao gestor como "6º ao 14º dia".
- Uma resposta recebida exatamente ao completar 120 horas pertence a esta leitura, não à Leitura Inicial.
- Se, após a ordem atômica da fronteira T0 + 120 horas (Princípio 18), não restar convite de coleta pendente e a Leitura de Excedência contiver uma ou mais respostas válidas, ocorre encerramento antecipado (Princípio 15): essas respostas integram a leitura, que é congelada, processada pelo Motor NSI e disponibilizada ao gestor ao final do processamento.
- Se, após essa mesma classificação, não restar convite de coleta pendente e a Leitura de Excedência não contiver nenhuma resposta — ou seja, todos os convites já haviam sido respondidos por respostas anteriores a T0 + 120 horas —, esta leitura não é coletada nem processada pelo Motor NSI. No Portal, esse cenário é o estado "Sem respostas de excedência" (Princípio 17 / ADR-004, Seção 7.24), não um erro, insuficiência ou falha.
- Se, após a classificação, houver convites de coleta pendentes, a coleta continua normalmente e encerra quando todos os pendentes responderem ou em T0 + 336 horas, o que ocorrer primeiro. Se, ao final, a Leitura de Excedência não contiver nenhuma resposta válida, o Motor NSI não processa um relatório semântico vazio (Princípio 19); o Portal apresenta o estado "Nenhuma resposta recebida no período de excedência" — distinto do estado anterior.
- Havendo pelo menos uma resposta válida na Leitura de Excedência ao final da janela — classificada na fronteira ou recebida posteriormente —, a leitura é congelada, processada e disponibilizada normalmente.
- Uma resposta com timestamp igual ou posterior ao instante efetivo de encerramento não pertence a esta leitura — já está fora da janela (Seção 8).
- Não recalcula, não mescla e não substitui os resultados já produzidos pela Leitura Inicial.
- Existe porque o gestor se beneficia de conhecer manifestações tardias — mas essas manifestações nunca contaminam a leitura já congelada.
- Não existe percentual mínimo, amostragem suficiente ou decisão automática baseada em 80%, maioria ou relevância para o encerramento antecipado (Princípio 16) — o único critério é 100% dos convites de coleta pendentes respondidos.

---

## 8. Encerramento da Janela e Comunicação ao Respondente

- A janela se encerra no instante efetivo de encerramento — o primeiro entre encerramento antecipado (Princípio 15), ausência de população pendente (Princípio 17) e encerramento obrigatório em T0 + 336 horas. T0 + 336 horas é o teto absoluto, nunca ultrapassado.
- O encerramento da janela e o congelamento da Leitura de Excedência (Seção 7), quando aplicável, ocorrem de forma atômica, no mesmo instante do gatilho, antes de qualquer processamento dessa leitura.
- A partir do instante efetivo de encerramento, nenhuma resposta é aceita como manifestação daquela operação, e nenhuma resposta é enviada ao Motor NSI.
- Se um convite de coleta que ainda não respondeu tentar enviar uma mensagem após o encerramento da janela, o canal deve informar que a coleta foi encerrada e orientar a pessoa a procurar o canal oficial da empresa — nunca ignorar a tentativa silenciosamente, nunca fingir que a resposta foi recebida.
- Se um convite de coleta já no estado "Respondido" (Princípio 13) enviar qualquer mensagem posterior — antes ou depois do encerramento da janela —, o canal pode confirmar: "Sua resposta já foi registrada. Agradecemos sua participação." (Princípio 14). Esta mensagem trata do convite de coleta individual; a mensagem do item anterior trata da operação como um todo — não devem ser confundidas.

---

## 9. Relação com o Portal Executivo (ADR-004)

- O Portal Executivo deve apresentar a Leitura Inicial e a Leitura de Excedência separadamente, com identificação clara do período de cada uma.
- A regra temporal que origina essa separação — o que é cada leitura, quando ela é congelada, por que existem duas — pertence exclusivamente a esta ADR.
- A ADR-004 (Seção 7) é responsável por definir *como* essas duas leituras aparecem no Painel — títulos, posição, componentes visuais — sem jamais redefinir a regra temporal aqui registrada.
- Os títulos definitivos do painel e das duas leituras estão, neste momento, em definição — fora do escopo desta ADR (Seção 2.2).
- O comportamento de bloqueio de conteúdo, barra de andamento e estados visuais da Segunda Leitura durante a coleta — incluindo os dois cenários sem relatório (Princípios 17 e 19) — é registrado na ADR-004, Seção 7.24, reagindo aos eventos definidos nesta ADR sem redefini-los.

---

## 10. Relação com a Filosofia do NSI

- O Motor NSI organiza e evidencia recorrências semânticas observáveis — em ambas as leituras, sem exceção.
- A existência de duas leituras não introduz nenhuma nova capacidade de julgamento, comparação de mérito ou recomendação ao Motor.
- O Motor não atravessa, em nenhum momento do ciclo temporal, a fronteira entre evidência estatística e decisão humana — reafirmando o Princípio da Observabilidade (ADR-004, Seção 7.17): *"O NSI organiza evidências. A interpretação pertence ao gestor."*
- A ausência de critério amostral, percentual mínimo ou decisão por maioria (Princípio 16) reafirma que o Motor não introduz julgamento estatístico sobre suficiência de dados — apenas observa e processa o que foi efetivamente coletado, dentro dos limites e gatilhos definidos.
- A ausência de relatório — seja pelo estado "Sem respostas de excedência" (Princípio 17, quando nenhuma resposta é classificada na fronteira T0 + 120h) seja pelo estado "Nenhuma resposta recebida no período de excedência" (Princípio 19) — não é tratada como falha ou insuficiência; é um fato observável, coerente com a neutralidade do Motor. Em nenhum dos dois cenários o Motor processa um relatório semântico vazio.

---

## 11. Decisões Aprovadas e Congeladas

1. Cada operação de coleta possui uma janela total de 336 horas (14 dias), contada a partir do timestamp exato do disparo (T0).
2. Pertencem à Leitura Inicial ("1º ao 5º dia") as respostas com T0 ≤ timestamp < T0 + 120 horas.
3. Ao completar 120 horas, a Leitura Inicial é congelada e processada pelo Motor NSI; uma resposta recebida exatamente nesse instante já pertence à Leitura de Excedência.
4. A Leitura de Excedência compreende respostas com timestamp maior ou igual a T0 + 120 horas e estritamente menor que o instante efetivo de encerramento, limitado no máximo a T0 + 336 horas. *(Corrigido nesta versão — ver Seção 15.)*
5. A Leitura de Excedência encerra no instante efetivo de encerramento — o primeiro entre o encerramento antecipado (todos os convites de coleta pendentes respondidos), a ausência de população pendente (Item 19) e o encerramento obrigatório em T0 + 336 horas, que permanece o teto absoluto —; nesse instante, quando houver população pendente e ao menos uma resposta recebida, o encerramento da janela e o congelamento da Leitura de Excedência ocorrem de forma atômica, antes de ela ser processada separadamente pelo Motor NSI e, em seguida, disponibilizada ao gestor. *(Evoluído nesta versão — ver Seção 15; texto original preservado no histórico do Git, commit `335b353`.)*
6. A Leitura de Excedência não altera, recalcula, mistura, substitui ou invalida a Leitura Inicial.
7. As duas leituras pertencem à mesma operação e ao mesmo contexto de coleta, mas representam recortes temporais independentes, sem sobreposição e sem lacunas entre si.
8. Não existe comparação automática de gravidade, importância ou prioridade entre as duas leituras.
9. A partir do instante efetivo de encerramento — antecipado ou obrigatório — nenhuma nova resposta é aceita como manifestação da operação e nenhuma resposta é enviada ao Motor NSI. *(Corrigido nesta versão — ver Seção 15.)*
10. O canal informa o encerramento da coleta e orienta a pessoa a procurar o canal oficial da empresa.
11. O Portal Executivo apresenta as duas leituras separadamente, com identificação clara do período de cada uma.
12. Cada convite de coleta válido aceita, no máximo, uma resposta válida durante toda a operação.
13. A primeira resposta válida de um convite de coleta encerra individualmente sua participação; a partir desse instante, o convite de coleta assume o estado "Respondido".
14. Mensagens posteriores de um convite de coleta já no estado "Respondido" não integram a coleta, não alteram a resposta registrada, não reabrem a participação e não são enviadas novamente ao Motor NSI.
15. O canal pode confirmar ao respondente de um convite de coleta já respondido: "Sua resposta já foi registrada. Agradecemos sua participação."
16. A Leitura de Excedência possui dois gatilhos de encerramento entre convites de coleta pendentes: antecipado (todos respondidos) e obrigatório (T0 + 336 horas) — o que ocorrer primeiro.
17. Não existe percentual mínimo, amostragem suficiente ou decisão automática baseada em 80%, maioria ou relevância para o encerramento antecipado.
18. Ao ocorrer qualquer um dos gatilhos com população pendente e ao menos uma resposta recebida, a coleta da Leitura de Excedência é encerrada, seu conjunto de respostas é congelado, ela é processada separadamente pelo Motor NSI e, depois do processamento, fica disponível ao gestor.
19. O estado "Sem respostas de excedência" ocorre exclusivamente quando todos os convites de coleta já haviam sido respondidos por respostas com timestamp estritamente menor que T0 + 120 horas e nenhuma resposta válida for classificada na Leitura de Excedência exatamente em T0 + 120 horas: nesse caso, e somente nele, a Leitura de Excedência não é coletada nem processada, e nenhum relatório semântico vazio é produzido. *(Corrigido nesta versão — ver Seção 15.)*
20. No instante T0 + 120 horas, a Leitura Inicial é congelada primeiro (timestamps estritamente menores que T0 + 120h), a Leitura de Excedência é aberta em seguida e toda resposta válida com timestamp igual a T0 + 120h é classificada nela, e somente depois dessa classificação se verifica a população pendente e o conteúdo já classificado (Itens 18 e 19). Uma ou mais respostas recebidas exatamente em T0 + 120h que completem o estado "Respondido" de todos os convites de coleta configuram encerramento antecipado (Item 16): essas respostas integram a Leitura de Excedência e são processadas normalmente pelo Motor NSI — nunca o cenário "Sem respostas de excedência" do Item 19, que exige que a Leitura de Excedência esteja vazia após a classificação.
21. Se, após a classificação da fronteira (Item 20), havia convites de coleta pendentes, mas nenhuma resposta válida for recebida na Leitura de Excedência até o encerramento obrigatório em T0 + 336 horas, a coleta é encerrada normalmente, o Motor NSI não processa um relatório semântico vazio, e o Portal apresenta o estado "Nenhuma resposta recebida no período de excedência" — distinto do estado "Sem respostas de excedência" (Item 19) e igualmente não representando erro, insuficiência ou falha do sistema. Havendo pelo menos uma resposta válida na Leitura de Excedência ao final — classificada na fronteira ou recebida posteriormente —, a leitura é congelada, processada e disponibilizada normalmente.

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
- Estados visuais, barra de andamento e demais elementos de exibição da Segunda Leitura durante a coleta.
- Critérios técnicos que definem o que constitui uma resposta válida versus inválida.
- Definição do que a barra de andamento representa (tempo, quantidade ou percentual).
- Qualquer alteração à ADR-001, à ADR-002 ou à ADR-003.

---

## 14. Referências

- `docs/architecture/ADR-004-portal-executivo-cliente.md` — Seção 7 (origem da necessidade das duas leituras) e Seção 7.17 (Princípio da Observabilidade, reafirmado nesta ADR).
- `docs/architecture/ADR-001-operations-console.md` — define o Motor NSI como componente invisível às plataformas do ecossistema (Seção 4.3).

---

## 15. Evolução Aprovada — Convite de Coleta, Gatilhos de Encerramento e Cenários Sem Relatório (2026-08-23)

Esta seção documenta uma evolução aprovada da ADR-005, na mesma data do congelamento original, preservando o histórico conceitual da versão anterior (commit `335b353`) sem apagá-lo.

**O que foi adicionado:**
- O convite de coleta como unidade de participação, com resposta única válida por operação (Princípios 12-14) — termo escolhido deliberadamente para não colidir com o "convite" de acesso ao Portal já definido na ADR-004 (Seção 4, Princípio 1).
- A mensagem de confirmação ao respondente de um convite de coleta já respondido (Princípio 14 / Seção 8).
- Os gatilhos de encerramento da Leitura de Excedência — antecipado (todos os convites de coleta pendentes respondidos) e obrigatório (T0 + 336 horas) — (Princípio 15).
- A ausência explícita de critério amostral, percentual mínimo ou decisão por maioria como condição de encerramento (Princípio 16).
- O estado "Sem respostas de excedência" (Princípio 17, Item 19), que ocorre apenas quando todos os convites de coleta responderam com timestamp estritamente anterior a T0 + 120h e nenhuma resposta é classificada na fronteira: a Leitura de Excedência não é coletada nem processada, e nenhum relatório semântico vazio é produzido.
- A ordem atômica das operações na fronteira T0 + 120 horas (Princípio 18, Item 20): a Leitura Inicial congela primeiro, a Leitura de Excedência recebe as respostas com timestamp exatamente igual a T0 + 120h, e só depois se verifica a população pendente — garantindo que uma resposta de fronteira que complete a população seja processada normalmente, e não descartada como "sem população".
- O cenário de população pendente sem nenhuma resposta recebida até o encerramento obrigatório (Princípio 19, Item 21): o Motor não processa relatório vazio, e o Portal apresenta um estado distinto do cenário sem população pendente.

**O que foi corrigido para eliminar contradição:**
- Os Princípios 3 e 7, e as Seções 5, 7 e 8, descreviam o encerramento da Leitura de Excedência e da janela como ocorrendo exclusivamente no instante T0 + 336 horas. Corrigido para "instante efetivo de encerramento", com T0 + 336 horas como teto absoluto, não como único instante possível.
- Os Itens 4, 5, 9 e 18 da Seção 11 foram reescritos pelo mesmo motivo, com ressalva explícita para os cenários sem relatório (Itens 19 e 21).
- A verificação de população pendente e do conteúdo da Leitura de Excedência (Princípios 15, 17 e 18) foi corrigida para distinguir explicitamente dois casos após a classificação da fronteira T0 + 120 horas: (a) zero convites pendentes com uma ou mais respostas já classificadas na Leitura de Excedência — encerramento antecipado, com processamento; e (b) zero convites pendentes e zero respostas classificadas — estado "Sem respostas de excedência", sem processamento. A versão anterior desta evolução testava apenas a ausência de convites pendentes, o que classificaria incorretamente uma resposta de fronteira que completasse a população como se a Leitura de Excedência estivesse vazia.

**Os dois estados sem relatório, diferenciados com precisão:**
- **"Sem respostas de excedência"** (Princípio 17 / Item 19): todos os convites de coleta já haviam sido respondidos por respostas com timestamp estritamente menor que T0 + 120 horas, e nenhuma resposta foi classificada na Leitura de Excedência na fronteira. A Leitura de Excedência nunca chega a existir com conteúdo.
- **"Nenhuma resposta recebida no período de excedência"** (Princípio 19 / Item 21): havia convite de coleta pendente após a fronteira, mas a Leitura de Excedência termina vazia no encerramento obrigatório em T0 + 336h.
Uma resposta classificada exatamente na fronteira T0 + 120 horas que complete a população nunca produz o primeiro estado — produz encerramento antecipado com processamento normal (Princípio 15). Ambos os estados sem relatório são fatos observáveis, não falhas — e em nenhum dos dois o Motor NSI processa um relatório semântico vazio.

**O que não mudou:**
- A janela total de 336 horas (Princípio 1) permanece o limite máximo absoluto — nenhum gatilho pode estendê-la, apenas adiantá-la.
- A independência entre as duas leituras (Princípio 4) e a ausência de comparação automática (Princípio 6) permanecem integralmente válidas.
- Nenhuma decisão desta evolução altera layout, títulos, cor ou o que a barra de andamento representa — tudo isso permanece em arquitetura para decisão futura (ADR-004, Seção 7.24).

---

## 16. Evolução Aprovada — Identidade Técnica da Leitura (2026-08-25)

Esta seção documenta uma evolução aprovada da ADR-005, identificada durante a arquitetura do schema conceitual da Trajetória Contínua (ADR-006), sem alterar nenhum texto já congelado anteriormente — incluindo a evolução já registrada na Seção 15.

**O que foi adicionado:**
- Identidade técnica da Leitura: chave composta por `operacao_id` (ADR-001, Seção 16) + tipo de leitura (Inicial | Excedência) — os dois tipos fechados já definidos pelos Princípios 2 e 3 desta ADR, sem introduzir um terceiro tipo ou alterar qualquer regra de janela.
- Essa identidade é estritamente separada de: estado da leitura (ex.: "Coleta em andamento", "Sem respostas de excedência"), a janela temporal em si (Princípios 1-3 e 11) e o relatório eventualmente produzido pelo Motor — nenhum desses integra a identidade; todos são atributos associados a ela.
- A chave permanece endereçável mesmo nos dois cenários sem relatório semântico (Princípios 17 e 19) — a ausência de relatório não impede que a Leitura de Excedência seja referenciada e tenha seu estado preservado historicamente.

**O que não mudou:**
- Nenhuma alteração às regras temporais, aos gatilhos de encerramento ou aos Princípios 1-19 e à evolução da Seção 15.
- Nenhuma implementação de código, schema de banco de dados ou API é definida aqui — apenas identidade conceitual.
- Continua fora do escopo desta ADR: onde e como o estado de cada leitura é efetivamente persistido (Seção 13, Itens Fora do Escopo).

**Origem desta decisão:**
- Registrada como pré-requisito do schema conceitual da Trajetória Contínua (ADR-006), que precisa vincular cada trajetória a uma Leitura específica sem ambiguidade.

---

## 17. Evolução Aprovada — Distinção Formal entre M0 e T0 da Coleta (2026-08-27)

Esta seção documenta uma evolução aprovada da ADR-005, complementando o Princípio 1 (Janela Total de 336 Horas) sem alterar seu texto. Nenhuma janela, gatilho ou decisão já congelada nas Seções 1 a 16 é alterada.

**O que foi adicionado:**
- O T0 desta ADR — "o timestamp exato do disparo do lote" (Princípio 1) — é agora formalmente distinguido de M0, o Marco de Upload definido na ADR-007 (Seção 6), que corresponde ao momento em que o CSV original é recebido e o lote é criado, anterior ao disparo.
- A ADR-007 define M0 e passa a reger integralmente o intervalo entre M0 e o disparo (validação, correção, congelamento, confirmação humana em dois atos) — um domínio inteiramente anterior ao início da janela de coleta desta ADR.
- O T0 desta ADR passa a ser operacionalmente definido, pela ADR-007 (Seção 18), como o timestamp exato do primeiro disparo confirmado pelo Operador Interno da NSI — preenchendo, sem alterar, a definição já existente do Princípio 1.

**O que não mudou:**
- Nenhuma alteração à janela de 336 horas, aos gatilhos de encerramento, aos princípios do convite de coleta (Princípios 12-14) ou a qualquer outra decisão já congelada nesta ADR.
- Esta ADR continua a não tratar de nada anterior ao disparo do lote — o que acontece antes (upload, validação, correção, congelamento, confirmação humana) pertence exclusivamente à ADR-007.

**Origem desta decisão:**
- Registrada durante a arquitetura do ciclo operacional de preparação e disparo da coleta (ADR-007), que precisou nomear e distinguir formalmente os dois relógios do sistema — M0 e T0 — para evitar colisão terminológica.
