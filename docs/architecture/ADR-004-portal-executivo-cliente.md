# ADR-004 — Portal Executivo do Cliente

## Metadados

| Campo | Valor |
|---|---|
| Status | Aprovado |
| Data | 2026-07-05 |
| Versão de referência do sistema | `v1.1.0-fonte-unica-webhook-motor` |
| Commit de referência | `d1b1e6e` |
| Branch | `master` |
| Escopo desta ADR | Arquitetura — nenhuma implementação de código, frontend ou componente visual |

> **Nota de processo:** ADR aberta exclusivamente para a arquitetura do Portal Executivo do Cliente, conforme previsto pela ADR-001 (Seções 2.2, 13 e 15: *"Definição do Portal Executivo do Cliente em detalhe (tratado em ADR futura)"*). A ADR-001 não é alterada por este documento. A Tela 01 (Seção 6) é a primeira tela oficialmente congelada do Portal. A Tela 02 (Seção 7) tem, nesta versão, seus princípios arquiteturais aprovados — status **EM ARQUITETURA**; layout, cabeçalho, cards, KPIs, gráficos, filtros e arquitetura visual permanecem em aberto para sessão futura.

---

## 1. Objetivo

Registrar a arquitetura completa do **Portal Executivo do Cliente** — uma das três plataformas do ecossistema NSI, já delimitada conceitualmente pela ADR-001 (Seção 4.2), agora detalhada tela por tela.

Esta ADR não implementa nada. Ela define, antes de qualquer código, **como o cliente entra no Portal, o que vê e por quê** — começando pela porta de entrada: o acesso.

---

## 2. Escopo

### 2.1 Escopo desta decisão

- Toda a arquitetura do Portal Executivo do Cliente, tela por tela, ao longo do tempo — cada tela congelada nesta mesma ADR, em versões subsequentes.
- **Tela 01 — Acesso ao Portal Executivo** (Seção 6): fluxo de acesso, cadastro, autenticação, isolamento de dados por empresa e boas-vindas ao primeiro acesso.
- **Tela 02 — Home (Painel Executivo do Portal)** (Seção 7): princípios arquiteturais aprovados nesta versão — status EM ARQUITETURA, ainda não congelada.

### 2.2 Fora do escopo desta decisão

- Qualquer implementação de código, componente de frontend, schema de banco de dados ou API.
- Definição de stack tecnológica (framework, biblioteca de UI, infraestrutura, provedor de autenticação).
- Quantidade de cartões, ordem definitiva e conteúdo individual dos cartões (além do Primeiro Cartão e das missões conceituais do Segundo e do Terceiro Cartão), soluções sugeridas, recomendações automáticas, comportamento consultivo ou mecanismo de IA para aconselhamento, layout, posição dos elementos, tamanho, cores, ícones, cabeçalho, componentes visuais, cards, KPIs, gráficos e filtros da Tela 02 — a definir em sessão futura.
- Telas além da Tela 01 e da Tela 02 — tratadas em futuras seções desta mesma ADR, mediante aprovação própria.
- Qualquer alteração ao Motor NSI, ao Operations Console (ADR-001) ou à Fundação de Marca (ADR-002).
- Definição de layout visual, grid, tipografia ou paleta — regidos pelo Sistema Editorial Visual (ADR-003), quando aplicável ao Portal.

---

## 3. Contexto

A ADR-001 estabeleceu o Portal Executivo do Cliente como uma das três plataformas do ecossistema NSI (Seção 4.2): produto comercial, acesso mediante login, cada empresa restrita aos próprios dados. A ADR-001 deliberadamente não detalhou o Portal, registrando-o como dependência de uma ADR futura (Seções 13 e 15).

Esta ADR cumpre essa dependência. Segue a mesma metodologia já validada nas ADRs anteriores: arquitetura primeiro, implementação depois, congelamento somente após aprovação explícita — aplicada agora tela por tela, começando pela tela de acesso, por ser o primeiro ponto de contato do cliente com o Portal.

---

## 4. Princípios Arquiteturais do Portal

### Princípio 1 — Acesso Exclusivo por Convite

Não existe cadastro público no Portal Executivo do Cliente. Todo acesso se origina de um convite.

### Princípio 2 — Cadastro Centralizado na NSI

O cadastro de empresas e usuários é realizado exclusivamente pela equipe NSI. Nenhum usuário se autocadastra.

### Princípio 3 — Múltiplos Usuários, Uma Empresa

Uma mesma empresa pode ter múltiplos usuários cadastrados, todos vinculados à mesma empresa.

### Princípio 4 — Isolamento de Dados por Empresa

Cada usuário acessa exclusivamente os dados da própria empresa. Este princípio é absoluto e não admite exceção por papel de usuário, volume de acesso ou qualquer outro critério.

### Princípio 5 — Linguagem Simples e Institucional

Toda comunicação do Portal ao cliente usa linguagem simples, sem termos técnicos, seguindo o tom de voz já congelado na Fundação de Marca (ADR-002).

### Princípio 6 — Simplicidade, Confiança e Clareza

Esta é a filosofia que governa toda decisão de experiência do Portal, começando pelo acesso: menos é mais, o cliente nunca deve se sentir perdido ou inseguro.

---

## 5. Fluxo — Jornada de Acesso ao Portal

```
Convite enviado pela NSI
  ↓
Usuário e empresa cadastrados exclusivamente pela NSI
  ↓
Primeiro acesso do usuário
  ↓
Criação de senha
  ↓
Login (usuário e senha)
  ↓
Tela de boas-vindas (somente no primeiro login)
  ↓
Acesso ao Portal Executivo
```

Em acessos subsequentes (não o primeiro), o fluxo é: Login → Acesso direto ao Portal, sem a tela de boas-vindas.

---

## 6. Tela 01 — Acesso ao Portal Executivo

**Status: CONGELADA.**

### 6.1 Propósito da tela

Ser a porta de entrada do cliente ao Portal Executivo — a primeira impressão institucional do NSI para quem usa o produto comercial, não apenas uma tela técnica de login.

### 6.2 Decisões aprovadas

- **Acesso por convite.** Não existe formulário de cadastro público em nenhuma parte da tela.
- **Cadastro exclusivo NSI.** Login e senha do usuário são criados a partir de um cadastro realizado pela equipe NSI — nunca pelo próprio usuário do zero.
- **Login e senha** como mecanismo de autenticação.
- **Primeiro acesso mediante criação de senha.** O usuário recebe o convite e, no primeiro acesso, define sua própria senha — não recebe uma senha definitiva pronta da NSI.
- **Múltiplos usuários por empresa.** A tela de acesso não impõe limite de um único usuário por empresa cliente.
- **Isolamento por empresa.** Após autenticado, cada usuário só pode ver dados da própria empresa (Princípio 4, Seção 4) — regra que nasce já na tela de acesso, não em uma tela posterior.
- **Tela de boas-vindas após o primeiro login.** Exibida uma única vez, imediatamente após a criação de senha bem-sucedida no primeiro acesso.
- **Linguagem simples, sem termos técnicos.** Nenhum vocabulário de sistema, API, banco de dados ou jargão técnico é exposto ao cliente nesta tela.
- **Texto institucional aprovado.** O conteúdo textual da tela segue o tom de voz já congelado na Fundação de Marca (ADR-002), não um texto de produto genérico.
- **Botão principal: "Entrar no Portal".** É a única ação primária da tela.
- **Filosofia: simplicidade, confiança e clareza** (Princípio 6, Seção 4) — critério de aprovação para qualquer decisão futura de conteúdo ou fluxo desta tela.

