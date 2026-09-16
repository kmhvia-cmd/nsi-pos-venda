# Contrato Oficial do Motor NSI

> **Status documental:** vigente como contrato fundacional do Motor NSI de classificação. Este documento antecede e não cobre a camada de persistência operacional, PostgreSQL, claims e idempotência introduzidos posteriormente pelas ADR-007 e ADR-008. Em caso de conflito sobre esses temas posteriores, prevalecem as ADRs e especificações mais recentes.

## Núcleo de Inteligência Semântica — Especificação Definitiva

**Versão:** 3.1.1
**Status:** ARQUITETURA NSI v3.1 — FASE CONCEITUAL ENCERRADA. v3.1.1 é aditivo não disruptivo (ver Seção 9.17) — nenhum campo existente foi alterado ou removido, nenhuma regra matemática já aprovada foi modificada. Especificação fechada. Não implementada.
**Escopo:** Define o contrato de entrada e saída do Motor NSI, consumido por Dashboard Operacional, Dashboard Executivo e PDF Executivo.
**Documento complementar:** `catalogo_nsi_v1_operacional.md` (v1.1, 91 entradas) — contém as entradas das 20 famílias semânticas, referenciadas por código a partir deste contrato.

### Mapa de camadas (v3.1)

| # | Camada | Mede |
|---|---|---|
| 1 | Contrato de Entrada + Execução/Resiliência | formato de entrada, rastreabilidade do modelo, fallback sem IA |
| 2 | Matemática | dados operacionais do lote (taxa, tempo, silêncio, qualidade da participação) |
| 3 | Linguística | **como** o cliente falou (forma) |
| 4 | Semântica | **o que** o cliente disse (tema — dor/força, incl. nicho, intensidade semântica) |
| 5 | Experiência Humana | **o que** o cliente sentiu (estado emocional inferido) |
| 6 | Evolução Temporal | variação de indicadores entre lotes da mesma empresa |
| 7 | Executiva | consolidação para decisão de negócio, incl. ações recomendadas |

A Camada de Impacto Comercial proposta em revisão anterior **não entra nesta versão** — ver Seção 9 (decisões de arquitetura) para o motivo.

---

## 0. Princípios do Motor

O NSI não mede sentimento. O NSI mede **experiência comercial**.

Uma resposta pode parecer positiva e esconder uma oportunidade de melhoria. Uma resposta pode parecer negativa e esconder uma força. Por isso o motor nunca classifica isoladamente por polaridade — toda categoria semântica é avaliada por contexto, não por tom.

O NSI não é analisador de sentimento, não é chatbot, não é sistema de NPS, não usa scoring -1/0/+1, não usa "churn", não usa risco abstrato.

Regras transversais a todas as camadas:

- Toda métrica de 0 a 100%. Nunca score arbitrário, nunca +1/-1, nunca "churn".
- Toda conclusão semântica precisa de evidência rastreável (a frase exata que originou a conclusão).
- Toda interpretação semântica carrega percentual de confiança **e** quantidade de ocorrências que sustentam aquele percentual.
- Nada é descartado como ruído: palavra, pontuação, emoji, gíria, silêncio, tempo de resposta, ortografia, vírgula, reticências, caixa alta, regionalismo, sotaque escrito, quantidade de palavras — tudo é dado de entrada para alguma camada.
- A arquitetura assume hoje 1 pergunta → 1 resposta, mas a estrutura de dados é preparada para múltiplas interações por cliente no futuro, sem quebra de contrato.
- **Nenhuma métrica entra no contrato sem fonte de dado real que a sustente.** Se um indicador não pode ser calculado com confiabilidade a partir do que o sistema coleta hoje, ele fica fora da versão atual — não entra como estimativa especulativa rotulada de "futuro".

---

## 1. Contrato de Entrada (o que o Motor recebe)

O Motor opera sobre um **lote** completo, não sobre respostas isoladas.

```json
{
  "empresa": "empresa_teste",
  "segmento": "moda",
  "lote_id": "NSI-TESTE-001",
  "data_envio": "2026-06-12T09:00:00",
  "quantidade_enviada": 50,
  "quantidade_respondida": 31,
  "respostas": [
    {
      "cliente_id": "5511955525922",
      "telefone": "5511955525922",
      "nome": "Kassein",
      "produto": "Produto Teste",
      "resposta": "Gostei muito do atendimento, mas a entrega demorou.",
      "data_envio_mensagem": "2026-06-12T09:00:00",
      "data_resposta": "2026-06-12T09:14:32",
      "status_entrega": "respondido"
    }
  ]
}
```

`segmento` é o campo que decide qual recorte de nicho dentro do catálogo universal o motor prioriza ao classificar (ver Seção 4.4). Valor `"generico"` quando a empresa não tiver segmento definido — nesse caso o motor usa apenas as subcategorias universais, sem prioridade de nicho.

`status_entrega` assume um destes valores, para capturar o silêncio como dado:

- `respondido`
- `visualizado_sem_resposta`
- `entregue_sem_visualizacao`
- `nao_entregue`

Essa estrutura é a mesma que `buscar_lote_por_telefone()` e `salvar_resposta_cliente()` já produzem hoje — o Motor consome o lote inteiro, não dispara nenhuma leitura própria de arquivo.

### 1.1 Rastreabilidade do modelo de classificação (Ajuste 04)

Toda execução da Camada Semântica registra qual modelo de IA gerou aquela classificação, para permitir auditoria futura, reprodutibilidade e comparação entre versões de prompt/modelo. Campo de uso interno — **não exibido ao cliente final**, não aparece em Dashboard Executivo nem PDF.

```json
{
  "modelo_classificacao": {
    "provider": "groq",
    "modelo": "llama",
    "versao_prompt": "v1"
  }
}
```

Este bloco acompanha a saída completa do motor (Seção 8), no nível raiz do JSON, junto de `versao_motor` e `versao_catalogo`.

### 1.2 Fallback operacional sem IA (Ajuste 05)

Se a Camada Semântica não puder ser executada por qualquer motivo — timeout, queda do provedor de IA, limite de uso excedido, erro externo — **o lote continua sendo processado normalmente** pelas camadas que não dependem de IA externa: Matemática e Linguística (Seção 0, ambas calculáveis só com texto livre + timestamps).

Nesse cenário, a saída do motor sinaliza:

```json
{
  "status_semantico": "pendente"
}
```

Os blocos `semantica`, `experiencia_humana_agregada` e `executiva` (que dependem da classificação semântica) ficam ausentes ou marcados como pendentes na mesma execução — nunca bloqueiam a entrega de `matematica` e `linguistica_agregada`. O sistema é reprocessado para a Camada Semântica posteriormente, sem precisar refazer o que já foi calculado. **O motor nunca para de processar um lote inteiro por indisponibilidade da IA.**

---

## 2. Camada Matemática

Converte dados operacionais do lote em indicadores percentuais. Nenhum indicador desta camada depende de interpretação de texto.

