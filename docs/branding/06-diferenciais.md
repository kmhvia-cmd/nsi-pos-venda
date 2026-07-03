# Diferenciais NSI

**Deriva de:** [`04-posicionamento.md`](04-posicionamento.md), [`05-missao-visao-valores.md`](05-missao-visao-valores.md).
**Status:** Fundação Sprint 1.

---

Cada diferencial abaixo corresponde a uma decisão de arquitetura já implementada ou congelada no Motor — não a uma promessa. Onde existe correspondência direta com o Contrato ou com uma ADR, ela está indicada.

### 1. Camadas, não score único

O NSI não entrega um número. Entrega seis camadas — Matemática, Linguística, Semântica, Experiência Humana, Evolução Temporal, Executiva — cada uma medindo uma dimensão diferente da mesma resposta. *(Contrato, Mapa de camadas v3.1.)*

### 2. Evidência rastreável por trás de cada conclusão

Toda interpretação semântica é amarrada à frase exata do cliente que a originou. Nenhuma conclusão existe "porque o modelo disse" sem a evidência que se pode auditar. *(Contrato, Seção 0.)*

### 3. Confiança quantificada, não afirmação binária

Cada conclusão carrega percentual de confiança **e** quantidade de ocorrências que a sustentam — nunca um "sim/não" sem grau. *(Contrato, Seção 0.)*

### 4. Silêncio e tempo de resposta como dado

Quem não respondeu, quem visualizou e não respondeu, quem nem recebeu a mensagem — tudo isso é capturado por `status_entrega` e processado como informação, não descartado como ausência de dado. *(Contrato, Seção 1.)*

### 5. Catálogo semântico por segmento

A classificação semântica prioriza um recorte de nicho (ex: moda) dentro de um catálogo universal, em vez de aplicar um modelo genérico igual para qualquer setor. *(Contrato, Seção 1 — campo `segmento`.)*

### 6. Continuidade sem IA — o motor nunca para

Se o provedor de IA cai, o Motor não interrompe o lote inteiro: as camadas que não dependem de IA externa (Matemática, Linguística) continuam sendo entregues, e o restante é reprocessado depois. *(Contrato, Seção 1.2 — Fallback operacional.)*

### 7. Segregação arquitetural de dados sensíveis

NPS, comentários, diagnósticos e respostas individuais nunca aparecem na ferramenta de uso interno (Operations Console) — existem exclusivamente onde a empresa cliente tem acesso autorizado (Portal Executivo do Cliente). *(ADR-001, Princípio 5.)*

### 8. Disciplina de arquitetura documentada, visível de fora para dentro

Cada decisão estrutural do NSI — de produto ou de marca — é registrada como ADR antes de virar implementação. Essa disciplina não é um detalhe interno: é evidência do mesmo rigor que o NSI promete aplicar aos dados de um cliente.
