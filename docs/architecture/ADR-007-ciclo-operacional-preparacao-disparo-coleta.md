# ADR-007 — Ciclo Operacional de Preparação e Disparo da Coleta

## Metadados

| Campo | Valor |
|---|---|
| Status | APROVADA E CONGELADA |
| Data | 2026-08-27 |
| Versão de referência do sistema | `v1.1.0-fonte-unica-webhook-motor` |
| Commit de referência | `64e0a30` |
| Branch | `master` |
| Escopo desta ADR | Arquitetura — nenhuma implementação de código, frontend ou componente visual |

> **Nota de processo:** ADR aberta para registrar o ciclo operacional que precede o Motor NSI — desde o upload do CSV original de uma Operação até a confirmação humana do primeiro disparo da mensagem de pós-venda. Este intervalo existia apenas de forma implícita no código (`adapters/storage.py`, `core/scheduler.py`, `core/dispatcher.py`, `services/whatsapp.py`) e nunca havia sido formalizado como decisão arquitetural própria. Esta ADR seguiu a mesma metodologia já validada nas ADRs anteriores: arquitetura primeiro, implementação depois, congelamento somente após aprovação explícita. **Esta ADR foi revisada em quatro partes, aprovada explicitamente em cada uma delas, e está APROVADA E CONGELADA** (Seção 28).

---

## 1. Objetivo

Registrar a arquitetura do ciclo operacional que antecede o Motor NSI: do instante em que o CSV original de uma Operação é recebido (upload) até o instante em que o primeiro disparo da mensagem de pós-venda é humanamente confirmado por um Operador Interno da NSI.

Esta ADR define, antes de qualquer código: como cada linha do CSV se torna um registro de coleta independente e imutavelmente vinculado a um produto; como registros válidos e inválidos são separados e preservados; como uma correção pré-D+8 se vincula ao registro original sem reabri-lo; o instante e o mecanismo conceitual do congelamento do lote; a exigência de confirmação humana em dois atos antes de qualquer disparo; o processamento idempotente do disparo entre processos e workers; os limites e a classificação das tentativas de reenvio; e a obrigação de que o sistema nunca afirme, por inferência, que uma mensagem foi recebida ou lida por uma pessoa.

Esta ADR não implementa nada. Ela define o que deve ser verdade antes que uma única mensagem de pós-venda seja enviada — e as regras que impedem disparo automático, perda de registros e vinculação incorreta entre resposta e produto.

---

## 2. Escopo

### 2.1 Escopo desta decisão

- Definição do Marco de Upload (M0) e da estrutura mínima do CSV original (nome, WhatsApp, produto).
- Definição do produto como objeto do pós-venda e do registro de coleta como unidade independente, imutavelmente vinculada a um produto.
- Regra de que o telefone não é unidade de deduplicação nem de associação de resposta.
- Validação automática de cada linha do CSV, separação entre registros válidos e inválidos, e preservação de ambos.
- Identidade técnica própria de cada registro de coleta (código técnico) e o fluxo de correção pré-D+8, em regime append-only.
- Cadeia técnica obrigatória entre convite enviado, resposta recebida, registro de coleta e produto de origem — incluindo a proibição explícita de mecanismos alternativos de associação (link, botão, pergunta posterior, inferência).
- Fórmula da contagem definitiva de registros aptos ao disparo.
- Regra de congelamento do lote em M0 + 192 horas (D+8), incluindo o comportamento de detecção tardia.
- Estado de espera pós-congelamento ("Aguardando confirmação de disparo") e sua não expiração.
- Regras de identificação da Operação na interface da Central de Operações, sem exposição de `lote_id` técnico.
- Papel e características do Operador Interno da NSI nesta primeira versão.
- Modelo de confirmação humana em dois atos, incluindo o que cada ato registra e o que cada ato não constitui.
- Exigência de idempotência do processamento do disparo entre processos e workers.
- Definição do T0 da Coleta (primeiro disparo confirmado), sua distinção formal de M0, e sua relação com o T0 já congelado na ADR-005.
- Limites, intervalo mínimo e escopo (por registro de coleta) das tentativas de reenvio.
- Categorias de classificação de falha (temporária, definitiva, não classificada) e a obrigação de registro de toda classificação.
- Estados finais do processamento de disparo.
- Regra de verdade observável: eventos técnicos da plataforma de mensageria (enviado, entregue, lido, falhou) são registrados como fatos técnicos, nunca como prova de leitura ou atenção humana.

### 2.2 Fora do escopo desta decisão