| Indicador | Fórmula | Faixa |
|---|---|---|
| Taxa de Resposta | `respondidas ÷ enviadas × 100` | 0–100% |
| Taxa de Silêncio | `(enviadas - respondidas) ÷ enviadas × 100` | 0–100% |
| Taxa de Visualização sem Resposta | `visualizado_sem_resposta ÷ enviadas × 100` | 0–100% |
| Taxa de Não Entrega | `nao_entregue ÷ enviadas × 100` | 0–100% |
| Tempo Médio de Resposta | média de `(data_resposta - data_envio_mensagem)` entre respondidos | em minutos/horas |
| Tempo Mediano de Resposta | mediana da mesma série | em minutos/horas |
| Distribuição de Tempo de Resposta | % respondido em: até 1h / até 24h / até 3 dias / acima de 3 dias | 4 percentuais somando 100% |
| Tamanho Médio da Resposta | média de caracteres das respostas válidas | número absoluto |
| Participação Válida | respostas com texto não vazio ÷ respondidas × 100 | 0–100% |
| Qualidade da Participação | combina riqueza lexical, quantidade de evidências, profundidade, contexto e detalhamento da resposta — mede colaboração, não satisfação nem experiência | 0–100% |

### Estrutura de saída — Camada Matemática

```json
{
  "matematica": {
    "taxa_resposta": 62.0,
    "taxa_silencio": 38.0,
    "taxa_visualizado_sem_resposta": 8.0,
    "taxa_nao_entrega": 2.0,
    "tempo_medio_resposta_minutos": 187.4,
    "tempo_mediano_resposta_minutos": 42.0,
    "distribuicao_tempo_resposta": {
      "ate_1h": 35.5,
      "ate_24h": 41.9,
      "ate_3_dias": 16.1,
      "acima_3_dias": 6.5
    },
    "tamanho_medio_resposta_caracteres": 68,
    "participacao_valida": 96.8,
    "qualidade_participacao_media": 71.0
  }
}
```

> `qualidade_participacao` é calculada por resposta individual (ver Seção 8, `respostas_individuais`) e agregada como média no nível do lote. Não confundir com `tamanho_medio_resposta_caracteres`: tamanho mede quantidade bruta de texto, qualidade mede riqueza do conteúdo — uma resposta curta e específica pode ter qualidade alta; uma resposta longa e repetitiva pode ter qualidade baixa.

---

## 3. Camada Linguística

Interpreta a forma da resposta — não o conteúdo de dor/força (isso é a Camada Semântica). Aqui o motor lê como o cliente falou, não o que ele quis dizer no nível temático.

### 3.1 Dimensões analisadas

| Dimensão | O que captura |
|---|---|
| Sintaxe | estrutura da frase: completa, fragmentada, telegráfica |
| Semântica de superfície | literalidade da frase, antes do agrupamento temático |
| Pragmática | o que a frase faz no contexto (reclamar, elogiar, pedir, desabafar), além do que ela diz literalmente |
| Hermenêutica | interpretação contextual de termos ambíguos ("tranquilo" pode ser elogio ou desinteresse) |
| Semiótica | signos não verbais: emojis, repetição de pontuação, caixa alta |
| Figuras de linguagem | ironia identificável, hiperbole, comparação ("foi um parto", "nota mil") |
| Variação diastrática | nível sociolinguístico do registro (culto, popular, técnico) |
| Variação diatópica | marca regional/geográfica do léxico (regionalismos por região do Brasil) |
| Variação diafásica | grau de formalidade conforme o contexto da fala (formal, neutro, informal, íntimo) |
| Léxico regional/gíria | termos como "top", "massa", "animal", "brabo", "da hora" — mapeados para intensidade positiva, com registro do termo original |
| Emojis | classificados por polaridade e intensidade, não descartados |
| Pontuação | "Muito bom." vs "MUITO BOM!!!" geram intensidades diferentes |
| Abreviações | "vlw", "blz", "tb" — registradas como marca de informalidade, não normalizadas silenciosamente |
| Repetição de palavras/letras | "muitooo bom", "ótimo ótimo" — sinal de ênfase |
| Tempo de resposta (cruzado) | resposta imediata costuma indicar maior engajamento emocional, positivo ou negativo |
| Silêncio | ausência de resposta é registrada como dado linguístico, não como dado faltante |

### 3.2 Indicadores derivados

| Indicador | Faixa |
|---|---|
| Intensidade Emocional | 0–100%, combinando pontuação + caixa alta + emoji + gíria + repetição |
| Polaridade Linguística | -100% a +100% (única métrica bipolar do sistema, pois mede direção, não desempenho) |
| Engajamento Linguístico | 0–100%, combinando tamanho da resposta + tempo de resposta + presença de detalhamento |
| Formalidade | 0–100% (0 = totalmente informal/gírias, 100 = totalmente formal) — corresponde à variação diafásica |
| Marca Regional | 0–100%, intensidade de regionalismo detectado no léxico — corresponde à variação diatópica |
| Ironia Detectada | booleano + confiança, quando aplicável |

### Estrutura de saída — Camada Linguística

```json
{
  "linguistica": {
    "intensidade_emocional": 74.0,
    "polaridade_linguistica": 38.0,
    "engajamento_linguistico": 81.0,
    "formalidade": 22.0,
    "marca_regional": 65.0,
    "ironia_detectada": {"presente": false, "confianca": 0.0},
    "marcadores_detectados": {
      "emojis": [
        {"simbolo": "🔥", "polaridade": "positiva", "intensidade": 90}
      ],
      "girias_regionalismos": [
        {"termo": "da hora", "polaridade": "positiva", "intensidade": 85, "variacao": "diatopica"}
      ],
      "abreviacoes": [],
      "pontuacao_intensificada": true,
      "caixa_alta": false,
      "repeticao_enfase": false
    }
  }
}
```

> Os campos acima refletem a análise de **uma resposta**. Quando agregado em nível de lote, cada métrica vira uma média/distribuição (ver Seção 6).

---

## 4. Camada Semântica

Identifica ocorrências temáticas (dores e forças) dentro do **Catálogo NSI** — base de aproximadamente 150 indicadores organizados em 20 famílias.

### 4.1 As 20 Famílias Semânticas

| Família | Família | Família | Família |
|---|---|---|---|
| Atendimento | Produto | Entrega | Preço |
| Qualidade | Experiência | Confiança | Pós-venda |
| Estrutura | Ambiente | Comunicação | Marketing |
| Tecnologia | Processos | Prazo | Logística |
| Relacionamento | Expectativa | Resultado | Recompra |

Cada família, no catálogo, possui: forças associadas, oportunidades (dores) associadas, sinônimos, gírias, variações regionais e emojis típicos. **A lista completa das 91 entradas (v1.1) vive em `catalogo_nsi_v1_operacional.md`** — este contrato referencia entradas do catálogo por código (ex: `ATEND-003`), nunca embute a lista inteira, para que o catálogo possa ser calibrado e expandido sem exigir nova versão do contrato.

### 4.2 Estrutura hierárquica de classificação

```
Família → Subcategoria → Evidência → Confiança → Percentual
```

Exemplo conceitual:

```
Família: Atendimento
Subcategoria: Tempo de Resposta
Percentual: 83%
Confiança: 92%
Evidências: "demorou", "retornou depois", "aguardei"
```

### 4.3 Limite de classificação por resposta e convivência entre força e dor

**Limite máximo (Ajuste 02):** uma resposta individual pode receber múltiplas classificações simultâneas, com limite máximo de **5 categorias detectadas por resposta**. Quando o motor identificar mais de 5 categorias candidatas, a regra de corte é: ordenar por confiança semântica (`confianca`), manter as 5 maiores, descartar as demais. Isso evita superclassificação e mantém estabilidade estatística — uma resposta não pode "inflar" artificialmente a incidência de dezenas de subcategorias de baixa confiança.