### 6.3 O que esta tela NÃO faz

- Não oferece cadastro público ou autocadastro.
- Não permite recuperação de senha por fluxo de autoatendimento não convidado (fora do escopo desta ADR — tratado, se necessário, em revisão futura desta mesma tela).
- Não expõe dados de outra empresa em nenhuma circunstância.
- Não usa linguagem técnica, institucional-corporativa fria ou jargão de sistema.

---

## 7. Tela 02 — Home (Painel Executivo do Portal)

**Status: EM ARQUITETURA.**

> Congelamento parcial: os princípios abaixo estão aprovados. Quantidade de cartões, ordem definitiva, conteúdo individual dos cartões além do Primeiro e das missões conceituais do Segundo e do Terceiro, soluções sugeridas, recomendações automáticas, qualquer comportamento consultivo ou mecanismo de IA para aconselhamento, layout, posição dos elementos, tamanho, cores, ícones, cabeçalho, componentes visuais, cards, KPIs, gráficos e filtros **não** fazem parte desta versão — serão tratados em sessão futura.

> **Evolução conceitual:** a Home deixou de ser concebida apenas como um "Resumo Executivo" e passou a ser concebida como um **Painel Executivo do Portal** — mantendo a mesma filosofia de não ser um dashboard completo, agora com uma missão mais precisa (Seção 7.2).
>
> **Evolução arquitetural:** o Painel Executivo passa a ser estruturado como uma sequência lógica de cartões, formando uma Jornada de Descoberta (Seções 7.6, 7.13), com o primeiro cartão definido em conteúdo (Seção 7.14) e o segundo e terceiro cartões definidos em missão conceitual (Seções 7.15 e 7.16).
>
> **Princípio da Jornada do Cliente:** os cartões não seguem os módulos internos do sistema — seguem a jornada vivida pelo cliente da empresa, com um fluxo cognitivo próprio: localizar → compreender → aprofundar → comparar → decidir (Seções 7.7 e 7.8).
>
> **Princípio da Neutralidade Decisória:** o Portal nunca decide pelo gestor — organiza, prioriza e contextualiza informações governáveis pela empresa, entregando inteligência organizada, não consultoria (Seções 7.9 a 7.12).

> **Dependência temporal:** a existência de duas leituras do mesmo lote — Leitura Inicial e Leitura de Excedência — e a regra de que a segunda não altera, recalcula, mistura, substitui ou invalida a primeira são definidas pela ADR-005 (Ciclo Temporal de Coleta e Leituras Independentes). Quando esta seção tratar da exibição dessas leituras no Painel — títulos, posição, componentes visuais —, deverá referenciar a ADR-005 como fonte da regra temporal, sem redefini-la.

### 7.1 Natureza da tela

- A Home **não** é um dashboard completo.
- A Home é o **Painel Executivo** do Portal — evolução do conceito inicial de Resumo Executivo.
- O objetivo principal da Home **não** é mostrar todos os dados da operação.
- Sua missão é apresentar uma visão geral da última Operação NSI e despertar o interesse do gestor em aprofundar a análise.

### 7.2 Missão da Home

- A Home existe para responder imediatamente ao gestor: **"Vale a pena continuar explorando este relatório."**
- A Home desperta curiosidade — ela não entrega toda a análise.

### 7.3 Sentimentos transmitidos

- A Home deve transmitir dois sentimentos: **valor percebido** ("valeu a pena contratar o NSI") e **urgência controlada** (existem oportunidades importantes que merecem atenção).
- A Home **não** deve transmitir sensação de desastre.
- O Portal jamais exagera problemas. O NSI apresenta apenas aquilo que os dados realmente sustentam.

### 7.4 O que o empresário compra

- O empresário compra **clareza para decidir** — não compra gráficos, não compra indicadores, não compra textos longos.
- O Portal entrega **direção para tomada de decisão**.

### 7.5 Relação com os módulos

- O Portal Executivo será composto por módulos especializados, independentes entre si.
- A Home não substitui nenhum módulo.
- Cada bloco apresentado na Home deverá convidar naturalmente o usuário a aprofundar aquele assunto nos módulos específicos.
- O usuário possui liberdade total de navegação.
- Não existe fluxo guiado obrigatório.

### 7.6 Arquitetura em Cartões

- A Home passa a ser composta por uma sequência lógica de cartões.
- Cada cartão possui uma única responsabilidade.
- Nenhum cartão deve tentar explicar toda a operação.
- Cada cartão prepara naturalmente o usuário para o cartão seguinte.
- A sequência dos cartões deverá manter continuidade lógica entre si.

### 7.7 Princípio da Jornada do Cliente

- O Painel Executivo não organiza a análise pelos módulos internos do sistema.
- O Painel Executivo organiza a leitura seguindo a jornada vivida pelo cliente da empresa.
- Cada cartão representa uma etapa lógica dessa jornada de análise.
- A missão dos cartões não é apresentar todas as informações disponíveis.
- A missão dos cartões é localizar rapidamente onde existe a maior oportunidade de evolução da experiência do cliente.
- O Portal não trabalha orientado por problemas isolados — trabalha orientado por oportunidades reais de melhoria identificadas ao longo da jornada do cliente.
- Essa filosofia deverá servir para qualquer segmento de mercado, produto ou serviço.

### 7.8 Fluxo Cognitivo dos Cartões

- O Portal deve reduzir o volume de informações apresentado inicialmente, priorizando apenas aquilo que merece atenção imediata.
- O gestor nunca deve ser sobrecarregado com dados logo na abertura da Home.
- O Portal conduz o gestor de forma progressiva, permitindo aprofundamento apenas quando existir interesse.
- Os cartões seguem sempre uma sequência lógica: **localizar → compreender → aprofundar → comparar → decidir**.
- O primeiro objetivo do Painel Executivo nunca é explicar — é localizar onde vale a pena investigar.
- Somente depois o Portal apresenta as causas e os detalhes daquela prioridade.
- Toda decisão futura dos cartões deverá respeitar esse fluxo cognitivo.

### 7.9 Princípio da Neutralidade Decisória

- O NSI não toma decisões pelo gestor.
- O Portal Executivo não substitui a experiência do empresário.
- O Portal organiza, prioriza e contextualiza as informações obtidas na jornada do cliente.
- O Portal nunca determina qual decisão o gestor deve tomar.
- Toda evolução da jornada dos cartões deverá respeitar esse princípio.

### 7.10 Governabilidade dos Insights

- O Portal apresenta apenas informações que estejam sob o controle do gestor.
- Nenhum insight poderá depender de fatores externos fora da governabilidade da empresa — por exemplo: economia nacional, clima, concorrência, política, eventos externos.
- Toda oportunidade apresentada pelo Portal deverá representar uma possibilidade real de ação dentro da empresa.

### 7.11 Inteligência, não Consultoria