- Mecanismo técnico concreto de detecção do instante de congelamento (cron, worker, polling ou equivalente).
- Schema de banco de dados, tabelas, colunas, índices ou constraints para qualquer entidade desta ADR.
- Qualquer endpoint, rota ou API concreta.
- Protocolo, provedor ou implementação concreta de autenticação e MFA do Operador Interno.
- Mapeamento concreto dos códigos de erro da WhatsApp Cloud API às categorias de falha (temporária/definitiva) — a ser feito em especificação técnica própria, com base na documentação oficial da Meta.
- Mecanismo técnico concreto de correlação persistente entre convite, envio, resposta e produto (Seção 10.3) — esta ADR fixa a obrigação de que essa correlação exista e seja íntegra, não o mecanismo que a implementa.
- Layout, componentes visuais, posição, cores ou qualquer arquitetura visual da Central de Operações.
- Qualquer alteração ao Motor NSI, ao Portal Executivo do Cliente (ADR-004) ou à Jornada de Transformação Organizacional (ADR-006).
- Qualquer alteração às janelas e princípios já congelados da ADR-005 (Leitura Inicial, Leitura de Excedência, 336 horas) — esta ADR referencia a ADR-005, nunca a redefine.
- Evolução para múltiplos Operadores Internos — registrada como decisão de escopo futuro (Seção 15).

---

## 3. Contexto

Durante a auditoria de retomada arquitetural do NSI (2026-08-27), identificou-se que o ciclo operacional entre o upload do CSV e o primeiro disparo de mensagem existia apenas de forma implícita e incompleta no código (`adapters/storage.py::salvar_lote`, `core/scheduler.py::calcular_d8`/`disparar_lote`, `services/whatsapp.py::enviar_template_d8`), sem nenhuma ADR própria. Essa lacuna documental deixava sem definição arquitetural formal um conjunto de regras operacionais críticas: validação de registros, correção pré-disparo, confirmação humana, idempotência de disparo e classificação de falhas.

Durante a elaboração inicial desta ADR, surgiu o risco de a tela de confirmação do Operador Interno exibir identificação técnica do lote (`lote_id`), o que colidiria com a regra já congelada na ADR-001 (§7 — o operador nunca vê identificadores internos de lote). Esse risco foi identificado e resolvido antes da redação do texto: a interface desta ADR exibirá a Operação — nome de negócio —, nunca o `lote_id` técnico (Seção 14). Se a implementação atual do código expuser `lote_id` em algum ponto de uma tela operacional, isso constitui não conformidade técnica a corrigir, nunca uma contradição entre esta ADR e a ADR-001, cujo texto já congelado esta ADR apenas confirma e aplica a um novo domínio.

Uma das regras desta ADR não é nova: o princípio de que o pós-venda é organizado por compra/produto, não por cliente, já estava registrado, em linguagem pré-ADR, no documento histórico `NSI_MASTER_CONTEXT.md` — seção "Regras fixas / decisões": *"Pós-venda é por compra/produto, não por cliente."* Esse documento antecede a metodologia de ADRs do projeto e hoje está preservado exclusivamente como registro histórico, fora do corpo ativo de documentação. Ele é citado aqui apenas como evidência de proveniência — não é fonte de verdade vigente, não é dependência normativa desta ADR, e esta ADR não depende, em nenhum grau, de sua preservação em qualquer branch ou arquivo. A partir desta ADR, a regra é integralmente incorporada e a ADR-007 passa a ser a referência arquitetural ativa e exclusiva para o vínculo entre resposta, registro de coleta e produto.

A mesma auditoria confirmou que o campo `produto`, embora nunca elevado a princípio de ADR, permaneceu presente em múltiplas camadas do código atual — é campo próprio em `models/input_models.py`, é persistido por linha em `adapters/storage.py::salvar_lote`, é enviado como parâmetro do template em `services/whatsapp.py::enviar_template_d8`, e é usado no prompt semântico em `core/motor_semantico.py::analisar_cliente`. A auditoria também confirmou que a correlação entre uma resposta recebida e o registro de coleta que a originou ainda depende apenas do telefone (`adapters/storage.py::buscar_lote_por_telefone`, `salvar_resposta_cliente`) — insuficiente sempre que um mesmo telefone possuir mais de um registro de coleta. Esta ADR fecha essa lacuna arquitetural, fixando a obrigação (Seção 10), sem alterar, nesta etapa, a implementação (Seção 24).

Esta ADR também cumpre a dependência implícita deixada pela ADR-005 (Princípio 1), que sempre definiu T0 como *"o timestamp exato do disparo do lote"* sem nunca operacionalizar esse instante em um cenário de múltiplos destinatários e possíveis reenvios — o T0 da Coleta, definido na Seção 18, preenche essa lacuna sem alterar uma palavra do texto já congelado da ADR-005.

---

## 4. Princípios Arquiteturais do Ciclo de Preparação e Disparo

### Princípio 1 — Marco de Upload (M0)

M0 é o timestamp exato em que o CSV original entra no NSI e o lote é criado. É o início de toda contagem relativa ao ciclo de preparação — distinto do T0 da Coleta (Princípio 11).

### Princípio 2 — Produto como Objeto do Pós-venda

O produto — não o cliente isoladamente — é o objeto do pós-venda. Cada linha do CSV original representa a experiência de um cliente com um produto específico, e é essa relação que o NSI observa e organiza.

### Princípio 3 — Registro de Coleta como Unidade Independente, Vinculada ao Produto

Cada linha do CSV cria um registro de coleta independente, imutavelmente vinculado ao produto daquela linha. Linhas idênticas — mesmo nome, mesmo WhatsApp, mesmo produto — permanecem registros independentes. O telefone nunca é unidade de deduplicação: o mesmo telefone pode legitimamente originar múltiplos registros de coleta quando houver múltiplos produtos.