**Convivência força/dor (Ajuste 03):** dentro do limite de 5, força e dor coexistem livremente na mesma resposta — uma não anula a outra. Exemplo:

```
Resposta: "O atendimento foi ótimo, mas a entrega demorou."

Classificação correta:
FORÇA → ATEND-006 (Cordialidade), confiança 90%
DOR   → ENTR-001 (Atraso), confiança 88%
```

Cada categoria é tratada de forma independente, preservando a realidade da experiência real do cliente — que raramente é puramente positiva ou puramente negativa. O motor nunca escolhe "a categoria dominante" e descarta a outra; ambas entram em `categorias_detectadas` (Seção 8), cada uma com seu próprio tipo (`forca`/`dor`), confiança e intensidade semântica.

### 4.4 Nicho — subcategorias setoriais dentro das famílias universais

**Decisão de arquitetura:** o NSI não mantém um catálogo paralelo por segmento. Categorias setoriais (ex: "caimento" e "modelagem" no segmento Moda; "procedimento" e "recuperação" no segmento Clínicas) entram como **subcategorias adicionais dentro das 20 famílias universais já existentes**, marcadas com o segmento ao qual pertencem.

Exemplo: "caimento" não cria uma família nova — vira subcategoria de `PRODUTO`, com a tag `segmento: "moda"`. O motor só aplica/prioriza essas subcategorias quando o campo `segmento` da empresa (Seção 1) corresponder.

| Segmento | Exemplos de subcategoria | Família universal onde entra |
|---|---|---|
| Moda | tecido, caimento, modelagem, numeração, acabamento, confecção | Produto / Qualidade |
| Clínicas | atendimento clínico, procedimento, recuperação, resultado estético, conforto | Atendimento / Experiência / Resultado |
| Restaurantes | temperatura, sabor, apresentação, tempo de preparo | Produto / Prazo |
| Turismo | hospedagem, transfer, check-in, passeios, atendimento local | Logística / Atendimento |
| Autopeças | compatibilidade, instalação, durabilidade, entrega técnica | Produto / Entrega |

Subcategorias de nicho ganham código próprio dentro da família (ex: `PROD-NICHO-MODA-001`), nunca um prefixo de família novo. Isso mantém um único catálogo, uma única lógica de classificação, e permite que uma subcategoria de nicho seja promovida a universal se aparecer com frequência relevante em segmentos diferentes.

### 4.5 Indicadores

| Indicador | Definição |
|---|---|
| Ranking de Incidência de Dores | famílias de dor ordenadas por % de respostas que as mencionam |
| Ranking de Incidência de Forças | famílias de força ordenadas por % de respostas que as mencionam |
| Confiança da Interpretação | % de certeza do motor sobre cada classificação semântica individual |
| Quantidade de Ocorrências | número absoluto de respostas que sustentam cada percentual — acompanha toda confiança, nunca aparece um percentual sem a contagem que o originou |
| Intensidade Semântica | % de gravidade/força do conteúdo relatado — ver regra de fronteira abaixo |

### 4.6 Regra de fronteira: Confiança x Intensidade Linguística x Intensidade Semântica

Três métricas do contrato usam a palavra "intensidade" ou medem algo próximo, mas respondem perguntas diferentes — esta seção fecha a distinção oficialmente, para não repetir a ambiguidade já resolvida entre Linguística e Experiência Humana (Seção 5.0):

| Métrica | Camada | Pergunta que responde | Exemplo |
|---|---|---|---|
| Confiança Semântica (`confianca_media`) | Semântica | Quão seguro o motor está de que classificou certo? | 92% de certeza que isso é "ENTR-001" |
| Intensidade Emocional (Linguística) | Linguística | Quão forte é a forma da fala? | CAIXA ALTA, "!!!", emoji 😡 |
| Intensidade Semântica | Semântica | Quão grave é o fato relatado, independente de como foi dito? | "demorou" (baixa) vs. "demorou tanto que perdi meu compromisso" (alta) |

Intensidade Semântica não mede emoção, não mede confiança de classificação, não mede estilo de escrita — mede a severidade do conteúdo relatado. Uma resposta pode ter Intensidade Linguística baixa (frase calma, sem pontuação forte) e Intensidade Semântica alta (o fato relatado é grave), e vice-versa.

### Estrutura de saída — Camada Semântica

```json
{
  "semantica": {
    "dores_identificadas": [
      {
        "codigo_catalogo": "ENTR-002",
        "familia": "ENTREGA",
        "subcategoria": "atraso",
        "nicho": null,
        "incidencia_percentual": 24.0,
        "confianca_media": 88.0,
        "intensidade_semantica_media": 61.0,
        "ocorrencias": 12,
        "evidencias": [
          {"cliente_id": "5511955525922", "trecho": "a entrega demorou", "confianca": 91.0, "intensidade_semantica": 45.0}
        ]
      }
    ],
    "forcas_identificadas": [
      {
        "codigo_catalogo": "ATEND-007",
        "familia": "ATENDIMENTO",
        "subcategoria": "cordialidade",
        "nicho": null,
        "incidencia_percentual": 58.0,
        "confianca_media": 92.0,
        "intensidade_semantica_media": 70.0,
        "ocorrencias": 29,
        "evidencias": [
          {"cliente_id": "5511955525922", "trecho": "gostei muito do atendimento", "confianca": 94.0, "intensidade_semantica": 68.0}
        ]
      }
    ]
  }
}
```

`intensidade_semantica` existe tanto por evidência individual quanto como média agregada por subcategoria (`intensidade_semantica_media`) — segue o mesmo padrão de `confianca_media`/`ocorrencias`.

### 4.7 Área responsável — orientação contextual, não verdade fixa

Cada entrada do catálogo carrega de 1 a 2 áreas de negócio possíveis (`catalogo_nsi_v1_operacional.md`), com uma marcada como primária. O motor usa essas áreas como **orientação de partida**, não como atribuição automática definitiva — o contexto do lote (volume, empresa, histórico) pode levar o motor a priorizar a área secundária em vez da primária quando fizer mais sentido para aquele caso específico.

Exemplo: `COMU-001` (Falta de informação) lista Atendimento como área primária e Marketing/Comercial como secundárias. Se o padrão de ocorrência em um lote específico estiver fortemente ligado a anúncios (e não a interações de atendimento), o motor pode reportar Marketing como área mais relevante para aquele lote, mesmo com Atendimento marcada como primária no catálogo.

Este campo é informativo para o Dashboard (agrupar problemas por departamento), nunca prescritivo de ação — a ação recomendada em si é responsabilidade exclusiva da Camada Executiva (Seção 7.4), nunca do catálogo.

### 4.8 Governança do catálogo — criação de famílias (Ajuste 06)

**Regra permanente:** nenhuma nova família semântica pode ser criada sem auditoria formal. O catálogo cresce por **subcategoria** dentro das 20 famílias existentes (calibração contínua, sem exigir nova versão do contrato — Seção 4.1), mas a criação de uma família nova (21ª família) segue um fluxo obrigatório:

```
Necessidade identificada nos dados reais
       ↓
Registrada como subcategoria dentro de uma família existente
       ↓
Validação recorrente (aparece com frequência relevante em múltiplos lotes/empresas)
       ↓
Avaliação formal: a subcategoria realmente não se encaixa em nenhuma das 20 famílias?
       ↓
Possível promoção para família nova (decisão consciente, documentada como as demais nesta Seção 9)
```

Isso evita explosão descontrolada de famílias e preserva a simplicidade do modelo — a mesma lógica que já se aplicou à decisão de não criar catálogo paralelo de Nicho (Seção 4.4) e à família CONC reservada, não criada por impulso (Seção 9.12).

`nicho` é `null` para subcategorias universais e recebe o nome do segmento (ex: `"moda"`) quando a subcategoria detectada for específica de nicho.

Toda entrada em `dores_identificadas` e `forcas_identificadas` é obrigatoriamente rastreável — nunca aparece uma categoria sem ao menos uma evidência textual de origem, e nunca uma confiança sem a contagem de ocorrências que a sustenta.

---

## 5. Camada de Experiência Humana

### 5.0 Regra de fronteira com a Camada Linguística (resolve ponto cego identificado em auditoria)

**Linguística mede a forma da fala — como foi dito.** Intensidade emocional, polaridade, formalidade: tudo deriva de sinais de superfície (pontuação, caixa alta, emoji, léxico).

**Experiência Humana mede o estado emocional inferido — o que foi sentido.** É uma camada de interpretação de segunda ordem: usa os sinais linguísticos **como insumo**, mas cruza com o conteúdo semântico (a categoria detectada) e o contexto (tempo de resposta, tamanho da resposta) para inferir um estado mais específico que a Linguística não tem vocabulário para descrever.

Exemplo do porquê as duas camadas não competem: "Foi bom." tem `polaridade_linguistica` positiva e `intensidade_emocional` baixa (frase curta, sem pontuação intensificada, sem emoji) — isso já é suficiente para a Linguística. Mas só a camada de Experiência Humana decide se isso é "Indiferença" (baixo entusiasmo apesar de polaridade positiva) ou "Confiança tranquila" (positivo sem precisar de entusiasmo) — distinção que depende de cruzar com outras respostas do mesmo cliente/lote, não só da frase isolada.

### 5.1 Indicadores

| Indicador | Definição |
|---|---|
| Entusiasmo | intensidade de empolgação expressa, distinta de polaridade simples |
| Confiança (do cliente na empresa) | segurança percebida na relação, não confiança estatística do motor |
| Frustração | insatisfação com componente emocional, distinta de dor temática |
| Envolvimento | grau de engajamento emocional com a experiência, não só linguístico |
| Empolgação | pico emocional positivo momentâneo |
| Segurança | ausência de receio/dúvida na relação com a empresa |
| Indiferença | ausência de carga emocional, mesmo com polaridade definida |
| Lealdade | sinal de vínculo contínuo, não pontual |
| Gratidão | reconhecimento explícito de benefício recebido |
| Desgaste | sinal de cansaço/saturação na relação com a empresa |

Todos os indicadores: 0 a 100%, com evidência e confiança, seguindo a mesma regra de rastreabilidade da Camada Semântica.

### Estrutura de saída — Camada de Experiência Humana

```json
{
  "experiencia_humana": {
    "entusiasmo": 22.0,
    "confianca_cliente": 78.0,
    "frustracao": 12.0,
    "envolvimento": 19.0,
    "empolgacao": 15.0,
    "seguranca": 80.0,
    "indiferenca": 10.0,
    "lealdade": 65.0,
    "gratidao": 30.0,
    "desgaste": 8.0
  }
}
```

> Estrutura por resposta individual. Em nível de lote (Seção 7), cada indicador vira média/distribuição, igual à Camada Linguística agregada.

---

## 6. Camada de Evolução Temporal

Compara indicadores de um lote com lotes anteriores da mesma empresa.

### 6.1 Pré-requisito: versionamento do catálogo (resolve ponto cego identificado em auditoria)

Toda saída do motor carrega `versao_catalogo` (Seção 7). A Evolução Temporal só compara dois lotes quando ambos referenciam a **mesma** `versao_catalogo`. Se o catálogo mudou entre os lotes comparados, o motor sinaliza explicitamente `comparabilidade: "parcial"` e lista quais subcategorias não existiam na versão anterior — nunca apresenta uma variação percentual como se fosse limpa quando a base de cálculo mudou.

### 6.2 Indicadores

| Indicador | Definição |
|---|---|
| Variação por Família | diferença percentual de incidência de uma família entre o lote atual e o lote anterior comparável |
| Variação por Indicador Matemático | diferença de taxa de resposta, tempo médio etc. entre lotes |
| Tendência | classificação simples: "subindo", "estável", "caindo", calculada sobre os últimos N lotes comparáveis |

### Estrutura de saída — Camada de Evolução Temporal

```json
{
  "evolucao_temporal": {
    "lote_comparado_id": "NSI-2026-05-LOTE-014",
    "comparabilidade": "total",
    "variacoes_familia": [
      {"familia": "ATENDIMENTO", "percentual_anterior": 72.0, "percentual_atual": 88.0, "variacao": 16.0, "tendencia": "subindo"},
      {"familia": "ENTREGA", "percentual_anterior": 85.0, "percentual_atual": 58.0, "variacao": -27.0, "tendencia": "caindo"}
    ],
    "variacoes_matematica": [
      {"indicador": "taxa_resposta", "anterior": 55.0, "atual": 62.0, "variacao": 7.0}
    ]
  }
}
```

> Esta camada só aparece na saída quando existe ao menos um lote anterior comparável da mesma empresa. Para o primeiro lote de uma empresa, o campo `evolucao_temporal` é omitido — não aparece como `null` nem com variação zerada, porque "sem dado anterior" é diferente de "sem variação".

---

## 7. Camada Executiva

Consolida as camadas anteriores em uma leitura de negócio. O empresário não quer linguística — quer decisão.

### 7.1 Componentes

| Componente | Definição |
|---|---|
| Top 15 Forças | as 15 forças de maior incidência no lote, em percentual |
| Top 15 Oportunidades | as 15 dores de maior incidência no lote, em percentual |
| Top 15 Prioridades | ranking combinando incidência + confiança das dores — **não** inclui "impacto comercial" (ver Seção 9.1) |
| Ações Recomendadas | geradas pela Camada Executiva a partir do lote completo (incidência, evidências, tendência, contexto) — **nunca** uma regra fixa por categoria do catálogo (ver Seção 7.4) |
| Resumo Executivo | leitura geral do lote, visão de topo |
| Resumo Comercial | leitura focada em conversão, recompra e indicação |
| Resumo Operacional | leitura focada em processos, prazo e logística |
| Resumo de Atendimento | leitura focada na família Atendimento |
| Resumo de Produto | leitura focada na família Produto/Qualidade |
| Resumo de Experiência | leitura focada na percepção geral do cliente |
| Resumo Evolutivo | leitura da variação frente ao lote anterior — omitido se `evolucao_temporal` não existir |
| Resumo de Nicho | leitura focada nas subcategorias de segmento — omitido se `segmento` for `"generico"` |
| ICE NSI | Índice de Confiança e Experiência — indicador único, 0 a 100% |