- O Portal não entrega consultoria.
- O Portal entrega inteligência organizada.
- O objetivo do Portal é reduzir a incerteza do gestor.
- O objetivo final é permitir que o gestor tome suas próprias decisões com maior segurança.
- O aprofundamento das informações existe para aumentar a confiança do gestor, nunca para substituir seu julgamento.
- O Portal não diz "Faça isto." O Portal mostra: "É aqui que existe a maior oportunidade de evolução."

### 7.12 Filosofia Oficial do Portal

> "O Portal reduz a incerteza do gestor até que ele tenha segurança para tomar sua própria decisão."

### 7.13 Jornada de Descoberta

- A navegação do Painel Executivo deverá criar uma **Jornada de Descoberta**.
- O gestor nunca deve sentir que está sendo obrigado a seguir um fluxo — porém cada cartão deve despertar interesse suficiente para que o próximo faça sentido.

### 7.14 Primeiro Cartão

- Missão única do primeiro cartão: responder **"Por onde devo começar?"**.
- O primeiro cartão não apresenta números.
- O primeiro cartão não apresenta gráficos.
- O primeiro cartão não apresenta indicadores matemáticos.
- O primeiro cartão orienta o gestor.
- O primeiro cartão fala diretamente com o gestor.
- A linguagem utilizada deverá ser operacional, simples e humana.
- O cartão utiliza linguagem investigativa, nunca acusatória.
- **Texto aprovado:** "Encontramos uma área que merece sua atenção."
- **CTA aprovado:** "Começar por aqui →"
- O CTA não é tratado como botão comercial.

### 7.15 Segundo Cartão — Missão Conceitual

- O Segundo Cartão **não** existe para sugerir soluções nem induzir ações imediatas.
- Sua missão é fornecer compreensão suficiente para que o gestor consiga conduzir a empresa internamente.
- Após compreender a prioridade apresentada no Primeiro Cartão, o gestor deve ser capaz de:
  - entender por que aquela prioridade existe;
  - identificar em qual etapa da jornada do cliente ocorreu a fricção;
  - reconhecer qual setor ou processo interno deve ser investigado;
  - iniciar uma conversa objetiva com sua equipe baseada em evidências.
- O Portal Executivo não entrega respostas prontas — organiza informações para que a empresa faça as perguntas corretas internamente.

**Consequência arquitetural:**

- Ao fechar o Portal após o Segundo Cartão, o gestor deve ser capaz de dizer naturalmente: *"Encontramos uma fricção neste setor. Agora preciso reunir os responsáveis para entender por que isso está acontecendo."*
- O Portal ainda não recomenda soluções — prepara a empresa para tomar decisões fundamentadas.

### 7.16 Terceiro Cartão — Missão Conceitual

- O Terceiro Cartão existe para reconstruir a cadeia de causalidade da fricção identificada anteriormente.
- Após compreender a prioridade e organizar a investigação, o Portal conduz o gestor a responder uma nova pergunta: *"Esta fricção é a causa do problema ou apenas consequência de outra etapa da jornada?"*
- O objetivo do Terceiro Cartão não é encontrar culpados nem recomendar soluções.
- Sua missão é organizar a sequência lógica de eventos que levou ao problema percebido pelo cliente, permitindo que o gestor compreenda a relação entre causa e consequência antes de qualquer tomada de decisão.
- O Portal impede conclusões precipitadas — mostra que o efeito observado pode ter origem em eventos anteriores da jornada do cliente.
- Ao finalizar este cartão, o gestor deve compreender:
  - o problema visível pode não representar a causa real;
  - uma fricção pode ser consequência de outra;
  - somente reconstruindo a cadeia de causalidade será possível agir sobre a origem do problema.

**Consequência arquitetural:**

- Ao fechar o Terceiro Cartão, o gestor deve ser capaz de dizer naturalmente: *"Agora entendo como esse problema foi construído. Antes de agir, preciso atacar a causa e não apenas a consequência."*

### 7.17 Princípio da Observabilidade

**Missão Conceitual**

- O NSI foi concebido para organizar evidências provenientes da experiência real dos clientes.
- Sua função é reduzir a incerteza do gestor por meio da organização de fatos observáveis, preservando absoluta neutralidade sobre interpretações humanas.
- Existe um limite arquitetural explícito para a atuação do sistema.
- O NSI atua apenas até o ponto em que os dados permitem estabelecer relações objetivas entre eventos.
- A partir do momento em que uma conclusão depende da interpretação de intenções, motivações, comportamentos individuais ou decisões humanas, a responsabilidade deixa de pertencer ao sistema e retorna integralmente ao gestor.

**Fundamentos**

O NSI pode afirmar:

- que uma fricção ocorreu;
- onde ocorreu;
- como ela se propagou pela cadeia operacional;
- quais evidências sustentam essa conclusão;
- quais padrões foram observados de forma consistente.

O NSI não pode afirmar:

- que um colaborador agiu com negligência;
- que houve má intenção;
- que determinada pessoa é responsável;
- qual decisão deve ser tomada;
- qual ação disciplinar deve ser aplicada;
- qual estratégia operacional deve ser adotada.

Esses elementos pertencem exclusivamente ao processo decisório humano.

**Princípio Fundamental**

> "O NSI organiza evidências.
>
> A interpretação pertence ao gestor."

**Princípio Arquitetural**

- O limite do NSI não é definido pela complexidade da operação. O limite é definido pela **observabilidade**.
- Sempre que uma conclusão depender de interpretação subjetiva, o Portal interrompe sua atuação e devolve a responsabilidade ao gestor.
- O sistema nunca atravessa a fronteira entre evidência e interpretação.

**Consequência Filosófica**

- O objetivo do Portal Executivo não é substituir a experiência do gestor.
- Seu objetivo é entregar uma representação organizada da realidade observável para que o gestor tome decisões com menor incerteza.
- A decisão permanece sempre humana.

**Observação**

- Esta seção estabelece um princípio arquitetural permanente do NSI e deverá orientar todos os cartões futuros do Portal Executivo.
- Ela não introduz funcionalidades, telas, recomendações ou fluxos de interface.
- Seu propósito é definir explicitamente o limite epistemológico da plataforma.

### 7.18 Quarto Cartão — Revelação da Realidade

**Pergunta Cognitiva**

> "O que essa recorrência revela sobre a realidade da minha empresa?"

**Missão Conceitual**

- Após compreender a cadeia de causalidade, o gestor precisa enxergar algo que, até então, permanecia invisível.
- O Quarto Cartão transforma padrões recorrentes da experiência dos clientes em uma realidade organizacional observável.
- O Portal não cria essa realidade. O Portal apenas torna visível aquilo que sempre existiu, mas permanecia fragmentado em experiências individuais.
- O gestor deixa de observar reclamações isoladas e passa a compreender padrões recorrentes sustentados por evidências.

**Fundamentos**

- O Quarto Cartão não recomenda ações.
- Não estabelece prioridades.
- Não determina urgências.
- Não interpreta intenções.
- Não responsabiliza pessoas.
- Sua função é revelar uma realidade organizacional sustentada pela recorrência das evidências observadas.
- A decisão continua pertencendo exclusivamente ao gestor.

**Consequência Cognitiva**

- Ao concluir este cartão, o gestor percebe que a empresa vista pelos clientes pode ser diferente da empresa imaginada internamente.
- O Portal amplia sua percepção sem substituir seu julgamento.
- A partir desse momento, a organização passa a compartilhar uma mesma compreensão da realidade observada.
- As discussões deixam de girar em torno da existência do problema e passam a concentrar-se na forma como a organização responderá a essa realidade.