### Princípio 4 — Validação Automática e Preservação do Inválido

Todo registro é validado automaticamente no upload. Registros inválidos nunca são apagados — permanecem preservados, com o motivo da invalidade, ao lado dos válidos, consistente com o Princípio 1 da ADR-001 (Registro Permanente).

### Princípio 5 — Identidade Técnica do Registro de Coleta

Cada registro de coleta recebe, automaticamente, um código técnico imutável — nunca exigido do CSV original — que passa a ser sua identidade ao longo de todo o ciclo: correção, envio, resposta e processamento pelo Motor.

### Princípio 6 — Correção Append-Only, Vinculada por Código Técnico

Uma correção recebida antes de D+8 nunca reabre, edita ou apaga o registro original — cria uma nova versão vinculada por código técnico, em regime estritamente append-only, no mesmo padrão já estabelecido pela ADR-005 (convite de coleta) e pela ADR-006 (Trajetória Contínua). A versão inválida original permanece intacta; a nova versão validada passa a representar o estado corrente do mesmo registro de coleta. Correção sem código correspondente é recusada. A correção nunca cria um novo registro de coleta.

### Princípio 7 — Vínculo Obrigatório entre Convite, Resposta e Produto

Toda resposta recebida deve permanecer tecnicamente vinculada ao mesmo registro de coleta — e, por consequência, ao mesmo produto — que originou o convite. Essa vinculação nunca depende do telefone isoladamente, nunca é delegada ao respondente e nunca é inferida pelo sistema. Nenhuma resposta entra no Motor NSI sem esse vínculo técnico íntegro.

### Princípio 8 — Congelamento Definitivo em M0+192h

No instante exato de M0 + 192 horas (D+8), o lote é congelado: nenhuma inclusão, nenhuma correção, nenhuma alteração de composição é aceita a partir desse instante. O único ato seguinte legítimo é a confirmação humana do disparo.

### Princípio 9 — Confirmação Humana Obrigatória (Dois Atos)

Nenhum disparo ocorre sem confirmação humana explícita, em dois atos distintos, do Operador Interno da NSI. O NSI nunca dispara automaticamente — reafirmando, sem exceção, o Capítulo 5 do Livro dos Princípios ("A tecnologia serve; não decide").

### Princípio 10 — Idempotência entre Processos e Workers

O processamento do disparo é idempotente de ponta a ponta — clique duplo, atualização de página ou repetição de requisição nunca duplicam uma mensagem — e essa garantia vale entre processos e workers distintos, não apenas em memória de um único processo.

### Princípio 11 — T0 da Coleta, Distinto de M0

O T0 da Coleta é o timestamp exato do primeiro disparo confirmado — distinto de M0 — e fixa o relógio de resposta de todo o lote, nos termos já congelados na ADR-005 (Princípio 1). Reenvios nunca reiniciam nem ampliam esse relógio.

### Princípio 12 — Tentativas Limitadas por Registro de Coleta

Cada registro de coleta — não cada telefone — possui uma tentativa inicial e até duas novas tentativas por falha temporária, com intervalo mínimo de uma hora entre tentativas, cada nova tentativa mediante confirmação do Operador Interno, e sempre limitadas pela janela total da coleta já definida na ADR-005.

### Princípio 13 — Verdade Observável dos Eventos do WhatsApp

A aceitação de um envio pela API nunca é apresentada como prova de recebimento. Eventos técnicos fornecidos pela plataforma (enviado, entregue, lido, falhou) são registrados separadamente, como fatos técnicos observáveis — nunca como inferência de atenção, leitura humana ou resposta.

---

## 5. Fluxo — Ciclo Operacional Completo

```
Upload do CSV (nome, WhatsApp, produto)
  ↓
M0 — Marco de Upload (lote criado)
  ↓
Validação automática linha a linha
  ↓
Separação: registros válidos / registros inválidos (preservados, com motivo)
  ↓
Código técnico gerado para cada registro de coleta
  ↓
[Janela de correção — até M0 + 192h]
  Empresa pode devolver CSV de correção (código técnico + nome + WhatsApp + produto)
  Correção válida entra no lote original (append-only, vinculada por código)
  Composição definitiva é recalculada
  ↓
M0 + 192h — Congelamento definitivo do lote
  Nenhuma inclusão, nenhuma correção, composição final travada
  ↓
Estado: "Aguardando confirmação de disparo" (não expira)
  ↓
Operador Interno da NSI — 1º ato: "Confirmar disparo" (abre a tela, não decide)
  ↓
Operador Interno da NSI — 2º ato: "Confirmar e disparar" (decide, irreversível)
  ↓
T0 da Coleta — timestamp do primeiro disparo confirmado (distinto de M0)
  ↓
Estado: "Disparo em processamento" (idempotente, botão bloqueado)
  ↓
Envio por registro de coleta (1 tentativa inicial + até 2 por falha temporária,
  intervalo mínimo de 1h, sempre dentro da janela de coleta da ADR-005)
  ↓
Estados finais: "Disparo processado" |
  "Disparo processado com novas tentativas pendentes" |
  "Disparo processado com falhas encerradas"
  ↓
Eventos técnicos do WhatsApp (enviado/entregue/lido/falhou) registrados separadamente
  ↓
Resposta recebida → vinculada ao mesmo registro de coleta e produto de origem
  ↓
Motor NSI (ADR-005 — Leitura Inicial / Leitura de Excedência)
```

