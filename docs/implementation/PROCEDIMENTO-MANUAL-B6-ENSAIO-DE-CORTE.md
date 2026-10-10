# Procedimento Manual — Ensaio de Corte (B6)

**Natureza deste documento:** procedimento operacional manual. Não é uma ADR e não é executado por nenhum teste automatizado, script de CI ou comando de aceite. Descreve, comando a comando, como o operador executa uma rodada do ensaio de corte com os componentes `C1` a `C9` da B6.2.

**Subordinação:** `docs/implementation/SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md` (referida aqui como "a especificação"), ADR-008 (Seção 16), ADR-010 e B5.2. Em caso de divergência, vale a especificação. Complementa, sem alterar, os procedimentos manuais da B3, da B4 e da B5.

**Status:** DOCUMENTO VIVO. **Nenhum passo deste documento foi executado na B6.2.** Os dois scripts administrativos exigem o superusuário e só rodam pelas mãos do operador, na B6.3, depois das decisões `D1` a `D10` (Seção 49 da especificação). A Rodada R, com dado real, exige ainda o termo de autorização da Seção 35.

---

## 1. Regras que valem em todo o procedimento

- O banco do ensaio é **`nsi_ensaio`**, descartável. Nenhum comando deste documento escreve em `nsi_dev` ou em `nsi_test`.
- Em `nsi_ensaio` só existe `upgrade`. **Nunca `downgrade`, nunca `DELETE`, nunca desabilitar trigger**: o único desfazimento é `desprovisionar_b6_ensaio.sql`.
- A área de ensaio vem **somente** da variável `NSI_ENSAIO_DIR`. Não existe valor padrão: sem ela, toda ferramenta recusa (`D5`). A área fica fora do repositório e fora de `data/`, em volume com criptografia em repouso atestada.
- Uma rodada interrompida **não é retomada**: descarta-se o ambiente e começa-se outra, com outro `ensaio_id`.
- Nenhuma senha, URL de conexão ou valor pessoal é escrito em arquivo versionado, em evidência ou em linha de comando.
- O ambiente é descartado ao fim de **toda** rodada, aprovada ou não (Seção 5).
- Enquanto `nsi_ensaio` existir, os scripts de provisionamento da B3.1, da B4.3 e da B5.3 não são reexecutáveis (limitação aceita na Seção 15 da especificação).

## 2. Preparação (uma vez por rodada)

Os comandos são para o PowerShell, na raiz do repositório. `<id>` é o identificador da rodada: letras, dígitos, `-` e `_`, até 64 caracteres, começando por letra ou dígito (por exemplo `s-2026-10-12` ou `r-2026-10-15`).

1. **Conferir o ponto de partida.** `nsi_dev` e `nsi_test` em `0006`; suíte completa aprovada (`E1`):

   ```powershell
   $env:NSI_REQUIRE_PG_TESTS = "1"; .venv\Scripts\python.exe -m pytest -q
   ```

2. **Criar a área de ensaio** no volume criptografado e informá-la à sessão:

   ```powershell
   $env:NSI_ENSAIO_DIR = "<diretorio da area de ensaio>"
   ```

3. **Provisionar o ambiente** (o psql pede a senha do superusuário local):

   ```powershell
   & "C:\Program Files\PostgreSQL\17\bin\psql.exe" -h localhost -p 5432 -U postgres -d postgres -X -f scripts/postgres_local/provisionar_b6_ensaio.sql 2>&1 | Tee-Object -FilePath "$env:TEMP\b6_provisionamento.log"
   ```

   Resultado esperado: `Fase 3 (pos-validacao completa) passou integralmente.` O script aceita dois estados — ambiente ausente ou ambiente já provisionado por inteiro — e aborta, sem escrever, em qualquer outro.

4. **Definir a senha do migrator**, interativamente, como superusuário: dentro do psql, `\password nsi_ensaio_migrator`.

5. **Configurar o `.env` local** (fora do versionamento) com duas variáveis, no mesmo formato das de teste:
   - `ENSAIO_DATABASE_URL` — usuário `nsi_ensaio_migrator`, banco `nsi_ensaio`;
   - `ENSAIO_DATABASE_URL_NSI_IMPORTACAO` — usuário `nsi_importacao`, banco `nsi_ensaio`.

6. **Aplicar a `0006`**, somente por `upgrade`:

   ```powershell
   $env:NSI_DATABASE_ENV = "ensaio"; .venv\Scripts\alembic.exe upgrade 0006
   ```

