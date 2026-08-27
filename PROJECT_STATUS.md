# PROJECT_STATUS.md

## NSI — Núcleo de Inteligência Semântica

---

## Versão atual

`v1.1.0-fonte-unica-webhook-motor`

---

## Status Geral

🟢 Núcleo do Motor: Concluído
🟢 Integration Layer: Concluída
🟢 Webhook Meta: Protegido por HMAC
🟢 Groq: Validada em produção
🟢 Git: Organizado
🟢 Segurança essencial: Concluída
🟢 Fonte única de verdade (Webhook → `lote.json` → Motor): Concluída
🟢 ADR-001 — NSI Operations Console: Aprovada e congelada na arquitetura — evolução aprovada em 2026-08-25 (identidade técnica da Empresa e da Operação: empresa_id e operacao_id, com lote_id e slug como referências legadas) — evolução adicional em 2026-08-26 (formato UUID4 de empresa_id e operacao_id) — evolução adicional em 2026-08-27 (Operador Interno, novos eventos de Timeline do ciclo de preparação e disparo, e reafirmação da exposição da Operação em vez do lote_id, referenciando a ADR-007)
🟢 ADR-002 — Fundação de Marca NSI: Aprovada e congelada na arquitetura
🟢 Branding Sprint 1 — Fundação da Marca (`docs/branding/`): CONGELADA
🟢 ADR-003 — Sistema Editorial Visual do NSI: Aprovada (abertura da Sprint 2)
🟢 Branding Sprint 2 — Sistema Editorial Visual: CONGELADA — arquitetura editorial encerrada
🟢 Branding Sprint 3 — Prototipação Visual: EM PRODUÇÃO — DT-001 v1 produzido e registrado (`docs/branding/documentos-visuais/DT-001.html`)
🟢 Livro dos Princípios do NSI (v1.0): Aprovado e congelado — fundação intelectual permanente do projeto
🟢 ADR-005 — Ciclo Temporal de Coleta e Leituras Independentes: Aprovada e congelada — evolução aprovada em 2026-08-23 (convite de coleta com resposta única, gatilhos de encerramento, ordem atômica em T0+120h e dois estados distintos sem relatório) — evolução adicional em 2026-08-25 (identidade técnica da Leitura: chave composta operacao_id+tipo) — evolução adicional em 2026-08-27 (distinção formal entre M0 e T0 da Coleta, referenciando a ADR-007)
🟢 ADR-006 — Jornada de Transformação Organizacional (Tela 03): APROVADA E CONGELADA — evolução aprovada em 2026-08-26 (identidade técnica em UUID4, PostgreSQL como armazenamento definitivo dos registros da Trajetória, política de idempotência, governança de autoria e correção referenciando a ADR-004, detalhamento do acesso à Tela 03, encerramento da relação e Pacote de Preservação Histórica); schema relacional concreto, componentes visuais e Política Jurídica futura permanecem como pendências técnicas e jurídicas não bloqueantes (ADR-006, Seção 14)
🟢 ADR-007 — Ciclo Operacional de Preparação e Disparo da Coleta: APROVADA E CONGELADA — arquitetura completa do ciclo entre o upload do CSV (M0) e a confirmação humana do primeiro disparo (T0 da Coleta); evolução correspondente registrada em ADR-001 (Seção 18) e ADR-005 (Seção 17)

---

## Componentes concluídos

- Pipeline NSI (10 fases, congelado)
- Processors (Matemática, Linguística, Semântica, Experiência Humana, Evolução Temporal, Executiva)
- Catálogo NSI v1.1 (91 entradas)
- Confidence Rules
- ICE NSI v1
- Output Builder
- Integration Layer (`integration/nsi_integration.py`)
- Dispatcher integrado ao Motor (`core/dispatcher.py`)
- Persistência de `saida_motor.json` por lote
- Validação HMAC-SHA256 do webhook da Meta
- `DEBUG=false` em produção
- `.gitignore` validado (segredos e dados sensíveis nunca versionados)
- `lote.json` consolidado como única fonte oficial de verdade do sistema (eliminada a duplicidade com `data/empresas/<slug>/respostas/`, que passou a existir exclusivamente como log bruto de auditoria)
- Escrita segura e atômica de `lote.json` (`adapters.storage.salvar_lote_atomico`: arquivo temporário + `os.replace`, serializada por `lote_id`), reutilizada por todo escritor de atualização (`salvar_resposta_cliente`, `disparar_lote`, `atualizar_status_pipeline`, `atualizar_status_lote`)
- Correção do bug crítico "`status_entrega` sempre `None` em produção": `integration/nsi_integration.py` agora promove um cliente a `"respondido"` somente quando o conjunto completo de fatos observados existir (`status_entrega`, `data_resposta`, `data_envio_mensagem`) — sem fallback, sem data aproximada, sem inferência
- Suíte de testes: **121/121 aprovados**