**Frase Fundadora**

> "O NSI não cria a realidade.
>
> Ele torna visível uma realidade que sempre existiu."

**Encerramento Filosófico**

- Antes do NSI, a voz do cliente permanecia dispersa em centenas de experiências individuais.
- O Quarto Cartão organiza essa voz.
- O gestor finalmente consegue escutar aquilo que sempre esteve sendo dito: *"Agora você escuta."*
- Essa frase representa a essência conceitual deste cartão.

**Observações importantes**

- Esta seção descreve exclusivamente a arquitetura cognitiva do Portal Executivo.
- Não introduz interface, dashboard, gráficos, KPIs, componentes, recomendações, IA consultiva ou fluxos operacionais.

### Decisão Arquitetural — Unidade da Jornada Cognitiva

- Uma Operação NSI pode revelar múltiplas realidades recorrentes.
- Cada realidade recorrente identificada possui sua própria Jornada de Descoberta.
- A Jornada de Descoberta não pertence à Operação NSI como um todo; ela pertence a cada realidade recorrente identificada.
- O Primeiro Cartão continua respondendo "Por onde devo começar?", porém essa resposta refere-se à realidade priorizada naquele momento.
- As demais realidades recorrentes continuam disponíveis ao gestor e nunca são ocultadas pelo Portal.
- O Portal conduz o gestor pela exploração dessas realidades de forma progressiva, reduzindo a carga cognitiva sem esconder informação.
- Esta decisão é exclusivamente arquitetural e não define interface, layout, navegação, componentes visuais ou comportamento do front-end.

### Quinto Cartão — Manifestações da Realidade

**Pergunta Cognitiva**

> "Como essa realidade se manifesta na experiência dos clientes?"

**Missão**

- Após o Quarto Cartão revelar que um padrão recorrente constitui uma realidade organizacional, o Quinto Cartão revela como essa realidade se manifesta na experiência dos clientes.
- O Quinto Cartão organiza as manifestações concretas da realidade já revelada, sustentadas exclusivamente pelas evidências observadas na experiência dos clientes.
- Sua missão não é revelar uma nova realidade nem compará-la com outras. Sua missão é revelar do que essa realidade é composta.

**Princípios Arquiteturais**

- Toda realidade organizacional é composta por manifestações observáveis sustentadas por evidências dos clientes.
- O Quinto Cartão permanece dentro da mesma realidade já revelada; não introduz uma realidade adicional.
- Cada manifestação apresentada deve estar diretamente sustentada por evidências dos clientes — nenhuma manifestação é inferida ou presumida.
- A organização das manifestações deve ser completa: nenhuma manifestação sustentada por evidência pode ser omitida por conveniência narrativa.
- O Quinto Cartão não compara esta realidade com outras realidades recorrentes eventualmente identificadas na mesma Operação NSI — a comparação pertence a um momento posterior da jornada.

**Limite Arquitetural**

- O Quinto Cartão termina no ponto em que organizar as manifestações deixaria de expor evidências e passaria a hierarquizá-las por relevância subjetiva.
- Ele não atribui causa, intenção ou motivação às manifestações apresentadas — essa fronteira já pertence aos cartões anteriores e ao Princípio da Observabilidade.
- Ele não recomenda ação a partir das manifestações organizadas.
- Ele não determina qual manifestação é mais importante entre as demais.

**Consequência Cognitiva**

- Ao concluir este cartão, o gestor deve ser capaz de dizer: "Agora entendo do que essa realidade é feita."
- O gestor permanece livre para continuar a jornada de descoberta daquela realidade ou explorar outras realidades recorrentes disponíveis, sem que o Portal decida por ele.
- A decisão sobre o que fazer com essas manifestações permanece exclusivamente humana.

### Sexto Cartão — Contexto Organizacional da Realidade

**Pergunta Cognitiva**

> "Em que contexto organizacional essa realidade existe?"

**Missão**

- Revelar o contexto organizacional em que a realidade já descoberta existe, permitindo ao gestor compreender o ambiente operacional onde ela está inserida, sem inferir causalidade e sem recomendar ações.

**Princípios Arquiteturais**

- Toda realidade organizacional existe inserida em um contexto operacional maior, composto por outras realidades e relações observáveis.

**Limite Arquitetural**

- O Sexto Cartão não revela novas realidades.
- O Sexto Cartão não cria relações inexistentes.
- O Sexto Cartão não afirma causalidade.
- O Sexto Cartão não recomenda ações.
- O Sexto Cartão não prioriza problemas.
- O Sexto Cartão não inicia transformação.
- Sua única função é ampliar a compreensão do gestor sobre o contexto organizacional da realidade já identificada.

**Consequência Cognitiva**

- Ao concluir este cartão, o gestor deve ser capaz de afirmar: "Agora compreendo o contexto em que essa realidade existe."

### Decisão Arquitetural — Encerramento da Jornada de Inteligência Organizacional

- A Jornada de Inteligência Organizacional está completa e encerrada no Sexto Cartão — Contexto Organizacional da Realidade.
- Não haverá Sétimo Cartão nesta jornada.
- Após o Sexto Cartão, inicia-se uma jornada conceitualmente independente, denominada Jornada de Transformação Organizacional.
- A Jornada de Transformação Organizacional ainda não está arquitetada nesta etapa; sua arquitetura será tratada em sessão futura.
- Esta decisão é exclusivamente conceitual e arquitetural — não define cartões, telas, layout, componentes visuais, KPIs, gráficos, filtros ou funcionalidades da nova jornada.

### 7.19 Linguagem

- Toda linguagem utilizada deverá ser simples, objetiva e compreensível para qualquer empresário, independentemente de formação técnica.
- O Portal traduz a complexidade do Motor NSI; nunca a expõe ao usuário.
- Toda navegação do Portal Executivo deverá utilizar convites naturais em vez de comandos tradicionais, como: "Clique aqui", "Saiba mais", "Próximo", "Continuar".
- O Portal conversa com o gestor como um consultor experiente, nunca como um software.

### 7.20 Unidade de análise do Portal

- A unidade principal do Portal passa a ser a **Operação NSI**.
- Toda comparação histórica ocorrerá entre Operações NSI, nunca entre relatórios isolados.
- O relatório é apenas uma representação visual de uma Operação NSI.

### 7.21 Módulos previstos (inicial)

- Resumo Executivo
- Indicadores
- Comentários dos Clientes
- Evolução
- Comparações
- Operações
- Todas as Respostas
- Configurações

### 7.22 Governança das decisões futuras

- Toda decisão visual futura da Home deverá respeitar os princípios registrados nesta seção (7.1 a 7.21).

### 7.23 O que ainda NÃO está definido

Fora de escopo nesta etapa — a definir em sessão futura:

- Quantidade de cartões da futura Jornada de Transformação Organizacional
- Ordem e sequência cognitiva dos cartões da futura Jornada de Transformação Organizacional
- Conteúdo individual dos cartões, além do Primeiro Cartão (7.14, texto e CTA aprovados) e das missões conceituais do Segundo (7.15), do Terceiro (7.16), do Quarto (7.18), do Quinto e do Sexto Cartão
- Soluções sugeridas ao gestor
- Recomendações automáticas
- Qualquer comportamento consultivo
- Qualquer mecanismo baseado em IA para aconselhamento
- Layout da Home
- Posição dos elementos, incluindo a posição do primeiro cartão
- Tamanho dos cartões
- Cores
- Ícones
- Cabeçalho
- Componentes visuais
- Cards
- KPIs
- Gráficos
- Filtros
- Arquitetura visual

