# Especificação Técnica NSI v1

> **Status documental:** parcialmente histórico. Registra a especificação técnica original do núcleo de classificação do Motor NSI. A estrutura e as decisões atuais do repositório, assim como a camada de persistência operacional, são regidas pelas ADRs, pelo PROJECT_STATUS.md e pelas especificações de Sprint mais recentes.

## Blueprint Técnico de Implementação do Motor NSI

**Versão:** 1.0
**Status:** Especificação técnica fechada. Não implementada.
**Deriva de:** `contrato_motor_nsi.md` v3.1 (congelado) e `catalogo_nsi_v1_operacional.md` v1.1 (congelado)
**Correção técnica (Fase 0 de implementação):** a pasta originalmente nomeada `logging/` foi renomeada para `logs/` em todo este documento. Motivo: `logging/` colide com o módulo `logging` da biblioteca padrão do Python — qualquer arquivo dentro do pacote do projeto que tentasse `import logging` (para uso real da stdlib) resolveria para o pacote local por engano, quebrando silenciosamente. Esta é uma correção de implementação, sem impacto na arquitetura conceitual (Contrato v3.1) nem na Especificação Técnica em si — apenas o nome da pasta mudou; módulos, responsabilidades e conteúdo de cada arquivo de log permanecem exatamente como especificado.
**Regra de ouro deste documento:** todo módulo, estrutura e fluxo aqui descrito é uma tradução técnica de uma decisão já aprovada nos documentos congelados — nenhuma camada, métrica, família ou regra nova é proposta aqui. Onde o contrato deixa algo deliberadamente indefinido (ex: pesos do ICE, fórmula de Impacto Comercial), este blueprint também deixa em aberto, sem antecipar decisão de produto.

---

## 1. Estrutura de Pastas

```
nsi_engine/
├── engine/                      # Orquestração e pipeline
│   ├── __init__.py
│   ├── pipeline.py              # Orquestrador principal — ordem de execução
│   └── context.py               # Objeto de contexto compartilhado entre módulos
│
├── processors/                  # Um arquivo por camada do contrato
│   ├── __init__.py
│   ├── math_processor.py        # Camada Matemática (Contrato Seção 2)
│   ├── linguistic_processor.py  # Camada Linguística (Seção 3)
│   ├── semantic_processor.py    # Camada Semântica (Seção 4)
│   ├── experience_processor.py  # Camada de Experiência Humana (Seção 5)
│   ├── evolution_processor.py   # Camada de Evolução Temporal (Seção 6)
│   └── executive_processor.py   # Camada Executiva (Seção 7)
│
├── catalog/                     # Carregamento e consulta do Catálogo NSI
│   ├── __init__.py
│   ├── loader.py                # Lê catalogo_nsi_v1_operacional.md/json
│   ├── matcher.py                # Casa texto livre contra entradas do catálogo
│   └── versioning.py             # Controle de versao_catalogo
│
├── models/                      # Estruturas de dados (dataclasses/schemas)
│   ├── __init__.py
│   ├── input_models.py           # Lote, RespostaCliente (Contrato Seção 1)
│   ├── output_models.py          # Saída de cada camada (Seções 2 a 8)
│   └── catalog_models.py         # EntradaCatalogo, AreaResponsavel
│
├── services/                    # Integrações externas
│   ├── __init__.py
│   ├── ai_classifier.py          # Cliente do provedor de IA (Groq ou equivalente)
│   └── fallback_handler.py       # Lógica de fallback sem IA (Contrato Seção 1.2)
│
├── confidence/                   # Transversal a Semântica e Experiência Humana
│   ├── __init__.py
│   └── confidence_rules.py       # Cálculo de confiança, ocorrências, limite de 5 categorias
│
├── outputs/                      # Montagem da saída final
│   ├── __init__.py
│   └── output_builder.py         # Monta o JSON final (Contrato Seção 8)
│
├── logs/                      # Estratégia de logs (Seção 8 deste blueprint)
│   ├── __init__.py
│   ├── engine_logger.py
│   ├── classification_logger.py
│   └── audit_logger.py
│
└── tests/                        # Estratégia de testes (Seção 9 deste blueprint)
    ├── unit/
    ├── integration/
    ├── semantic/
    └── regression/
```