7. **Criar a estrutura da rodada:**

   ```powershell
   .venv\Scripts\python.exe scripts/ensaio_corte.py preparar --ensaio-id <id>
   ```

   Cria `<area>/<id>/` com `backup/`, `origem/`, `evidencias/` e `restauracao/`. O comando recusa um `<id>` já existente.

8. **Guardar o log do provisionamento** em `<area>/<id>/evidencias/` (`E2`), depois de conferir que ele não contém senha.

Todo comando de `scripts/ensaio_corte.py` imprime um JSON sem valor pessoal e devolve `0` (aprovado), `1` (executado e reprovado) ou `2` (recusado). As evidências são gravadas em `evidencias/` e **nunca sobrescritas**: repetir um comando com o mesmo rótulo é recusado.

## 3. Rodada S — origem sintética

Não há aplicação a pausar nem dado real. A rodada ensaia as ferramentas, mede os tempos e comprova a verificação `V5`.

1. **`S2` — gerar a instalação sintética** e declarar os destinos esperados **antes** da importação. Use o fuso que será declarado em `S5`, e 20 lotes extras por geração (`D10`):

   ```powershell
   .venv\Scripts\python.exe scripts/ensaio_corte.py gerar-sintetico --ensaio-id <id> --fuso America/Sao_Paulo --lotes-extras 20
   ```

   Grava a instalação em `<area>/<id>/instalacao_sintetica/` e `evidencias/esperado.json`.

2. **`S3` — inventários e prova de quiescência** (`E4`), com a janela de observação de 2 minutos entre `I1` e `I2`:

   ```powershell
   $sint = "$env:NSI_ENSAIO_DIR\<id>\instalacao_sintetica"
   .venv\Scripts\python.exe scripts/ensaio_corte.py inventario --ensaio-id <id> --rotulo I1 --diretorio $sint
   .venv\Scripts\python.exe scripts/ensaio_corte.py inventario --ensaio-id <id> --rotulo I2 --diretorio $sint
   .venv\Scripts\python.exe scripts/ensaio_corte.py comparar --ensaio-id <id> --a I1 --b I2
   ```

3. **`S3` — backup e teste de restauração** (`E5`), com a ferramenta nativa do sistema operacional. O arquivo vai para `backup/`; a extração, para `restauracao/`. O inventário da restauração precisa ser idêntico a `I1`:

   ```powershell
   Compress-Archive -Path "$sint\*" -DestinationPath "$env:NSI_ENSAIO_DIR\<id>\backup\backup.zip"
   Get-FileHash "$env:NSI_ENSAIO_DIR\<id>\backup\backup.zip" -Algorithm SHA256
   Expand-Archive -Path "$env:NSI_ENSAIO_DIR\<id>\backup\backup.zip" -DestinationPath "$env:NSI_ENSAIO_DIR\<id>\restauracao"
   .venv\Scripts\python.exe scripts/ensaio_corte.py inventario --ensaio-id <id> --rotulo RESTAURACAO --diretorio "$env:NSI_ENSAIO_DIR\<id>\restauracao"
   .venv\Scripts\python.exe scripts/ensaio_corte.py comparar --ensaio-id <id> --a I1 --b RESTAURACAO
   ```

   Depois da comparação, apagar o conteúdo de `restauracao/`. O tamanho e o SHA-256 do backup são anotados pelo operador em `evidencias/E5_backup.json`.

4. **`S3` — cópia congelada** (`E6`). Copia somente o escopo, marca somente leitura e confere contra `I1`:

   ```powershell
   .venv\Scripts\python.exe scripts/ensaio_corte.py copiar --ensaio-id <id> --instalacao $sint --referencia I1
   ```

5. **`S4` — levantamento estrutural** (`E7`):

   ```powershell
   .venv\Scripts\python.exe scripts/ensaio_corte.py levantamento --ensaio-id <id>
   ```

   Na Rodada S, `lotes_com_divergencia` é igual ao total de lotes esperados como recusados.

