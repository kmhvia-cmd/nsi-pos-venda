# Plano de Implementação do Motor NSI

> **Status documental:** histórico e concluído. Este plano registra as fases iniciais de implementação do Motor NSI e não representa o roadmap atual. Para o planejamento vigente, consulte ROADMAP-SPRINTS-B-G.md, PROJECT_STATUS.md e as especificações atuais de Sprint.

## Roadmap Técnico — Da Especificação ao Motor Funcional

**Versão:** 1.0
**Status:** Plano de execução. Implementação ainda não iniciada.
**Deriva de:** `especificacao_tecnica_nsi_v1.md` v1.0 (congelada) — a ordem das fases segue exatamente o pipeline da Seção 3, sem reordenar nem pular etapas.
**Regra de trabalho:** uma fase só começa após a anterior estar validada. Nenhuma fase avança sem critério de aceite confirmado.

---

## Visão geral das fases

| Fase | Entrega | Depende de | Risco |
|---|---|---|---|
| 0 | Esqueleto de projeto e modelos de dados | Nenhuma | Baixo |
| 1 | Camada Matemática | Fase 0 | Baixo |
| 2 | Camada Linguística (sinais determinísticos) | Fase 0, 1 | Médio |
| 3 | Catálogo — carregamento e matcher determinístico | Fase 0 | Médio |
| 4 | Integração com IA + fallback | Fase 0 | Alto |
| 5 | Camada Semântica completa | Fases 2, 3, 4 | Alto |
| 6 | Regras de Confiança (limite de 5, corte por confiança) | Fase 5 | Baixo |
| 7 | Camada de Experiência Humana | Fases 2, 5, 6 | Alto |
| 8 | Camada de Evolução Temporal | Fases 1, 5 | Médio |
| 9 | Camada Executiva | Fases 1–8 | Alto |
| 10 | Output Builder e montagem do JSON final | Fases 1–9 | Médio |
| 11 | Pipeline completo (orquestração end-to-end) | Fases 0–10 | Médio |
| 12 | Logs e auditoria | Fase 11 | Baixo |
| 13 | Testes de regressão com caso real + validação final | Fase 12 | Médio |

A numeração de fase **não corresponde 1:1** ao número de seção do pipeline da Especificação Técnica — a Fase 0 e as Fases 3/4 antecipam infraestrutura (modelos, catálogo, cliente de IA) que o pipeline da Seção 3 assume já existir antes do primeiro processor rodar.

---

## Fase 0 — Esqueleto de Projeto e Modelos de Dados

**Objetivo:** criar a estrutura de pastas completa (Especificação Técnica Seção 1) e implementar as dataclasses de entrada/saída (Seção 5), sem nenhuma lógica de negócio ainda.

**Complexidade:** Baixa — é estrutura e tipagem, sem cálculo.

**Dependências:** nenhuma.

**Risco:** Baixo. O único risco real é modelar um campo de forma incompatível com o contrato — mitigado por revisão campo a campo contra `contrato_motor_nsi.md` antes de prosseguir.

**O que entra:**
- Estrutura de pastas completa (`engine/`, `processors/`, `catalog/`, `models/`, `services/`, `confidence/`, `outputs/`, `logs/`, `tests/`)
- `models/input_models.py` — `RespostaCliente`, `Lote`
- `models/output_models.py` — todas as dataclasses de saída (vazias de lógica, só estrutura)
- `models/catalog_models.py` — `EntradaCatalogo`, `AreaResponsavel`

**Critério de aceite:**
- Toda dataclass tem 1:1 correspondência de campo com o contrato (checagem manual, campo por campo)
- Projeto importa sem erro (`import` de todos os módulos vazios funciona)
- Nenhuma lógica de cálculo presente — só tipos

---

## Fase 1 — Camada Matemática

**Objetivo:** implementar `math_processor.py` completo (Especificação Técnica Seção 4) — a única camada sem qualquer dependência de IA ou catálogo, conforme decidido no Contrato.

**Complexidade:** Baixa — cálculos de data, contagem e média, sem ambiguidade de interpretação.

**Dependências:** Fase 0 (modelos `Lote`/`RespostaCliente`).