Todos os resumos em linguagem empresarial simples, sem jargão técnico de linguística ou estatística.

### 7.2 Top 15 Prioridades — critério de ranqueamento

Como a Camada de Impacto Comercial não existe nesta versão (Seção 9.1), "prioridade" aqui é **operacional, não preditiva**: combina `incidencia_percentual × confianca_media` das dores identificadas. Isso responde "o que aparece com mais frequência e mais certeza", não "o que mais afeta receita" — distinção que o Dashboard e o PDF devem deixar explícita ao exibir este ranking, para não sugerir uma previsão de negócio que o motor não calcula.

### 7.3 Áreas Responsáveis no agregado do lote

A Camada Executiva consolida `area_responsavel` (Seção 4.7) de todas as dores/forças do lote para gerar uma visão por departamento — ex: "60% das oportunidades deste lote concentram-se em Atendimento". Essa consolidação usa a área primária de cada subcategoria por padrão, mas pode reportar a área secundária quando o padrão de evidências do lote apontar mais fortemente para ela (mesma lógica contextual da Seção 4.7).

### 7.4 Ações Recomendadas — geradas pelo motor, nunca fixas no catálogo

**Decisão de arquitetura:** o catálogo não carrega `acao_recomendada` por entrada. A mesma subcategoria (ex: `ENTR-001` — Atraso) pode exigir ações completamente diferentes dependendo da empresa, do segmento, do histórico de lotes e do volume de ocorrências — uma regra fixa de "categoria X sempre sugere ação Y" contradiria o princípio central do motor (avaliar por contexto, nunca isoladamente).

A Camada Executiva gera as ações recomendadas no momento do processamento do lote, combinando:

- Incidência e confiança da subcategoria naquele lote específico
- Evidências textuais reais daquele lote (não exemplos genéricos do catálogo)
- Tendência, quando `evolucao_temporal` existir (ex: uma dor crescente pede ação diferente de uma dor estável)
- `segmento` da empresa, quando relevante

### Estrutura de saída — Ações Recomendadas

```json
{
  "acoes_recomendadas": [
    {
      "posicao": 1,
      "categoria": "Prazo",
      "codigo_catalogo": "ENTR-001",
      "area_responsavel": "Logística",
      "recomendacao": "Atraso de entrega é a oportunidade mais recorrente neste lote, com tendência de alta frente ao período anterior. Revisar prazo combinado com a transportadora.",
      "baseado_em": {"ocorrencias": 12, "confianca_media": 88.0, "tendencia": "subindo"}
    }
  ]
}
```

> Este bloco entra como parte da saída da Camada Executiva (Seção 8), nunca como dado estático do catálogo.

### 7.5 ICE NSI — Índice de Confiança e Experiência (v1)

**Decisão de arquitetura:** o ICE v1 usa apenas fatores com dado real e verificável hoje. Evolução e Impacto Comercial ficam reservados para uma v2 do índice, quando houver dado longitudinal suficiente (ver Seção 9).

Composição conceitual da v1:

```
ICE_v1 = f(taxa_resposta, polaridade_linguistica, engajamento_linguistico,
            incidencia_forcas, incidencia_dores, confianca_media_semantica)
```

**A especificação matemática completa — pesos, normalização, fórmula final, critério híbrido de liberação do cálculo e faixas de interpretação — está oficialmente congelada na Seção 9.17.** Esta seção mantém apenas a composição conceitual de alto nível; qualquer detalhe de implementação do ICE deve referenciar a 9.17, não esta seção.

O ICE é a única métrica que resume o lote inteiro em um número.

### Estrutura de saída — Camada Executiva

```json
{
  "executiva": {
    "status_ice": "calculado",
    "ice_nsi": 78.5,
    "ice_versao": "v1",
    "motivo": null,
    "top_forcas": [
      {"posicao": 1, "categoria": "Atendimento", "percentual": 58.0},
      {"posicao": 2, "categoria": "Qualidade", "percentual": 51.0}
    ],
    "top_oportunidades": [
      {"posicao": 1, "categoria": "Prazo", "percentual": 24.0},
      {"posicao": 2, "categoria": "Comunicação", "percentual": 17.0}
    ],
    "top_prioridades": [
      {"posicao": 1, "categoria": "Prazo", "criterio": "incidencia_x_confianca", "valor": 21.1}
    ],
    "areas_responsaveis_agregado": [
      {"area": "Logística", "percentual_oportunidades": 24.0},
      {"area": "Atendimento", "percentual_oportunidades": 17.0}
    ],
    "acoes_recomendadas": [
      {
        "posicao": 1,
        "categoria": "Prazo",
        "codigo_catalogo": "ENTR-001",
        "area_responsavel": "Logística",
        "recomendacao": "Atraso de entrega é a oportunidade mais recorrente neste lote, com tendência de alta frente ao período anterior. Revisar prazo combinado com a transportadora.",
        "baseado_em": {"ocorrencias": 12, "confianca_media": 88.0, "tendencia": "subindo"}
      }
    ],
    "resumo_executivo": "Os clientes demonstram elevada percepção de qualidade e atendimento. As principais oportunidades de melhoria estão relacionadas ao prazo de entrega e comunicação. Observa-se forte predisposição de recomendação da empresa.",
    "resumo_comercial": "Alta propensão à recompra e indicação, sustentada pela percepção positiva de atendimento.",
    "resumo_operacional": "Prazo de entrega é o ponto de atenção operacional mais recorrente neste lote.",
    "resumo_atendimento": "Atendimento é a maior força identificada, com destaque para cordialidade.",
    "resumo_produto": "Produto bem avaliado em qualidade, sem incidência relevante de defeito.",
    "resumo_experiencia": "Experiência geral positiva, com oportunidade concentrada na etapa de logística.",
    "resumo_evolutivo": "Atendimento avançou 16 pontos desde o último lote; Entrega caiu 27 pontos e merece atenção.",
    "resumo_nicho": null
  }
}
```

---

## 8. Estrutura JSON Final — Contrato Dashboard / PDF

Este é o objeto completo que o Motor entrega como saída final, consumido por Dashboard Operacional, Dashboard Executivo e PDF Executivo.