---

## Pendências

### Branding — Sprint 3 — Prototipação Visual (em produção)
Arquitetura editorial encerrada (Sprint 2). Produção iniciada: `DT-001` v1 já construído e registrado em `docs/branding/documentos-visuais/DT-001.html`, aplicando integralmente `16-DT001-direcao-de-arte.md` e `17-DT001-prompt-master.md`. Nenhum documento arquitetural novo é criado nesta fase — evolução guiada pela prática dos documentos reais. Próximo passo: refinamento de DT-001 e/ou início de DT-002, aguardando instrução.

### Sprint 2
- Dashboard Executivo (`/empresa/<slug>`)
- Interface Operacional
- PDF Executivo

### Sprint 3
- Webhook operacional completo: consumir eventos de status de entrega da Meta (`statuses` do payload, hoje não lidos) para popular `visualizado_sem_resposta` / `entregue_sem_visualizacao` / `nao_entregue`
- Cálculo completo do ICE em produção (com cobertura semântica real)
- `adapters.storage.salvar_lote` (criação inicial do lote no upload) ainda escreve `lote.json` diretamente, fora de `salvar_lote_atomico` — aceito por ora, pois trata exclusivamente da criação (arquivo ainda não existe no momento da escrita, sem risco de concorrência); candidato a unificação em Sprint futura

### ADR-007 — Ciclo Operacional de Preparação e Disparo da Coleta (aprovada e congelada)
Arquitetura completa aprovada e congelada para o ciclo entre o upload do CSV (M0) e a confirmação humana do primeiro disparo (T0 da Coleta). Pendências técnicas registradas na própria ADR-007 (Seção 24), não bloqueantes ao congelamento conceitual: mecanismo concreto de detecção do congelamento em M0+192h; chave de idempotência persistente entre processos/workers para o disparo; mapeamento dos códigos de erro da WhatsApp Cloud API às categorias de falha; autenticação e MFA do Operador Interno; schema de dados, endpoints e interface visual da Central de Operações. Uma pendência técnica é bloqueante para o uso operacional conforme a ADR-007: a correlação persistente entre registro de coleta, envio, resposta e produto — hoje `adapters.storage.buscar_lote_por_telefone` e `salvar_resposta_cliente` casam a resposta apenas por telefone, o que não é conforme à ADR-007 sempre que um mesmo telefone possuir mais de um registro de coleta; enquanto essa correlação não existir, nenhuma resposta ambígua pode entrar no Motor NSI como corretamente vinculada a um produto.

---

## Sprints concluídas

### Livro dos Princípios do NSI — Fundação Intelectual (2026-07-03)
Adicionado o documento fundacional do NSI (`docs/principios/livro-dos-principios.md`), contendo História, Filosofia, Missão, Visão, Valores, Princípios Fundamentais e Vocabulário Oficial. Este documento estabelece a base intelectual permanente do projeto e servirá como referência para toda a produção editorial, institucional e técnica futura.

Não é um documento de arquitetura, de marca ou de produto — é anterior a todos eles. Registra a observação humana que originou o NSI antes de qualquer tecnologia (IA, análise semântica, WhatsApp), e por isso vive fora de `docs/architecture/` e `docs/branding/`, em `docs/principios/`.

**Estado: CONGELADO.** Versão 1.0, aprovada em 03/07/2026. Autor: Kassein Mohamad. Curadoria editorial: ChatGPT + Claude. Commit: `c27735b`.

