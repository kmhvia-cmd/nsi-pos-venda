# ADR-002 — Fundação de Marca NSI

## Metadados

| Campo | Valor |
|---|---|
| Status | Aprovado |
| Data | 2026-07-03 |
| Versão de referência do sistema | `v1.1.0-fonte-unica-webhook-motor` |
| Commit de referência | `886c8e7` |
| Branch | `master` |
| Escopo desta ADR | Arquitetura de marca — nenhuma peça de comunicação, layout, imagem ou identidade visual |

> **Nota de processo:** este ADR foi revisado linha por linha e validado. Status `Aprovado` — as decisões da Seção 8 estão congeladas a partir desta versão.

---

## 1. Objetivo

Registrar a decisão arquitetural que inicia o **módulo de branding do NSI**, aplicando à marca a mesma metodologia já validada na arquitetura técnica (ADR-001): **arquitetura primeiro, implementação depois**.

Esta ADR não define como o NSI vai se comunicar visualmente. Ela define **onde mora a verdade sobre o que o NSI é, por que existe e como fala**, antes de qualquer peça de comunicação ser produzida.

**O Branding do NSI é um ativo arquitetural do projeto** — sujeito ao mesmo rigor de decisão, documentação e revisão que qualquer componente do Motor, do Operations Console ou do Portal Executivo do Cliente.

O objetivo deste módulo não é apenas definir uma identidade visual, mas construir um **Sistema Editorial Proprietário** capaz de garantir consistência na comunicação da marca em qualquer mídia, plataforma ou formato.

---

## 2. Escopo

### 2.1 Escopo desta decisão

- Criação do diretório `docs/branding/` como fonte única de verdade da marca NSI.
- Definição do conjunto de documentos fundacionais da Sprint 1: filosofia, manifesto, propósito, posicionamento, missão, visão, valores, diferenciais, tom de voz e princípios editoriais.
- Definição do princípio de que toda comunicação futura do NSI — interna ou externa, em qualquer canal — deriva destes documentos, sem exceção.
- Definição das regras de versionamento e governança do módulo de branding.

### 2.2 Fora do escopo desta decisão

- Qualquer peça de comunicação: posts, textos publicitários, roteiros, e-mails.
- Identidade visual: logotipo, paleta de cores, tipografia, ícones, layouts, templates.
- Imagens, fotografias, ilustrações ou qualquer ativo gráfico.
- Definição de canais de publicação (site, redes sociais, materiais comerciais).
- Calendário editorial ou cronograma de publicação.
- Qualquer alteração ao Motor, ao Operations Console ou ao Portal Executivo do Cliente (ADR-001).

---

## 3. Contexto

O sistema NSI, na versão `v1.1.0-fonte-unica-webhook-motor`, tem seu núcleo técnico congelado, com `lote.json` como fonte única de verdade e suíte de 121/121 testes aprovados. A ADR-001 já formalizou a arquitetura das três plataformas do ecossistema (Motor, Operations Console, Portal Executivo do Cliente) antes de qualquer implementação de dashboard.

O NSI chega agora ao ponto em que precisa se comunicar — com clientes, com o mercado, com sua própria equipe — e essa comunicação corre o mesmo risco que qualquer construção sem arquitetura prévia: inconsistência, retrabalho e deriva de identidade a cada nova peça produzida por uma pessoa diferente.

Assim como o Motor não foi implementado antes do Contrato (`contrato_motor_nsi.md`) estar fechado, a marca não deve produzir sua primeira peça de comunicação antes de sua fundação estar documentada e aprovada.

Um ponto de partida relevante: o próprio Contrato do Motor já define, na Seção 0, uma postura que não é apenas técnica — é uma visão de mundo sobre o que é escutar um cliente com rigor:

> "O NSI não mede sentimento. O NSI mede **experiência comercial**."

Esta ADR reconhece esse princípio técnico como a semente da filosofia de marca, e não trata marca e produto como narrativas separadas.