```json
{
  "empresa": "empresa_teste",
  "segmento": "generico",
  "lote_id": "NSI-TESTE-001",
  "data_processamento": "2026-06-20T12:00:00",
  "versao_motor": "3.1",
  "versao_catalogo": "1.1",
  "status_semantico": "concluido",
  "evidencias_semanticas_validas": 41,
  "modelo_classificacao": {
    "provider": "groq",
    "modelo": "llama",
    "versao_prompt": "v1"
  },

  "matematica": {
    "taxa_resposta": 62.0,
    "taxa_silencio": 38.0,
    "taxa_visualizado_sem_resposta": 8.0,
    "taxa_nao_entrega": 2.0,
    "tempo_medio_resposta_minutos": 187.4,
    "tempo_mediano_resposta_minutos": 42.0,
    "distribuicao_tempo_resposta": {
      "ate_1h": 35.5,
      "ate_24h": 41.9,
      "ate_3_dias": 16.1,
      "acima_3_dias": 6.5
    },
    "tamanho_medio_resposta_caracteres": 68,
    "participacao_valida": 96.8,
    "qualidade_participacao_media": 71.0
  },

  "linguistica_agregada": {
    "intensidade_emocional_media": 74.0,
    "polaridade_linguistica_media": 38.0,
    "engajamento_linguistico_medio": 81.0,
    "formalidade_media": 22.0,
    "marca_regional_media": 65.0
  },

  "semantica": {
    "dores_identificadas": [
      {
        "codigo_catalogo": "ENTR-002",
        "familia": "ENTREGA",
        "subcategoria": "atraso",
        "nicho": null,
        "incidencia_percentual": 24.0,
        "confianca_media": 88.0,
        "intensidade_semantica_media": 61.0,
        "ocorrencias": 12,
        "evidencias": [
          {"cliente_id": "5511955525922", "trecho": "a entrega demorou", "confianca": 91.0, "intensidade_semantica": 45.0}
        ]
      }
    ],
    "forcas_identificadas": [
      {
        "codigo_catalogo": "ATEND-007",
        "familia": "ATENDIMENTO",
        "subcategoria": "cordialidade",
        "nicho": null,
        "incidencia_percentual": 58.0,
        "confianca_media": 92.0,
        "intensidade_semantica_media": 70.0,
        "ocorrencias": 29,
        "evidencias": [
          {"cliente_id": "5511955525922", "trecho": "gostei muito do atendimento", "confianca": 94.0, "intensidade_semantica": 68.0}
        ]
      }
    ]
  },

  "experiencia_humana_agregada": {
    "entusiasmo_medio": 22.0,
    "confianca_cliente_media": 78.0,
    "frustracao_media": 12.0,
    "envolvimento_medio": 19.0,
    "empolgacao_media": 15.0,
    "seguranca_media": 80.0,
    "indiferenca_media": 10.0,
    "lealdade_media": 65.0,
    "gratidao_media": 30.0,
    "desgaste_medio": 8.0
  },

  "evolucao_temporal": {
    "lote_comparado_id": "NSI-2026-05-LOTE-014",
    "comparabilidade": "total",
    "variacoes_familia": [
      {"familia": "ATENDIMENTO", "percentual_anterior": 72.0, "percentual_atual": 88.0, "variacao": 16.0, "tendencia": "subindo"}
    ],
    "variacoes_matematica": [
      {"indicador": "taxa_resposta", "anterior": 55.0, "atual": 62.0, "variacao": 7.0}
    ]
  },

  "executiva": {
    "status_ice": "calculado",
    "ice_nsi": 78.5,
    "ice_versao": "v1",
    "motivo": null,
    "top_forcas": [
      {"posicao": 1, "categoria": "Atendimento", "percentual": 58.0},
      {"posicao": 2, "categoria": "Qualidade", "percentual": 51.0}
    ],
    "top_oportunidades": [
      {"posicao": 1, "categoria": "Prazo", "percentual": 24.0},
      {"posicao": 2, "categoria": "Comunicação", "percentual": 17.0}
    ],
    "top_prioridades": [
      {"posicao": 1, "categoria": "Prazo", "criterio": "incidencia_x_confianca", "valor": 21.1}
    ],
    "areas_responsaveis_agregado": [
      {"area": "Logística", "percentual_oportunidades": 24.0},
      {"area": "Atendimento", "percentual_oportunidades": 17.0}
    ],
    "acoes_recomendadas": [
      {
        "posicao": 1,
        "categoria": "Prazo",
        "codigo_catalogo": "ENTR-001",
        "area_responsavel": "Logística",
        "recomendacao": "Atraso de entrega é a oportunidade mais recorrente neste lote, com tendência de alta frente ao período anterior. Revisar prazo combinado com a transportadora.",
        "baseado_em": {"ocorrencias": 12, "confianca_media": 88.0, "tendencia": "subindo"}
      }
    ],
    "resumo_executivo": "Os clientes demonstram elevada percepção de qualidade e atendimento. As principais oportunidades de melhoria estão relacionadas ao prazo de entrega e comunicação. Observa-se forte predisposição de recomendação da empresa.",
    "resumo_comercial": "Alta propensão à recompra e indicação, sustentada pela percepção positiva de atendimento.",
    "resumo_operacional": "Prazo de entrega é o ponto de atenção operacional mais recorrente neste lote.",
    "resumo_atendimento": "Atendimento é a maior força identificada, com destaque para cordialidade.",
    "resumo_produto": "Produto bem avaliado em qualidade, sem incidência relevante de defeito.",
    "resumo_experiencia": "Experiência geral positiva, com oportunidade concentrada na etapa de logística.",
    "resumo_evolutivo": "Atendimento avançou 16 pontos desde o último lote.",
    "resumo_nicho": null
  },

  "respostas_individuais": [
    {
      "cliente_id": "5511955525922",
      "telefone": "5511955525922",
      "resposta": "Gostei muito do atendimento, mas a entrega demorou.",
      "qualidade_participacao": 71.0,
      "linguistica": {
        "intensidade_emocional": 74.0,
        "polaridade_linguistica": 38.0,
        "engajamento_linguistico": 81.0,
        "formalidade": 22.0,
        "marca_regional": 65.0,
        "ironia_detectada": {"presente": false, "confianca": 0.0},
        "marcadores_detectados": {
          "emojis": [],
          "girias_regionalismos": [],
          "abreviacoes": [],
          "pontuacao_intensificada": false,
          "caixa_alta": false,
          "repeticao_enfase": false
        }
      },
      "experiencia_humana": {
        "entusiasmo": 22.0,
        "confianca_cliente": 78.0,
        "frustracao": 12.0,
        "envolvimento": 19.0,
        "empolgacao": 15.0,
        "seguranca": 80.0,
        "indiferenca": 10.0,
        "lealdade": 65.0,
        "gratidao": 30.0,
        "desgaste": 8.0
      },
      "categorias_detectadas": [
        {"tipo": "forca", "codigo_catalogo": "ATEND-007", "familia": "ATENDIMENTO", "subcategoria": "cordialidade", "nicho": null, "area_responsavel": "Atendimento", "confianca": 94.0, "intensidade_semantica": 68.0},
        {"tipo": "dor", "codigo_catalogo": "ENTR-002", "familia": "ENTREGA", "subcategoria": "atraso", "nicho": null, "area_responsavel": "Logística", "confianca": 91.0, "intensidade_semantica": 45.0}
      ]
    }
  ]
}
```

> `categorias_detectadas` tem no máximo 5 entradas por resposta (Seção 4.3) — força e dor coexistem livremente dentro desse limite, ordenadas por `confianca` quando mais de 5 forem candidatas.

### Notas sobre o contrato

- `matematica` e `linguistica_agregada` são sempre calculáveis com os dados atuais (texto livre + timestamps), sem dependência de IA externa.
- `semantica`, `experiencia_humana_agregada` e `executiva` dependem do motor de classificação (Groq ou equivalente) — fora do escopo desta especificação, que define apenas o formato, não a implementação.
- `evolucao_temporal` é omitido por completo (não enviado como `null`) quando não há lote anterior comparável.
- `respostas_individuais` preserva a granularidade por cliente, permitindo que o Dashboard Operacional explore caso a caso, enquanto `executiva` e os agregados servem ao Dashboard Executivo e ao PDF.
- A estrutura está pronta para suportar múltiplas respostas por cliente no futuro: bastaria `respostas_individuais[].resposta` virar `respostas_individuais[].interacoes[]`, sem alterar o restante do contrato.