**Justificativa da divisão `engine/` vs `processors/`:** `engine/` cuida de orquestração (ordem, contexto compartilhado, tratamento de falha entre módulos); `processors/` contém a lógica de cada camada isoladamente. Essa separação permite testar cada processor sozinho (Seção 9) sem precisar rodar o pipeline completo.

**Por que `catalog/` é uma pasta própria, fora de `processors/`:** o catálogo é consultado por mais de um processor (`semantic_processor.py` é o principal, mas `executive_processor.py` também precisa ler `area_responsavel` para o agregado por departamento — Contrato Seção 7.3). Centralizar evita que cada processor implemente sua própria leitura do catálogo.

---

## 2. Módulos do Motor — Visão Geral

| Módulo | Camada do Contrato | Depende de IA? |
|---|---|---|
| `math_processor.py` | Seção 2 — Matemática | Não |
| `linguistic_processor.py` | Seção 3 — Linguística | Parcial (ver Seção 7 deste blueprint) |
| `semantic_processor.py` | Seção 4 — Semântica | Sim |
| `catalog/matcher.py` | Seção 4 (apoio) | Não (é o catálogo determinístico que a IA consulta) |
| `experience_processor.py` | Seção 5 — Experiência Humana | Sim |
| `evolution_processor.py` | Seção 6 — Evolução Temporal | Não |
| `executive_processor.py` | Seção 7 — Executiva | Sim (resumos) / Não (rankings) |
| `confidence/confidence_rules.py` | Transversal (Seções 4.3, 4.5) | Não |
| `fallback_handler.py` | Seção 1.2 | N/A (ativa quando IA falha) |

Não existe módulo "Impacto Comercial", "peso_relevancia" ou "ação fixa por catálogo" — coerente com a ausência dessas peças no Contrato (Seções 9.1, 9.7, 9.8).

---

## 3. Pipeline de Execução

### 3.1 Ordem oficial

```
Lote recebido (Contrato Seção 1)
       ↓
[1] math_processor.py        → matematica (sempre executa)
       ↓
[2] linguistic_processor.py  → linguistica_agregada + linguistica por resposta (sempre executa)
       ↓
[3] fallback_handler.py      → verifica disponibilidade da IA antes de prosseguir
       ↓                          se IA indisponível: marca status_semantico = "pendente",
       ↓                          monta saída parcial (math + linguistic) e finaliza aqui
       ↓ (IA disponível)
[4] catalog/loader.py        → carrega catálogo na versao_catalogo vigente
       ↓
[5] semantic_processor.py    → semantica (usa catalog/matcher.py + ai_classifier.py)
       ↓
[6] confidence/confidence_rules.py → aplica limite de 5 categorias, ordena por confiança (Contrato 4.3)
       ↓
[7] experience_processor.py  → experiencia_humana_agregada (usa ai_classifier.py)
       ↓
[8] evolution_processor.py   → evolucao_temporal (se houver lote anterior comparável — Contrato 6)
       ↓
[9] executive_processor.py   → executiva (ICE, top listas, ações recomendadas, resumos)
       ↓
[10] outputs/output_builder.py → monta o JSON final completo (Contrato Seção 8)
       ↓
JSON Final entregue
```

### 3.2 Por que esta ordem, não outra

- **Matemática antes de tudo:** não depende de nenhum outro processor e é a camada mais barata de calcular — falhar rápido aqui (ex: lote vazio) evita gastar chamada de IA inutilmente.
- **Linguística antes de Semântica:** alguns sinais linguísticos (ex: marcadores de ironia, intensidade) podem ser usados como contexto auxiliar pela classificação semântica, mas o inverso não é verdadeiro — Semântica nunca precisa rodar antes de Linguística.
- **Fallback é um portão, não um processor isolado:** ele se posiciona logo antes da primeira chamada de IA (Semântica), porque é exatamente esse o ponto onde a dependência externa começa. Tudo antes dele (Matemática, Linguística) já está garantido como sempre executável (Contrato Seção 0, princípio de "nenhuma métrica sem fonte real").
- **Confiança roda depois de Semântica, antes de Experiência:** o limite de 5 categorias (Contrato 4.3) se aplica à saída da Semântica antes que qualquer camada posterior (Executiva) consuma essa lista — evita a Executiva trabalhar sobre uma lista não filtrada.
- **Evolução Temporal depois de tudo, antes da Executiva:** precisa dos indicadores já calculados do lote atual (Matemática, Semântica) para compará-los com o lote anterior, e a Executiva precisa do resultado da comparação para montar `resumo_evolutivo` (Contrato 7.1).
- **Executiva é sempre a penúltima:** ela consome a saída de todas as camadas anteriores (Contrato Seção 7, "consolida as camadas anteriores").