6. **`S5` — importação** (`E8`), com o mesmo fuso do passo 1. O relatório é gravado como evidência:

   ```powershell
   $env:NSI_DATABASE_ENV = "ensaio"
   .venv\Scripts\python.exe scripts/importar_legado.py --origem "$env:NSI_ENSAIO_DIR\<id>\origem" --fuso America/Sao_Paulo | Out-File -Encoding utf8 "$env:NSI_ENSAIO_DIR\<id>\evidencias\E8_relatorio_do_executor.json"
   $LASTEXITCODE
   ```

   Saída `0`: paridade aprovada (`V1` e `V2`). Saída `1`: paridade reprovada (`F6`). Saída `2`: recusada ou abortada (`F1` ou `F5`). O executor recusa qualquer origem que não seja `<area>/<id>/origem`.

7. **`S6` — auditoria e quantificação** (`E10`, `E11`), com o mesmo fuso:

   ```powershell
   .venv\Scripts\python.exe scripts/ensaio_corte.py auditar --ensaio-id <id> --fuso America/Sao_Paulo
   ```

   Roda em transação somente leitura, como `nsi_ensaio_migrator` sob `nsi_eventos_owner`. Grava `E10_auditoria.json` (partes A e B e, na Rodada S, a `V5`), `E11_quantificacao.json` (parte C) e `E10_privacidade.json` (parte D). A comparação do catálogo com `nsi_test` exige `TEST_DATABASE_URL` configurada; sem ela, a auditoria reprova com `a_catalogo_nao_comparado`.

8. **Fechar o índice das evidências** — depois dele, nenhuma evidência entra na rodada:

   ```powershell
   .venv\Scripts\python.exe scripts/ensaio_corte.py indice --ensaio-id <id>
   ```

9. **`S7` — eliminação e descarte** (Seção 5) e **`S8`** — registro do resultado.

## 4. Rodada R — dado real

**Só ocorre com `D1` = sim, o termo de autorização da Seção 35 assinado, a criptografia do volume atestada e a janela de `D4` confirmada.** Começa sempre de um ambiente novo: a Seção 2 é refeita por inteiro, com outro `<id>`. O comando `gerar-sintetico` não é usado.

`<instalacao>` é o diretório de dados da instalação de origem (`D2`).

1. **`R3` — inventário inicial `I0`**, com a aplicação em operação (`E3`):

   ```powershell
   .venv\Scripts\python.exe scripts/ensaio_corte.py inventario --ensaio-id <id> --rotulo I0 --diretorio <instalacao>
   ```

2. **`R4` — pausar a aplicação.** Encerrar todos os processos que escrevem no diretório de dados: o servidor (`app.py`), qualquer agendador que chame `core/scheduler.py` e o receptor de webhook. Confirmar que nenhum processo da aplicação está em execução e que a porta do serviço não está em escuta. **Anotar o instante da parada.**

3. **`R4` — prova de quiescência** (`E4`): inventário `I1`, janela de **pelo menos 2 minutos** sem nenhuma ação sobre a origem, inventário `I2` e `comparar --a I1 --b I2`. Saída `1` é a falha `F2`: algum escritor não foi parado — **retomar a aplicação imediatamente** e cancelar a rodada.

4. **`R5` — backup integral e teste de restauração** (`E5`), como no passo 3 da Seção 3, sobre `<instalacao>` inteira. Reprovação é `F3`: retomar a aplicação e cancelar.

5. **`R6` — cópia congelada** (`E6`): `copiar --instalacao <instalacao> --referencia I1`. Saída `1` é `F4`: retomar a aplicação e cancelar. O prazo de retenção de `D6` conta a partir deste passo.

6. **`R7` — inventário `I3` e retomada da aplicação.** `inventario --rotulo I3` e `comparar --a I1 --b I3`; saída `1` é `F8`. Iniciar a aplicação com a mesma configuração de antes da pausa, confirmar que o serviço responde e que a listagem de lotes funciona. **Anotar o instante da retomada**; a duração da pausa é o principal insumo para a janela da B7 (`E4`, `E12`).

   A partir daqui a instalação de origem não é mais lida pelo ensaio.

7. **`R8` — levantamento estrutural** (`E7`) e decisão `D8`. `caminhos_com_divergencia` lista os lotes que seriam **recusados e não preservados**. Prosseguir, ou não, é decisão do operador, registrada.

8. **`R9` — importação** (`E8`), como no passo 6 da Seção 3. `--fuso` recebe o valor de `D3`; se o fuso não for atestável, o parâmetro é **omitido** — todos os lotes são processados e nenhum é promovido.

9. **`R10` — auditoria e quantificação** (`E10`, `E11`), como no passo 7 da Seção 3, com o mesmo fuso da importação (ou sem `--fuso`). `E11_quantificacao.json` é o resultado que a B6 existe para produzir: lotes por geração e destino, motivos, status literal e lotes em andamento.

