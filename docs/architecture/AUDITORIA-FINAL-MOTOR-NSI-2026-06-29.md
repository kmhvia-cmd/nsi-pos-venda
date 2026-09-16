# Relatório de Auditoria Final — Motor NSI

> **Status documental:** histórico. Este relatório registra o estado do Motor NSI em 29/06/2026, antes da camada de persistência operacional e das ADR-007/ADR-008. Os números, arquivos e testes descritos representam aquela fotografia histórica e não o estado atual do sistema.

## Dados coletados por execução real (não estimados)

**Data:** 29/06/2026
**Motor:** NSI Engine — implementação das Fases 0–13 do Plano de Implementação v1.0
**Contrato base:** `contrato_motor_nsi.md` v3.1.1

---

## 1. Árvore Completa do Projeto

```
nsi_engine/                                    (raiz do pacote)
├── __init__.py
│
├── engine/                                    # Orquestração do pipeline
│   ├── __init__.py
│   ├── config.py                              # Parâmetros calibráveis
│   ├── context.py                             # Objeto de contexto compartilhado
│   └── pipeline.py                            # Orquestrador principal (ponto de entrada)
│
├── processors/                                # Uma camada por arquivo
│   ├── __init__.py
│   ├── math_processor.py                      # Camada Matemática
│   ├── linguistic_processor.py                # Camada Linguística
│   ├── semantic_processor.py                  # Camada Semântica
│   ├── experience_processor.py                # Camada de Experiência Humana
│   ├── evolution_processor.py                 # Camada de Evolução Temporal
│   └── executive_processor.py                 # Camada Executiva
│
├── catalog/                                   # Catálogo NSI v1.1
│   ├── __init__.py
│   ├── catalogo_v1.1.json                     # 91 entradas (gerado por build_catalog_json.py)
│   ├── build_catalog_json.py                  # Script de build Markdown→JSON
│   ├── loader.py                              # Carregamento em memória
│   ├── matcher.py                             # Casamento textual determinístico
│   └── versioning.py                          # Controle de versao_catalogo
│
├── models/                                    # Dataclasses (tipos, sem lógica)
│   ├── __init__.py
│   ├── input_models.py                        # RespostaCliente, Lote
│   ├── catalog_models.py                      # EntradaCatalogo, AreaResponsavel
│   └── output_models.py                       # ~19 dataclasses — Contrato Seção 8
│
├── services/                                  # Integrações externas
│   ├── __init__.py
│   ├── ai_classifier.py                       # ClienteIA (ABC), ClienteGroq, ClienteIAFalso
│   └── fallback_handler.py                    # Lógica de fallback sem IA
│
├── confidence/                                # Regras de confiança (transversal)
│   ├── __init__.py
│   └── confidence_rules.py                    # Limite de 5 categorias, desempate 4 níveis
│
├── outputs/                                   # Montagem da saída final
│   ├── __init__.py
│   └── output_builder.py                      # Monta e valida SaidaMotorCompleta
│
├── logs/                                      # Instrumentação
│   ├── __init__.py
│   ├── engine_logger.py                       # Logs de execução do pipeline
│   ├── classification_logger.py               # Logs de classificação via IA
│   └── audit_logger.py                        # Logs de auditoria de longo prazo
│
└── tests/
    ├── __init__.py
    ├── unit/                                  # Testes unitários por módulo
    │   ├── test_math_processor.py
    │   ├── test_linguistic_processor.py
    │   ├── test_catalog.py
    │   ├── test_ai_classifier_e_fallback.py
    │   ├── test_confidence_rules.py
    │   ├── test_evolution_processor.py
    │   ├── test_output_builder.py
    │   └── test_logs.py
    ├── semantic/                              # Testes das camadas com IA
    │   ├── test_semantic_processor.py
    │   ├── test_experience_processor.py
    │   └── test_executive_processor.py
    ├── integration/                           # Testes de pipeline end-to-end
    │   └── test_pipeline.py
    └── regression/                            # Casos congelados de regressão
        └── test_regression_final.py
```

**Total de arquivos Python:** 47 (incluindo `__init__.py`)
**Arquivos com lógica:** 34 (excluindo `__init__.py`)

---

## 2. Linhas de Código por Arquivo

### Código de produção (3.577 linhas)

