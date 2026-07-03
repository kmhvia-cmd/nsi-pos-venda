# Missão, Visão e Valores NSI

**Deriva de:** [`01-filosofia.md`](01-filosofia.md), [`04-posicionamento.md`](04-posicionamento.md).
**Status:** Fundação Sprint 1.

---

## Missão

Transformar cada resposta de cliente em evidência estruturada e rastreável — para que quem decide, decida sobre o que de fato aconteceu, não sobre uma média que apaga o que foi dito.

## Visão

Ser a referência em experiência comercial mensurada com evidência: a lente pela qual empresas sérias entendem, com rigor, o que realmente aconteceu entre elas e seus clientes — no lugar do score genérico que hoje passa por resposta.

## Valores

Os valores do NSI não foram escolhidos por aspiração. Foram extraídos de decisões já tomadas — e congeladas — na arquitetura técnica do Motor (Contrato Seção 0) e na governança do Operations Console (ADR-001). Um valor que não se sustenta em uma decisão real não entra nesta lista.

### 1. Evidência antes de opinião

Nenhuma conclusão é aceita sem a frase exata que a originou. Uma opinião sem evidência rastreável não é uma conclusão do NSI — é um palpite, e palpite não é o que o NSI entrega.

### 2. Contexto antes de rótulo

Uma resposta nunca é classificada pelo tom isolado. É classificada pelo que ela significa dentro do contexto em que foi dita. Rotular rápido é o caminho mais fácil; entender o contexto é o único caminho certo.

### 3. Nada é descartado como ruído

Emoji, pontuação, silêncio, tempo de resposta, gíria — tudo é dado de entrada para alguma camada. Essa disciplina de atenção ao detalhe técnico se estende a como o NSI trata qualquer detalhe de sua comunicação.

### 4. Confiança declarada, nunca fingida

Toda conclusão carrega percentual de confiança e quantidade de ocorrências que a sustentam. O NSI não finge certeza que não tem, e não hesita quando a evidência é suficiente.

### 5. Nenhuma métrica sem fonte real

Se não pode ser calculado com confiabilidade a partir do que o sistema efetivamente coleta, fica de fora — nunca entra como estimativa especulativa disfarçada de dado.

### 6. Arquitetura antes de implementação

Nenhuma decisão estrutural — de produto ou de marca — é implementada antes de estar documentada e aprovada. É a mesma disciplina que gerou o Contrato do Motor antes do primeiro `processor.py`, a ADR-001 antes do primeiro componente do Console, e esta própria fundação de marca antes de qualquer peça de comunicação.

### 7. Privacidade e segregação de dados sensíveis por padrão

Dados sensíveis (NPS, comentários, diagnósticos, respostas individuais) só existem onde têm finalidade legítima e autorizada — nunca por padrão, nunca por conveniência de acesso interno. Princípio já congelado na ADR-001 e válido para qualquer plataforma futura do ecossistema.
