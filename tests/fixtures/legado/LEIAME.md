# Fixtures sinteticas do legado (Sprint B, B5.4 - ADR-010, Secao 21)

Todo o conteudo deste diretorio e SINTETICO: foi gerado pelos construtores de
`tests/apoio_b5.py` e nunca copiado de `data/`. Reproduz somente a estrutura
das quatro geracoes de `lote.json` e dos formatos de recusa.

| Caminho | Caso |
|---|---|
| `lotes/NSI-20260101-A00001/lote.json` | geracao `anterior_a1` |
| `lotes/NSI-20260102-A00002/lote.json` | geracao `a1` |
| `lotes/NSI-20260103-A00003/lote.json` | geracao `a2` |
| `lotes/NSI-20260104-A00004/lote.json` | geracao `a3` |
| `lotes/NSI-20260105-A00005/lote.json` | `formato_desconhecido` (chave extra na raiz) |
| `lotes/NSI-20260106-A00006/lote.json` | `formato_desconhecido` (mistura de identidade) |
| `lotes/NSI-20260107-A00007/lote.json` | `documento_ilegivel` (JSON truncado) |
| `lotes/NSI-20260108-A00008/lote.json` | `identidade_divergente` (`lote_id` diferente do diretorio) |
| `correcoes_rejeitadas/2026-01-09/*.json` | tentativa recusada da A3 (somente manifesto) |

Os testes que gravam com COMMIT real nunca usam estes arquivos: constroem
documentos com identificadores aleatorios.
