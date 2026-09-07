# ROADMAP — Sprints B a G da Arquitetura Operacional (ADR-007 / ADR-008)

**Natureza deste documento:** não é uma ADR. É um plano de sequenciamento de implementação, formalizando no repositório o roadmap que, até esta data, existia apenas no histórico da conversa de planejamento. Não decide arquitetura — cada sprint aqui listada permanece subordinada às decisões já congeladas na ADR-007 e na ADR-008, e a qualquer nova ADR que uma sprint futura venha a exigir.

**Status deste documento:** DOCUMENTO VIVO — atualizado ao final de cada sprint concluída, no mesmo padrão já usado pelo `PROJECT_STATUS.md`.

**Data de criação:** 2026-09-07.

---

## Relação com a ADR-007 e a ADR-008

Este roadmap sequencia a implementação das pendências técnicas já nomeadas, seção por seção, pela ADR-007 (§24) e pela fundação de persistência definida pela **ADR-008 (APROVADA E CONGELADA)**. Nenhuma sprint aqui descrita redefine uma decisão já congelada em qualquer ADR — cada uma delas implementa, na ordem definida, o que as ADRs já autorizam ou o que uma ADR própria e futura autorizará quando chegar sua vez.

A ordem B → C → D → E → F → G não é arbitrária: cada sprint depende de dados ou mecanismos produzidos pela anterior (ver "Dependências" de cada uma). Nenhuma sprint pode ser antecipada dentro de outra sem nova rodada de decisão humana explícita — o mesmo princípio metodológico já seguido durante toda esta conversa de planejamento.

## Convenção usada por sprint

Cada sprint abaixo é descrita por oito campos fixos:

- **Objetivo** — o que a sprint entrega, em uma frase.
- **Dependências** — o que precisa estar concluído antes dela.
- **Entregas** — o que passa a existir ao final.
- **Exclusões** — o que fica explicitamente fora, mesmo que relacionado.
- **Critérios de aceite** — como se verifica que a sprint está de fato concluída.
- **Bloqueios que remove** — qual pendência nomeada pela ADR-007 ou pela ADR-008 deixa de bloquear a operação.
- **Bloqueios que permanecem** — o que continua impedido até uma sprint posterior.
- **Condição para uso operacional** — o que precisa ser verdade antes que essa entrega possa operar com dados reais de clientes.

---

## Sprint B — Persistência Imutável, Claims e Idempotência

**Objetivo:** implementar a fundação de persistência definitiva (PostgreSQL), o modelo de evento imutável e projeção corrente, o mecanismo de claim/heartbeat por `registro_coleta_id`, e a migração por corte controlado dos dados hoje mantidos em JSON — exatamente conforme a ADR-008.

**Dependências:** ADR-008 aprovada e congelada; disponibilidade de infraestrutura de banco PostgreSQL (pré-requisito operacional, fora do escopo de qualquer ADR).

**Entregas:** especificação técnica e schema relacional concreto; mecanismo de criação, renovação, expiração e revisão de claim; log de eventos imutável e projeção corrente para lotes, registros de coleta e correções; script de migração por corte controlado (pausa de escritas → backup → importação → validação → mudança de fonte de verdade); JSONs legados congelados, com manifesto e checksums; suíte de testes cobrindo criação de claim, concorrência real com threads, heartbeat, expiração determinística por relógio injetável, proibição de reatribuição automática, e idempotência persistente sobrevivendo a um "reinício de processo" simulado.

**Exclusões:** nenhuma integração nova com a Meta; nenhuma rota HTTP; nenhuma alteração a `services/whatsapp.py`, `services/webhook_handler.py` ou `app.py`.

**Critérios de aceite:** suíte de testes descrita nas Entregas passando integralmente; paridade campo a campo entre os `lote.json` existentes e o estado reconstruído via projeção corrente após a migração; nenhum teste desta sprint depende de Meta ou WhatsApp.

**Bloqueios que remove:** a limitação documentada literalmente em `adapters/storage.py::_obter_lock_lote` e citada nominalmente pela ADR-007 (§17, §24) — "não protege contra múltiplos processos/workers"; a ausência de qualquer persistência definitiva para o domínio operacional.

