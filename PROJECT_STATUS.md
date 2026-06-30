# PROJECT_STATUS.md

## NSI — Núcleo de Inteligência Semântica

---

## Versão atual

`v1.0.1-security`

---

## Status Geral

🟢 Núcleo do Motor: Concluído
🟢 Integration Layer: Concluída
🟢 Webhook Meta: Protegido por HMAC
🟢 Groq: Validada em produção
🟢 Git: Organizado
🟢 Segurança essencial: Concluída

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
- Suíte de testes: **108/108 aprovados**

---

## Pendências

### Sprint 2
- Dashboard Executivo (`/empresa/<slug>`)
- Interface Operacional
- PDF Executivo

### Sprint 3
- Webhook operacional completo (status reais de entrega via Meta)
- `status_entrega` e `data_envio_mensagem` reais por cliente
- Cálculo completo do ICE em produção (com cobertura semântica real)

---

## Commits importantes