**Risco:** Baixo. Os únicos pontos de atenção são edge cases (lote com zero respostas, divisão por zero) e a definição exata de `qualidade_participacao` (Contrato 9.11 deixa os critérios qualitativos — riqueza lexical, profundidade — sem fórmula fechada).

**O que entra:**
- `processors/math_processor.py`
- Testes unitários (`tests/unit/test_math_processor.py`) com lotes sintéticos de tamanho conhecido

**Critério de aceite:**
- Lote sintético de 10 respostas, 6 respondidas → `taxa_resposta == 60.0`
- Lote com timestamps conhecidos → `tempo_medio_resposta_minutos` e `distribuicao_tempo_resposta` batem com cálculo manual
- Lote vazio (zero enviados) não quebra o módulo — retorna estrutura válida com zeros ou estado explícito, não exceção não tratada
- `qualidade_participacao_media` calculável e dentro de 0–100% para qualquer entrada de teste

**Rollback:** módulo isolado, sem dependência de outras fases além da 0 — reverter é remover o arquivo e seus testes, sem efeito colateral em nenhuma outra parte do sistema.

---

## Fase 2 — Camada Linguística (sinais determinísticos)

**Objetivo:** implementar a parte de `linguistic_processor.py` que **não depende de IA** (Especificação Técnica Seção 7.2) — emojis, pontuação, caixa alta, regionalismos já catalogados, abreviações.

**Complexidade:** Média — exige dicionários/regex bem calibrados para emoji, pontuação intensificada e regionalismo, mas é determinístico.

**Dependências:** Fase 0.

**Risco:** Médio. Risco principal é cobertura incompleta de regionalismos/gírias na primeira versão — mitigado porque o catálogo (`catalogo_nsi_v1_operacional.md`) já lista exemplos por entrada, servindo de base inicial, com expansão contínua prevista pelo próprio contrato (Seção 4.1).

**O que entra:**
- `processors/linguistic_processor.py` — implementação parcial (sinais de superfície apenas; pragmática/hermenêutica/ironia ficam para Fase 7, junto da Experiência Humana, por dependerem de IA)
- Testes unitários com frases conhecidas (ex: "MUITO BOM!!!" → `pontuacao_intensificada: true`, `caixa_alta: true`)

**Critério de aceite:**
- Detecção correta de emoji, pontuação intensificada, caixa alta, abreviação em conjunto de frases de teste cobrindo os exemplos do catálogo
- `formalidade` e `marca_regional` calculáveis e dentro de 0–100%
- Módulo roda de forma independente da IA — nenhuma chamada externa nesta fase

**Rollback:** reverter ao estado da Fase 0 (remover lógica de `linguistic_processor.py`, manter estrutura vazia).

---

## Fase 3 — Catálogo: Carregamento e Matcher Determinístico

**Objetivo:** implementar `catalog/loader.py` e `catalog/matcher.py` (Especificação Técnica Seções 4, 6) — carregar as 91 entradas do catálogo e fazer correspondência textual determinística.

**Complexidade:** Média — a busca textual precisa lidar com variações (sinônimo, gíria, regionalismo) sem falsos positivos grosseiros.

**Dependências:** Fase 0 (modelo `EntradaCatalogo`).

**Risco:** Médio. Risco de o matcher ser "cego de contexto" (ex: confundir "tranquilo" positivo com "tranquilo" negativo) — **mitigado por design**, porque o Contrato já determina que a decisão fina de ambiguidade é responsabilidade da IA (Fase 5), não do matcher determinístico. O matcher só precisa fornecer candidatos corretos, não decidir.

**O que entra:**
- `catalog/loader.py` — carrega as 91 entradas a partir de `catalogo_nsi_v1_operacional.md` (ou de uma representação estruturada equivalente gerada a partir dele)
- `catalog/matcher.py` — retorna candidatos por texto
- `catalog/versioning.py` — expõe `versao_catalogo` corrente ("1.1")
- Testes com frases de evidência do próprio catálogo (ex: "Esperei mais de vinte minutos para ser atendido" → candidato `ATEND-001`)

**Critério de aceite:**
- Loader carrega exatamente 91 entradas, todas com `codigo`, `tipo`, `familia`, `areas` preenchidos
- Para cada uma das 91 entradas, ao menos uma das 2 evidências-exemplo do catálogo gera aquele código como candidato no matcher (teste de cobertura 1:1 contra o catálogo)
- `versao_catalogo` retornada é exatamente `"1.1"`

