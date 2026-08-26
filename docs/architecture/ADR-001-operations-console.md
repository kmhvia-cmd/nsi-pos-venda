# ADR-001 — NSI Operations Console

## Metadados

| Campo | Valor |
|---|---|
| Status | Aprovado |
| Data | 2026-07-02 |
| Versão de referência do sistema | `v1.1.0-fonte-unica-webhook-motor` |
| Commit de referência | `0ee7c48` |
| Branch | `master` |
| Escopo desta ADR | Arquitetura — nenhuma implementação de código |

---

## 1. Objetivo

Registrar a decisão arquitetural que introduz o **NSI Operations Console** como uma das três plataformas que compõem o ecossistema NSI, definindo seu propósito, seus limites e os princípios que governam seu funcionamento.

O Operations Console existe para responder a uma única pergunta operacional:

> "O Motor está funcionando corretamente?"

Ele não é um produto comercial, não é o Motor, e não substitui o Portal Executivo do Cliente. Esta ADR delimita essas fronteiras antes de qualquer trabalho de implementação futuro.

---

## 2. Escopo

### 2.1 Escopo desta decisão

- Definição conceitual das três plataformas do ecossistema NSI.
- Definição do propósito e das responsabilidades do Operations Console.
- Definição dos princípios de auditoria, rastreabilidade e governança que o Console deve seguir.
- Definição da unidade de negócio principal da plataforma (**Operação**, substituindo o **Lote** como conceito central de exposição).
- Definição da jornada completa de uma Operação, do contrato ao arquivamento.

### 2.2 Fora do escopo desta decisão

- Qualquer implementação de código, API, componente de frontend ou schema de banco de dados.
- Definição de stack tecnológica do Console (framework, biblioteca de UI, infraestrutura).
- Alterações ao Motor NSI, aos Processors, aos Models, aos Outputs ou às Confidence Rules.
- Especificação de contratos de API entre Console e Motor.
- Definição do Portal Executivo do Cliente em detalhe (tratado em ADR futura).

---

## 3. Contexto

O sistema NSI, na versão `v1.1.0-fonte-unica-webhook-motor`, consolidou o Motor, o Webhook e a Integration Layer como núcleo técnico estável, com `lote.json` como fonte única de verdade e suíte de 121/121 testes aprovados.

Com o núcleo técnico congelado, inicia-se a Sprint de Arquitetura do Dashboard. Antes de qualquer implementação, é necessário formalizar a decisão de que a camada de operação (uso interno) e a camada de produto (uso do cliente) são plataformas distintas, com propósitos, audiências e dados diferentes — e que ambas permanecem estritamente desacopladas do Motor.

---

## 4. Conceito — As três plataformas do NSI

### 4.1 NSI Operations Console

- Uso interno da equipe operacional do NSI.
- Finalidade: operação da plataforma, monitoramento, auditoria e rastreabilidade.
- Não é vendido. Não possui finalidade comercial.

### 4.2 Portal Executivo do Cliente

- Produto comercial do NSI.
- Acesso mediante login; cada empresa acessa exclusivamente seus próprios dados.
- Exibe gráficos, KPIs, histórico, relatórios e insights.

### 4.3 Motor NSI

- Permanece invisível a ambas as plataformas acima.
- Não sofre alteração alguma em decorrência desta ADR.

---

## 5. Responsabilidades

### 5.1 O que o Operations Console FAZ

- Monitora a execução da operação de ponta a ponta.
- Audita cada evento gerado pela plataforma.
- Acompanha o estado de cada Operação através de sua Timeline.
- Consulta o estado do Motor e da Integration Layer sem interferir em sua execução.
- Registra o aceite eletrônico da empresa antes de qualquer processamento de dados.

### 5.2 O que o Operations Console NÃO FAZ

- Não altera o Motor, seus parâmetros ou sua execução.
- Não exibe NPS, comentários, diagnósticos ou respostas individuais de clientes finais.
- Não é acessível pelas empresas contratantes — é uma ferramenta de uso exclusivamente interno.
- Não decide nem infere status; apenas reflete fatos já registrados.

---

## 6. Princípios Arquiteturais Aprovados

### Princípio 1 — Registro Permanente

Nenhum evento acontece sem ser registrado. Todo evento gera um registro permanente. Histórico nunca é apagado; apenas novos eventos são adicionados.

### Princípio 2 — Timeline Completa por Operação

Toda Operação possui uma Timeline completa e ordenada cronologicamente, do início ao encerramento. Cada evento da Timeline registra, no mínimo:

- Data
- Hora
- Status
- Origem
- Responsável (quando aplicável)

### Princípio 3 — Não Interferência com o Motor

O Console nunca altera o Motor. Suas únicas ações permitidas em relação ao núcleo técnico são: monitorar, auditar, acompanhar e consultar.

### Princípio 4 — Autorização Prévia Obrigatória

Nenhuma operação é iniciada sem autorização explícita da empresa. Antes do upload do CSV, deve existir um aceite eletrônico, registrando:

- Data
- Hora
- Versão do termo aceito
- Usuário que aceitou
- IP de origem (quando disponível)

### Princípio 5 — Segregação de Dados Sensíveis

O Console não exibe NPS, comentários, diagnósticos ou respostas individuais. Essas informações pertencem exclusivamente ao Portal Executivo do Cliente.

---

## 7. Decisão — Unidade Principal da Plataforma

A unidade principal de exposição da plataforma **deixa de ser o Lote** e **passa a ser a Operação**.

- O Lote permanece como componente técnico interno (usado por Motor, Webhook e Integration Layer).
- O Console trabalha visualmente em termos de Operações nomeadas pelo negócio, por exemplo:
  - "Pesquisa Pós-venda Julho 2026"
  - "Pesquisa Agosto 2026"
  - "Pesquisa Loja Moema"
  - "Pesquisa Black Friday"
- O cliente e o operador, nas telas do Console e do Portal, nunca veem identificadores internos de lote.

Esta decisão não implica alteração do modelo técnico de `lote.json` ou de qualquer estrutura interna do Motor — trata-se exclusivamente de uma decisão de camada de apresentação e de vocabulário de domínio para as plataformas Console e Portal.

---

## 8. Fluxo — Jornada da Operação

```
Cliente
  ↓
Contrato
  ↓
Empresa cadastrada
  ↓
Operação criada
  ↓
Aceite eletrônico
  ↓
Upload CSV
  ↓
Validação
  ↓
Lote
  ↓
Agendamento
  ↓
Disparo
  ↓
Webhook
  ↓
Motor
  ↓
Dashboard publicado
  ↓
Operação encerrada
  ↓
Operação arquivada
```

---

## 9. Timeline — Eventos de uma Operação

Exemplo de sequência de eventos rastreados pelo Console para uma Operação:

```
Empresa criada
  ↓
Aceite eletrônico
  ↓
CSV recebido
  ↓
CSV validado
  ↓
Lote criado
  ↓
Agendamento D+8
  ↓
Mensagem enviada
  ↓
Aguardando respostas
  ↓
Resposta recebida
  ↓
Motor iniciado
  ↓
Motor concluído
  ↓
Diagnóstico gerado
  ↓
Dashboard publicado
  ↓
Operação encerrada
```

Cada evento acima é persistido de forma permanente, conforme o Princípio 1, e compõe a Timeline da Operação, conforme o Princípio 2.

---

## 10. Governança

- O Operations Console é uma ferramenta de uso exclusivamente interno da equipe NSI; não possui audiência comercial.
- Toda mudança de status de uma Operação deve se originar de um evento real do sistema (Motor, Webhook, Integration Layer ou ação humana registrada) — nunca de inferência do Console.
- O vocabulário de domínio exposto nas interfaces (Console e Portal) usa "Operação" como unidade central; "Lote" é terminologia interna, restrita à documentação técnica e ao código.
- Qualquer nova decisão arquitetural relativa ao Dashboard deve ser registrada como ADR subsequente neste mesmo diretório, mantendo a numeração sequencial.

## 11. Auditoria

- Todo evento registrado é imutável: correções ou mudanças de estado geram novos eventos, nunca a edição ou remoção de eventos anteriores.
- O aceite eletrônico (Princípio 4) é o evento fundacional de qualquer Operação e é pré-requisito obrigatório para o evento "Upload CSV".
- A trilha de auditoria de uma Operação deve permitir reconstrução completa do que aconteceu, quando, a partir de qual origem, e sob responsabilidade de quem — sem depender de nenhuma informação fora da própria Timeline.

---

## 12. Decisões Congeladas

As seguintes decisões são consideradas aprovadas e estáveis a partir desta ADR:

1. O ecossistema NSI é composto por três plataformas distintas: Operations Console, Portal Executivo do Cliente e Motor NSI.
2. O Operations Console é de uso interno, não comercial, e funciona como torre de controle operacional.
3. O Operations Console nunca altera o Motor — apenas monitora, audita, acompanha e consulta.
4. Nenhuma operação inicia sem aceite eletrônico prévio da empresa.
5. O Operations Console não exibe NPS, comentários, diagnósticos ou respostas individuais.
6. A unidade principal de exposição da plataforma é a Operação; o Lote é um componente técnico interno.
7. Todo evento gera um registro permanente e imutável; histórico nunca é apagado.

---

## 13. Dependências

- Depende da estabilidade do núcleo técnico congelado na versão `v1.1.0-fonte-unica-webhook-motor` (Motor, Webhook, Integration Layer, `lote.json` como fonte única de verdade).
- Depende de decisão arquitetural futura para definir o modelo de dados de "Operação" e sua relação técnica com "Lote" (fora do escopo desta ADR).
- Depende de ADR futura para detalhar o Portal Executivo do Cliente.

---

## 14. Itens Fora do Escopo