### 3.3 Pipeline em caso de fallback (Contrato 1.2)

```
[1] math_processor.py        → matematica
       ↓
[2] linguistic_processor.py  → linguistica_agregada
       ↓
[3] fallback_handler.py detecta IA indisponível
       ↓
[10] outputs/output_builder.py → monta saída PARCIAL:
       { matematica, linguistica_agregada, status_semantico: "pendente" }
       ↓
JSON Parcial entregue — lote marcado para reprocessamento da Semântica em diante
```

Este é o único desvio permitido da ordem oficial — qualquer outra falha (ex: erro no `math_processor.py`) não tem fallback definido neste blueprint, porque o Contrato não define esse cenário (ver Seção 11 — Itens não definidos).

---

## 4. Responsabilidade de Cada Módulo

### `math_processor.py`
- **Entrada:** lote completo (lista de respostas com timestamps e `status_entrega`)
- **Saída:** objeto `matematica` (Contrato Seção 2) — taxa de resposta, silêncio, tempo médio/mediano, distribuição de tempo, tamanho médio, participação válida, qualidade da participação média
- **Responsabilidade:** calcular indicadores puramente operacionais, sem interpretar conteúdo do texto
- **Dependências:** nenhuma (módulo de mais baixo nível do pipeline)

### `linguistic_processor.py`
- **Entrada:** texto de cada resposta individual
- **Saída:** objeto `linguistica` por resposta + `linguistica_agregada` no nível do lote (Contrato Seção 3)
- **Responsabilidade:** analisar a forma da fala (sintaxe, pragmática, hermenêutica, semiótica, emojis, pontuação, regionalismo, formalidade) — nunca o tema
- **Dependências:** nenhuma camada anterior; pode rodar de forma determinística (regras/dicionários) ou com IA leve — ver Seção 7 deste blueprint

### `semantic_processor.py`
- **Entrada:** texto de cada resposta + `segmento` da empresa + catálogo carregado (via `catalog/loader.py`)
- **Saída:** `categorias_detectadas` por resposta (até 5, Contrato 4.3) + agregados `dores_identificadas`/`forcas_identificadas` no nível do lote
- **Responsabilidade:** identificar **o que** o cliente disse, classificando contra as entradas do catálogo (código, família, subcategoria, nicho), com `confianca`, `ocorrencias` e `intensidade_semantica`
- **Dependências:** `catalog/matcher.py`, `services/ai_classifier.py`, `confidence/confidence_rules.py`

### `catalog/matcher.py`
- **Entrada:** texto de uma resposta + lista de entradas do catálogo (carregadas)
- **Saída:** lista de candidatos a categoria, cada um com termos correspondentes encontrados (sinônimo, gíria ou regionalismo que disparou o match)
- **Responsabilidade:** fazer o casamento textual determinístico — fornece candidatos para o `ai_classifier.py` confirmar/ponderar, não decide sozinho a classificação final (a decisão semântica fina, especialmente em casos de ambiguidade como "tranquilo", é responsabilidade da IA, conforme a Hermenêutica do Contrato Seção 3)
- **Dependências:** `catalog/loader.py`

### `experience_processor.py`
- **Entrada:** texto da resposta + saída de `linguistic_processor.py` + `categorias_detectadas` da Semântica (contexto)
- **Saída:** objeto `experiencia_humana` por resposta + `experiencia_humana_agregada` no lote (Contrato Seção 5)
- **Responsabilidade:** inferir estado emocional (entusiasmo, frustração, lealdade etc.), cruzando forma + tema + contexto — nunca duplicando o que a Linguística já calculou (fronteira formal do Contrato 5.0)
- **Dependências:** `linguistic_processor.py`, `semantic_processor.py`, `services/ai_classifier.py`