---

## 6. Marco de Upload (M0) e Estrutura do CSV Original

- M0 é o timestamp exato em que o CSV original entra no NSI e o lote é criado — evento fundacional de todo o ciclo desta ADR.
- O CSV original possui exclusivamente três campos: nome, WhatsApp, produto. Nenhum outro campo é exigido nesta etapa.
- Cada linha do CSV é processada como um registro de coleta candidato, sujeito à validação da Seção 8.
- Linhas idênticas — mesmo nome, mesmo WhatsApp, mesmo produto — não são deduplicadas: permanecem registros de coleta independentes (Seção 7).

---

## 7. Produto como Objeto do Pós-venda e Registro de Coleta

### 7.1 Cada linha é um registro de coleta, vinculado a um produto

O produto é o objeto do pós-venda. Cada linha do CSV cria um registro de coleta independente e imutavelmente vinculado ao produto daquela linha — nunca ao cliente isoladamente. Se o mesmo telefone aparecer em três linhas com três produtos distintos, existirão três registros de coleta, três mensagens e três vínculos independentes entre envio, resposta e produto.

### 7.2 Origem da regra: consolidação, não criação

Esta regra não nasce nesta ADR. Ela já constava, em linguagem pré-ADR, no documento histórico `NSI_MASTER_CONTEXT.md` ("Pós-venda é por compra/produto, não por cliente"), citado aqui apenas como proveniência histórica (Seção 3) — sem que esta ADR dependa, normativamente, daquele documento. O campo `produto` permaneceu presente, de forma implícita, em múltiplas camadas do código atual: é campo próprio de entrada, é propagado ao template de disparo e ao prompt do Motor. O que nunca existiu foi a garantia técnica de que uma resposta recebida permanece corretamente vinculada ao mesmo registro de coleta e produto que originaram o convite (Seção 10.3). Esta ADR formaliza a regra pela primeira vez como princípio arquitetural, sem alterar sua substância, e passa a ser sua referência arquitetural ativa.

### 7.3 Telefone não é unidade de deduplicação nem de associação

O telefone identifica um canal de contato, nunca a identidade de um registro de coleta. Ele nunca é usado para deduplicar linhas do CSV e nunca é, isoladamente, suficiente para associar uma resposta recebida ao registro de coleta correto (Seção 10).

---

## 8. Validação Automática e Separação de Registros

- O NSI valida automaticamente cada linha do CSV no momento do upload.
- Telefone brasileiro é aceito com ou sem `+55` e com ou sem formatação (espaços, parênteses, hífens); o sistema remove esses caracteres e acrescenta `+55` quando ausente.
- A validação exige DDD e uma quantidade estruturalmente válida de dígitos — sem presumir, em nenhum momento, que o número efetivamente possui WhatsApp.
- Cada linha é classificada como válida ou inválida.
- O sistema exibe o total recebido, o total válido e o total inválido.
- Registros inválidos são preservados integralmente, junto de seu motivo de invalidade — nunca apagados (Princípio 4).

---

## 9. Identidade Técnica do Registro de Coleta e Fluxo de Correção

### 9.1 Código técnico (identidade)

O NSI gera automaticamente um código técnico imutável para cada linha importada, no momento em que o registro de coleta é criado. Esse código nunca é exigido no CSV original — nasce inteiramente do lado do sistema.

### 9.2 Relatório de correção

Quando solicitado, o relatório/arquivo de correção apresenta, por registro: código técnico, nome, WhatsApp, produto — permitindo que a empresa devolva apenas os registros corrigidos, identificados por esse código.

### 9.3 Regras de vínculo e recusa

- A empresa devolve somente o CSV dos registros corrigidos.
- O código técnico vincula a correção ao registro original.
- A correção cria uma nova versão em regime append-only. A versão inválida original permanece intacta, nunca apagada ou reescrita; a nova versão validada passa a representar o estado corrente do mesmo registro de coleta.
- Uma correção sem código correspondente é recusada.
- A correção nunca cria um novo registro de coleta (nunca é tratada como nova venda) — apenas qualifica, por acréscimo, o estado corrente de um registro já existente.
- Uma correção válida, recebida antes de D+8, entra no lote original.
- A correção não reinicia nem altera nenhum relógio do ciclo (nem M0, nem, posteriormente, o T0 da Coleta).

### 9.4 Correspondência com o "convite de coleta" da ADR-005

O código técnico do registro de coleta, definido nesta Seção, é a identidade técnica concreta do **convite de coleta** já referenciado conceitualmente pela ADR-005 (Princípio 12 — "Convite de Coleta como Unidade de Participação"). Esta ADR não altera uma palavra do texto já congelado da ADR-005 — apenas atribui, agora, a identidade técnica que aquele princípio sempre pressupôs sem formalizar.