**Bloqueios que permanecem:** correlação persistente registro→envio→resposta→produto (Sprint E); autenticação/MFA/rotas do Operador Interno (Sprint D); envio efetivo pelo WhatsApp (Sprint C); mapeamento de erros da Meta (Sprint G).

**Condição para uso operacional:** a validação do passo 4 do corte controlado (ADR-008, Seção 16) precisa estar formalmente aprovada antes da mudança de fonte de verdade; nenhuma sprint subsequente pode iniciar uso operacional de claims antes dessa aprovação.

---

## Sprint C — Envio Efetivo, wamid e Webhook

**Objetivo:** implementar e testar, em ambiente controlado, a integração de envio pelo WhatsApp, a captura de `wamid` e o processamento de webhook — **sem habilitar envio real a clientes nesta sprint**.

**Dependências:** Sprint B concluída e validada; **aprovação arquitetural formal, própria e anterior à implementação**, do catálogo de eventos do domínio de envio (`solicitado`, `aceito_api`, `falha_api_observada`, `resultado_desconhecido`, e qualquer outro evento deste domínio). Este roadmap **não aprova esse catálogo sozinho** — esses eventos não pertencem ao catálogo fechado de claims da ADR-008 (Seção 11) e exigem decisão arquitetural própria antes de existir em código.

**Entregas:** `services/whatsapp.py` e `services/webhook_handler.py` reescritos e testados com **mocks, fixtures, sandbox da Meta ou ambiente controlado equivalente**; eventos imutáveis do domínio de envio, definidos pela decisão arquitetural própria mencionada acima, reaproveitando o modelo geral de evento imutável da ADR-008 (Seção 6); mecanismo técnico de envio implementado, porém **mantido desabilitado para disparo real a clientes**.

**Exclusões:** qualquer ativação de envio real a clientes nesta sprint; rotas/autenticação do Operador Interno (Sprint D); correlação determinística final (Sprint E); classificação oficial de falhas (Sprint G).

**Critérios de aceite:** suíte de testes cobrindo `wamid`, `statuses`, `context`, usando exclusivamente mocks/fixtures/sandbox — nenhum envio real ocorre durante os testes desta sprint; catálogo de eventos do domínio de envio formalmente aprovado antes da implementação; nenhuma inferência de leitura ou atenção humana a partir de eventos técnicos (ADR-007 §22).

**Bloqueios que remove:** ausência de captura de `wamid`; ausência de processamento correto de `statuses`/`context`.

**Bloqueios que permanecem — bloqueio operacional explícito:**
- nenhum claim, heartbeat ou evento técnico, desta ou de qualquer sprint, autoriza disparo;
- nenhuma mensagem real pode ser enviada antes da implementação da Sprint D e da confirmação humana obrigatória em dois atos (ADR-007 §16);
- a ativação para envio real depende, cumulativamente, também das condições de segurança das Sprints E, F e G.

**Condição para uso operacional:** a funcionalidade de envio implementada nesta sprint permanece **desabilitada para clientes reais** até que: (a) a Sprint D esteja implementada, com confirmação humana em dois atos funcional; (b) a Sprint E garanta a correlação determinística; (c) a Sprint F valide o comportamento real da Meta em teste controlado; e (d) a Sprint G forneça a classificação de falhas — nenhuma dessas condições pode ser dispensada isoladamente.

---

## Sprint D — Operador Interno, Autenticação, Rotas e Detecção do Congelamento M0+192h

**Objetivo:** implementar autenticação e MFA do Operador Interno (ADR-007 §15); as rotas HTTP para a confirmação humana em dois atos (ADR-007 §16); a exposição HTTP do relatório e da correção (lógica interna já implementada na Sprint A3, sem rota); **e o mecanismo técnico concreto de detecção automática do congelamento do lote em M0+192h (ADR-007 §12)**, hoje apenas conceitual.