| Arquivo | Linhas | Fase |
|---|---|---|
| `processors/executive_processor.py` | 508 | 9 |
| `models/output_models.py` | 350 | 0 (+aditivo v3.1.1) |
| `engine/pipeline.py` | 267 | 11 |
| `processors/semantic_processor.py` | 265 | 5 |
| `processors/linguistic_processor.py` | 264 | 2 + 7 |
| `services/ai_classifier.py` | 230 | 4 |
| `processors/math_processor.py` | 213 | 1 |
| `processors/experience_processor.py` | 203 | 7 |
| `outputs/output_builder.py` | 189 | 10 |
| `processors/evolution_processor.py` | 188 | 8 |
| `catalog/build_catalog_json.py` | 140 | 3 |
| `catalog/matcher.py` | 106 | 3 |
| `confidence/confidence_rules.py` | 92 | 6 |
| `catalog/loader.py` | 80 | 3 |
| `services/fallback_handler.py` | 73 | 4 |
| `logs/engine_logger.py` | 73 | 12 |
| `engine/context.py` | 73 | 11 |
| `models/input_models.py` | 54 | 0 |
| `models/catalog_models.py` | 54 | 0 |
| `logs/audit_logger.py` | 52 | 12 |
| `logs/classification_logger.py` | 52 | 12 |
| `catalog/versioning.py` | 28 | 3 |
| `engine/config.py` | 23 | 8 (refatoração) |

### Testes (2.813 linhas)

| Arquivo | Linhas | Fase | Testes |
|---|---|---|---|
| `tests/semantic/test_executive_processor.py` | 351 | 9 | 16 |
| `tests/semantic/test_semantic_processor.py` | 296 | 5 | 10 |
| `tests/regression/test_regression_final.py` | 266 | 13 | 6 |
| `tests/unit/test_evolution_processor.py` | 245 | 8 | 8 |
| `tests/unit/test_output_builder.py` | 233 | 10 | 6 |
| `tests/unit/test_ai_classifier_e_fallback.py` | 210 | 4 | 11 |
| `tests/semantic/test_experience_processor.py` | 209 | 7 | 10 |
| `tests/unit/test_confidence_rules.py` | 183 | 6 | 9 |
| `tests/integration/test_pipeline.py` | 181 | 11 | 4 |
| `tests/unit/test_math_processor.py` | 182 | 1 | 6 |
| `tests/unit/test_logs.py` | 175 | 12 | 6 |
| `tests/unit/test_catalog.py` | 146 | 3 | 6 |
| `tests/unit/test_linguistic_processor.py` | 136 | 2 | 10 |

**Total geral:** 6.390 linhas (produção + testes, excluindo `__init__.py` e `catalogo_v1.1.json`)

---

## 3. Fase Geradora de Cada Arquivo

| Fase | Arquivos criados |
|---|---|
| **0 — Esqueleto e Modelos** | Estrutura de pastas, `models/input_models.py`, `models/catalog_models.py`, `models/output_models.py` |
| **1 — Matemática** | `processors/math_processor.py`, `tests/unit/test_math_processor.py` |
| **2 — Linguística determinística** | `processors/linguistic_processor.py` (parcial), `tests/unit/test_linguistic_processor.py` |
| **3 — Catálogo** | `catalog/loader.py`, `catalog/matcher.py`, `catalog/versioning.py`, `catalog/build_catalog_json.py`, `catalog/catalogo_v1.1.json`, `tests/unit/test_catalog.py` |
| **4 — IA e Fallback** | `services/ai_classifier.py`, `services/fallback_handler.py`, `tests/unit/test_ai_classifier_e_fallback.py` |
| **5 — Semântica** | `processors/semantic_processor.py`, `tests/semantic/test_semantic_processor.py` |
| **6 — Regras de Confiança** | `confidence/confidence_rules.py`, `tests/unit/test_confidence_rules.py` |
| **7 — Experiência Humana** | `processors/experience_processor.py` (+ conclusão de `linguistic_processor.py`), `tests/semantic/test_experience_processor.py` |
| **8 — Evolução Temporal** | `processors/evolution_processor.py`, `tests/unit/test_evolution_processor.py`; `engine/config.py` criado como refatoração do limiar de estabilidade |
| **9 — Executiva** | `processors/executive_processor.py`, `tests/semantic/test_executive_processor.py` |
| **10 — Output Builder** | `outputs/output_builder.py`, `tests/unit/test_output_builder.py` |
| **11 — Pipeline** | `engine/pipeline.py`, `engine/context.py`, `tests/integration/test_pipeline.py` |
| **12 — Logs** | `logs/engine_logger.py`, `logs/classification_logger.py`, `logs/audit_logger.py`, `tests/unit/test_logs.py` |
| **13 — Regressão** | `tests/regression/test_regression_final.py` |