### 7.24 Exibição da Segunda Leitura (Leitura de Excedência) Durante a Coleta

> Esta seção registra apenas o comportamento de exibição e bloqueio da Segunda Leitura enquanto ela está em coleta, sendo processada, já disponível, ou encerrada sem relatório. As regras de quando um convite de coleta é considerado respondido, quando a Leitura de Excedência encerra (antecipada ou obrigatoriamente) e quando ela é congelada e processada pelo Motor NSI pertencem exclusivamente à ADR-005 (Ciclo Temporal de Coleta e Leituras Independentes) — esta seção não as redefine, apenas reage a elas.

- Enquanto a Leitura de Excedência estiver em coleta, ela aparece no Painel, mas seu conteúdo permanece bloqueado ao gestor: apenas uma barra de andamento e o status "Coleta em andamento" são exibidos — sem respostas, recorrências semânticas, conclusões parciais ou qualquer conteúdo semântico prévio do Motor NSI.
- Estados visíveis ao gestor, refletindo os eventos definidos na ADR-005:
  - **Coleta em andamento**
  - **Coleta concluída — preparando leitura**
  - **Processamento pelo Motor NSI**
  - **Leitura disponível**
  - **Sem respostas de excedência**
  - **Nenhuma resposta recebida no período de excedência**
- Os dois últimos estados não são etapas posteriores de "Coleta em andamento" — cada um substitui toda a sequência normal, em circunstâncias distintas:
  - **"Sem respostas de excedência"** (ADR-005, Princípio 17): todos os convites de coleta foram respondidos na Primeira Leitura, com timestamps estritamente menores que T0 + 120h, e nenhuma resposta foi classificada na Leitura de Excedência na fronteira temporal. A Segunda Leitura nunca chega a exibir "Coleta em andamento"; vai diretamente a este estado. O Painel informa: "Todos os convites foram respondidos na Primeira Leitura." Uma resposta classificada exatamente na fronteira T0 + 120h nunca produz este estado — produz encerramento antecipado com processamento normal, seguido do estado "Leitura disponível".
  - **"Nenhuma resposta recebida no período de excedência"** (ADR-005, Princípio 19): havia população pendente ao iniciar a Leitura de Excedência, mas nenhuma resposta chegou até o encerramento obrigatório em T0 + 336h. Neste caso, a Segunda Leitura exibe "Coleta em andamento" normalmente durante o período, chegando a este estado apenas no encerramento.
  - Nenhum dos dois estados representa erro, insuficiência ou falha do sistema.
- A Primeira Leitura permanece disponível e inalterada durante todo esse processo — sua exibição nunca é interrompida, ocultada ou modificada pelo estado da Segunda Leitura.
- A Segunda Leitura, mesmo depois de disponível, nunca altera, mistura, recalcula ou substitui a Primeira Leitura na exibição do Painel — consequência direta do Princípio 4 da ADR-005 (Independência Entre Leituras), aplicada aqui à camada de apresentação.
- Esta seção não define:
  - layout, cor, dimensão ou estética da barra de andamento nem dos demais elementos visuais;
  - se a barra representa tempo decorrido, quantidade de respostas recebidas ou percentual de convites de coleta respondidos.
  Ambos permanecem em arquitetura para decisão futura, sob a governança do Sistema Editorial Visual (ADR-003) quando aplicável.

### 7.25 Títulos Aprovados e Congelados do Painel e das Duas Leituras

**Status: CONGELADO.**

- Título do Painel: **"Painel de Inteligência Organizacional"**.
- Primeira frente — título: **"Primeira Leitura da Realidade Organizacional"**; subtítulo: **"Respostas recebidas do 1º ao 5º dia"**.
- Segunda frente — título: **"Segunda Leitura da Realidade Organizacional"**; subtítulo: **"Respostas recebidas do 6º ao 14º dia"**.

**Regras arquiteturais:**

- "Primeira" e "Segunda" indicam exclusivamente ordem temporal — os títulos não estabelecem gravidade, prioridade, importância, qualidade ou superioridade entre as leituras.
- As duas leituras permanecem distintas e independentes (ADR-005, Princípio 4).
- No domínio técnico da ADR-005, os nomes permanecem **Leitura Inicial** e **Leitura de Excedência** — esta decisão não os altera, redefine ou substitui.
- No front-end do Portal, devem ser usados exclusivamente os títulos aprovados nesta seção — nunca os nomes técnicos da ADR-005.
- Os estados definidos na Seção 7.24 — incluindo "Sem respostas de excedência" e "Nenhuma resposta recebida no período de excedência" — pertencem à **Segunda Leitura da Realidade Organizacional**.
- Enquanto a Segunda Leitura estiver em coleta, as duas frentes permanecem visíveis simultaneamente:
  - **Primeira Leitura da Realidade Organizacional** — Disponível;
  - **Segunda Leitura da Realidade Organizacional** — Coleta em andamento.
- Quando processada, a Segunda Leitura passa para o estado "Leitura disponível" (Seção 7.24).
- Esta seção não define nem altera layout, cores, dimensões, componentes, o significado da barra de andamento ou qualquer arquitetura visual — permanece regida pelas mesmas exclusões da Seção 7.24 e pelo Sistema Editorial Visual (ADR-003) quando aplicável.

### 7.26 Identidade Técnica da Realidade Recorrente

**Status: CONGELADO.**

- `realidade_id`: identificador técnico próprio, opaco e permanente, atribuído a cada realidade recorrente.
- `codigo_catalogo` (Catálogo NSI) permanece exclusivamente como atributo histórico e versionável associado à realidade — nunca compõe sua identidade e nunca garante, sozinho, unicidade.
- O Motor NSI produz um **resultado semântico candidato** a partir do processamento de uma Leitura (ADR-005) — esse resultado, por si só, ainda não é considerado uma realidade organizacional, em conformidade com o **Quarto Cartão** ("Revelação da Realidade") e a "Decisão Arquitetural — Unidade da Jornada Cognitiva" desta ADR.
- O `realidade_id` nasce **exclusivamente** no momento em que o Quarto Cartão efetivamente revela aquele padrão como realidade organizacional — nunca antes.
- O **Sexto Cartão não participa do nascimento da realidade**: ele apenas conclui a Jornada de Inteligência Organizacional de uma realidade já revelada anteriormente pelo Quarto Cartão, sendo o evento que habilita (ADR-006, Seção 9) o acesso à Tela 03 para aquela mesma realidade — já existente desde o Quarto Cartão.
- Cada `realidade_id`, ao nascer, referencia exatamente um resultado candidato de origem — esse vínculo de origem é único, explícito e imutável.

**Regras arquiteturais:**