---

## 10. Cadeia Obrigatória — Do CSV ao Motor

### 10.1 A cadeia técnica vinculante

A cadeia obrigatória entre a criação de um registro de coleta e sua chegada ao Motor NSI é:

```
linha do CSV
  → código técnico do registro de coleta
  → nome + WhatsApp + produto
  → convite enviado
  → identidade técnica do envio
  → resposta recebida
  → mesmo registro de coleta
  → mesmo produto
  → Motor NSI
```

Nenhuma resposta pode entrar no Motor NSI sem estar tecnicamente vinculada ao registro de coleta e ao produto que a originaram. Esta é uma obrigação arquitetural, válida independentemente do mecanismo concreto que venha a implementá-la (Seção 10.3).

### 10.2 Exclusões explícitas

Não haverá, como solução para este vínculo: link externo; botão de escolha de produto; pergunta posterior ao respondente sobre qual produto está sendo avaliado; inferência pelo último envio realizado; ou associação presumida apenas pelo telefone. A vinculação é inteiramente técnica e decidida no momento do envio — nunca delegada ao respondente, nunca resolvida por heurística.

### 10.3 Não conformidade da implementação atual

O campo `produto` já está representado e propagado em múltiplas camadas do código atual: é campo próprio em `models/input_models.py`; é persistido por linha em `adapters/storage.py::salvar_lote`; o template de disparo em `services/whatsapp.py::enviar_template_d8` usa `nome` e `produto` como parâmetros da mensagem; e o Motor recebe `produto` no prompt semântico (`core/motor_semantico.py::analisar_cliente`) e na saída agregada (`integration/nsi_integration.py`).

Porém a correlação da **resposta recebida** ainda usa o telefone isoladamente: `adapters/storage.py::buscar_lote_por_telefone` e `salvar_resposta_cliente` casam a resposta ao primeiro cliente cujo telefone corresponda, sem considerar qual registro de coleta — e, portanto, qual produto — originou aquele convite específico.

Consequência: a cadeia ponta a ponta descrita na Seção 10.1 **ainda não está conforme** à obrigação arquitetural desta ADR. Esta ADR fixa o resultado obrigatório; ela não define, nesta etapa, o mecanismo técnico concreto que trará a implementação à conformidade (Seção 24) — apenas declara que essa conformidade é exigida e que o estado atual não a satisfaz.

---

## 11. Contagem Definitiva para Disparo

- Total definitivo para disparo = linhas válidas no upload original + registros originalmente inválidos cuja correção foi recebida e validada antes de D+8.
- Uma correção válida cria uma nova versão vinculada ao registro de coleta original; a versão inválida original permanece intacta e preservada. A nova versão validada passa a representar o estado corrente daquele mesmo registro de coleta para fins de contagem. Nenhuma soma é feita e nenhum novo registro de coleta é criado por uma correção.
- Linhas idênticas continuam contando separadamente, consistente com o Princípio 3.

---

## 12. D+8, Congelamento e Detecção Tardia

- D+8 corresponde exatamente a M0 + 192 horas.
- No instante de D+8, o lote é congelado.
- A partir do congelamento: nenhuma inclusão é permitida; nenhuma correção é permitida; a composição final não muda; o único próximo ato legítimo é a confirmação humana do disparo (Seção 16).
- Correções recebidas após esse instante ficam definitivamente fora daquele lote.
- O interesse e a responsabilidade de corrigir dentro do prazo pertencem à empresa.
- O NSI detecta o instante de D+8 sem depender de qualquer tela estar aberta.
- Se o sistema estiver indisponível exatamente no instante de D+8, ele regulariza a situação imediatamente ao retornar.
- O sistema registra, separadamente: (a) o horário conceitual do congelamento — sempre M0 + 192h, fixo; e (b) o horário real em que a execução técnica do congelamento efetivamente ocorreu, quando tardia.
- O mecanismo técnico concreto de detecção (cron, worker ou equivalente) fica para especificação técnica futura (Seção 24) — esta ADR não o define.

---

## 13. Estado de Espera — "Aguardando Confirmação de Disparo"

- Após o congelamento, o lote assume o estado "Aguardando confirmação de disparo".
- O lote não expira nesse estado.
- O atraso do Operador Interno em confirmar: não reabre o lote; não permite novas correções; não altera a composição definitiva; e não provoca disparo automático em nenhuma hipótese.
- O aviso de que um lote aguarda confirmação existe exclusivamente na Central de Operações.
- Nesta versão, não há aviso por e-mail ou WhatsApp.

---

## 14. Identificação na Interface — Central de Operações

- A interface da Central de Operações nunca exibe o `lote_id` técnico.
- Exibe, em vez disso: nome da empresa; nome ou identificação de negócio da Operação; data e hora do upload; data e hora de D+8; total recebido; válidos; inválidos; correções recebidas e aceitas; e o total definitivo para disparo.
- O `lote_id` permanece exclusivamente na estrutura técnica interna e nos registros de auditoria — nunca em tela voltada ao operador, consistente com a ADR-001 (§7 — a unidade de exposição da plataforma é a Operação; o Lote é componente técnico interno). Caso a implementação atual exponha `lote_id` em algum ponto da interface, isso constitui não conformidade técnica a corrigir — nunca uma contradição entre esta ADR e a ADR-001, cujo texto já congelado esta regra apenas confirma.