### Branding Sprint 2 — Sistema Editorial Visual, etapa documental (2026-07-03)
Aberta pela ADR-003. Produzidos, nesta ordem: Arquitetura Visual (`09-sistema-editorial-visual.md`), Componentes (`10-componentes-visuais.md`, antecipado por exceção deliberada), Grid e Zona de Segurança (`11-grid-e-zona-de-seguranca.md`, aprovado provisoriamente), Sistema Modular de Composição (`12-sistema-modular-de-composicao.md` — decisão de que o NSI usa composição modular, não templates, registrada sob a governança da ADR-003, sem ADR própria), Tipografia Oficial (`13-tipografia-oficial.md`), Paletas Oficiais (`14-paletas-oficiais.md`) e Biblioteca de Composição (`15-biblioteca-de-composicao.md`, Bloco 06 renomeado de "Biblioteca Oficial de Layouts"). Nenhuma fonte, cor, layout ou prompt concreto foi definido — apenas a arquitetura que cada um vai obedecer. Prompt Master (Bloco 07) e Biblioteca Oficial de Conteúdo (Bloco 08) ficaram fora deste escopo documental.

**Estado: CONCLUÍDA.** Tag: `v1.1.0-branding-sistema-editorial-visual`. Próxima fase: **Sprint 3 — Prototipação Visual**, começando por `DT-001`, o primeiro Documento Visual Oficial do NSI. Evolução arquitetural a partir daqui é guiada pela prática, não por documentação adicional.

### Branding Sprint 1 — Fundação documental da marca (2026-07-03)
Construída e **congelada** a documentação fundacional da marca NSI (o "Livro da Marca"), seguindo a mesma metodologia da arquitetura técnica: arquitetura primeiro, implementação depois, congelamento somente após aprovação. Nenhum layout, imagem ou post foi produzido nesta sprint, por decisão explícita (ADR-002).

Entregue em `docs/branding/`: filosofia, manifesto, propósito, posicionamento, missão/visão/valores, diferenciais, tom de voz e princípios editoriais — todos derivados dos princípios já congelados do Motor (Contrato Seção 0) e da governança da ADR-001, não de uma narrativa de marketing independente. Inclui dois princípios editoriais nomeados (Singularidade e Memorização) e a convenção de sequência `DT-001`, `DT-002`...

A ADR-002 passou por revisão arquitetural formal (`Em Revisão` → `Aprovado`) antes do congelamento, incorporando: Sistema Editorial em três camadas (Fundamentos da Marca, Design System, Sistema de Publicações), separação permanente entre Tipo de Documento e Tema, nomenclatura oficial e fechada dos Tipos de Documento (`DT`, `ART`, `REL`, `MAN`, `EST`, `GUI`, `INS`), e os princípios de Consistência de Longo Prazo, Identidade Única e Unicidade de Sigla Institucional. Durante a revisão, o código `SEM` foi identificado como ambíguo (confundia Tipo com Tema) e eliminado definitivamente da nomenclatura — "Semântica" existe hoje exclusivamente como Tema Editorial. Decisão estrutural registrada em [`docs/architecture/ADR-002-brand-foundation.md`](docs/architecture/ADR-002-brand-foundation.md).

**Estado: CONGELADA.** Registro oficial de encerramento: [`docs/branding/SPRINT_01_FREEZE.md`](docs/branding/SPRINT_01_FREEZE.md).

### Sprint — Fonte única de verdade Webhook → Motor NSI (2026-07-02)
Eliminada a duplicidade entre `lote.json` e `data/empresas/<slug>/respostas/` como fontes de dado para o Motor. Implementada em 3 blocos incrementais + 1 revisão arquitetural final, cada um validado isoladamente antes do próximo:

- **Bloco 1**: `adapters/storage.py::salvar_resposta_cliente` passa a gravar `resposta`/`data_resposta`/`status_entrega="respondido"` diretamente no registro do cliente em `lote.json` (fonte oficial), mantendo `data/empresas/<slug>/respostas/` apenas como log bruto de auditoria. Introduzida `salvar_lote_atomico` (escrita atômica + lock por `lote_id`).
- **Bloco 2**: `core/scheduler.py::disparar_lote` passa a gravar `data_envio_mensagem` por cliente, reutilizando `salvar_lote_atomico`.
- **Bloco 3**: `integration/nsi_integration.py::_montar_resposta_cliente` lê os fatos reais em vez de hardcode `None`, promovendo um cliente a `"respondido"` apenas quando `status_entrega` + `data_resposta` + `data_envio_mensagem` estiverem todos presentes (regra documentada no próprio código).
- **Revisão arquitetural final**: `atualizar_status_pipeline`/`atualizar_status_lote` (`core/scheduler.py`) passaram a reutilizar `salvar_lote_atomico`, unificando o mecanismo oficial de escrita de `lote.json`.

