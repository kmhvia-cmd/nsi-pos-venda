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

- Quantidade de cartões
- Ordem definitiva dos cartões
- Conteúdo individual dos cartões, além do Primeiro Cartão (7.14, texto e CTA aprovados) e das missões conceituais do Segundo (7.15), do Terceiro (7.16) e do Quarto Cartão (7.18)
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