---

## 15. Operador Interno da NSI

- Nesta primeira versão, existe apenas um Operador Interno autorizado.
- É uma conta interna da NSI, separada de qualquer perfil de usuário de empresa cliente (Usuário Comum, Gestor ou Administrador, ADR-004 §14).
- Possui login individual e MFA obrigatório.
- Ainda que essa conta utilize o mesmo endereço de e-mail de outra conta em outro contexto, sua autorização pertence exclusivamente ao ambiente interno da NSI — as duas identidades não se confundem.
- Somente esse Operador Interno confirma disparos e novas tentativas de reenvio.
- A existência de múltiplos Operadores Internos fica registrada como decisão de escopo para evolução arquitetural futura e própria — não é definida nesta ADR.

---

## 16. Confirmação em Dois Atos

- **Primeiro ato — "Confirmar disparo":** apenas abre a tela de confirmação. Não constitui, por si só, nenhuma decisão. Se a janela for fechada nesse ponto, nada acontece e o lote permanece "Aguardando confirmação de disparo".
- **Segundo ato — "Confirmar e disparar":** a confirmação final informa a quantidade definitiva de destinatários e um aviso explícito de irreversibilidade.
- Somente o segundo ato: autoriza o disparo; muda o estado do lote; e é registrado como decisão.
- O ato registrado inclui: operador responsável, data, hora e a composição definitiva do lote naquele momento.

---

## 17. Processamento, Bloqueio e Idempotência

- Após o segundo ato, o lote assume o estado "Disparo em processamento".
- O botão de confirmação fica bloqueado.
- Duplo clique, atualização da página ou repetição da requisição não duplicam mensagens em nenhuma circunstância.
- Cada registro de coleta possui uma chave persistente de idempotência.
- Essa idempotência funciona entre processos e workers distintos — não apenas em memória de um único processo, resolvendo a limitação hoje documentada no próprio código (`adapters/storage.py::_obter_lock_lote`: *"Não protege contra múltiplos processos/workers"*).

---

## 18. T0 da Coleta — Relação com a ADR-005

- O T0 da Coleta é o timestamp exato do primeiro disparo confirmado.
- É formalmente distinto de M0 (Marco de Upload, Seção 6).
- O T0 da Coleta fixa o relógio de resposta de todo o lote — é o T0 que a ADR-005 (Princípio 1) já define como *"o timestamp exato do disparo do lote"*; esta ADR não redefine esse conceito, apenas o operacionaliza para o cenário de múltiplos destinatários e possíveis reenvios.
- Reenvios não reiniciam nem ampliam o prazo fixado por esse T0.
- Quem recebe um reenvio posteriormente dispõe apenas do tempo restante da janela original — nunca de uma nova janela.
- Falhas e reenvios nunca atrasam o cronograma das Leituras já definidas na ADR-005.

---

## 19. Tentativas de Disparo — Limites e Intervalos

- Cada linha/produto (cada registro de coleta) possui uma tentativa inicial e até duas novas tentativas em caso de falha temporária.
- O limite é por registro de coleta — nunca por telefone.
- O intervalo mínimo entre tentativas do mesmo registro de coleta é de uma hora.
- Envios já aceitos tecnicamente pela API não são repetidos.
- Cada nova tentativa exige confirmação explícita do Operador Interno.
- Novas tentativas só podem ocorrer enquanto a janela total da coleta (ADR-005) estiver aberta.
- O encerramento dessa janela bloqueia definitivamente qualquer nova tentativa.

---

## 20. Classificação de Falhas

- **Falha temporária:** permite nova tentativa, dentro dos limites da Seção 19.
- **Falha definitiva:** não permite nova tentativa.
- **Falha não classificada:** não permite nova tentativa enquanto não for analisada e formalmente classificada.
- O mapeamento concreto dos códigos de erro da WhatsApp Cloud API para essas três categorias fica para especificação técnica futura, baseada na documentação oficial da Meta — não é definido nesta ADR.
- Toda classificação e toda reclassificação de falha ficam registradas.

---

## 21. Estados Posteriores ao Processamento

- "Disparo processado".
- "Disparo processado com novas tentativas pendentes".
- "Disparo processado com falhas encerradas".
- Nenhuma falha interrompe o cronograma geral ou impede a coleta de resposta de quem teve seu envio efetivamente aceito.

---

## 22. Verdade Observável — Eventos Técnicos do WhatsApp

- A aceitação de um envio pela API nunca significa, por si só, recebimento pelo destinatário.
- O NSI nunca afirma que alguém recebeu uma mensagem sem um evento técnico correspondente que sustente essa afirmação.
- Eventos fornecidos pela plataforma — enviado, entregue, lido, falhou — são registrados separadamente, como eventos técnicos observáveis.
- O NSI registra esses fatos técnicos sem jamais inferir atenção, leitura humana ou intenção de resposta a partir deles — reafirmando, para este domínio, o mesmo Princípio da Observabilidade já congelado na ADR-004 (§7.17): o sistema organiza evidências; não interpreta.