---

## 4. Dependências entre Módulos

```
engine/pipeline.py          ← PONTO DE ENTRADA
    ├── models/input_models.py
    ├── models/output_models.py
    ├── catalog/loader.py
    │       └── models/catalog_models.py
    ├── engine/context.py
    │       └── models/output_models.py
    ├── outputs/output_builder.py
    │       └── models/output_models.py
    ├── processors/math_processor.py
    │       ├── models/input_models.py
    │       └── models/output_models.py
    ├── processors/linguistic_processor.py
    │       └── models/output_models.py
    ├── processors/semantic_processor.py
    │       ├── catalog/loader.py
    │       ├── catalog/matcher.py
    │       │       └── catalog/loader.py
    │       ├── confidence/confidence_rules.py
    │       │       └── models/output_models.py
    │       ├── models/catalog_models.py
    │       ├── models/output_models.py
    │       ├── services/ai_classifier.py
    │       │       └── models/output_models.py
    │       └── services/fallback_handler.py
    │               └── services/ai_classifier.py
    ├── processors/experience_processor.py
    │       ├── models/output_models.py
    │       ├── services/ai_classifier.py
    │       └── services/fallback_handler.py
    ├── processors/evolution_processor.py
    │       ├── catalog/versioning.py
    │       │       └── catalog/loader.py
    │       ├── engine/config.py
    │       └── models/output_models.py
    └── processors/executive_processor.py
            ├── models/output_models.py
            ├── services/ai_classifier.py
            └── services/fallback_handler.py

logs/engine_logger.py        (sem dependências internas — usa stdlib logging)
logs/classification_logger.py  ← models/output_models.py
logs/audit_logger.py           ← models/output_models.py
```

**Módulos folha (sem dependências internas):** `models/input_models.py`, `models/catalog_models.py`, `engine/config.py`

**Módulo mais dependido:** `models/output_models.py` — importado por 10 dos 14 módulos de produção. Qualquer mudança estrutural nele afeta toda a cadeia.

---

## 5. Fluxo Completo de Execução

```
ENTRADA: executar_pipeline(lote: Lote, catalogo: CatalogoNSI, cliente_ia: ClienteIA)
│
├─[1] math_processor.processar_matematica(lote)
│     → ResultadoMatematico
│     → SEMPRE executa. Nunca falha por causa da IA.
│
├─[2] linguistic_processor.processar_linguistica_resposta(texto) × N respostas
│     → list[ResultadoLinguistico]
│     → agregar_linguistica_lote(resultados) → ResultadoLinguisticoAgregado
│     → SEMPRE executa. Determinístico.
│
├─[3] PORTÃO DE FALLBACK (verifica ClienteIA via chamada de ping)
│     SE falha:
│     │   ctx.status_semantico = "pendente"
│     └── output_builder.montar_saida_parcial() → SaidaMotorCompleta (PARCIAL)
│                                                   └─ FIM (saída parcial entregue)
│
│     SE IA disponível: continua ↓
│
├─[4] catálogo já carregado antes de chamar executar_pipeline
│     (catalog/loader.carregar_catalogo())
│
├─[5] semantic_processor.processar_semantica_resposta(cliente_id, texto, catalogo, ia)
│         × N respostas válidas
│         ├── catalog/matcher.buscar_candidatos(texto, catalogo)  [determinístico]
│         ├── services/ai_classifier.ClienteIA.classificar(requisicao) [IA]
│         ├── confidence_rules.ordenar_e_aplicar_limite(categorias)   [determinístico]
│         └── → (list[CategoriaDetectada], list[Evidencia], sucesso_ia)
│     → agregar_semantica_lote() → ResultadoSemantico
│     SE qualquer resposta tem sucesso_ia=False:
│     └── output_builder.montar_saida_parcial() → SaidaMotorCompleta (PARCIAL)
│
├─[6] (aplicado dentro do step 5 via confidence_rules)
│
├─[7] experience_processor.processar_experiencia_humana_resposta(texto, ling, cats, ia)
│         × N respostas válidas
│         └── services/ai_classifier.ClienteIA.classificar(requisicao) [IA]
│     → agregar_experiencia_humana_lote() → ResultadoExperienciaHumanaAgregado
│     → Falha de IA individual não para o pipeline (usa placeholder zerado)
│
├─[8] evolution_processor.processar_evolucao_temporal(empresa, versao, math, sem, anterior)
│         [100% determinístico — sem IA]
│     → ResultadoEvolucaoTemporal | None
│       (None quando não há lote_anterior ou é o primeiro lote)
│
├─[9] executive_processor.processar_executiva(math, ling, sem, cobertura, total, evid, evo, seg, ia)
│     ├── calcular_ice(...)          [determinístico — Contrato Seção 9.17]
│     ├── calcular_top_forcas(...)   [determinístico]
│     ├── calcular_top_oportunidades() [determinístico]
│     ├── calcular_top_prioridades() [determinístico]
│     ├── calcular_areas_responsaveis_agregado() [determinístico]
│     ├── gerar_resumos_executivos(..., ia) [IA — 8 campos de texto]
│     └── gerar_acoes_recomendadas(..., ia) [IA — lista de ações]
│     → ResultadoExecutivo
│
└─[10] output_builder.montar_saida_completa(...)
       ├── _validar_saida_completa(saida)  ← valida schema antes de entregar
       └── → SaidaMotorCompleta (COMPLETA, validada)

SAÍDA: SaidaMotorCompleta
```