**Dependências:** Sprint B (idempotência persistente; modelo geral de evento imutável, cujo uso para o registro do congelamento depende de aprovação própria — ver abaixo); **Sprint C (mecanismo técnico de envio já implementado, ainda desabilitado para clientes reais — a Sprint D consome esse mecanismo através da confirmação humana, nunca o reimplementa)**; ADR-001 §18 (Operador Interno, Timeline); ADR-007 §12, §15, §16; **aprovação arquitetural formal, própria e anterior à implementação, do nome, payload, identidade idempotente e regras do evento imutável de congelamento** — este roadmap não aprova esse evento sozinho; ele não pertence ao catálogo fechado de claims da ADR-008 (Seção 11) e não pode ser criado apenas por decisão de especificação técnica.

**Entregas:**
- `app.py` passa a expor rotas reais para confirmação de disparo, correção e relatório.
- Autenticação e MFA obrigatórios do Operador Interno.
- **Mecanismo de detecção automática de M0+192h**: worker, cron ou mecanismo técnico equivalente; execução idempotente (o mesmo lote nunca é congelado mais de uma vez, mesmo sob execução repetida ou concorrente); relógio injetável para testes determinísticos; **registro do congelamento como um evento imutável cujo nome, payload, identidade idempotente e regras são definidos por decisão arquitetural formal própria, anterior a esta implementação** — nunca inventados pela especificação técnica nem por este roadmap; esse evento registra um fato ocorrido uma única vez e **nunca é usado para alterar retroativamente qualquer evento anterior**; impossibilidade técnica de aceitar qualquer correção após o instante do congelamento.
- **Interface da Central de Operações** exibindo, no mínimo: identificação da empresa; identificação de negócio da Operação; **nunca o `lote_id` técnico** (ADR-007 §14; ADR-001 §7); a composição definitiva do lote, apresentada ao Operador **antes** de qualquer decisão; **o primeiro ato — abertura da confirmação de disparo, sem efeito decisório**; o segundo ato ("Confirmar e disparar") como decisão efetiva e irreversível, com registro de operador, data, hora e composição definitiva (ADR-007 §16). **Nenhum botão ou texto do primeiro ato pode sugerir que o disparo já foi autorizado.**

**Exclusões:** lógica de envio (já implementada, desabilitada, pela Sprint C); classificação de erro (Sprint G).

**Critérios de aceite:**
- dois atos de confirmação implementados exatamente como a ADR-007 §16 exige — **o primeiro ato apresentado exclusivamente como abertura da confirmação, sem qualquer linguagem de decisão efetiva; somente o segundo ato ("Confirmar e disparar") usa linguagem de decisão**;
- MFA obrigatório e testado;
- teste determinístico da fronteira exata M0+192h (relógio injetado) comprovando: o congelamento ocorre exatamente uma vez, mesmo sob execução repetida; nenhuma correção é aceita após o instante do congelamento; **o evento de congelamento — já formalmente aprovado por decisão arquitetural própria — é registrado de forma imutável e nunca altera retroativamente eventos anteriores**;
- **nenhuma tela, rota ou texto de interface sugere, no primeiro ato, que o disparo já foi autorizado**;
- nenhuma tela ou rota expõe `lote_id` técnico, em nenhum teste;
- composição definitiva do lote exibida ao Operador antes do primeiro e do segundo ato.

**Bloqueios que remove:** ausência de rota HTTP para o ciclo (`app.py` intocado desde a Sprint A1); ausência de autenticação do Operador Interno; ausência do mecanismo técnico concreto de detecção do congelamento — pendência nomeada literalmente na ADR-007 §24 ("Mecanismo técnico concreto de detecção do instante de congelamento").

**Bloqueios que permanecem:** uso operacional pleno do envio (já implementado tecnicamente pela Sprint C) continua desabilitado até que as Sprints E, F e G completem as demais condições cumulativas descritas em "Encerramento da Sprint G".

**Condição para uso operacional:** MFA funcional e testado; mecanismo de M0+192h validado por teste de fronteira determinístico antes de qualquer congelamento real de lote em produção.

---

## Sprint E — Correlação Determinística e Motor NSI

**Objetivo:** implementar a cadeia técnica obrigatória `registro_coleta_id → envio → resposta → produto` (ADR-007 §10), substituindo `buscar_lote_por_telefone` por vínculo determinístico; implementar quarentena para resposta sem vínculo; garantir que nenhuma resposta ambígua entre no Motor NSI.