---

## 23. Decisões Aprovadas e Congeladas

As decisões a seguir constituem a arquitetura aprovada e congelada desta ADR:

1. M0 como Marco de Upload, distinto do T0 da Coleta (Princípio 1; Seção 6).
2. Produto como objeto do pós-venda; registro de coleta como unidade independente vinculada ao produto (Princípios 2-3; Seção 7).
3. Telefone não é unidade de deduplicação nem de associação de resposta (Seção 7.3).
4. Validação automática por linha, com separação e preservação de válidos e inválidos (Princípio 4; Seção 8).
5. Identidade técnica própria do registro de coleta (código técnico), gerada pelo NSI, nunca exigida no CSV original (Princípio 5; Seção 9.1).
6. Fluxo de correção pré-D+8 em regime append-only: a correção cria nova versão vinculada por código técnico; a versão inválida original permanece intacta; a nova versão validada passa a representar o estado corrente do mesmo registro de coleta; correção sem código correspondente é recusada; nenhuma correção cria novo registro de coleta (Princípio 6; Seção 9.3).
7. Correspondência entre o código técnico do registro de coleta e o "convite de coleta" já congelado na ADR-005, Princípio 12 (Seção 9.4).
8. Cadeia técnica obrigatória entre convite, resposta, registro de coleta, produto e Motor NSI, com exclusão explícita de link, botão, pergunta posterior ou inferência como mecanismo de associação — obrigação fixada nesta ADR; implementação atual ainda não conforme (Princípio 7; Seções 10.1-10.3).
9. Fórmula da contagem definitiva para disparo, sem soma indevida por correção (Seção 11).
10. Congelamento definitivo do lote em M0 + 192 horas, com registro separado do horário conceitual e do horário real de execução tardia (Princípio 8; Seção 12).
11. Estado "Aguardando confirmação de disparo", sem expiração, imune a atraso do operador (Seção 13).
12. Identificação da Operação — nunca do `lote_id` técnico — na interface da Central de Operações (Seção 14).
13. Operador Interno único nesta versão, conta interna da NSI, com login individual e MFA obrigatório (Seção 15).
14. Confirmação humana em dois atos — o primeiro sem efeito decisório, o segundo como decisão efetiva —, com registro de operador, data, hora e composição definitiva (Princípio 9; Seção 16).
15. Idempotência do processamento de disparo entre processos e workers (Princípio 10; Seção 17).
16. T0 da Coleta como o timestamp do primeiro disparo confirmado, distinto de M0 e consistente com o T0 já congelado na ADR-005 (Princípio 11; Seção 18).
17. Limites, intervalo mínimo e escopo por registro de coleta das tentativas de reenvio (Princípio 12; Seção 19).
18. Três categorias de classificação de falha, com registro obrigatório de toda classificação (Seção 20).
19. Três estados finais de processamento de disparo (Seção 21).
20. Regra de verdade observável para os eventos técnicos do WhatsApp (Princípio 13; Seção 22).

---

## 24. Pendências Técnicas Não Bloqueantes ao Congelamento Arquitetural

Nenhuma das pendências abaixo é lacuna conceitual da arquitetura desta ADR, e nenhuma delas reabre ou impede o congelamento registrado na Seção 28. São exclusivamente pendências de implementação técnica, a resolver em especificação técnica futura. Algumas, no entanto, bloqueiam a implementação ou o uso operacional da arquitetura aqui congelada, mesmo sem bloquear seu congelamento conceitual — essa distinção é explicitada individualmente abaixo.

- Mecanismo técnico concreto de detecção do instante de congelamento (cron, worker, polling ou equivalente) — não bloqueia o congelamento conceitual; é pré-requisito apenas para a automação da detecção de M0+192h (Seção 12).
- **Correlação persistente entre registro de coleta, envio, resposta e produto** (Seção 10.1) — não bloqueia o congelamento conceitual desta ADR. Bloqueia, especificamente, qualquer operação em que um mesmo telefone possua mais de um registro de coleta: enquanto essa correlação não existir tecnicamente, o casamento atual apenas por telefone (`adapters/storage.py::buscar_lote_por_telefone`, `salvar_resposta_cliente`) não pode ser considerado implementação aceitável desta ADR para esse cenário. Nenhuma resposta ambígua — isto é, uma resposta cujo registro de coleta e produto de origem não possam ser determinados com certeza técnica — pode entrar no Motor NSI como se estivesse corretamente vinculada a um produto.
- Mecanismo técnico concreto de chave de idempotência persistente entre processos e workers para o processamento de disparo (Seção 17) — não bloqueia o congelamento conceitual; bloqueia apenas a operação em ambiente com múltiplos workers antes de sua implementação.
- Mapeamento concreto dos códigos de erro da WhatsApp Cloud API às categorias de falha temporária/definitiva/não classificada, com base na documentação oficial da Meta (Seção 20) — não bloqueia o congelamento conceitual; até que exista, toda falha permanece "não classificada" e, por definição, sem nova tentativa.
- Autenticação e MFA concretos do Operador Interno — protocolo, provedor, armazenamento de credenciais (Seção 15) — não bloqueia o congelamento conceitual; bloqueia o próprio funcionamento do fluxo de confirmação humana até que exista.
- Schema de dados para código técnico do registro de coleta, correções, tentativas e eventos técnicos do WhatsApp — não bloqueia o congelamento conceitual; é pré-requisito de qualquer implementação de código desta ADR.
- Qualquer endpoint, rota ou API concreta para as operações descritas nesta ADR — não bloqueia o congelamento conceitual; é pré-requisito de implementação.
- Layout, componentes visuais e arquitetura visual concreta da Central de Operações — não bloqueia o congelamento conceitual; é pré-requisito apenas da interface visual.