**Rollback:** módulo isolado; reverter remove `catalog/` sem afetar Fases 0–2.

---

## Fase 4 — Integração com IA e Fallback

**Objetivo:** implementar `services/ai_classifier.py` e `services/fallback_handler.py` (Especificação Técnica Seções 4, 7, e Contrato 1.1/1.2) — a porta única de chamada ao provedor de IA e a lógica de contingência.

**Complexidade:** Alta — primeira integração externa do sistema, exige tratamento robusto de erro, timeout e registro de `modelo_classificacao`.

**Dependências:** Fase 0.

**Risco:** Alto. É a única dependência externa de todo o motor — qualquer instabilidade do provedor (Groq) se propaga. Mitigado pelo próprio desenho do fallback (Contrato 1.2): a Fase 4 entrega o **fallback antes** de qualquer processor depender de IA estar funcionando, então as Fases 1–3 já são validáveis independentemente.

**O que entra:**
- `services/ai_classifier.py` — cliente único de chamada, com registro de `modelo_classificacao`
- `services/fallback_handler.py` — detecção de falha (timeout, erro externo, limite excedido) e sinalização de `status_semantico: "pendente"`
- Testes com stub determinístico de IA (resposta fixa simulada) para não depender do provedor real em teste automatizado
- Teste específico de fallback: simular timeout/erro e confirmar que o sinal correto é emitido

**Critério de aceite:**
- Chamada simulada de sucesso retorna estrutura esperada + `modelo_classificacao` preenchido
- Chamada simulada de falha (timeout, erro 5xx) aciona `fallback_handler.py` corretamente, sem exceção não tratada subindo para o pipeline
- Nenhum outro módulo do sistema chama IA diretamente — só via `ai_classifier.py` (checagem de code review, não automatizável em teste)

**Rollback:** reverter remove `services/`, mas como nenhuma fase anterior depende disso, o impacto é zero nas Fases 0–3.

---

## Fase 5 — Camada Semântica Completa

**Objetivo:** implementar `semantic_processor.py` (Especificação Técnica Seção 4) — classificação fina usando candidatos do matcher (Fase 3) + decisão da IA (Fase 4).

**Complexidade:** Alta — é o núcleo de inteligência do motor, integra catálogo + IA + regras de evidência/confiança do contrato.

**Dependências:** Fases 2 (sinais linguísticos como contexto auxiliar), 3 (matcher), 4 (IA + fallback).

**Risco:** Alto. Risco de qualidade de classificação (falsos positivos/negativos semânticos) é o maior risco de produto de todo o motor — mitigado pela bateria de testes semânticos previstos na Especificação Técnica (Seção 9.3), incluindo casos de ambiguidade hermenêutica e convivência força/dor.

**O que entra:**
- `processors/semantic_processor.py`
- Testes semânticos (`tests/semantic/`) cobrindo: convivência força/dor na mesma resposta (Contrato 4.3), caso de ambiguidade ("tranquilo" em contextos diferentes), nicho como subcategoria quando `segmento` ≠ `"generico"`

**Critério de aceite:**
- Frase "O atendimento foi ótimo, mas a entrega demorou" → gera **exatamente** 1 força (família ATENDIMENTO) + 1 dor (família ENTREGA), nenhuma anulando a outra
- Toda categoria detectada carrega `confianca`, `intensidade_semantica`, `area_responsavel` e ao menos 1 evidência textual — nunca uma classificação sem essas 4 informações (Contrato Seção 0)
- Quando `segmento` = "moda", subcategorias de nicho (ex: caimento) aparecem como candidatas quando o texto as menciona

**Rollback:** módulo isolado dentro de `processors/`; reverter não afeta Fases 0–4, que continuam validáveis isoladamente.

---

## Fase 6 — Regras de Confiança (Limite de 5 Categorias)

**Objetivo:** implementar `confidence/confidence_rules.py` (Contrato 4.3, Especificação Técnica Seção 4) — corte de categorias candidatas para no máximo 5, ordenadas por confiança.