---

## 6. Cobertura dos Testes

### Por fase

| Fase | Arquivo de teste | Testes |
|---|---|---|
| 1 — Matemática | `test_math_processor.py` | 6 |
| 2 — Linguística | `test_linguistic_processor.py` | 10 |
| 3 — Catálogo | `test_catalog.py` | 6 |
| 4 — IA e Fallback | `test_ai_classifier_e_fallback.py` | 11 |
| 5 — Semântica | `test_semantic_processor.py` | 10 |
| 6 — Confiança | `test_confidence_rules.py` | 9 |
| 7 — Experiência Humana | `test_experience_processor.py` | 10 |
| 8 — Evolução Temporal | `test_evolution_processor.py` | 8 |
| 9 — Executiva | `test_executive_processor.py` | 16 |
| 10 — Output Builder | `test_output_builder.py` | 6 |
| 11 — Pipeline (integração) | `test_pipeline.py` | 4 |
| 12 — Logs | `test_logs.py` | 6 |
| 13 — Regressão | `test_regression_final.py` | 6 |
| **TOTAL** | **13 arquivos** | **108** |

### Resultado da última execução (verificado agora)

- **108 testes executados**
- **108 passando**
- **0 falhas**
- **Percentual de sucesso: 100%**

---

## 7. Placeholders, TODOs e FIXMEs

**Resultado da varredura:** 2 ocorrências encontradas, nenhuma é pendência real.

| Arquivo | Linha | Conteúdo | Natureza |
|---|---|---|---|
| `services/ai_classifier.py` | 95 | `raise NotImplementedError` | **Intencional** — é o corpo do método abstrato `ClienteIA.classificar()` (ABC). Python exige que métodos abstratos tenham um corpo; `raise NotImplementedError` é o padrão correto. As duas implementações concretas (`ClienteGroq` e `ClienteIAFalso`) sobrescrevem esse método com lógica real. |
| `processors/semantic_processor.py` | 95 | "de TODOS os códigos válidos" | **Falso positivo** — é a palavra "TODOS" em maiúsculo dentro de um comentário de documentação, não uma diretiva de pendência. |

**Conclusão: zero pendências reais de implementação.**

---

## 8. O que Depende Exclusivamente da Groq para Funcionar em Produção

Toda a dependência da Groq está contida em **um único ponto de configuração de ambiente**:

```
GROQ_API_KEY=<chave>        # variável de ambiente
GROQ_MODEL=llama-3.3-70b-versatile  # opcional, tem default
```

O único arquivo que instancia a conexão com a Groq é `services/ai_classifier.py`, classe `ClienteGroq`. Tudo mais no motor usa a interface abstrata `ClienteIA` — nunca a Groq diretamente.

**Funcionalidades que precisam da Groq em produção:**

| Funcionalidade | Módulo | Tarefa IA |
|---|---|---|
| Classificação semântica fina | `semantic_processor.py` | `"classificacao_semantica"` |
| Inferência de experiência humana | `experience_processor.py` | `"experiencia_humana"` |
| Geração dos 8 resumos executivos | `executive_processor.py` | `"resumo_executivo"` |
| Geração de ações recomendadas | `executive_processor.py` | `"acao_recomendada"` |

**Para ativar a Groq em produção:** substituir `ClienteIAFalso` por `ClienteGroq()` no ponto de composição (onde `executar_pipeline` é chamado). **Zero mudanças no código do motor.**

