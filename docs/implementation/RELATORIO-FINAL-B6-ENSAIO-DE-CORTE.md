# Relatório Final — Sprint B, Subetapa B6: Ensaio de Corte Controlado

**Natureza deste documento:** relatório de encerramento (evidência `E18` e passo `P5` de `SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md`, referida aqui como "a especificação"). Não é uma ADR e não altera nenhum documento congelado.

**Data do ensaio e do encerramento:** 2026-10-10.

**Resultado:** **B6 ENCERRADA** — Rodada S executada e **aprovada**; Rodada R **formalmente dispensada** por `D1` = não. A B7 permanece bloqueada (Seção 7 deste relatório).

---

## 1. Subetapas

| Subetapa | Conteúdo | Situação |
|---|---|---|
| B6.0 | Projeto executivo | concluída |
| B6.1 | Especificação técnica e operacional | publicada (commit `f263986`); a implementação e a execução foram autorizadas pelo operador com base nela. O texto publicado mantém o cabeçalho de proposta e **não foi alterado** |
| B6.2 | Componentes `C1` a `C9` | concluída (commit `c912a30`) |
| B6.3 | Provisionamento e Rodada S | **executada e aprovada** |
| B6.4 | Rodada R, com dado real | **dispensada** por `D1` = não |
| B6.5 | Encerramento | este relatório |

## 2. Decisões do operador (Seção 49 da especificação)

| # | Decisão | Registro |
|---|---|---|
| `D1` | Executar a Rodada R, com dado real? | **Não.** A Rodada R fica dispensada nesta sprint e passa a ser pré-requisito exclusivo da B7 |
| `D2`, `D3`, `D4`, `D6`, `D8` | Instalação de origem, fuso, janela da pausa, retenção, prosseguir com recusas | não se aplicam: só existem na Rodada R |
| `D5` | Área de ensaio | `C:\NSI_ENSAIO`, fora do repositório e de `data/`; criptografia do volume atestada pelo operador |
| `D7` | Destino do backup produzido | eliminado junto com o ensaio (o backup da Rodada S continha somente dado sintético) |
| `D9` | Ensaio de `pg_dump` e restauração (`O1`) | não executado; evidência opcional |
| `D10` | Composição da origem sintética | as oito fixtures da B5 mais 20 lotes por geração |

## 3. Rodada S — `s-2026-10-10`

Ambiente: banco `nsi_ensaio` (UTF8, dono `postgres`), provisionado pelo operador com o superusuário; revisão `0006` aplicada somente por `upgrade` (`0001` → `0006`); `CONNECT` e `USAGE` somente para `nsi_ensaio_migrator` e `nsi_importacao`. Servidor sem registro de comandos nem de parâmetros (`log_statement = none`, `log_min_duration_statement = -1`, `log_parameter_max_length_on_error = 0`).

| Passo | Verificação | Resultado |
|---|---|---|
| `S1` | Provisionamento, Fases 1 a 3; `0006`; catálogo comparado com `nsi_test` | aprovado — catálogo idêntico (13 tabelas, 21 funções, 29 índices, 97 constraints, 6 triggers) |
| `S2` | Origem sintética, com destinos declarados antes da importação | 104 lotes e 2 tentativas recusadas |
| `S3` | Quiescência: `I1` = `I2`, com janela de observação de 125 segundos | idênticos |
| `S3` | Backup integral (`tar.exe`) e teste de restauração | restauração idêntica a `I1` |
| `S3` | Cópia congelada do escopo | 106 arquivos, confere com `I1`, somente leitura |
| `S4` | Levantamento estrutural | 8 lotes com divergência — exatamente os 8 esperados como recusados |
| `S5` | Importação, fuso `America/Sao_Paulo` | saída `0`; 43 promovidos, 53 preservados, 8 recusados |
| `S6` — `V1` | Paridade do banco | aprovada; nenhum lote reprovado; `evoluidos_no_fluxo_novo` = 0 |
| `S6` — `V2` | Paridade da origem | `origem_confere` e `manifesto_completo` verdadeiros |
| `S6` — `V3` | Auditoria, partes A e B | aprovada, nenhuma divergência |
| `S6` — `V5` | Destinos obtidos contra os esperados | 104 de 104 conferem |
| `S6` — parte D | Privacidade | nenhuma evidência com valor pessoal |
| — | `I3` = `I1` (ensaio parcial de cancelamento) | idênticos |
| `S7` | Descarte do ambiente, pelo operador | banco e migrator inexistentes; concessões revogadas |
| `S7` — `V4` | Suíte completa depois do descarte | registrada na Seção 5 |