**Complexidade:** Baixa — é lógica de ordenação e corte sobre uma lista já calculada.

**Dependências:** Fase 5 (precisa da lista de candidatos da Semântica para ter o que filtrar).

**Risco:** Baixo. Lógica simples e objetiva, sem ambiguidade de interpretação.

**O que entra:**
- `confidence/confidence_rules.py`
- Teste com lote sintético de 8+ categorias candidatas de confiança variada → confirma corte nas 5 maiores

**Critério de aceite:**
- Entrada com 8 candidatos, confianças variadas → saída tem exatamente 5, as de maior `confianca`
- Entrada com 3 candidatos → saída retorna os 3, sem alteração (corte só age acima do limite)
- Empate de confiança no 5º/6º lugar tem critério de desempate definido e testado (ex: ordem de detecção como critério secundário) — ponto que a Especificação Técnica não detalhou e esta fase precisa fechar antes de implementar

**Rollback:** módulo isolado e pequeno; reverter não afeta nenhuma fase anterior.

---

## Fase 7 — Camada de Experiência Humana

**Objetivo:** implementar `experience_processor.py` (Contrato Seção 5, Especificação Técnica Seção 4) — inferência de estado emocional, e a parte de Linguística que depende de IA (pragmática, hermenêutica, ironia — deixada pendente na Fase 2).

**Complexidade:** Alta — depende de cruzar três fontes (linguística, semântica, IA) com fronteira conceitual delicada frente à Linguística (Contrato 5.0).

**Dependências:** Fase 2 (sinais linguísticos), Fase 5 (categorias detectadas como contexto), Fase 6 (lista já filtrada), Fase 4 (IA).

**Risco:** Alto. Maior risco é a IA não respeitar a fronteira conceitual do Contrato 5.0 (confundir intensidade de forma com estado emocional) — mitigado por prompt bem ancorado no exemplo do próprio contrato ("Foi bom." = positivo mas não entusiasmado) e por teste de regressão dedicado.

**O que entra:**
- Conclusão de `processors/linguistic_processor.py` (pragmática, hermenêutica, ironia identificável)
- `processors/experience_processor.py` completo
- Teste de fronteira: mesma frase avaliada nas duas camadas, confirmando que os números não são idênticos nem redundantes

**Critério de aceite:**
- Todos os 10 indicadores de Experiência Humana (Contrato 5.1) calculáveis e dentro de 0–100% por resposta
- `experiencia_humana_agregada` corretamente calculada como média/distribuição no nível do lote
- Caso de teste "Foi bom." (do próprio Contrato) produz polaridade positiva mas entusiasmo baixo — a distinção exemplificada no contrato precisa se manifestar no resultado real, não só na documentação

**Rollback:** reverter a parte de Experiência Humana não afeta a Linguística básica (Fase 2) já validada; a parte de pragmática/ironia adicionada nesta fase pode ser revertida isoladamente dentro de `linguistic_processor.py`.

---

## Fase 8 — Camada de Evolução Temporal

**Objetivo:** implementar `evolution_processor.py` (Contrato Seção 6, Especificação Técnica Seção 4) — comparação entre lotes da mesma empresa, com salvaguarda de `versao_catalogo`.

**Complexidade:** Média — lógica de comparação é simples, mas exige acesso a saídas de lotes anteriores já persistidas (fora do escopo deste motor, conforme a própria Especificação Técnica Seção 4 já registra como dependência externa).

**Dependências:** Fase 1 (indicadores matemáticos do lote atual), Fase 5 (indicadores semânticos do lote atual), mais acesso de leitura a saída de lote anterior (dependência de persistência externa).

**Risco:** Médio. Principal risco é comparar indicadores de lotes com `versao_catalogo` diferente sem marcar a ressalva — mitigado porque essa regra já está fechada no contrato (Seção 6.1) e só precisa ser implementada fielmente, não desenhada.

**O que entra:**
- `processors/evolution_processor.py`
- Teste com 2 lotes sintéticos da mesma `versao_catalogo` → variação calculada corretamente
- Teste com 2 lotes de `versao_catalogo` diferentes → `comparabilidade: "parcial"` corretamente sinalizada
- Teste de primeiro lote de uma empresa (sem histórico) → campo `evolucao_temporal` **omitido por completo**, não `null`