**Dependências:** Sprint C (wamid e eventos de envio capturados); Sprint B (persistência definitiva onde a correlação é gravada).

**Entregas:** mecanismo de correlação determinística entre envio e resposta; fila/registro de quarentena para respostas sem vínculo íntegro; correção de `integration/nsi_integration.py` para consumir apenas respostas corretamente vinculadas.

**Exclusões:** qualquer alteração ao Motor NSI em si (`processors/`, `models/`, `confidence/`, `outputs/`) — já excluída pela própria ADR-007 (§2.2).

**Critérios de aceite:** nenhuma resposta entra no Motor sem vínculo técnico íntegro (ADR-007 §10.1); teste reproduzindo o cenário "mesmo telefone, múltiplos registros de coleta" comprovando o vínculo correto a cada produto.

**Bloqueios que remove:** a não conformidade citada literalmente na ADR-007 (§10.3, §24) — `buscar_lote_por_telefone` e `salvar_resposta_cliente` hoje casam por telefone isoladamente.

**Bloqueios que permanecem:** classificação de falha ainda "não classificada" até a Sprint G — o que não bloqueia a correlação em si, apenas a decisão de nova tentativa.

**Condição para uso operacional:** esta é a pendência que a própria ADR-007 (§24) já identifica como bloqueante ao uso operacional pleno da arquitetura para qualquer Operação em que um mesmo telefone possua mais de um registro de coleta — nenhuma resposta pode ser processada pelo Motor nesse cenário até esta sprint estar concluída e validada.

---

## Sprint F — Teste Controlado da Meta

**Objetivo:** validar, em ambiente controlado e **sob autorização humana explícita**, o comportamento real da integração com a Meta, com captura temporária do payload íntegro, criptografado, exclusivamente para diagnóstico.

**Dependências:** Sprint C (integração implementada e testada com mocks/sandbox); **Sprint D (autenticação e MFA funcionais; confirmação humana em dois atos operacional; registro do operador; composição definitiva apresentada antes da decisão) — nenhum teste real controlado com mensagem para cliente pode contornar essas exigências, mesmo sendo um teste isolado: a autorização humana em dois atos, já congelada pela ADR-007 §16, aplica-se integralmente a qualquer disparo real, inclusive o desta sprint**; Sprint E (correlação determinística, para validar o teste ponta a ponta com dados reais).

**Entregas:** mecanismo de captura temporária do payload da Meta, com criptografia e controle de acesso; teste real **isolado, limitado e auditável**, executado somente mediante autorização humana explícita e prévia; eliminação auditada do payload ao final do prazo de retenção.

**Exclusões:** qualquer uso do payload capturado como fonte de verdade permanente; **qualquer liberação geral para produção** — esta sprint não representa liberação geral para produção, apenas um teste controlado e isolado.

**Critérios de aceite:**
- nenhum teste com dados reais da Meta ocorre sem autorização humana explícita e registrada previamente;
- payload capturado com criptografia e controle de acesso comprovados;
- **prazo de retenção definido por decisão técnica, jurídica e de privacidade própria** — não definido nem estimado por esta sprint;
- eliminação do payload comprovadamente auditada (evento registrado) ao final desse prazo.

**Bloqueios que remove:** ausência de visibilidade sobre o comportamento real da Meta antes de qualquer teste com dados reais.

**Bloqueios que permanecem:** classificação oficial de erros (Sprint G) — este teste é insumo direto para ela; liberação geral para produção permanece bloqueada até a conclusão cumulativa das condições descritas em "Encerramento da Sprint G".

**Condição para uso operacional:** autorização humana explícita e prévia para cada teste real, **obtida através do mesmo mecanismo de confirmação em dois atos da Sprint D — nunca por um caminho alternativo ou simplificado, ainda que o teste seja isolado**; MFA e registro do operador responsável comprovados para o teste; composição definitiva (mesmo que reduzida a poucos destinatários de teste) apresentada antes da decisão; prazo de retenção definido pela decisão técnica/jurídica/de privacidade própria antes de qualquer captura; eliminação auditada comprovada antes de considerar a sprint concluída.