- Definição de schema de dados para Operação, Timeline e Evento.
- Definição de stack tecnológica (linguagem, framework, banco de dados) do Console.
- Definição de autenticação e controle de acesso interno ao Console.
- Definição de layout, componentes visuais ou fluxos de tela.
- Qualquer alteração em `engine/`, `processors/`, `models/`, `outputs/` ou `confidence/`.
- Qualquer criação de API ou endpoint.

---

## 15. Referências

- `PROJECT_STATUS.md` — status consolidado do núcleo técnico na versão `v1.1.0-fonte-unica-webhook-motor`.
- Commit `0ee7c48` — "fix: consolida lote.json como fonte unica de verdade entre webhook e Motor NSI".

---

## 16. Evolução Aprovada — Identidade Técnica da Empresa e da Operação (2026-08-25)

Esta seção documenta uma evolução aprovada da ADR-001, cumprindo a dependência registrada em sua própria Seção 13 ("Depende de decisão arquitetural futura para definir o modelo de dados de 'Operação' e sua relação técnica com 'Lote'"), sem alterar nenhum texto já congelado anteriormente.

**O que foi adicionado:**
- `empresa_id`: identificador técnico próprio, opaco e estável, atribuído a cada empresa cliente.
- O slug atual (`adapters.storage.gerar_slug_empresa`) permanece como atributo de rota e apresentação — usado em `data/empresas/<slug>/` e na rota `/empresa/<slug>` — sem nenhuma migração nesta etapa.
- `operacao_id`: identificador técnico próprio, opaco e estável, representando a Operação como unidade de negócio (Seção 7).
- `lote_id` permanece como referência técnica legada utilizada pelos componentes internos atuais, sem alteração do seu funcionamento (Seção 7).
- Cada `operacao_id` pertence exatamente a um `empresa_id` — nunca a mais de um.
- Cardinalidade **vigente** entre Operação e Lote: 1 Operação : 1 Lote — refletindo a prática já implícita na Seção 7 original e reafirmada pela ADR-005 (Princípio 5 — Unidade da Operação, Pluralidade de Recortes). Esta é a cardinalidade hoje observada, não uma regra permanente ou imutável — qualquer evolução futura exigirá decisão arquitetural própria, registrada em ADR subsequente.

**O que não mudou:**
- Nenhuma alteração ao modelo técnico de `lote.json`, ao slug ou a qualquer estrutura interna do Motor — a Seção 7 original permanece integralmente válida, incluindo sua frase-chave: *"Esta decisão não implica alteração do modelo técnico de `lote.json` ou de qualquer estrutura interna do Motor."*
- Nenhuma migração de dados existentes é realizada ou exigida nesta etapa; `lote_id`, o slug e o funcionamento atual de todos os componentes internos permanecem exatamente como são.
- O momento e o mecanismo concretos de geração de `empresa_id` e `operacao_id`, e a garantia concreta de sua unicidade, permanecem pendentes — seguem listados na Seção 14 ("Definição de schema de dados para Operação").

**Origem desta decisão:**
- Registrada durante a arquitetura do schema conceitual da Trajetória Contínua (ADR-006). A identidade de Operação compõe, junto ao tipo, a identidade da Leitura (ADR-005, Seção 16), da qual depende, transitivamente, a identidade da realidade recorrente (ADR-004, Seção 7.26). A identidade de Empresa não integra essa cadeia — ela ancora, em paralelo, a propriedade e o isolamento de cada Operação e de cada usuário (ADR-004, Seção 12).

---

## 17. Evolução Aprovada — Formato Técnico dos Identificadores (2026-08-26)

Esta seção documenta uma evolução aprovada da ADR-001, complementando a Seção 16 (Evolução Aprovada — Identidade Técnica da Empresa e da Operação), sem alterar nenhum texto já congelado anteriormente.

**O que foi adicionado:**
- `empresa_id` e `operacao_id` usam UUID4 completo, canônico, opaco, estável e imutável como formato técnico do identificador.
- `empresa_id` nasce no momento do cadastro da empresa pela equipe NSI (Seção 8, "Empresa cadastrada"; ADR-004, §4, Princípio 2 — Cadastro Centralizado na NSI).
- `operacao_id` nasce no momento da criação da Operação (Seção 8, "Operação criada").
- Permanecem pendentes apenas: o mecanismo técnico concreto de geração, a persistência e a garantia concreta de unicidade persistida (constraints de banco de dados, tratamento de colisão, schema concreto) de ambos os identificadores — pendências já registradas na Seção 16 e listadas na Seção 14.

**O que não mudou:**
- Nenhuma alteração ao `lote_id`, ao slug ou a qualquer estrutura interna do Motor.
- Nenhuma implementação de código, schema de banco de dados ou API é definida aqui — apenas formato técnico e momento conceitual de nascimento do identificador.

**Origem desta decisão:**
- Registrada durante a consolidação da identidade técnica e da política de idempotência da Trajetória Contínua (ADR-006), que exige um formato uniforme de identificador — e o momento de seu nascimento — para toda a cadeia de entidades (`empresa_id`, `operacao_id`, `usuario_id`, `resultado_id`, `realidade_id`, `registro_id`).