### `evolution_processor.py`
- **Entrada:** saída agregada do lote atual (Matemática + Semântica) + saída persistida do(s) lote(s) anterior(es) da mesma empresa
- **Saída:** objeto `evolucao_temporal` (Contrato Seção 6), omitido por completo se não houver lote anterior comparável
- **Responsabilidade:** comparar indicadores entre lotes, respeitando `versao_catalogo` — nunca compara lotes com catálogos diferentes sem marcar `comparabilidade: "parcial"`
- **Dependências:** `math_processor.py`, `semantic_processor.py`, acesso de leitura a saídas anteriores persistidas (fora do escopo deste motor — ver Seção 6 deste blueprint, Catálogo/persistência)

### `executive_processor.py`
- **Entrada:** saída de todas as camadas anteriores do lote
- **Saída:** objeto `executiva` completo (Contrato Seção 7) — ICE, top forças/oportunidades/prioridades, áreas agregadas, ações recomendadas, 8 resumos textuais
- **Responsabilidade:** consolidar tudo em linguagem de negócio; gerar ações recomendadas **a partir do contexto real do lote**, nunca de regra fixa do catálogo (Contrato 7.4/9.8)
- **Dependências:** todos os processors anteriores, `services/ai_classifier.py` (para os resumos textuais)

### `confidence/confidence_rules.py`
- **Entrada:** lista de categorias candidatas (de `semantic_processor.py`) com suas confianças
- **Saída:** lista filtrada e ordenada, máximo 5 entradas (Contrato 4.3)
- **Responsabilidade:** aplicar a regra de corte por confiança; também usado por `experience_processor.py` para os mesmos princípios de rastreabilidade (evidência + confiança + ocorrências, Contrato Seção 0)
- **Dependências:** nenhuma (módulo de regra pura, sem chamada externa)

### `services/ai_classifier.py`
- **Entrada:** texto + candidatos do catálogo (quando aplicável) + tipo de tarefa (classificação semântica, experiência humana, ou geração de resumo executivo)
- **Saída:** resposta estruturada do modelo de IA
- **Responsabilidade:** única porta de entrada para chamadas externas de IA no motor — nenhum outro módulo chama a IA diretamente
- **Dependências:** provedor externo (Groq ou equivalente); registra `modelo_classificacao` (Contrato 1.1) em toda chamada

### `services/fallback_handler.py`
- **Entrada:** resultado (ou exceção) da tentativa de chamada a `ai_classifier.py`
- **Saída:** sinal de "prosseguir" ou "interromper aqui com status_semantico: pendente"
- **Responsabilidade:** implementar o Contrato 1.2 — nunca bloquear Matemática/Linguística por falha de IA
- **Dependências:** `services/ai_classifier.py` (observa suas falhas, não as causa)

### `outputs/output_builder.py`
- **Entrada:** saída de todos os processors executados (parcial ou completa)
- **Saída:** o JSON final único (Contrato Seção 8), incluindo `versao_motor`, `versao_catalogo`, `modelo_classificacao`, `status_semantico`
- **Responsabilidade:** montagem final e validação de schema antes de entregar — não calcula nada, apenas compõe
- **Dependências:** todos os processors (mas só lê suas saídas, não os invoca — essa orquestração é do `engine/pipeline.py`)

---

## 5. Estruturas de Dados

Definidas como dataclasses (ou Pydantic, a decidir na implementação — este blueprint não escolhe framework). Nomenclatura espelha exatamente os campos do Contrato, para que a tradução contrato → código seja direta.

### `models/input_models.py`

```
RespostaCliente
  cliente_id: str
  telefone: str
  nome: str
  produto: str
  resposta: str
  data_envio_mensagem: datetime
  data_resposta: datetime | None
  status_entrega: Literal["respondido", "visualizado_sem_resposta",
                            "entregue_sem_visualizacao", "nao_entregue"]

Lote
  empresa: str
  segmento: str  # "generico" por padrão
  lote_id: str
  data_envio: datetime
  quantidade_enviada: int
  quantidade_respondida: int
  respostas: list[RespostaCliente]
```

### `models/output_models.py`