---

## 4. Decisão — Estrutura do Módulo de Branding

```
docs/branding/
├── README.md                        # Índice e regras de uso do módulo
├── 01-filosofia.md                  # Crenças fundamentais — o porquê por trás do porquê
├── 02-manifesto.md                  # Declaração de convicção, registro público de postura
├── 03-proposito.md                  # Por que o NSI existe
├── 04-posicionamento.md             # Categoria, público, contraste competitivo
├── 05-missao-visao-valores.md       # Missão, visão e valores
├── 06-diferenciais.md               # O que distingue o NSI de alternativas
├── 07-tom-de-voz.md                 # Como o NSI fala
└── 08-principios-editoriais.md      # Regras de escrita para qualquer conteúdo futuro
```

**Justificativa de um arquivo por tema, em vez de um único documento:** cada tema evolui em ritmo próprio — o tom de voz pode ganhar exemplos novos sem tocar na missão; o posicionamento pode ser revisado por decisão comercial sem reabrir a filosofia. Arquivos separados mantêm o histórico do Git limpo por tema, exatamente como cada ADR vive em seu próprio arquivo em vez de um documento único de decisões.

### 4.1 Códigos documentais oficiais

Todo conteúdo produzido pelo NSI segue uma estrutura documental identificada por códigos oficiais, incluindo, entre outros:

| Código | Significado |
|---|---|
| `DT` | Documento Técnico |
| `ART` | Artigo |
| `REL` | Relatório |
| `MAN` | Manual |
| `EST` | Estudo |
| `GUI` | Guia |
| `INS` | Insight |

Esta lista de Tipos de Documento é a **nomenclatura oficial e fechada** do Livro da Marca (ver Decisões Congeladas, item 13). O código `SEM` foi avaliado e **eliminado definitivamente** — nenhuma sigla institucional pode representar simultaneamente um Tipo de Documento e um Tema (Princípio 8); "Semântica" existe exclusivamente como Tema Editorial (Seção 4.2).

As regras de numeração, os formatos aceitos e a relação de cada Tipo com a Camada 3 do Sistema Editorial (Seção 5) serão definidos posteriormente pelo Design System.

### 4.2 Tipo de Documento vs. Tema

O Tipo de Documento e o Tema são eixos independentes e nunca se confundem:

- **Tipo de Documento** — a estrutura institucional da publicação (Seção 4.1). Lista fechada: `DT` (Documento Técnico), `ART` (Artigo), `REL` (Relatório), `MAN` (Manual), `EST` (Estudo), `GUI` (Guia), `INS` (Insight).
- **Tema** — o assunto tratado pela publicação, independente do tipo. Exemplos: Fundamentos, Experiência do Cliente, Semântica, Linguagem, Dados, Cultura, Inteligência Artificial.

Um mesmo Tema pode ser tratado por diferentes Tipos de Documento (ex.: `DT-001` e `DT-002` podem tratar o mesmo Tema "Semântica" em profundidades diferentes). Um mesmo Tipo de Documento cobre múltiplos Temas ao longo do tempo — por exemplo:

```
DT-001 — Tema: Semântica
DT-002 — Tema: Inteligência Artificial
DT-003 — Tema: Experiência do Cliente
```

Nenhuma sigla de Tipo pode carregar, mesmo implicitamente, o significado de um Tema — violação direta do Princípio 8. Foi por essa regra que `SEM` foi eliminado da nomenclatura oficial (Seção 4.1).

A nomenclatura completa que combina Tipo + Tema + sequência é definida pelo Design System (Seção 5, Camada 3).

---

## 5. Sistema Editorial — Três Camadas

O Sistema Editorial do NSI é composto por três camadas independentes, que juntas formam a Fonte Única de Verdade da comunicação institucional do NSI.

### Camada 1 — Fundamentos da Marca