Nenhum arquivo de `engine/`, `processors/`, `models/`, `confidence/` ou `outputs/` foi alterado em nenhuma etapa. Suíte de testes: 108 → 121 aprovados (13 novos testes, cobrindo os três blocos e o cenário de risco identificado antes da implementação).

---

## Decisões Arquiteturais (ADRs)

### ADR-001 — NSI Operations Console (2026-07-02)
**Status: Aprovada e congelada.**

Formaliza a arquitetura das três plataformas do ecossistema NSI — Operations Console (uso interno, torre de controle operacional), Portal Executivo do Cliente (produto comercial) e Motor NSI (invisível, sem alteração) — e estabelece a Operação como unidade principal de exposição da plataforma, substituindo o Lote nesse papel (que permanece como componente técnico interno). Define os princípios de registro permanente de eventos, Timeline completa por Operação, não interferência do Console sobre o Motor, aceite eletrônico obrigatório antes de qualquer processamento e segregação de dados sensíveis (NPS, comentários, diagnósticos e respostas individuais ficam restritos ao Portal do Cliente).

Documento completo: [`docs/architecture/ADR-001-operations-console.md`](docs/architecture/ADR-001-operations-console.md). Decisão exclusivamente documental — nenhum código, API ou lógica do Motor foi alterado.

### ADR-002 — Fundação de Marca NSI (2026-07-03)
**Status: Aprovada e congelada**, após revisão arquitetural linha por linha (`Em Revisão` → `Aprovado`).

Formaliza o módulo de branding do NSI, aplicando a mesma metodologia da arquitetura técnica (arquitetura primeiro, implementação depois, congelamento somente após aprovação). Define `docs/branding/` como fonte única de verdade da marca, estabelece que a filosofia de marca deriva dos princípios já congelados do Motor (Contrato Seção 0), e determina que nenhuma peça de comunicação, layout ou identidade visual seja produzida antes desta fundação documental. O branding é tratado como ativo arquitetural do projeto, com o objetivo de construir um Sistema Editorial Proprietário — não apenas uma identidade visual — em três camadas (Fundamentos da Marca, Design System, Sistema de Publicações), com 8 princípios arquiteturais congelados, incluindo Consistência de Longo Prazo, Identidade Única e Unicidade de Sigla Institucional (nenhuma sigla pode representar mais de um significado — regra que motivou a eliminação do código `SEM`).

Documento completo: [`docs/architecture/ADR-002-brand-foundation.md`](docs/architecture/ADR-002-brand-foundation.md). Decisão exclusivamente documental — nenhum ativo visual, código ou peça de comunicação foi produzido.

### ADR-003 — Sistema Editorial Visual do NSI (2026-07-03)
**Status: Aprovada** (aprovação de abertura de sprint, sem revisão linha a linha, por decisão explícita de quem aprova).

Formaliza a abertura da Branding Sprint 2, aplicando a mesma metodologia das sprints anteriores: arquitetura primeiro, implementação depois. Estabelece que o Sistema Editorial Visual deriva integralmente da Fundação da Marca (ADR-002) e não pode contrariar nenhuma decisão nela já congelada; que todo componente visual deriva de um princípio filosófico aprovado; e divide a sprint em 8 blocos independentes e sequenciais. Acrescenta dois princípios: a forma nunca compete com a mensagem, e a identidade visual deve sobreviver ao tempo. Registra explicitamente que a Sprint 2 produzirá um Sistema Editorial Visual Proprietário, não apenas layouts.

Documento completo: [`docs/architecture/ADR-003-sistema-editorial-visual.md`](docs/architecture/ADR-003-sistema-editorial-visual.md). Decisão exclusivamente documental — nenhuma cor, tipografia, grid, componente ou prompt foi definido nesta ADR.

---

## Commits importantes