- A cardinalidade inversa — quantas realidades um mesmo resultado candidato pode originar — não está congelada por esta seção e permanece pendente de decisão futura.
- O formato concreto da referência técnica ao resultado candidato (antes da revelação) permanece pendente — não se assume chave composta, identificador próprio do resultado, índice ou caminho de arquivo.
- Não existe comparação ou equivalência automática entre realidades, nem dentro da mesma leitura, nem entre leituras diferentes (ADR-005, Princípio 6; ADR-006, Princípio 8).
- Esta seção não define schema de banco de dados, tabelas, colunas, endpoints ou código — apenas identidade conceitual.

---

## 8. Decisões Congeladas

As seguintes decisões são consideradas aprovadas e estáveis a partir desta ADR:

1. O Portal Executivo do Cliente não possui cadastro público; todo acesso nasce de convite.
2. O cadastro de empresas e usuários é responsabilidade exclusiva da equipe NSI.
3. A autenticação do Portal é feita por login e senha.
4. O primeiro acesso do usuário exige a criação de senha própria.
5. Uma empresa pode ter múltiplos usuários cadastrados.
6. Cada usuário acessa exclusivamente os dados da própria empresa — sem exceção.
7. Existe uma tela de boas-vindas, exibida apenas no primeiro login.
8. Toda a linguagem do Portal ao cliente é simples, sem termos técnicos, seguindo o tom de voz da ADR-002.
9. O botão principal da Tela 01 é "Entrar no Portal".
10. A filosofia de simplicidade, confiança e clareza governa toda decisão de experiência do Portal.
11. **Tela 01 — Acesso ao Portal Executivo** está CONGELADA — é a primeira tela oficialmente congelada do Portal Executivo do Cliente.

---

## 9. Dependências

- Depende da ADR-001 (Seção 4.2), que define o Portal Executivo do Cliente como uma das três plataformas do ecossistema NSI.
- Depende da ADR-002 (Fundação de Marca), para tom de voz e texto institucional.
- Depende da ADR-003 (Sistema Editorial Visual), quando a arquitetura visual concreta do Portal for definida — fora do escopo desta ADR.
- Depende da ADR-005 (Ciclo Temporal de Coleta e Leituras Independentes), para a regra temporal que origina a Leitura Inicial e a Leitura de Excedência exibidas na Seção 7 — esta ADR não redefine essa regra, apenas a referencia.
- A Tela 02 (Seção 7) já teve seus princípios registrados nesta ADR, com status EM ARQUITETURA; sua arquitetura visual e demais telas subsequentes do Portal dependem desta ADR como registro fundacional e serão adicionadas a ela mediante aprovação própria, uma a uma.

---

## 10. Itens Fora do Escopo

- Qualquer implementação de código, frontend, componente visual ou API.
- Definição de stack tecnológica de autenticação (provedor de identidade, biblioteca, protocolo).
- Fluxo de recuperação de senha e demais fluxos de autoatendimento não convidado.
- Schema de dados de usuário, empresa ou sessão.
- Quantidade de cartões, ordem definitiva e conteúdo individual dos cartões (além do Primeiro Cartão e das missões conceituais do Segundo e do Terceiro Cartão), soluções sugeridas, recomendações automáticas, comportamento consultivo ou mecanismo de IA para aconselhamento, layout, posição dos elementos, tamanho, cores, ícones, cabeçalho, componentes visuais, cards, KPIs, gráficos e filtros da Tela 02 — a definir em sessão futura.
- Qualquer tela do Portal além da Tela 01 (congelada) e da Tela 02 (princípios aprovados).
- Qualquer alteração à ADR-001, à ADR-002 ou à ADR-003.

---

## 11. Referências

- `docs/architecture/ADR-001-operations-console.md` — define o Portal Executivo do Cliente como plataforma (Seção 4.2) e registra a dependência desta ADR (Seções 2.2, 13, 15).
- `docs/architecture/ADR-002-brand-foundation.md` — tom de voz e princípios editoriais aplicados ao texto institucional do Portal.
- `docs/architecture/ADR-003-sistema-editorial-visual.md` — arquitetura visual, aplicável ao Portal quando sua camada visual concreta for definida.
- `docs/architecture/ADR-005-ciclo-temporal-coleta-leituras-independentes.md` — regra temporal do ciclo de coleta (Leitura Inicial e Leitura de Excedência) exibida na Seção 7.

---

## 12. Evolução Aprovada — Identidade Técnica do Usuário (2026-08-25)

Esta seção documenta uma evolução aprovada da ADR-004, registrada como pré-requisito do schema conceitual da Trajetória Contínua (ADR-006), sem alterar nenhum texto já congelado anteriormente — incluindo a Tela 01 (Seção 6, CONGELADA) e a Seção 7 (Tela 02).

**O que foi adicionado:**
- `usuario_id`: identificador técnico próprio, opaco e estável, atribuído a cada usuário.
- Gerado no momento do cadastro centralizado pela equipe NSI (Seção 4, Princípio 2 — Cadastro Centralizado na NSI).
- Independente de nome, e-mail, telefone ou senha — nenhum desses dados compõe ou substitui a identidade do usuário.
- Cada usuário pertence a exatamente uma empresa — tecnicamente, a exatamente um `empresa_id` (ADR-001, Seção 16) — nunca a mais de uma (Seção 4, Princípio 3 — Múltiplos Usuários, Uma Empresa).

**O que não mudou:**
- Nenhuma alteração à Tela 01 (Seção 6) ou aos seus princípios já congelados — login e senha continuam o mecanismo de autenticação; o cadastro continua exclusivo da NSI.
- Nenhuma implementação de código, autenticação, schema de banco de dados ou sessão é definida aqui — apenas identidade conceitual. Continua fora do escopo desta ADR: "Schema de dados de usuário, empresa ou sessão" (Seção 10, Itens Fora do Escopo).
- A geração concreta e a garantia de unicidade do `usuario_id` — e do `empresa_id` ao qual ele pertence (ADR-001, Seção 16) — permanecem pendentes.

**Origem desta decisão:**
- Registrada durante a arquitetura do schema conceitual da Trajetória Contínua (ADR-006), que exige autoria técnica obrigatória em cada registro (ADR-006, Seção 10).

---

## 13. Evolução Aprovada — Identidade Técnica do Resultado Candidato e Formato dos Identificadores (2026-08-26)

Esta seção documenta uma evolução aprovada da ADR-004, complementando a Seção 7.26 (Identidade Técnica da Realidade Recorrente, CONGELADA) e a Seção 12 (Evolução Aprovada — Identidade Técnica do Usuário), sem alterar nenhum texto já congelado anteriormente.

**O que foi adicionado:**
- `resultado_id`: identificador técnico próprio, opaco, estável e imutável, atribuído a cada resultado semântico candidato produzido pelo Motor NSI — a mesma entidade já referida na Seção 7.26 como "resultado candidato", agora com identidade nomeada. `resultado_id` usa UUID4 completo, canônico, opaco, estável e imutável como formato técnico.
- `resultado_id` nasce no momento em que o candidato é produzido pelo processamento de uma Leitura (ADR-005) — antes e independentemente de qualquer revelação pelo Quarto Cartão.
- `codigo_catalogo` e `versao_catalogo` (Catálogo NSI) são atributos históricos e versionáveis do resultado candidato. Nenhum dos dois, isoladamente ou em conjunto, compõe identidade ou garante unicidade do resultado candidato ou da realidade. Se e como `versao_catalogo` se reproduz (ou não) na realidade eventualmente originada por aquele candidato é uma decisão ainda não tomada — não se assume herança, cópia ou qualquer outro mecanismo de propagação.
- Cardinalidade entre `resultado_id` e `realidade_id`: cada `resultado_id` origina zero ou um `realidade_id`; cada `realidade_id` referencia exatamente um `resultado_id`.
- O Quarto Cartão, ao revelar uma realidade, não divide, funde ou compara resultados candidatos entre si — cada revelação opera exclusivamente sobre um único `resultado_id` de origem, preservando o vínculo único, explícito e imutável já congelado na Seção 7.26.
- `realidade_id` usa UUID4 completo, canônico, opaco, estável e imutável como formato técnico.
- `usuario_id` (Seção 12) usa UUID4 completo, canônico, opaco, estável e imutável como formato técnico.