Filosofia, Manifesto, Posicionamento, Missão, Visão, Valores, Tom de Voz. Conteúdo já entregue em `docs/branding/` (Sprint 1 — Seção 4 desta ADR).

### Camada 2 — Design System

Grid, tipografia, componentes, paletas, layouts, espaçamentos, zonas de segurança. Fora do escopo desta ADR (Seção 2.2 e Seção 10).

### Camada 3 — Sistema de Publicações

Códigos documentais, templates, biblioteca de layouts, prompts mestres, banco de conteúdo. Fora do escopo desta ADR; a nomenclatura completa dos códigos documentais (Seção 4.1) depende da formalização desta camada.

A Camada 1 é a única congelada por esta ADR. As Camadas 2 e 3 são objeto de ADRs futuras, subsequentes a esta.

---

## 6. Princípios Arquiteturais Aprovados

### Princípio 1 — Fonte Única de Verdade

`docs/branding/` é a única fonte oficial de filosofia, propósito, posicionamento e tom de voz do NSI. Nenhuma peça de comunicação — interna ou externa — pode divergir do que está registrado aqui sem que o documento correspondente seja alterado primeiro.

### Princípio 2 — Arquitetura Antes de Implementação

Nenhum layout, imagem, post ou peça de comunicação é produzido antes de sua justificativa estar documentada nesta fundação. A Sprint 1 entrega exclusivamente documentação; identidade visual e peças pertencem a sprints futuras.

### Princípio 3 — Coerência com os Princípios Técnicos do Motor

A filosofia de marca deriva diretamente dos princípios já congelados do Motor (Contrato Seção 0) — rigor, evidência rastreável, recusa de redução simplista, confiança declarada em vez de fingida. Marca e produto compartilham a mesma postura; não são narrativas desconectadas.

### Princípio 4 — Versionamento como Governança

Toda alteração de conteúdo de marca é uma mudança versionada em Git, sujeita a revisão, exatamente como uma mudança de código. Não existe "versão oficial" de um texto de marca fora deste repositório.

### Princípio 5 — Construção Incremental por Sprints

Assim como o Motor foi construído em fases validadas sequencialmente, a marca é construída em sprints. Sprint 1 é a fundação documental (esta ADR). Identidade visual, peças de comunicação e calendário editorial são sprints futuras, registradas como ADRs subsequentes sempre que envolverem decisão estrutural (não apenas execução).

### Princípio 6 — Consistência de Longo Prazo

Toda decisão tomada neste módulo deve preservar a identidade do NSI por muitos anos. O objetivo deste módulo não é atender campanhas específicas — é garantir continuidade, coerência e reconhecimento da marca independentemente da evolução do produto.

### Princípio 7 — Identidade Única

Todo material produzido pelo NSI deve ser imediatamente reconhecido como pertencente à marca, mesmo na ausência do logotipo. A identidade da marca é construída pela repetição consistente de sua linguagem visual, editorial e conceitual — não por um único elemento gráfico isolado.

### Princípio 8 — Unicidade de Sigla Institucional

Uma sigla institucional nunca pode possuir mais de um significado dentro do Livro da Marca. Cada código de Tipo de Documento (Seção 4.1) representa exclusivamente uma estrutura — nunca um tema, nunca uma leitura dupla. Conflito de significado é resolvido antes do congelamento da decisão que o introduziu, nunca depois.

---

## 7. Governança

- `docs/branding/` é de leitura obrigatória antes da produção de qualquer peça de comunicação do NSI.
- Nenhuma pessoa ou agente produz conteúdo de marca "no estilo que achar melhor" — o Tom de Voz (`07-tom-de-voz.md`) e os Princípios Editoriais (`08-principios-editoriais.md`) são vinculantes.
- Alterações a qualquer documento de `docs/branding/` seguem o mesmo processo de revisão do restante do repositório (commit descritivo, revisão antes de merge quando aplicável).
- Qualquer nova decisão estrutural sobre a marca (ex: introdução de identidade visual, nova plataforma de comunicação) deve ser registrada como ADR subsequente neste mesmo diretório, mantendo a numeração sequencial.