---

## 9. O que Funciona Completamente Sem IA

As seguintes camadas e componentes rodam 100% sem qualquer chamada externa:

| Componente | Módulo | Garantia |
|---|---|---|
| Camada Matemática completa | `math_processor.py` | Pura aritmética de datas e contagens |
| Camada Linguística (sinais de superfície) | `linguistic_processor.py` | Regex + dicionários locais |
| Carregamento do Catálogo | `catalog/loader.py` | Lê `catalogo_v1.1.json` do disco |
| Matcher determinístico | `catalog/matcher.py` | Busca textual, sem rede |
| Regras de Confiança (limite de 5) | `confidence/confidence_rules.py` | Ordenação pura |
| Camada de Evolução Temporal completa | `evolution_processor.py` | Aritmética sobre saídas já calculadas |
| Rankings executivos (Top Forças, Oportunidades, Prioridades) | `executive_processor.py` | Ordenação determinística |
| Áreas responsáveis agregadas | `executive_processor.py` | Soma por família |
| **ICE NSI v1 completo** | `executive_processor.py` | Fórmula fechada (Contrato 9.17) |
| Critério híbrido de bloqueio do ICE | `executive_processor.py` | Comparação numérica |
| Output Builder (montagem e validação do JSON final) | `output_builder.py` | Composição e validação de schema |
| Toda a instrumentação de logs | `logs/` | stdlib `logging` |

**O motor entrega uma saída parcial válida (Matemática + Linguística) sem nenhuma chamada de rede**, conforme o Contrato Seção 1.2. O ICE, rankings e resumos são bloqueados na saída parcial — mas os dados operacionais fundamentais chegam ao Dashboard mesmo com a Groq fora do ar.

---

## 10. Integração com Dashboard e PDF Executivo

**O motor pode ser integrado imediatamente sem alterações estruturais.**

A interface de integração é exatamente `SaidaMotorCompleta`, definida em `models/output_models.py`. O Dashboard e o PDF consomem os dados a partir deste objeto — ou do dicionário equivalente via `outputs/output_builder.saida_para_dict()`.

**Pontos confirmados para integração:**

| Item | Status |
|---|---|
| Schema de saída (Contrato Seção 8) | Fixo e validado — `_validar_saida_completa()` garante antes de entregar |
| `versao_motor` e `versao_catalogo` na raiz | Presentes em toda saída |
| `status_semantico` ("concluido" / "pendente") | Sinaliza ao Dashboard quando exibir blocos IA ou não |
| `evidencias_semanticas_validas` | Disponível na raiz para exibição em auditoria |
| `status_ice` ("calculado" / "cobertura_insuficiente") | O Dashboard pode tratar os dois casos sem lógica adicional |
| `ice_nsi` como `Optional[float]` | Quando `null`, Dashboard exibe "cobertura insuficiente" com o `motivo` |
| `evolucao_temporal` como `Optional` | Quando `None`, Dashboard simplesmente não renderiza o bloco de evolução |
| 8 campos `resumo_*` prontos para renderização | Strings prontas para exibição, sem processamento adicional |
| Ações recomendadas com `posicao`, `categoria`, `recomendacao`, `baseado_em` | Estrutura completa para renderização direta |
| `respostas_individuais` para drill-down | Lista completa com linguística + experiência + categorias por resposta |
| `saida_para_dict()` — serialização JSON | Converte `datetime` para ISO 8601 automaticamente |

**Única responsabilidade do Dashboard/PDF que não está no motor:** decidir o layout visual e o que mostrar em cada cenário (ex: o que exibir quando `status_ice = "cobertura_insuficiente"`). Isso é decisão de UX, não do motor.

---

## Conclusão da Auditoria

| Item | Resultado |
|---|---|
| Fases implementadas | 14 de 14 (0 a 13) |
| Arquivos de produção | 23 arquivos com lógica (3.577 linhas) |
| Arquivos de teste | 13 arquivos (2.813 linhas) |
| Total de linhas | 6.390 |
| Testes executados e passando | 108/108 (100%) |
| TODOs / FIXMEs reais | 0 |
| Conformidade com Contrato v3.1.1 | Verificada campo a campo |
| Dependência de Groq para produção | 1 variável de ambiente (`GROQ_API_KEY`) — zero mudanças de código |
| Pronto para integração com Dashboard/PDF | Sim, sem alterações estruturais |