Tempos medidos (segundos): geração 0,2; inventário 0,9; cópia congelada 0,3; levantamento 0,05; importação dos 104 lotes 3; auditoria e quantificação 0,4. Backup e extração ficaram abaixo de 1 segundo cada e **não foram medidos com precisão**. O volume sintético (168 KB de escopo) não permite extrapolar a duração da pausa para o dado real.

**Quantificação da Rodada S** (parte C — somente dado sintético; **não substitui** a quantificação da ADR-010, Seção 12.3):

| Geração | Preservados | Promovidos | Recusados |
|---|---|---|---|
| `anterior_a1` | 21 | — | — |
| `a1` | 21 | — | — |
| `a2` | 10 | 22 | — |
| `a3` | 1 | 21 | — |
| `formato_desconhecido` | — | — | 4 |
| não classificado | — | — | 4 |

Motivos de não promoção: `geracao_nao_promovivel` 42, `evidencia_de_disparo` 2, `m0_invalido` 2, e um de cada: `colisao_de_identidade`, `historico_incoerente`, `identidade_repetida`, `lote_id_legado_invalido`, `m0_inexistente_ou_ambiguo`, `projecao_incompativel`, `totais_incoerentes`. Motivos de recusa: `formato_desconhecido` 4, `documento_ilegivel` 2, `identidade_divergente` 2.

## 4. Evidências

Gravadas em `docs/implementation/evidencias-b6/s-2026-10-10/` (cópia byte a byte de `evidencias/` da área de ensaio), com índice fechado — SHA-256 do índice `1cbb9c697b83c1cbb985bc6041bed006de13fd8a5bf95d92b4feb673ee66515e`. Nenhum arquivo contém valor pessoal, credencial ou caminho absoluto.

| Evidência | Arquivo ou registro |
|---|---|
| `E1` | commit `c912a30`; suíte de 1991 testes aprovada antes da publicação |
| `E2` | `E2_ambiente.json`. **Limitação:** o log do psql do provisionamento não foi entregue; a aprovação da Fase 3 está registrada conforme informada pelo operador, e o estado resultante foi conferido por leitura |
| `E4` | `inventario_I1.json`, `inventario_I2.json`, `inventario_I3.json`, `comparacao_I1_I2.json`, `comparacao_I1_I3.json` |
| `E5` | `E5_backup.json`, `inventario_RESTAURACAO.json`, `comparacao_I1_RESTAURACAO.json` |
| `E6` | `E6_copia_congelada.json` |
| `E7` | `E7_levantamento_estrutural.json` |
| `E8`, `E9` | `E8_relatorio_do_executor.json` (inclui a saída da paridade); `importacao_id` `37c9c731-2953-41c2-aa99-4d723ab9c845`, sem valor fora do ensaio |
| `E10` | `E10_auditoria.json`, `E10_privacidade.json` |
| `E11` | `E11_quantificacao.json` |
| `E12` | `E12_tempos.json` |
| `E13` | `E13_cancelamento_parcial.json` (parcial, como previsto para a Rodada S) |
| `E15`, `E16`, `E17` | Seção 5 deste relatório (posteriores ao fechamento do índice) |
| `E3`, `E14` | não se aplicam: exclusivas da Rodada R |
| `E18` | este relatório; não há termo de autorização, porque não houve dado real |

## 5. Eliminação, descarte e estado final