---

## 8. Decisões Congeladas

As decisões abaixo estão congeladas e aprovadas a partir desta versão do ADR.

1. `docs/branding/` é a fonte única de verdade da marca NSI.
2. A Sprint 1 do módulo de branding entrega exclusivamente documentação fundacional — nenhum layout, imagem ou post.
3. A filosofia de marca do NSI deriva dos princípios técnicos já congelados do Motor (Contrato Seção 0), não de uma narrativa de marketing independente.
4. Toda comunicação futura do NSI, em qualquer canal, deve ser coerente com os documentos de `docs/branding/`.
5. Alterações de conteúdo de marca seguem a mesma disciplina de versionamento em Git aplicada ao código.
6. O Branding do NSI é um ativo arquitetural do projeto, não uma iniciativa de campanha.
7. O objetivo do módulo é um Sistema Editorial Proprietário — não apenas uma identidade visual — composto por três camadas (Fundamentos da Marca, Design System, Sistema de Publicações).
8. Toda decisão de marca deve preservar a identidade do NSI por muitos anos (Consistência de Longo Prazo), nunca atender apenas a uma campanha pontual.
9. O NSI deve ser reconhecível mesmo sem o logotipo, pela repetição consistente de sua linguagem visual, editorial e conceitual (Identidade Única).
10. Uma sigla institucional nunca possui mais de um significado dentro do Livro da Marca (Princípio 8 — Unicidade de Sigla Institucional).
11. Tipo de Documento e Tema são eixos permanentemente separados (Seção 4.2); nenhuma sigla de Tipo pode representar um Tema.
12. O código `SEM` é eliminado definitivamente da nomenclatura oficial do Sistema Editorial do NSI; "Semântica" existe exclusivamente como Tema Editorial.
13. Nomenclatura oficial e fechada dos Tipos de Documento do Livro da Marca (Seção 4.1): `DT`, `ART`, `REL`, `MAN`, `EST`, `GUI`, `INS`.

---

## 9. Dependências

- Depende da estabilidade do núcleo técnico congelado na versão `v1.1.0-fonte-unica-webhook-motor`, cujos princípios (Contrato Motor NSI, Seção 0) fundamentam a filosofia de marca.
- Depende da ADR-001 apenas como precedente metodológico (arquitetura antes de implementação); não há dependência funcional entre os dois módulos.
- Depende de ADR futura para formalizar identidade visual e peças de comunicação (fora do escopo desta ADR).
- Depende de ADR futura (Camada 2 — Design System) para as regras de numeração e formatos dos códigos documentais (Seção 4.1 — lista de Tipos já oficial e fechada) e para toda decisão de identidade visual.

---

## 10. Itens Fora do Escopo

- Definição de logotipo, paleta de cores, tipografia ou qualquer ativo visual.
- Produção de posts, textos publicitários ou qualquer peça de comunicação publicável.
- Definição de canais de publicação e calendário editorial.
- Regras de numeração, formatos aceitos e relação com a Camada 3 dos códigos documentais (lista de Tipos já oficial e fechada na Seção 4.1: `DT`, `ART`, `REL`, `MAN`, `EST`, `GUI`, `INS`); demais decisões da Camada 2 — Design System e Camada 3 — Sistema de Publicações (Seção 5).
- Qualquer alteração em `engine/`, `processors/`, `models/`, `outputs/`, `confidence/` ou nas plataformas definidas na ADR-001.

---

## 11. Referências

- `contrato_motor_nsi.md` — Seção 0 (Princípios do Motor), origem da filosofia de marca.
- `docs/architecture/ADR-001-operations-console.md` — precedente metodológico (arquitetura antes de implementação).
- `docs/branding/` — documentos fundacionais entregues por esta ADR.
