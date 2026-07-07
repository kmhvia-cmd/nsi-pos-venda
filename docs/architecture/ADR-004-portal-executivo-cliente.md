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
- **Tela 02 — Home (Resumo Executivo)** (Seção 7): princípios arquiteturais aprovados nesta versão — status EM ARQUITETURA, ainda não congelada.

### 2.2 Fora do escopo desta decisão

- Qualquer implementação de código, componente de frontend, schema de banco de dados ou API.
- Definição de stack tecnológica (framework, biblioteca de UI, infraestrutura, provedor de autenticação).
- Layout, cabeçalho, cards, KPIs, gráficos, filtros e arquitetura visual da Tela 02 — a definir em sessão futura.
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

## 7. Tela 02 — Home (Resumo Executivo)

**Status: EM ARQUITETURA.**

> Congelamento parcial: os princípios abaixo estão aprovados. Layout, cabeçalho, cards, KPIs, gráficos, filtros e arquitetura visual **não** fazem parte desta versão — serão tratados em sessão futura.

### 7.1 Natureza da tela

- A Home **não** é um dashboard completo.
- A Home é o **Resumo Executivo** do Portal Executivo.
- Sua missão é apresentar uma visão geral da última Operação NSI e despertar o interesse do gestor em aprofundar a análise.

### 7.2 Relação com os módulos

- O Portal Executivo será composto por módulos especializados, independentes entre si.
- A Home não substitui nenhum módulo.
- O usuário possui liberdade total de navegação.
- Não existe fluxo guiado obrigatório.
- A Home deve despertar curiosidade para que o usuário explore os módulos especializados.

### 7.3 Linguagem

- Toda linguagem utilizada deverá ser simples, objetiva e compreensível para qualquer empresário, independentemente de formação técnica.
- O Portal traduz a complexidade do Motor NSI; nunca a expõe ao usuário.

### 7.4 Unidade de análise do Portal

- A unidade principal do Portal passa a ser a **Operação NSI**.
- Toda comparação histórica ocorrerá entre Operações NSI, nunca entre relatórios isolados.
- O relatório é apenas uma representação visual de uma Operação NSI.

### 7.5 Módulos previstos (inicial)

- Resumo Executivo
- Indicadores
- Comentários dos Clientes
- Evolução
- Comparações
- Operações
- Todas as Respostas
- Configurações

### 7.6 O que ainda NÃO está definido

Fora de escopo nesta etapa — a definir em sessão futura:

- Layout da Home
- Cabeçalho
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
- Layout, cabeçalho, cards, KPIs, gráficos, filtros e arquitetura visual da Tela 02 — a definir em sessão futura.
- Qualquer tela do Portal além da Tela 01 (congelada) e da Tela 02 (princípios aprovados).
- Qualquer alteração à ADR-001, à ADR-002 ou à ADR-003.

---

## 11. Referências

- `docs/architecture/ADR-001-operations-console.md` — define o Portal Executivo do Cliente como plataforma (Seção 4.2) e registra a dependência desta ADR (Seções 2.2, 13, 15).
- `docs/architecture/ADR-002-brand-foundation.md` — tom de voz e princípios editoriais aplicados ao texto institucional do Portal.
- `docs/architecture/ADR-003-sistema-editorial-visual.md` — arquitetura visual, aplicável ao Portal quando sua camada visual concreta for definida.