- **Banco:** `desprovisionar_b6_ensaio.sql` executado pelo operador, com sucesso conforme informado; o log não foi entregue. Conferido por leitura depois do descarte: `nsi_ensaio` e `nsi_ensaio_migrator` inexistentes; `nsi_importacao` com `CONNECT` somente em `nsi_test`; membros de `nsi_eventos_owner` somente `nsi_dev_migrator` e `nsi_test_migrator`.
- **Área de ensaio:** `origem/`, `restauracao/`, `instalacao_sintetica/` e `backup/` apagados; resta somente `evidencias/`.
- **Configuração:** variáveis `ENSAIO_DATABASE_URL` e `ENSAIO_DATABASE_URL_NSI_IMPORTACAO` removidas do `.env` local; arquivos temporários da rodada apagados.
- **Bancos permanentes:** `nsi_dev` e `nsi_test` em `0006 (head)`.
- **Suíte completa (`V4`)**, com integração real obrigatória, depois do descarte: **1993 de 1993 aprovados, nenhuma falha, nenhum pulado**. Antes da rodada, com `nsi_ensaio` presente, a suíte também passou por inteiro (1992 de 1992) — o que comprova, no cluster real, a tolerância dos testes de provisionamento ao ambiente de ensaio.
- Nenhum dado real foi lido, copiado ou importado em nenhum momento da B6.

## 6. Achados

1. **Primeira execução real dos scripts administrativos.** `provisionar_b6_ensaio.sql` e `desprovisionar_b6_ensaio.sql`, até então verificados só estaticamente, executaram sem erro na primeira tentativa.
2. **Formato da URL de conexão.** A primeira tentativa de configurar `ENSAIO_DATABASE_URL` usou o prefixo de dialeto `postgresql+psycopg://`, que o parser do psycopg/libpq não aceita. As variáveis do projeto usam sempre `postgresql://`; o prefixo é acrescentado somente por `migrations/env.py`. A mensagem fixa de URL inválida passou a orientar sobre isso, sem ecoar a URL, e o procedimento manual foi ajustado.
3. **Defeitos encontrados e corrigidos antes da rodada**, pelos testes da B6.2: modo somente leitura não religado depois de uma troca de banco no provisionamento; leitura da revisão do Alembic sem privilégio sob `nsi_eventos_owner`; invariante da auditoria que reprovaria um lote legitimamente preservado por `colisao_de_identidade`.
4. **Desvios em relação ao texto da especificação**, sem efeito sobre as regras: a origem sintética fica em um quinto subdiretório da rodada (`instalacao_sintetica/`); a revisão do Alembic é lida pela ferramenta como o migrator, e não dentro do arquivo SQL de auditoria.
5. **Medição de tempo incompleta** para backup e extração (Seção 3).

## 7. O que a B6 não resolveu — bloqueios da B7

A dispensa da Rodada R tem um custo declarado pela especificação (Seção 50, item 9): **a quantificação dos lotes por geração sobre o dado real (ADR-010, Seção 12.3) não existe** e passa a bloquear a B7, junto com o ensaio da pausa real da aplicação e a medição da janela.

Continuam bloqueados para a B7, sem alteração, os doze itens da Seção 50 da especificação: backup de produção, RPO e RTO; infraestrutura definitiva; mecanismo de pausa de escritas; troca do backend de `adapters/storage.py`; congelamento e manifesto definitivo dos JSONs; rollback posterior ao corte; decisão sobre lotes em andamento não promovíveis; tratamento de lotes reais recusados; quantificação sobre dado real; política jurídica de retenção; desabilitação de `nsi_importacao`; autorização própria da B7.

Permanece também aberto o critério de aceite 1 da B5 (duas execuções do script da role `nsi_importacao`, com a Fase 3 aprovada, a confirmar pelo operador).

**Nenhum resultado da B6 autoriza a B7.**

## 8. Critérios de saída da B6 (Seção 8 da especificação)

| # | Critério | Situação |
|---|---|---|
| 1 | Rodada S executada e aprovada | satisfeito |
| 2 | Rodada R executada ou formalmente dispensada | satisfeito — dispensada por `D1` = não |
| 3 | Evidências obrigatórias aplicáveis coletadas | satisfeito, com a limitação registrada em `E2` |
| 4 | Dado real eliminado | não se aplica — nenhum dado real entrou |
| 5 | `nsi_ensaio` e o migrator inexistentes; concessões revogadas | satisfeito |
| 6 | Suíte completa aprovada; `nsi_dev` e `nsi_test` em `0006` | satisfeito |
| 7 | Relatório final e documentação de encerramento | satisfeito por este relatório |