**Escopo desta evolução em relação à Seção 7.26:**
- Esta seção resolve, especificamente, as duas únicas pendências que a própria Seção 7.26 declarava abertas: (i) "o formato concreto da referência técnica ao resultado candidato (antes da revelação)", agora nomeado `resultado_id`; e (ii) "a cardinalidade inversa... quantas realidades um mesmo resultado candidato pode originar", agora fixada em 0..1. Nenhuma outra frase da Seção 7.26 é alterada, reinterpretada ou substituída por esta seção.

**O que não mudou:**
- Nenhuma alteração à Tela 01 (Seção 6, CONGELADA), à Seção 7 (Tela 02) ou a qualquer outra frase da Seção 7.26 além das duas pendências explicitadas acima.
- O formato UUID4 define representação e geração probabilisticamente única — não define, por si só, a garantia de unicidade persistida (constraints, schema concreto de banco de dados), que permanece pendente.
- O armazenamento técnico e a preservação histórica dos resultados candidatos do Motor NSI e de eventuais reprocessamentos permanecem inteiramente pendentes. Nenhuma decisão desta seção implica que `resultado_id` ou a saída do Motor passem a ser persistidos em PostgreSQL — o PostgreSQL aprovado para a Trajetória Contínua (ADR-006) não substitui nem se estende a `saida_motor.json`.
- Nenhuma implementação de código, schema de banco de dados ou API é definida aqui — apenas identidade conceitual.

**Origem desta decisão:**
- Registrada durante a consolidação da identidade técnica e da política de idempotência da Trajetória Contínua (ADR-006).

---

## 14. Evolução Aprovada — Perfis de Acesso, Cadastro Delegado, Convites e Administração da Empresa (2026-08-26)

Esta seção documenta uma evolução aprovada da ADR-004, a partir da consolidação de governança, acesso, auditoria e encerramento do Portal NSI. Ela evolui explicitamente o Princípio 2 (Seção 4) e a Decisão Congelada 2 (Seção 8) — preservando seu texto original como registro histórico — e não altera nenhuma outra decisão já congelada, incluindo a Tela 01 (Seção 6, CONGELADA).

### Evolução do cadastro centralizado na NSI

- **Texto original preservado como registro histórico, mas parcialmente superado por esta evolução quanto ao agente responsável pelos cadastros posteriores:** Princípio 2 — "O cadastro de empresas e usuários é realizado exclusivamente pela equipe NSI. Nenhum usuário se autocadastra." Decisão Congelada 2 — "O cadastro de empresas e usuários é responsabilidade exclusiva da equipe NSI."
- A NSI continua responsável pelo cadastro da empresa e do primeiro Administrador.
- Os cadastros posteriores passam a ser responsabilidade dos Administradores da própria empresa.
- A antiga exclusividade da NSI deixa de reger os cadastros posteriores — permanece válida apenas para o cadastro inicial (empresa e primeiro Administrador).
- O autocadastro público continua proibido em qualquer hipótese (Princípio 1, Seção 4) — o usuário-alvo de um convite nunca se cadastra "do zero" por conta própria (Tela 01, §6.2), independentemente de quem inicia o convite.

### Perfis de Acesso

**Usuário Comum**
- Possui login individual.
- Visualiza apenas o conteúdo básico liberado no Portal.
- Não abre Cartões, conjuntos, detalhes ou pop-ups.
- Não registra declarações ou decisões.
- Não gera PDF.
- Não administra usuários.
- Não consulta a auditoria completa — apenas o próprio histórico (Seção 15).

**Gestor**
- Possui todas as permissões de visualização.
- Abre Cartões, conjuntos, detalhes e pop-ups.
- Acessa a Jornada de Transformação Organizacional (ADR-006).
- Gera PDFs.
- Registra decisões e declarações.
- Pode declarar em nome da organização (ADR-006, Seção 19).
- Não administra usuários.
- Não consulta a auditoria completa — apenas o próprio histórico (Seção 15).

**Administrador da Empresa**
- Possui todas as permissões do Gestor.
- Cria, convida, remove, promove e rebaixa usuários.
- Define Gestores e outros Administradores.
- Consulta e exporta a auditoria completa da empresa (Seção 15).
- Não pode editar ou apagar registros históricos.
- A empresa pode ter no máximo três Administradores.
- A empresa deve manter pelo menos um Administrador.
- A quantidade recomendada, mas não obrigatória, é de dois Administradores.

### Cadastro e Convites

- A NSI cadastra a empresa e o primeiro Administrador.
- A partir daí, os Administradores criam usuários e enviam convites diretamente pelo Portal.
- Não existe autocadastro público (Princípio 1, Seção 4, integralmente preservado).
- O Administrador define no convite o perfil: Usuário Comum, Gestor ou Administrador.
- O convidado não escolhe nem altera o próprio perfil.
- O convite possui validade de sete dias corridos.
- Se expirar, um Administrador poderá emitir outro.
- Criação, convite, expiração, reemissão, aceitação e perfil atribuído ficam auditados (Seção 15).

### Administração e Responsabilidade da Empresa

- A empresa é responsável pelas pessoas que autoriza e pelas permissões que concede.
- A NSI não verifica propriedade, hierarquia ou legitimidade interna das escolhas empresariais.
- A NSI não arbitra conflitos internos.
- Qualquer Administrador ativo pode remover outro Administrador sozinho.
- Uma regra de aprovação por dois Administradores foi cogitada e expressamente descartada — não é adotada nesta ou em nenhuma outra seção.
- O último Administrador não pode sair definitivamente sem substituição.

#### Transição do último Administrador

- Ao solicitar saída, o último Administrador assume o status "Administrador em transição".
- Continua ativo por até sete dias corridos enquanto indica e ativa o substituto.
- Imediatamente após a solicitação, aparece na tela inicial um aviso discreto com contagem regressiva, visível para todos os usuários, em um canto da tela, sem prejudicar a visualização.
- Durante os sete dias, o Portal funciona normalmente.
- Se não houver substituição ao final do prazo, todos poderão fazer login, mas ficarão restritos à tela inicial — o restante do Portal permanecerá bloqueado.
- O Administrador em transição poderá apenas concluir a indicação e ativação do substituto.
- A ativação do substituto desbloqueia o Portal.
- A NSI nunca escolhe quem será o novo Administrador.

### Remoção, Rebaixamento e Retorno de Usuário