---

## 9. Decisões de Arquitetura (consolidado v3.0 → v3.1)

Esta seção registra decisões tomadas a partir das auditorias críticas da arquitetura, para que o histórico de "por que não incluímos X" não se perca.

### 9.1 Camada de Impacto Comercial — não incluída nesta versão

A proposta original pedia um indicador de "impacto" por categoria (ex: Entrega = 92% de impacto), distinto de incidência. **Decisão: não incluir.** Impacto comercial real (efeito sobre recompra, ticket médio, churn) não é observável a partir de texto livre de um único lote — exige dados longitudinais de múltiplos lotes cruzados com comportamento de compra real, que o NSI não coleta hoje. Incluir esse campo agora, mesmo como estimativa "qualitativa", criaria um número de aparência objetiva sem base de evidência, violando o princípio de rastreabilidade que rege todo o resto do contrato. Fica reservado para uma fase futura, condicionada à existência de dado real — não há campo "placeholder" no contrato atual.

### 9.2 Camada de Nicho — resolvida como subcategoria, não catálogo paralelo

Ver Seção 4.4. Decisão tomada para evitar duplicar a lógica de classificação e para não exigir, antes da hora, resolver como o motor decidiria automaticamente o segmento de uma empresa sem informação explícita. O campo `segmento` (Seção 1) resolve isso de forma simples: a empresa declara o segmento no cadastro, o motor prioriza as subcategorias correspondentes.

### 9.3 Evolução Temporal — implementada com salvaguarda de versionamento

Ver Seção 6.1. O risco identificado na auditoria (comparar lotes com catálogos diferentes sem avisar) é resolvido pelo campo `versao_catalogo` e pelo campo `comparabilidade`, que nunca deixam uma variação percentual aparecer como "limpa" quando a base de cálculo mudou no meio do caminho.

### 9.4 Experiência Humana vs. Linguística — fronteira documentada

Ver Seção 5.0. A sobreposição identificada na auditoria foi resolvida documentando explicitamente que Linguística mede forma e Experiência Humana mede estado emocional inferido, cruzando sinais linguísticos com contexto — não são dois caminhos paralelos calculando a mesma coisa.

### 9.5 ICE NSI — fechado como v1 reduzido

Ver Seção 7.5. Removidos Evolução e Impacto da fórmula até que tenham dado real de suporte, para que o índice não misture fatores confiáveis com fatores especulativos sob o mesmo número.

### 9.6 Indicador de saúde do lote — registrado como ponto cego, não fechado

A auditoria identificou que nenhuma camada mede se uma taxa de resposta baixa é sintoma de desinteresse do cliente ou de falha técnica do próprio disparo (ex: template mal configurado, horário de envio ruim). Este contrato não resolve isso agora — fica registrado como lacuna conhecida para entrar em versão futura, quando houver histórico suficiente de taxa de resposta por empresa para detectar anomalia.

### 9.7 `peso_relevancia` — rejeitado por reintroduzir o mesmo problema do Impacto Comercial

Uma segunda rodada de auditoria propôs um peso fixo de 1 a 5 por entrada do catálogo, classificando "impacto" de cada subcategoria, com a justificativa de ser "uso interno". **Decisão: não incluir, nem como campo interno.** Um peso fixo, definido manualmente hoje sem dado real, é o mesmo problema do Impacto Comercial (Seção 9.1) com outro nome — e entraria pela porta dos fundos no cálculo de `top_prioridades` (Seção 7.2), que foi deliberadamente mantido livre de qualquer fator de impacto não verificável. `peso_relevancia` só poderá existir quando houver dado histórico real (recorrência, recompra, correlação observada entre lotes) que sustente o valor — nunca como número arbitrário definido na criação do catálogo.

### 9.8 `acao_recomendada` — removida do catálogo, vira responsabilidade da Camada Executiva

A mesma subcategoria pode exigir ações diferentes dependendo da empresa, segmento, histórico e volume de ocorrências — uma ação fixa por entrada do catálogo (ex: "Atraso → Revisar logística", sempre, para qualquer empresa) contradiz o princípio central do motor de avaliar por contexto. **Decisão: o catálogo não carrega `acao_recomendada`.** Esse componente passa a ser gerado pela Camada Executiva (Seção 7.4), a partir do lote completo — incidência, evidências reais daquele lote, tendência e segmento — nunca como regra estática.

### 9.9 `area_responsavel` — contextual, com até 2 áreas possíveis por entrada

Uma área única e fixa por entrada do catálogo forçaria respostas artificialmente certas em casos ambíguos (ex: "Falta de informação" pode ser tanto Atendimento quanto Marketing). **Decisão: cada entrada do catálogo carrega até 2 áreas possíveis, uma marcada como primária.** O motor usa isso como orientação de partida (Seção 4.7), podendo priorizar a área secundária quando o padrão de evidências do lote específico apontar mais fortemente para ela. O catálogo nunca é tratado como verdade absoluta de departamento.

### 9.10 `intensidade_semantica` — aprovada, com fronteira formal frente a Confiança e Intensidade Linguística

Ver Seção 4.6. Diferente de `peso_relevancia` e `acao_recomendada`, esta métrica não duplica nem reabre decisão anterior: mede a gravidade do conteúdo relatado (ex: "demorou" vs. "demorou tanto que perdi meu compromisso"), distinta de confiança de classificação e de intensidade de forma. Aprovada e incorporada à Camada Semântica (Seção 4.5) com regra de fronteira explícita para não repetir a ambiguidade já identificada entre Linguística e Experiência Humana.

### 9.11 Qualidade da Participação — aprovada sem ressalvas, incorporada à Camada Matemática

Mede riqueza lexical, quantidade de evidências, profundidade e detalhamento da resposta — distinta de `tamanho_medio_resposta_caracteres` (quantidade bruta) e de qualquer métrica de satisfação ou experiência. Sem sobreposição identificada com indicadores existentes. Incorporada à Seção 2.

### 9.12 Família CONC (Concorrência) — reservada, com tensão conhecida frente a RCMP-002

A família CONC (fenômenos como "troquei de fornecedor", "o concorrente era melhor") permanece **reservada para implementação futura, não implementada agora**. Fica registrado que `RCMP-002` (Migração para concorrente, dentro da família Recompra) cobre hoje o mesmo fenômeno que CONC cobriria. Se CONC for criada no futuro, ela deve **absorver** `RCMP-002`, nunca coexistir com ela — caso contrário, a mesma frase do cliente seria contada em duas categorias diferentes, inflando ocorrências artificialmente.

### 9.13 Preparação para múltiplas perguntas por lote (Ajuste 07)

**Estado atual:** a arquitetura opera sob o modelo 1 pergunta → 1 resposta por cliente (Seção 0).

**Decisão arquitetural registrada para o futuro:** o modelo evoluirá para N perguntas → N respostas por cliente, sem exigir quebra de contrato. A compatibilidade já está embutida na estrutura de dados atual: `respostas_individuais[].resposta` (string única, Seção 8) é o ponto exato que se expande para `respostas_individuais[].interacoes[]` (lista de respostas, uma por pergunta), preservando todos os demais campos (`linguistica`, `experiencia_humana`, `categorias_detectadas`) — que passam a existir por interação individual dentro da lista, em vez de por resposta única.