---

## 25. Dependências

- Depende da ADR-001 (Seção 7 — Operação como unidade de exposição da plataforma; Princípio 1 — Registro Permanente), para a regra de identificação na interface (Seção 14) e para a preservação de registros inválidos (Seção 8).
- Depende da ADR-005 (Princípio 1 — definição de T0; Princípios 12-14 — convite de coleta como unidade de participação; janela total de 336 horas), para o T0 da Coleta (Seção 18) e para os limites das tentativas de reenvio (Seção 19) — esta ADR não redefine nenhuma dessas regras, apenas as referencia e, no caso do T0, as operacionaliza.
- Depende do Livro dos Princípios do NSI, especialmente "A tecnologia serve; não decide" (Capítulo 5) e "Compreensão Antes de Automação" (Princípio 3), para a exigência de confirmação humana obrigatória (Seção 16).

---

## 26. Itens Fora do Escopo

Ver Seção 2.2.

---

## 27. Referências

- `docs/architecture/ADR-001-operations-console.md` — Seção 7 (Operação como unidade de exposição), Princípio 1 (Registro Permanente).
- `docs/architecture/ADR-005-ciclo-temporal-coleta-leituras-independentes.md` — Princípio 1 (T0), Princípios 12-14 (convite de coleta), janela de 336 horas.
- `docs/principios/livro-dos-principios.md` — Capítulo 5 ("A tecnologia serve; não decide"), Princípio 3 ("Compreensão Antes de Automação").
- `PROJECT_STATUS.md` — pendência já registrada de consumo dos eventos `statuses` do webhook Meta (Sprint 3), retomada e formalizada nesta ADR (Seção 22).

---

## 28. Status Final e Congelamento (2026-08-27)

Com a arquitetura completa registrada nas Seções 1 a 27, revisada e aprovada em quatro partes — auditoria de consistência e estrutura; texto integral; diffs de ADR-001, ADR-005 e PROJECT_STATUS.md; arquivos afetados, referências, pendências e plano de aplicação —, a ADR-007 passa do status EM ARQUITETURA para **APROVADA E CONGELADA**.

### O que o congelamento significa

- Os princípios arquiteturais (Seção 4), o fluxo completo (Seção 5), a definição do Marco de Upload M0 (Seção 6), o produto como objeto do pós-venda e o vínculo obrigatório entre produto, registro de coleta e resposta (Seções 7 e 10), a validação e preservação de registros (Seção 8), a identidade técnica e o fluxo de correção append-only (Seção 9), a contagem definitiva (Seção 11), o congelamento do lote em M0+192h (Seção 12), o estado de espera (Seção 13), a identificação na interface (Seção 14), o Operador Interno (Seção 15), a confirmação humana em dois atos (Seção 16), a idempotência do processamento (Seção 17), o T0 da Coleta (Seção 18), os limites de tentativas (Seção 19), a classificação de falhas (Seção 20), os estados finais (Seção 21) e a verdade observável dos eventos do WhatsApp (Seção 22) estão aprovados e estáveis.
- A arquitetura conceitual desta ADR está congelada. Mudanças futuras a qualquer decisão aqui congelada só poderão ocorrer por evolução arquitetural formalmente documentada — no mesmo método já usado por esta e por todas as demais ADRs do projeto: preservação do texto histórico, registro explícito do que muda e do que não muda, e aprovação própria.
- As pendências técnicas registradas na Seção 24 não reabrem, não contradizem e não impedem este congelamento — são, por natureza, posteriores a ele: dizem respeito a como a arquitetura aqui aprovada será implementada, nunca ao que ela decide.
- Nenhuma implementação de código foi aprovada ou realizada por este documento. Esta ADR permanece, do início ao fim, uma decisão de arquitetura — nenhuma linha de código, schema de banco de dados, endpoint, componente visual ou configuração foi criada, modificada ou autorizada por ela.
- A ADR-004 (Portal Executivo do Cliente) e a ADR-006 (Jornada de Transformação Organizacional) permanecem intocadas por esta ADR — nenhuma de suas seções, decisões ou pendências foi alterada, referenciada como dependência ou reaberta.

**Origem desta decisão:**
- Consolidação aprovada da arquitetura do ciclo operacional de preparação e disparo da coleta (2026-08-27), após revisão e aprovação explícita das quatro partes desta proposta.