```
SaidaMatematica          # espelha Contrato Seção 2
SaidaLinguistica         # por resposta — espelha Contrato Seção 3
SaidaLinguisticaAgregada # por lote
CategoriaDetectada       # codigo_catalogo, familia, subcategoria, nicho,
                         # area_responsavel, confianca, intensidade_semantica
SaidaSemantica           # dores_identificadas, forcas_identificadas
SaidaExperienciaHumana   # por resposta e agregada — espelha Contrato Seção 5
SaidaEvolucaoTemporal    # opcional — Contrato Seção 6
AcaoRecomendada          # Contrato Seção 7.4
SaidaExecutiva           # ICE, tops, resumos — Contrato Seção 7
ModeloClassificacao      # provider, modelo, versao_prompt — Contrato 1.1
SaidaMotorCompleta       # objeto raiz — Contrato Seção 8
```

### `models/catalog_models.py`

```
AreaResponsavel
  primaria: str
  secundaria: str | None

EntradaCatalogo
  codigo: str               # ex: "ATEND-001"
  tipo: Literal["F", "D"]
  familia: str
  subcategoria: str
  areas: AreaResponsavel
  sinonimos: list[str]
  girias: list[str]
  regionalismos: list[dict]  # {termo, regiao, significado}
  emojis: list[str]
  nicho: str | None          # None = universal; nome do segmento se for subcategoria de nicho
```

Esta estrutura é o espelho fiel de cada entrada do `catalogo_nsi_v1_operacional.md` — nenhum campo aqui existe que não esteja no catálogo congelado, e nenhum campo do catálogo (`Áreas`, sinônimos, gírias, regionalismos, emojis) ficou de fora.

---

## 6. Catálogo — Carregamento, Consulta, Versionamento, Expansão

### 6.1 Carregamento (`catalog/loader.py`)

O catálogo operacional (atualmente em Markdown, `catalogo_nsi_v1_operacional.md`) é a fonte de verdade legível por humanos. Para uso pelo motor, este blueprint assume a existência de uma representação estruturada equivalente (ex: JSON ou YAML gerado a partir do Markdown, ou mantido em paralelo) — a decisão de formato exato de armazenamento é de implementação, não deste blueprint. O que é fixo: o loader carrega todas as **91 entradas** da `versao_catalogo` vigente em memória, indexadas por código.

### 6.2 Consulta (`catalog/matcher.py`)

Consulta é sempre por **texto contra termos** (termos-chave + sinônimos + gírias + regionalismos), nunca por categoria isolada — conforme a nota operacional do catálogo congelado ("o motor compara o texto livre... não apenas contra a subcategoria nominal"). O matcher retorna candidatos; a confirmação final (especialmente em casos de ambiguidade semântica) é responsabilidade da IA via `semantic_processor.py`.

### 6.3 Versionamento (`catalog/versioning.py`)

Cada execução do motor registra a `versao_catalogo` usada (hoje `"1.1"`). Esse valor:
- Acompanha a saída final do motor (Contrato Seção 8)
- É o critério de comparabilidade da Evolução Temporal (Contrato 6.1) — dois lotes só são comparados sem ressalva quando usam a mesma versão

### 6.4 Expansão futura

Duas formas de crescimento, ambas já previstas no Contrato, nenhuma nova aqui:
- **Por subcategoria** dentro de uma família existente (calibração contínua, Contrato 4.1) — não exige nova versão do *contrato*, mas exige nova `versao_catalogo` (ex: 1.1 → 1.2), pelo princípio de versionamento da Seção 6.1 do Contrato.
- **Por família nova** — segue o fluxo de governança formal do Contrato 4.8 (necessidade → subcategoria → validação recorrente → avaliação formal → possível promoção). Este blueprint não implementa esse fluxo como ferramenta automatizada; é processo de decisão de produto, não de engenharia.

---

## 7. Estratégia de IA

### 7.1 Onde a IA entra