**Critério de aceite:**
- Os três cenários de teste acima passam exatamente como descritos
- Nenhuma variação percentual aparece como "limpa" quando os catálogos comparados diferem

**Rollback:** módulo isolado; reverter não afeta Fases 1–7, que não dependem de Evolução Temporal para funcionar.

---

## Fase 9 — Camada Executiva

**Objetivo:** implementar `executive_processor.py` (Contrato Seção 7, Especificação Técnica Seção 4) — ICE, rankings, áreas agregadas, ações recomendadas, 8 resumos textuais.

**Complexidade:** Alta — é a fase que consolida todas as anteriores e tem a maior superfície de campos (mais componentes de qualquer camada do contrato).

**Dependências:** Fases 1 a 8 (consome a saída de todas).

**Risco:** Alto. Dois riscos específicos: (1) fórmula do ICE v1 não tem pesos definidos no contrato (Contrato 9.5 deixa isso para "fase de calibração") — esta fase precisa de uma decisão de produto antes de codificar, não é uma decisão técnica que se possa tomar sozinha; (2) ações recomendadas geradas por IA podem variar de qualidade conforme o contexto do lote — mitigado por teste de regressão.

**O que entra:**
- `processors/executive_processor.py`
- Teste de rankings determinísticos (top forças/oportunidades/prioridades) — sem IA, só ordenação
- Teste de resumos e ações recomendadas com stub de IA determinístico

**Critério de aceite:**
- `top_prioridades` corretamente calculado como `incidencia_percentual × confianca_media`, sem nenhum fator de impacto comercial (Contrato 7.2/9.1)
- `areas_responsaveis_agregado` reflete corretamente a soma por área primária, com possibilidade de área secundária quando o padrão do lote justificar (Contrato 7.3)
- Todos os 8 resumos (`resumo_executivo`, `resumo_comercial` etc.) presentes e em linguagem natural, sem jargão técnico
- **Bloqueio explícito:** esta fase não avança para implementação de `ice_nsi` até receber a decisão de pesos da fórmula (ver Pendência de Produto, ao final deste documento)

**Rollback:** módulo isolado; reverter não afeta Fases 1–8.

---

## Fase 10 — Output Builder e Montagem do JSON Final

**Objetivo:** implementar `outputs/output_builder.py` (Contrato Seção 8, Especificação Técnica Seção 4) — monta o objeto JSON final completo, parcial (fallback) ou total.

**Complexidade:** Média — não calcula nada, mas precisa validar schema rigorosamente contra o contrato.

**Dependências:** Fases 1 a 9 (lê a saída de todas).

**Risco:** Médio. Risco de inconsistência de schema (campo faltante, tipo errado) — mitigado por validação automática contra um schema derivado diretamente do Contrato Seção 8.

**O que entra:**
- `outputs/output_builder.py`
- Schema de validação (formato a decidir na implementação — JSON Schema, Pydantic, ou equivalente)
- Teste: saída completa (todas as camadas presentes) valida contra schema
- Teste: saída parcial (fallback ativo) valida contra schema parcial, com `status_semantico: "pendente"` e ausência correta de `semantica`/`executiva`

**Critério de aceite:**
- JSON final de um lote de teste completo bate campo a campo com o exemplo do Contrato Seção 8
- JSON parcial (fallback) contém exatamente `matematica`, `linguistica_agregada`, `status_semantico` — nada além disso, nada faltando

**Rollback:** módulo isolado; reverter não afeta as Fases 1–9, que continuam testáveis isoladamente (sem montagem final).

---

## Fase 11 — Pipeline Completo (Orquestração End-to-End)

**Objetivo:** implementar `engine/pipeline.py` e `engine/context.py` (Especificação Técnica Seções 1, 3) — a orquestração que chama cada processor na ordem oficial, incluindo o desvio de fallback.

**Complexidade:** Média — não é cálculo novo, é amarrar tudo que já foi validado isoladamente nas Fases 1–10.

**Dependências:** todas as Fases 0–10.

**Risco:** Médio. Risco de erro de ordem ou de propagação incorreta de contexto entre módulos — mitigado porque a ordem já está fechada e testada conceitualmente na Especificação Técnica (Seção 3), só falta a amarração de código.

