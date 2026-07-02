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
🟢 ADR-001 — NSI Operations Console: Aprovada e congelada na arquitetura

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

### Sprint 2
- Dashboard Executivo (`/empresa/<slug>`)
- Interface Operacional
- PDF Executivo

### Sprint 3
- Webhook operacional completo: consumir eventos de status de entrega da Meta (`statuses` do payload, hoje não lidos) para popular `visualizado_sem_resposta` / `entregue_sem_visualizacao` / `nao_entregue`
- Cálculo completo do ICE em produção (com cobertura semântica real)
- `adapters.storage.salvar_lote` (criação inicial do lote no upload) ainda escreve `lote.json` diretamente, fora de `salvar_lote_atomico` — aceito por ora, pois trata exclusivamente da criação (arquivo ainda não existe no momento da escrita, sem risco de concorrência); candidato a unificação em Sprint futura

---

## Sprints concluídas

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

---

## Commits importantes