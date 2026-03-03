# NSI — MASTER CONTEXT

## Objetivo

O NSI é um sistema de análise semântica de pós-venda.

Após a compra, o cliente recebe uma mensagem objetiva (D+7 ou D+8) e responde de forma subjetiva.

A IA analisa a resposta considerando semântica, hermenêutica e figuras de linguagem, com o objetivo de identificar fricções e dores do cliente, classificadas em 110 categorias estruturadas.

## Stack

- Python 3.12
- Streamlit (interface)
- Pandas (leitura e normalização de dados)
- ReportLab (geração de PDF executivo)
- VPS Linux (Hostinger)
- Domínio e e-mail oficial via Hostinger
- WhatsApp Oficial (API oficial, sem uso de APIs não oficiais)


## Arquitetura (fluxo)

1. Exportar relatório de vendas do sistema da loja (últimos 15 dias).
2. Upload do arquivo no sistema (Streamlit).
3. O sistema inicia contagem D+8 (agendamento via Cron).
   - Existe um botão de emergência para interromper/forçar o fluxo caso haja perda de data/atraso.
4. No D+8, o sistema chama a API oficial do WhatsApp e dispara a mensagem de pós-venda.
5. O sistema aguarda 72 horas por respostas (janela de resposta com contagem regressiva).
6. Ao finalizar a janela, as respostas retornam para o motor de análise.
7. O motor analisa padrões e identifica as principais fricções/dores:
   - Retorna top fricções (ex: top 10) com score/percentual de 0 a 100, ordenadas da maior para a menor.
8. Exportação de resultados:
   - Excel/CSV (dados)
   - PDF (relatório didático + semântico)
9. Interface (Streamlit) executa em cascata com status/ok por etapa e barra de progresso (vermelho → verde)

## Módulos (arquivos)

- app.py (interface Streamlit)
- services/excel_reader.py
- services/analisar_ab.py
- services/export_pdf.py
- processar_lote.py
- export_reports.py

## Regras fixas / decisões

- O disparo de pós-venda ocorre exclusivamente em D+8 (contagem por dia via Cron).
- Existe botão de emergência para interromper ou forçar o fluxo caso haja falha de data.
- A janela de resposta é fixa em 72 horas (contagem regressiva).
- Após 72h, o lote é fechado automaticamente e enviado para o motor de análise.
- Modelo A (determinístico) sempre executa.
- Modelo B (IA semântica profunda) pode falhar, mas nunca pode quebrar o pipeline.
- O contrato de saída em JSON é fixo e não pode ser alterado.
- A análise deve classificar as dores dentro das 110 categorias estruturadas.
- A saída sempre deve gerar:
  - CSV/Excel estruturado
  - PDF executivo (didático + semântico)
- Cada etapa do sistema deve concluir com status claro (OK/erro) na interface.
- O fluxo é em cascata: nenhuma etapa avança sem concluir a anterior.
- O sistema deve usar apenas WhatsApp Oficial (sem APIs não oficiais).
- Modularização é obrigatória (proibido monolito).
- A chave principal de rastreamento é o celular.
- Pós-venda é por compra/produto, não por cliente.

## O que já funciona

- Upload do arquivo (entrada) funciona.
- Motor de análise (núcleo) funciona.
- Exportação de CSV funciona parcialmente (gera saída, mas o relatório completo não está consistente).

## O que NÃO está funcionando (estado atual)

- Contagem D+8 (Cron) não está funcionando.
- Botão de emergência não está funcionando.
- Disparo via WhatsApp Oficial não está funcionando.
- Webhook/retorno de respostas não está funcionando.
- Geração de relatório/PDF não está funcionando como deveria.
- Estrutura do projeto está inconsistente (muitos arquivos dentro de arquivos, módulos não se conversam).

## O que falta

## Próximo passo (1 hora)