**O que entra:**
- `engine/pipeline.py`
- `engine/context.py`
- Teste de integração: lote real de ponta a ponta (mesmo lote/cliente já validado em produção: `NSI-TESTE-001`, telefone `5511955525922`) → resultado final compatível com o JSON de exemplo do Contrato

**Critério de aceite:**
- Pipeline completo roda sem erro para o lote de teste real
- Pipeline com fallback simulado (IA indisponível) interrompe corretamente após Linguística, entregando saída parcial válida
- Tempo de execução registrado por etapa (preparação para a Fase 12 de logs)

**Rollback:** reverter `engine/pipeline.py` não afeta os processors individuais (Fases 1–10), que continuam testáveis via chamada direta nos próprios testes unitários/integração.

---

## Fase 12 — Logs e Auditoria

**Objetivo:** implementar `logs/engine_logger.py`, `logs/classification_logger.py`, `logs/audit_logger.py` (Especificação Técnica Seção 8).

**Complexidade:** Baixa — é instrumentação sobre um pipeline já funcional, não lógica de negócio nova.

**Dependências:** Fase 11 (precisa do pipeline rodando para ter o que logar).

**Risco:** Baixo. Risco de excesso de log sensível (ex: logar texto completo do cliente em log de erro sem necessidade) — mitigado por revisão de conteúdo de cada log antes de fechar a fase.

**O que entra:**
- Os 3 módulos de log
- Verificação manual de que `classification_logger.py` registra `modelo_classificacao` em toda chamada de IA

**Critério de aceite:**
- Execução completa do pipeline gera entradas nos 3 logs, com `lote_id` presente em todas
- Log de fallback é gerado quando (e só quando) o fallback é acionado em teste simulado

**Rollback:** logs são aditivos; reverter não afeta o funcionamento do pipeline, só a observabilidade.

---

## Fase 13 — Testes de Regressão e Validação Final

**Objetivo:** consolidar a suíte de regressão (Especificação Técnica Seção 9.4) com casos reais, fechando o motor como pronto para uso.

**Complexidade:** Média — não é código novo, é consolidação e congelamento de resultado esperado.

**Dependências:** Fase 12 (pipeline + logs completos).

**Risco:** Médio. Risco de a suíte de regressão ser pequena demais para pegar regressões reais — mitigado por incluir, no mínimo, o caso real de produção já validado (lote `NSI-TESTE-001`) mais um conjunto de lotes sintéticos cobrindo cada camada.

**O que entra:**
- `tests/regression/` com o conjunto de lotes + saída esperada congelada
- Execução completa da suíte (unitários + integração + semânticos + regressão)

**Critério de aceite:**
- 100% dos testes das Fases 1–12 passam em conjunto, não só isoladamente
- Caso real `NSI-TESTE-001` reproduz exatamente a saída esperada
- Motor NSI considerado **funcional e pronto para entrega**

**Rollback:** N/A — esta é a fase de validação final, não introduz código novo além dos testes.

---

## Pendência de Produto (bloqueia parte da Fase 9)

Antes da Fase 9 poder ser **concluída** (ela pode começar, mas não fechar `ice_nsi`), é necessária uma decisão de produto que não é técnica: os **pesos da fórmula do ICE v1** (Contrato 9.5 deixa isso para "fase de calibração", sem fórmula fechada). Esta pendência é registrada aqui para não bloquear silenciosamente a implementação quando chegar a hora — será trazida à sua decisão no momento em que a Fase 9 for iniciada.

---

## Resumo de risco por fase

| Risco | Fases |
|---|---|
| Alto | 4 (IA/fallback), 5 (Semântica), 7 (Experiência Humana), 9 (Executiva) |
| Médio | 2 (Linguística), 3 (Catálogo), 8 (Evolução), 10 (Output), 11 (Pipeline), 13 (Regressão) |
| Baixo | 0 (Esqueleto), 1 (Matemática), 6 (Confiança), 12 (Logs) |

As 4 fases de risco Alto coincidem exatamente com as 4 camadas que dependem de IA (Especificação Técnica Seção 7.3) — não é coincidência, é onde a interpretação de linguagem natural introduz incerteza que nenhuma camada determinística tem.