| Camada | Usa IA? | Como |
|---|---|---|
| Matemática | Não | 100% determinístico (datas, contagens, médias) |
| Linguística | Parcial | Sinais de superfície (emoji, pontuação, caixa alta, regionalismo conhecido) são determinísticos via dicionário/regex; Pragmática, Hermenêutica e Ironia (Contrato 3.1) exigem IA, pois dependem de interpretação contextual que regras fixas não cobrem |
| Semântica | Sim | Classificação fina contra o catálogo, especialmente em ambiguidade — `catalog/matcher.py` é determinístico (fornece candidatos), a decisão final é da IA |
| Experiência Humana | Sim | Inferência de estado emocional é inerentemente interpretativa — não há regra fixa que separe "Confiança tranquila" de "Indiferença" (exemplo do próprio Contrato 5.0) |
| Evolução Temporal | Não | Comparação aritmética entre indicadores já calculados |
| Executiva — rankings (top forças/oportunidades/prioridades) | Não | Ordenação determinística sobre dados já calculados |
| Executiva — resumos textuais | Sim | Geração de linguagem natural a partir dos dados consolidados |
| Executiva — ações recomendadas | Sim | Depende de contexto do lote (Contrato 7.4), não é regra fixa |

### 7.2 O que é determinístico (nunca usa IA)

Matemática completa; sinais de superfície da Linguística (emoji, pontuação, regionalismo já catalogado); `catalog/matcher.py` (busca textual); `confidence/confidence_rules.py` (corte por confiança); Evolução Temporal; ordenação dos rankings executivos.

### 7.3 O que depende de modelo (usa IA)

Pragmática/Hermenêutica/Ironia da Linguística; toda a Semântica fina; toda a Experiência Humana; resumos e ações recomendadas da Executiva.

### 7.4 O que pode funcionar sem IA

Matemática e Linguística de superfície — exatamente as duas camadas que o fallback (Contrato 1.2) garante que sempre rodam, mesmo com a IA fora do ar. Não é coincidência: o fallback foi desenhado em torno do que já era, por natureza, determinístico.

### 7.5 O que entra no fallback

Quando `services/fallback_handler.py` detecta indisponibilidade: Semântica, Experiência Humana e os componentes dependentes de IA da Executiva (resumos, ações recomendadas) ficam pendentes. Rankings determinísticos da Executiva (Seção 7.2 acima) também ficam pendentes nesse cenário, porque dependem da Semântica já ter rodado — não há ranking de forças/oportunidades sem classificação semântica prévia.

---

## 8. Estratégia de Logs

| Tipo de log | Módulo responsável | Conteúdo | Uso |
|---|---|---|---|
| Logs do motor | `logs/engine_logger.py` | Início/fim de cada etapa do pipeline, tempo de execução por processor, lote_id | Observabilidade operacional, performance |
| Logs de classificação | `logs/classification_logger.py` | Toda chamada a `ai_classifier.py`: texto de entrada, candidatos do catálogo, resposta da IA, `modelo_classificacao` usado | Auditoria de classificação (Contrato 1.1), reprodutibilidade |
| Logs de erro | `logs/engine_logger.py` (nível ERROR) | Exceções por módulo, com lote_id e cliente_id quando aplicável | Debug, alertas |
| Logs de fallback | `logs/engine_logger.py` (nível WARN) + evento dedicado | Quando `fallback_handler.py` ativa o modo sem IA: motivo (timeout, erro externo, limite excedido), lote_id, timestamp | Rastrear frequência de indisponibilidade da IA, decidir reprocessamento |
| Logs de auditoria | `logs/audit_logger.py` | Toda saída final do motor por lote: `versao_motor`, `versao_catalogo`, `modelo_classificacao`, contagens agregadas | Auditoria de longo prazo, suporte à Evolução Temporal (precisa acessar saídas anteriores) |

`classification_logger.py` e `audit_logger.py` nunca registram dados que vão para o cliente final sem o contexto de auditoria interna — alinhado ao Contrato 1.1 ("não exibido ao cliente final").

---

## 9. Estratégia de Testes

### 9.1 Testes unitários (`tests/unit/`)
Um arquivo de teste por processor, testando cada um isoladamente com entrada mockada:
- `math_processor`: taxas e médias com lotes sintéticos de tamanho conhecido (ex: 10 respostas, 6 respondidas → taxa_resposta = 60.0)
- `confidence_rules`: lote de 8 categorias candidatas → confirma que só 5 retornam, as de maior confiança
- `catalog/matcher`: texto com gíria conhecida → confirma que retorna o código certo como candidato