---

## Sprint G — Classificação Oficial de Falhas

**Objetivo:** mapear oficialmente os códigos de erro da WhatsApp Cloud API, documentados pela Meta, às três categorias já congeladas pela ADR-007 (§20), e consolidar as regras finais de tentativas e intervalos dentro dos limites já fixados pela ADR-007 (§19).

**Dependências:** Sprint F (evidência real observada em ambiente controlado); ADR-007 §19/§20 (limites e categorias já congelados, não redefinidos por esta sprint); **documentação oficial e vigente da Meta, consultada no momento da implementação**.

**Entregas:** tabela de mapeamento código de erro → categoria, com base na documentação oficial e vigente da Meta no momento da implementação; lógica de reclassificação registrada e auditável.

**Exclusões:** qualquer alteração aos limites de negócio já congelados pela ADR-007.

**Critérios de aceite:**
- todo código de erro **conhecido e documentado oficialmente pela Meta**, no momento da implementação, possui mapeamento para uma das três categorias;
- todo código **desconhecido ou sem evidência suficiente** para classificação segura permanece na categoria `não_classificada`;
- toda falha `não_classificada` bloqueia qualquer nova tentativa até classificação formal, exatamente como a ADR-007 §20 exige;
- a documentação oficial e vigente da Meta é a referência consultada no momento da implementação — não uma lista fixada nesta sprint como definitiva para sempre; evolução futura da documentação da Meta pode exigir reclassificação, registrada como tal.

**Bloqueios que remove:** a pendência nomeada literalmente na ADR-007 (§2.2, §20) — "o mapeamento concreto (...) fica para especificação técnica futura".

**Bloqueios que permanecem:** a conclusão da Sprint G **não ativa automaticamente a operação**. A ativação operacional plena depende cumulativamente de:
- validação integrada das Sprints B a G;
- testes ponta a ponta;
- confirmação da correlação `registro_coleta_id` → envio → resposta → produto (Sprint E);
- autenticação e MFA funcionais (Sprint D);
- confirmação humana em dois atos funcional (Sprint D; ADR-007 §16);
- validação do comportamento real da Meta (Sprint F);
- revisão das pendências remanescentes;
- **autorização humana explícita para ativação**.

**Condição para uso operacional:** nenhuma condição isolada desta sprint basta — a ativação depende exclusivamente da lista cumulativa acima.

---

## Changelog de Status

| Sprint | Status |
|---|---|
| A1 — Identidade por linha e schema estrutural do CSV | CONCLUÍDA |
| A2 — Validação de conteúdo e normalização de WhatsApp | CONCLUÍDA |
| A3 — Correção append-only de registros inválidos | CONCLUÍDA |
| B — Persistência imutável, claims e idempotência | EM PLANEJAMENTO |
| C — Envio efetivo, wamid e webhook | NÃO INICIADA |
| D — Operador Interno, autenticação, rotas e detecção do congelamento M0+192h | NÃO INICIADA |
| E — Correlação determinística e Motor NSI | NÃO INICIADA |
| F — Teste controlado da Meta | NÃO INICIADA |
| G — Classificação oficial de falhas | NÃO INICIADA |

## Nota de fronteira

Nenhuma sprint listada acima pode ser antecipada dentro de outra sem nova rodada de decisão humana explícita, registrada como evolução deste documento ou como nova ADR, conforme o caso — o mesmo princípio metodológico seguido por toda a arquitetura do projeto: arquitetura primeiro, implementação depois, congelamento somente após aprovação explícita.

A capacidade técnica de envio implementada na Sprint C permanece desabilitada para clientes reais até que as condições cumulativas de ativação — descritas no encerramento da Sprint G — estejam integralmente satisfeitas e explicitamente autorizadas por decisão humana. Nenhuma sprint, isoladamente, ativa a operação real. Mesmo um teste real isolado (Sprint F) exige o mecanismo integral de confirmação humana em dois atos da Sprint D — nenhuma exceção de "teste" contorna essa exigência da ADR-007 §16.