10. **`R11` — ensaio de cancelamento** (`E13`): `I3` = `I1`; aplicação operante sobre os JSONs originais; `origem/` é uma cópia somente leitura em outra área; o banco de ensaio é declarado sem valor operacional.

11. **Fechar o índice** (`indice`), e então **`R12`** — eliminação e descarte (Seção 5) — e **`R13`** — suíte completa (`E17`).

## 5. Eliminação e descarte (fim de toda rodada)

Na ordem (Seção 32 da especificação):

1. Conferir o índice e copiar `evidencias/` para fora da área de ensaio.
2. **Descartar o banco e o migrator.** O script pede a frase `CONFIRMO-DESCARTAR-NSI-B6-AMBIENTE-DE-ENSAIO` e aborta se houver sessão aberta em `nsi_ensaio` (ele nunca derruba sessão):

   ```powershell
   & "C:\Program Files\PostgreSQL\17\bin\psql.exe" -h localhost -p 5432 -U postgres -d postgres -X -f scripts/postgres_local/desprovisionar_b6_ensaio.sql
   ```

   Resultado esperado: `passou integralmente - ambiente de ensaio descartado` (`E16`). O script também força `CHECKPOINT` e a troca do segmento de WAL.
3. Apagar `origem/`, `restauracao/`, `instalacao_sintetica/` (Rodada S) e, conforme `D7`, `backup/`.
4. Remover do `.env` local as variáveis `ENSAIO_DATABASE_URL` e `ENSAIO_DATABASE_URL_NSI_IMPORTACAO`; limpar `NSI_ENSAIO_DIR` e `NSI_DATABASE_ENV` da sessão.
5. Limpar o histórico do terminal e os arquivos temporários da rodada, inclusive os logs em `$env:TEMP`.
6. **Verificar** (`E14`, `E15`): `nsi_ensaio` e `nsi_ensaio_migrator` inexistentes; `nsi_importacao` com `CONNECT` somente em `nsi_test`; área de ensaio contendo somente `evidencias/`.
7. **Suíte completa** em `nsi_test`, no modo de aceite, e conferência de `nsi_dev` e `nsi_test` em `0006` (`E17`).

Limite técnico declarado: apagar arquivos e remover o banco não sobrescreve os blocos no disco. A proteção é a criptografia em repouso do volume.

## 6. Falhas e o que fazer

| Sinal | Falha | Ação |
|---|---|---|
| Ferramenta responde "area de ensaio nao informada" | configuração | definir `NSI_ENSAIO_DIR`; nada foi feito |
| Executor responde "banco nao permitido" ou "nao foi possivel conectar" | `F1` | conferir `NSI_DATABASE_ENV` e as variáveis `ENSAIO_DATABASE_URL*`; nada foi gravado |
| `comparar I1 I2` devolve `1` | `F2` | retomar a aplicação; cancelar a rodada |
| Restauração diferente de `I1` | `F3` | retomar a aplicação; cancelar a rodada |
| `copiar` devolve `1` | `F4` | retomar a aplicação; cancelar a rodada |
| Executor devolve `2` depois de iniciar | `F5` | **não retomar a execução**; descartar e recomeçar |
| Executor devolve `1` | `F6` | registrar; descartar; a rodada está reprovada |
| `auditar` devolve `1` | `F7` | o campo `divergencias` traz os códigos; registrar; descartar |
| `comparar I1 I3` devolve `1` | `F8` | a origem mudou durante a pausa: investigar antes de qualquer nova rodada |
| Prazo de `D6` vencido | `F9` se o dado não for eliminado | encerrar como interrompida e eliminar |

Em qualquer falha durante a pausa, **a aplicação é retomada antes de qualquer análise**. Depois de qualquer falha, a Seção 5 é executada por inteiro.

## 7. O que este procedimento não faz

- Não define o backup de produção, RPO ou RTO (Seção 14 da Especificação Técnica da Sprint B).
- Não executa o corte: nenhum identificador, snapshot ou promoção do ensaio tem valor fora dele. O corte é da B7.
- Não substitui a decisão jurídica de retenção do sistema.
- Não cobre a evidência opcional `O1` (`pg_dump` e restauração, `D9`): ela é executada pelo operador com as ferramentas do PostgreSQL, e o dump e o banco temporário são eliminados com o ambiente.