### 9.2 Testes de integração (`tests/integration/`)
Testam a composição de 2+ módulos reais (sem mock de IA, usando um stub determinístico de `ai_classifier.py` que retorna respostas fixas):
- Pipeline completo Matemática → Linguística → Semântica → Executiva, com lote pequeno e saída esperada conhecida
- Fallback: simular falha do `ai_classifier.py` e confirmar que a saída final tem `status_semantico: "pendente"` e os campos `matematica`/`linguistica_agregada` presentes

### 9.3 Testes semânticos (`tests/semantic/`)
Específicos da Camada Semântica, usando o catálogo real (não mock):
- Casos de convivência força/dor (Contrato 4.3): "O atendimento foi ótimo, mas a entrega demorou" → confirma 1 força (ATEND) + 1 dor (ENTR) simultâneas
- Casos de ambiguidade hermenêutica: "tranquilo" em contextos diferentes → confirma que a classificação muda com o contexto (não é sempre a mesma categoria)
- Caso de limite: texto sintético desenhado para disparar 8+ candidatos → confirma corte em 5

### 9.4 Testes de regressão (`tests/regression/`)
Conjunto de lotes reais (anonimizados) com saída esperada congelada — toda mudança no motor (novo prompt, nova versão de catálogo) roda contra esse conjunto antes de ir para produção, para detectar mudança de comportamento não intencional. Inclui obrigatoriamente o caso real já validado em produção (mensagem do cliente teste, lote `NSI-TESTE-001`, "Gostei muito do atendimento, mas a entrega demorou" → JSON salvo confirmado em sessão anterior do projeto).

---

## 10. Estratégia de Evolução (v1 → v2 → v3, sem quebrar contrato)

| Tipo de mudança | Exige nova versão de quê | Quebra contrato? |
|---|---|---|
| Nova subcategoria dentro de família existente | `versao_catalogo` (ex: 1.1 → 1.2) | Não |
| Nova família (após governança formal, Contrato 4.8) | `versao_catalogo` (major, ex: 1.x → 2.0) | Não, se os campos do contrato (`familia`, `codigo_catalogo`) continuam preenchidos do mesmo jeito |
| Múltiplas perguntas por lote (Contrato 9.13) | `versao_motor` (ex: 3.1 → 4.0) | Não — `resposta` (string) expande para `interacoes[]` (lista), mas os campos internos de cada interação são os mesmos já definidos |
| Camada de Impacto Comercial (quando houver dado real, Contrato 9.1) | `versao_motor` (major) | Não, é campo aditivo — não remove nem renomeia nada existente |
| ICE v2 (incluindo Evolução/Impacto, Contrato 9.5) | `ice_versao` (campo já existe no contrato, "v1" → "v2") | Não — o contrato já reserva esse campo exatamente para essa migração |
| Troca de provedor de IA (Groq → outro) | `modelo_classificacao.provider` | Não — é exatamente o que esse campo existe para registrar (Contrato 1.1) |

**Princípio geral de evolução:** todo crescimento é **aditivo** — novos campos, novos códigos de catálogo, novos valores de versão. Nenhuma evolução prevista neste blueprint remove ou renomeia um campo já existente no Contrato v3.1, o que preserva compatibilidade para qualquer Dashboard/PDF já construído sobre versões anteriores da saída.

---

## 11. O que este blueprint NÃO define (propositalmente)

- Linguagem/framework de implementação (Python assumido pelo contexto do projeto, mas não fixado aqui)
- Formato exato de armazenamento do catálogo em runtime (JSON vs YAML vs banco) — decisão de implementação
- Escolha entre dataclasses puras, Pydantic, ou outro mecanismo de validação — decisão de implementação
- Fallback para falhas em Matemática ou Linguística (o Contrato só define fallback para indisponibilidade de IA — Seção 1.2; falha em módulo determinístico é cenário não coberto, deliberadamente fora de escopo aqui)
- Pesos do ICE v1, fórmula de Impacto Comercial, lista de sinônimos/gírias além do ponto de partida do catálogo — todos já marcados como não definidos no Contrato (Seção 10), e este blueprint não antecipa essas decisões
- Qualquer linha de código — este documento é blueprint técnico, não implementação