- Remoção ou redução de permissão produz efeito imediato.
- Todas as sessões abertas do usuário são encerradas (Seção 15).
- O usuário recebe aviso automático por e-mail, sem exposição de justificativas internas.
- Autor da alteração, data, hora, perfil anterior e perfil posterior ficam auditados (Seção 15).
- O histórico da pessoa permanece associado ao mesmo `usuario_id` (Seção 12) — consistente com sua natureza opaca e estável.
- Se a mesma pessoa retornar futuramente, o mesmo `usuario_id` será reativado.
- Remoção, período sem acesso e reativação permanecem visíveis.
- Nenhum histórico é transferido para outra pessoa.

### O que não mudou

- O Princípio 1 (Acesso Exclusivo por Convite, Seção 4) permanece integralmente válido — não existe cadastro público em nenhuma hipótese.
- A Tela 01 (Seção 6, CONGELADA) não é alterada: login e senha continuam o mecanismo de autenticação; o usuário-alvo de um convite continua sem se autocadastrar "do zero".
- O `usuario_id` (Seção 12) continua opaco, estável e independente de nome, e-mail, telefone ou senha; a reativação reutiliza o mesmo identificador, nunca cria um novo.
- "Schema de dados de usuário, empresa ou sessão" (Seção 10, Itens Fora do Escopo) continua fora do escopo — esta seção define perfis e fluxos arquiteturais, não schema técnico concreto.
- Nenhuma implementação de código, frontend, componente visual, schema de banco de dados ou API é definida aqui.

**Origem desta decisão:**
- Consolidação aprovada de governança, acesso, auditoria e encerramento do Portal NSI (2026-08-26).

---

## 15. Evolução Aprovada — Autenticação, Sessões, Recuperação de Acesso e Auditoria do Portal (2026-08-26)

Esta seção documenta uma evolução aprovada da ADR-004, complementando a Seção 14 (perfis e administração) a partir da mesma consolidação. Ela adiciona um fator de autenticação e um fluxo de recuperação mediado — sem revogar a Decisão Congelada 3 nem a Seção 6.3 — e define a arquitetura de auditoria do Portal.

### Autenticação e Sessões

- MFA é obrigatório para Gestores e Administradores.
- MFA não é obrigatório para Usuários Comuns nesta etapa.
- A Decisão Congelada 3 ("A autenticação do Portal é feita por login e senha", Seção 8) permanece o mecanismo-base para todos os perfis; o MFA é um fator adicional exigido apenas de Gestores e Administradores — não uma substituição do login e senha.
- A sessão expira após 30 minutos sem atividade.
- Cada usuário pode manter até três sessões simultâneas.
- Todas as sessões são identificadas e auditadas.
- Acesso por novo dispositivo gera aviso automático.
- A remoção ou redução de permissão de um usuário (Seção 14) encerra imediatamente todas as suas sessões.

### Recuperação de Acesso

- O usuário solicita recuperação a um Administrador.
- O Administrador autoriza o envio de um link individual, temporário e de uso único.
- O usuário cria a própria senha; o Administrador nunca vê a senha.
- Qualquer provedor de e-mail é aceito, desde que o endereço esteja previamente cadastrado e confirmado.
- Este fluxo é mediado por um Administrador — não é o "fluxo de autoatendimento não convidado" que a Tela 01 (§6.3, CONGELADA) excluiu de seu escopo original. Esta seção cumpre o ponteiro que a própria Tela 01 deixou aberto ("tratado, se necessário, em revisão futura desta mesma tela"), sem contrariar a regra congelada.

#### Alteração de e-mail

- O usuário solicita a mudança.
- Confirma o endereço antigo e o novo.
- Um Administrador autoriza a alteração.
- O endereço anterior recebe notificação.
- Todo o processo fica auditado.

#### Único Administrador

- Se o único Administrador alterar o próprio e-mail, serão exigidos: acesso ao e-mail antigo; confirmação do e-mail novo; senha atual; MFA.
- Se o único Administrador ainda possui acesso ao e-mail previamente cadastrado, mas perdeu o MFA, a NSI poderá executar recuperação técnica excepcional mediante confirmação por esse e-mail.
- Se o único Administrador perdeu o acesso ao e-mail previamente cadastrado, a NSI não realizará recuperação por documentos, por outro endereço ou por decisão própria — a empresa deverá primeiro recuperar o acesso ao e-mail cadastrado por seus próprios meios.
- A NSI apenas recupera tecnicamente o acesso quando o e-mail cadastrado permanece acessível — nunca decide quem representa a empresa e não assume função de governança interna (consistente com "A NSI não arbitra conflitos internos", Seção 14).

### Auditoria Integral do Portal

A auditoria registrará: login e logout; usuário, empresa, data e hora; páginas acessadas; abertura e fechamento de Cartões, conjuntos e pop-ups; entrada, saída e tempo de permanência; geração e exportação de PDFs; declarações e decisões; contexto pessoal ou institucional da declaração; solicitações, aprovações e recusas; criação de usuários e convites; aceitação e expiração de convites; mudanças de perfil e permissão; remoções e reativações; tentativas bloqueadas de alteração ou exclusão; consultas e exportações de auditoria; endereço IP; navegador; dispositivo; identificador da sessão.

As regras de substância dos eventos ligados a declarações, correções e tentativas bloqueadas de alteração ou exclusão de registros da Trajetória Contínua pertencem à ADR-006 (Seções 19 e 21) — esta seção apenas os inclui no catálogo de eventos auditados do Portal, sem redefini-los.

#### Limite interpretativo

- Tempo de permanência não prova leitura, atenção, trabalho, produtividade, eficiência, intenção, mérito ou culpa.
- O NSI não produz pontuação nem conclusão sobre esses dados.
- O sistema torna os eventos observáveis; a interpretação pertence exclusivamente às pessoas autorizadas da empresa — reafirmando, para os dados de auditoria, o Princípio da Observabilidade já congelado (Seção 7.17).

#### Acesso à auditoria

- Cada Usuário Comum pode consultar somente o próprio histórico.
- Cada Gestor pode consultar somente o próprio histórico.
- Administradores podem consultar a auditoria completa da empresa.
- Administradores podem exportar toda a auditoria a qualquer momento, em PDF e CSV.
- A própria consulta ou exportação fica auditada.

#### Integridade

- A auditoria é append-only e verificável.
- Nenhum Usuário Comum, Gestor, Administrador ou operador comum da NSI pode editar ou apagar eventos.
- Eventual correção gera novo evento vinculado ao anterior.
- Senhas, códigos MFA, tokens, segredos e links de recuperação nunca entram na auditoria. Registra-se somente que a autenticação, recuperação ou alteração ocorreu e qual foi seu resultado.

### O que não mudou

- A Decisão Congelada 3 (Seção 8) permanece o mecanismo-base de autenticação para todos os perfis; o MFA descrito aqui é adicional, restrito a Gestores e Administradores.
- A Tela 01 (§6.3, CONGELADA) continua vedando recuperação por autoatendimento não convidado; o fluxo aqui definido é mediado por Administrador, portanto distinto.
- "Schema de dados de usuário, empresa ou sessão" (Seção 10, Itens Fora do Escopo) continua fora do escopo — esta seção define arquitetura e política, não schema técnico concreto.
- Nenhuma implementação de código, frontend, componente visual, schema de banco de dados ou API é definida aqui.

**Origem desta decisão:**
- Consolidação aprovada de governança, acesso, auditoria e encerramento do Portal NSI (2026-08-26).