Esta seção apenas documenta a decisão e a compatibilidade — **não implementar agora**. Nenhuma mudança de código ou estrutura é necessária até que o produto realmente precise de múltiplas perguntas por lote.

### 9.14 Limite de classificação e convivência força/dor — fechados sem ressalvas

O limite de 5 categorias por resposta (Seção 4.3) resolve um risco de estabilidade estatística que não havia sido endereçado nas auditorias anteriores: sem teto, uma resposta longa e rica poderia inflar artificialmente a contagem de dezenas de subcategorias de baixa confiança. A regra de corte por `confianca` (manter as 5 maiores) é objetiva e auditável. A convivência força/dor na mesma resposta já era implícita no design (Seção 4 sempre tratou `dores_identificadas` e `forcas_identificadas` como listas independentes), mas faltava a afirmação explícita de que uma não anula a outra — agora registrada formalmente.

### 9.15 Rastreabilidade e fallback — fecham a lacuna operacional entre "especificado" e "executável"

`modelo_classificacao` (Seção 1.1) e o fallback sem IA (Seção 1.2) não mudam nenhuma regra de negócio já decidida — fecham uma lacuna puramente operacional: o contrato definia o que o motor produz, mas não o que acontece quando a IA externa falha. Sem essa seção, uma queda do provedor de IA poderia ser interpretada como "bloquear o lote inteiro", o que contradiria o princípio de o motor nunca parar por indisponibilidade externa.

### 9.16 Governança do catálogo — formaliza o que já era prática implícita

A regra de não criar família nova sem auditoria (Seção 4.8) formaliza o que já vinha sendo seguido na prática: a família CONC foi conscientemente **reservada, não criada por impulso** (Seção 9.12), e o crescimento do catálogo desde a v1.0 sempre ocorreu por subcategoria dentro das 20 famílias, nunca por família nova. Esta seção apenas torna esse comportamento uma regra escrita, em vez de um padrão observado.

### 9.17 ICE NSI v1 — fórmula, pesos e critério de bloqueio oficialmente congelados (Revisão v3.1.1, aditivo não disruptivo)

Esta seção fecha definitivamente a especificação matemática do ICE v1, referenciada de forma conceitual na Seção 7.5. Nenhum campo existente foi alterado ou removido; nenhuma regra matemática já aprovada em seções anteriores foi modificada — esta é uma revisão estritamente aditiva (v3.1 → v3.1.1).

**Pesos oficiais (somam 100%):**

| Fator | Peso | Direção |
|---|---|---|
| Incidência de Forças | 25% | Positiva |
| Incidência de Dores | 25% | Negativa (entra invertida na fórmula) |
| Confiança Semântica Média | 20% | Positiva |
| Polaridade Linguística | 10% | Positiva (normalizada antes de aplicar o peso) |
| Engajamento Linguístico | 10% | Positiva |
| Taxa de Resposta | 10% | Positiva |

**Normalização da Polaridade Linguística** (que no Contrato Seção 3.2 varia de -100 a +100, única métrica bipolar do sistema):

```
polaridade_normalizada = (polaridade_linguistica + 100) / 2
```

**Fórmula oficial:**

```
ICE_v1 =
      0.25 × incidencia_forcas
    + 0.25 × (100 - incidencia_dores)
    + 0.20 × confianca_media_semantica
    + 0.10 × ((polaridade_linguistica + 100) / 2)
    + 0.10 × engajamento_linguistico
    + 0.10 × taxa_resposta
```

Por construção, com todos os fatores de entrada já garantidos em 0–100 pelas camadas que os produzem, o resultado está sempre em 0–100, sem necessidade de normalização adicional na fórmula em si (uma salvaguarda defensiva de clamp é, ainda assim, mantida na implementação por princípio de robustez contra entrada inesperada).

**Critério híbrido de liberação do cálculo:** o ICE só é calculado quando **ao menos um** dos dois critérios abaixo é atendido:

```
(cobertura_semantica >= 20%)  OU  (evidencias_semanticas_validas >= 10)
```

Onde:
- `cobertura_semantica = respostas_com_categoria_detectada / total_respostas × 100`
- `evidencias_semanticas_validas` = contagem total de evidências usadas pelo Motor para justificar classificações semânticas no lote (ver definição do indicador abaixo)

**Motivo do critério híbrido:** Cobertura responde "o Motor encontrou informação suficiente?"; Confiança (já parte da fórmula) responde "o Motor acredita nessa informação?" — são conceitos diferentes, ambos necessários. O critério B (evidência absoluta) existe para que lotes grandes com poucas respostas extremamente ricas em conteúdo não tenham o ICE bloqueado injustamente apenas por baixa proporção, quando a quantidade absoluta de evidência já é robusta.

**Quando nenhum critério é atendido:**

```json
{
  "status_ice": "cobertura_insuficiente",
  "ice_nsi": null,
  "motivo": "Quantidade insuficiente de evidências semânticas para cálculo confiável."
}
```

Esta é a única situação em que o ICE não é apresentado. Quando o ICE é calculado normalmente: `status_ice: "calculado"`.

**Faixas de interpretação (linguagem comercial, não técnica):**

| Faixa | Nome |
|---|---|
| 0 – 39,9 | Experiência Crítica |
| 40 – 59,9 | Experiência de Atenção |
| 60 – 74,9 | Experiência Satisfatória |
| 75 – 89,9 | Experiência Muito Boa |
| 90 – 100 | Experiência Excelente |

**Aditivo arquitetural — novo indicador operacional `evidencias_semanticas_validas`:**

Por decisão expressa, a quantidade de evidências semânticas válidas do lote passa a ser um **indicador oficial exposto na saída do Motor**, não apenas uma variável interna usada para o critério de bloqueio do ICE. Uma evidência válida é qualquer evidência (Contrato Seção 4, campo `evidencias` de `CategoriaAgregada`) efetivamente utilizada pelo Motor para justificar uma categoria classificada no lote.

- **Campo:** `evidencias_semanticas_validas` (inteiro, contagem absoluta)
- **Localização:** objeto raiz da saída do Motor (Seção 8), no mesmo nível de `versao_motor` e `status_semantico` — não dentro de `matematica` nem de `executiva`, para ficar acessível independente de qual camada o consumir
- **Usos previstos:** alimentar o Critério B do ICE (acima); auditoria do Motor; Dashboard Executivo; PDF Executivo; calibração futura do Catálogo NSI
- **Não altera nenhum cálculo de nenhuma camada existente** — é estritamente um indicador derivado, somado depois que a Camada Semântica já produziu sua saída normal

---

## 10. O que este contrato NÃO define (propositalmente)

- O catálogo completo das dores/forças das 20 famílias (vive em `catalogo_nsi_v1_operacional.md`, versionável independente deste contrato)
- Os pesos da fórmula do ICE NSI v1 (fase de calibração)
- A fórmula da Camada de Impacto Comercial (não existe nesta versão — Seção 9.1)
- `peso_relevancia` por categoria (rejeitado por reintroduzir Impacto Comercial pela porta dos fundos — Seção 9.7)
- `acao_recomendada` fixa por entrada do catálogo (vira responsabilidade da Camada Executiva — Seção 9.8)
- A engine de classificação semântica (Groq, modelo, prompt) — implementação futura
- Qualquer lógica de cálculo em código — este documento é o contrato, não a implementação
