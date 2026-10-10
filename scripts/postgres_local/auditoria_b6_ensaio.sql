-- =============================================================
-- scripts/postgres_local/auditoria_b6_ensaio.sql
-- Sprint B (B6) - SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md (Secao 28,
-- componente C7): auditoria e quantificacao do ensaio de corte.
--
-- SOMENTE LEITURA. Este arquivo contem exclusivamente consultas SELECT -
-- nenhum comando de escrita, de transacao, de sessao ou de papel. Nao e
-- executado diretamente no psql: e lido por scripts/ensaio_corte.py
-- ("auditar"), que abre a transacao em modo READ ONLY, assume
-- nsi_eventos_owner com SET LOCAL ROLE e executa cada consulta.
--
-- FORMATO: cada consulta comeca numa linha "-- @consulta <nome>" e devolve
-- UMA linha com UMA coluna JSONB. Os nomes sao a chave do resultado.
--
-- PRIVACIDADE: toda saida e contagem, enum, booleano, identificador
-- tecnico, caminho relativo do escopo ou o valor LITERAL do status legado
-- (ADR-010, Secao 14) - nunca nome, telefone, produto ou conteudo de
-- registro. O snapshot e lido somente para contar e para aplicar as
-- evidencias de disparo do item 6.3 da B5.2.
--
-- Partes: A (integridade estrutural), B (invariantes da importacao) e
-- C (quantificacao - ADR-010, Secao 12.3). A parte D (privacidade das
-- evidencias) e feita em Python, sobre valores amostrados em memoria.
-- =============================================================

-- A revisao do Alembic NAO e lida aqui: a tabela de controle pertence ao
-- migrator, e estas consultas rodam como nsi_eventos_owner, que nao tem
-- privilegio nela. scripts/ensaio_corte.py le a revisao como o migrator,
-- antes de assumir o owner, e a acrescenta ao resultado de a_revisao.
-- @consulta a_revisao
SELECT jsonb_build_object('banco', current_database());

-- @consulta a_catalogo
SELECT jsonb_build_object(
    'tabelas', (SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname = 'nsi_operacional'),
    'funcoes', (SELECT count(*) FROM pg_catalog.pg_proc p
                  JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'nsi_operacional'),
    'funcoes_security_definer', (SELECT count(*) FROM pg_catalog.pg_proc p
                                   JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                                  WHERE n.nspname = 'nsi_operacional' AND p.prosecdef),
    'indices', (SELECT count(*) FROM pg_catalog.pg_indexes WHERE schemaname = 'nsi_operacional'),
    'constraints', (SELECT count(*) FROM pg_catalog.pg_constraint o
                      JOIN pg_catalog.pg_class c ON c.oid = o.conrelid
                      JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                     WHERE n.nspname = 'nsi_operacional'),
    'triggers', (SELECT count(*) FROM pg_catalog.pg_trigger t
                   JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
                   JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = 'nsi_operacional' AND NOT t.tgisinternal),
    'impressao_digital', md5(
        COALESCE((SELECT string_agg(tablename || '|' || CASE WHEN tablename = 'alembic_version'
                                                             THEN 'migrator' ELSE tableowner END,
                                    ',' ORDER BY tablename)
                    FROM pg_catalog.pg_tables WHERE schemaname = 'nsi_operacional'), '')
        || '#' ||
        COALESCE((SELECT string_agg(p.proname || '|' || pg_get_userbyid(p.proowner) || '|' || p.prosecdef::text
                                    || '|' || COALESCE(p.proconfig::text, '') || '|'
                                    || md5(pg_get_functiondef(p.oid)), ',' ORDER BY p.proname)
                    FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                   WHERE n.nspname = 'nsi_operacional'), '')
        || '#' ||
        COALESCE((SELECT string_agg(indexname || '|' || indexdef, ',' ORDER BY indexname)
                    FROM pg_catalog.pg_indexes WHERE schemaname = 'nsi_operacional'), '')
        || '#' ||
        COALESCE((SELECT string_agg(c.relname || '|' || o.conname || '|' || pg_get_constraintdef(o.oid),
                                    ',' ORDER BY c.relname, o.conname)
                    FROM pg_catalog.pg_constraint o
                    JOIN pg_catalog.pg_class c ON c.oid = o.conrelid
                    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'nsi_operacional'), '')
        || '#' ||
        COALESCE((SELECT string_agg(c.relname || '|' || t.tgname || '|' || t.tgtype::text || '|' || t.tgenabled::text,
                                    ',' ORDER BY c.relname, t.tgname)
                    FROM pg_catalog.pg_trigger t
                    JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
                    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'nsi_operacional' AND NOT t.tgisinternal), '')));

-- @consulta a_objetos_invalidos
SELECT jsonb_build_object(
    'indices_invalidos', (SELECT count(*) FROM pg_catalog.pg_index i
                            JOIN pg_catalog.pg_class c ON c.oid = i.indexrelid
                            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                           WHERE n.nspname = 'nsi_operacional' AND (NOT i.indisvalid OR NOT i.indisready)),
    'constraints_nao_validadas', (SELECT count(*) FROM pg_catalog.pg_constraint o
                                    JOIN pg_catalog.pg_namespace n ON n.oid = o.connamespace
                                   WHERE n.nspname = 'nsi_operacional' AND NOT o.convalidated),
    'triggers_desabilitadas', (SELECT count(*) FROM pg_catalog.pg_trigger t
                                 JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
                                 JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                                WHERE n.nspname = 'nsi_operacional' AND NOT t.tgisinternal AND t.tgenabled <> 'O'),
    'security_definer_sem_search_path_fixo', (
        SELECT count(*) FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND p.prosecdef
           AND (p.proconfig IS NULL
                OR NOT ('search_path=pg_catalog, nsi_operacional, pg_temp' = ANY (p.proconfig)))),
    'funcoes_com_execute_de_public', (
        SELECT count(*) FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         CROSS JOIN LATERAL aclexplode(p.proacl) a
         WHERE n.nspname = 'nsi_operacional' AND a.grantee = 0),
    'objetos_com_outro_dono', (
        (SELECT count(*) FROM pg_catalog.pg_proc p
           JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
          WHERE n.nspname = 'nsi_operacional' AND pg_get_userbyid(p.proowner) <> 'nsi_eventos_owner')
        + (SELECT count(*) FROM pg_catalog.pg_tables
            WHERE schemaname = 'nsi_operacional' AND tablename <> 'alembic_version'
              AND tableowner <> 'nsi_eventos_owner')));

-- @consulta a_concessoes
SELECT jsonb_build_object(
    'connect_no_banco', (
        SELECT COALESCE(jsonb_agg(nome ORDER BY nome), '[]'::jsonb)
          FROM (SELECT DISTINCT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS nome
                  FROM pg_catalog.pg_database d
                 CROSS JOIN LATERAL aclexplode(d.datacl) a
                 WHERE d.datname = current_database() AND a.privilege_type = 'CONNECT'
                   AND a.grantee <> d.datdba) AS s),
    'usage_no_schema', (
        SELECT COALESCE(jsonb_agg(nome ORDER BY nome), '[]'::jsonb)
          FROM (SELECT DISTINCT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS nome
                  FROM pg_catalog.pg_namespace n
                 CROSS JOIN LATERAL aclexplode(n.nspacl) a
                 WHERE n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE'
                   AND a.grantee <> n.nspowner) AS s),
    'concessoes_em_tabela', (
        SELECT count(*) FROM pg_catalog.pg_class c
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
         CROSS JOIN LATERAL aclexplode(c.relacl) a
         WHERE n.nspname = 'nsi_operacional' AND c.relkind = 'r' AND c.relname <> 'alembic_version'
           AND a.grantee <> c.relowner),
    'execute_de_nsi_importacao', (
        SELECT COALESCE(jsonb_agg(p.proname ORDER BY p.proname), '[]'::jsonb)
          FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND has_function_privilege('nsi_importacao', p.oid, 'EXECUTE')));

-- @consulta b_tabelas_que_devem_estar_vazias
SELECT jsonb_build_object(
    'eventos_lote', (SELECT count(*) FROM nsi_operacional.eventos_lote),
    'eventos_registro_coleta', (SELECT count(*) FROM nsi_operacional.eventos_registro_coleta),
    'eventos_claim', (SELECT count(*) FROM nsi_operacional.eventos_claim),
    'claims', (SELECT count(*) FROM nsi_operacional.claims),
    'comandos_idempotentes', (SELECT count(*) FROM nsi_operacional.comandos_idempotentes));

-- @consulta b_execucoes
SELECT jsonb_build_object(
    'execucoes', (SELECT count(*) FROM nsi_operacional.importacoes_legado),
    'concluidas', (SELECT count(*) FROM nsi_operacional.importacoes_legado_conclusoes),
    'logins', (SELECT COALESCE(jsonb_agg(DISTINCT executado_por_login), '[]'::jsonb)
                 FROM nsi_operacional.importacoes_legado),
    'fusos_declarados', (SELECT COALESCE(jsonb_agg(DISTINCT fuso_declarado), '[]'::jsonb)
                           FROM nsi_operacional.importacoes_legado),
    'conclusoes_com_total_divergente', (
        SELECT count(*) FROM nsi_operacional.importacoes_legado_conclusoes c
         WHERE c.total_arquivos <> (SELECT count(*) FROM nsi_operacional.importacoes_legado_arquivos a
                                     WHERE a.importacao_id = c.importacao_id)),
    'conclusoes_com_sha256_divergente', (
        SELECT count(*) FROM nsi_operacional.importacoes_legado_conclusoes c
         WHERE c.manifesto_sha256 <> encode(sha256(c.manifesto_canonico), 'hex')));

-- @consulta b_invariantes
SELECT jsonb_build_object(
    'promovidos_de_geracao_anterior_a_a2', (
        SELECT count(*) FROM nsi_operacional.lotes_legado
         WHERE destino = 'promovido' AND geracao NOT IN ('a2', 'a3')),
    'registros_sem_identidade_com_uuid', (
        SELECT count(*) FROM nsi_operacional.registros_legado
         WHERE classificacao = 'legado_sem_identidade_tecnica' AND registro_coleta_id IS NOT NULL),
    'registros_identificados_sem_uuid', (
        SELECT count(*) FROM nsi_operacional.registros_legado
         WHERE classificacao <> 'legado_sem_identidade_tecnica' AND registro_coleta_id IS NULL),
    -- Restrito ao lote promovido DO PROPRIO snapshot: um lote preservado por
    -- 'colisao_de_identidade' repete, legitimamente, o identificador de um
    -- registro que outro lote levou para a projecao.
    'registros_nao_promovidos_na_projecao', (
        SELECT count(*) FROM nsi_operacional.registros_legado g
          JOIN nsi_operacional.lotes_legado s ON s.snapshot_lote_id = g.snapshot_lote_id
          JOIN nsi_operacional.registros_coleta r ON r.registro_coleta_id = g.registro_coleta_id
                                                 AND r.lote_id = s.lote_id_promovido
         WHERE g.classificacao = 'legado_identificado_nao_promovido'),
    'lotes_promovidos_fora_do_estado_inicial', (
        SELECT count(*) FROM nsi_operacional.lotes_legado g
          JOIN nsi_operacional.lotes l ON l.lote_id = g.lote_id_promovido
         WHERE l.status <> 'aguardando_d8' OR l.versao_eventos_atual <> 1),
    'registros_promovidos_com_versao_de_eventos', (
        SELECT count(*) FROM nsi_operacional.lotes_legado g
          JOIN nsi_operacional.registros_coleta r ON r.lote_id = g.lote_id_promovido
         WHERE r.versao_eventos_atual <> 0),
    'lotes_da_projecao_sem_origem_legada', (
        SELECT count(*) FROM nsi_operacional.lotes l
         WHERE NOT EXISTS (SELECT 1 FROM nsi_operacional.lotes_legado g WHERE g.lote_id_promovido = l.lote_id)),
    'snapshots_com_sha256_divergente', (
        SELECT count(*) FROM nsi_operacional.lotes_legado
         WHERE documento_sha256 <> encode(sha256(documento_bruto), 'hex')));

-- @consulta b_arquivos
SELECT COALESCE(jsonb_agg(jsonb_build_object(
                    'caminho_relativo', a.caminho_relativo,
                    'geracao', a.geracao,
                    'destino', a.destino,
                    'motivo', a.motivo,
                    'constraint_violada', a.constraint_violada)
                ORDER BY a.caminho_relativo COLLATE "C"), '[]'::jsonb)
  FROM nsi_operacional.importacoes_legado_arquivos a;

-- @consulta c_lotes_por_geracao_e_destino
SELECT COALESCE(jsonb_agg(jsonb_build_object('geracao', s.geracao, 'destino', s.destino, 'lotes', s.lotes)
                          ORDER BY s.geracao NULLS LAST, s.destino), '[]'::jsonb)
  FROM (SELECT geracao, destino, count(*) AS lotes
          FROM nsi_operacional.importacoes_legado_arquivos
         GROUP BY geracao, destino) AS s;

-- @consulta c_motivos
SELECT COALESCE(jsonb_agg(jsonb_build_object('destino', s.destino, 'motivo', s.motivo, 'lotes', s.lotes)
                          ORDER BY s.destino, s.motivo), '[]'::jsonb)
  FROM (SELECT destino, motivo, count(*) AS lotes
          FROM nsi_operacional.importacoes_legado_arquivos
         WHERE motivo IS NOT NULL
         GROUP BY destino, motivo) AS s;

-- @consulta c_registros_por_classificacao
SELECT COALESCE(jsonb_agg(jsonb_build_object('geracao', s.geracao, 'lista', s.lista,
                                             'classificacao', s.classificacao, 'registros', s.registros)
                          ORDER BY s.geracao, s.lista, s.classificacao), '[]'::jsonb)
  FROM (SELECT g.geracao, r.lista, r.classificacao, count(*) AS registros
          FROM nsi_operacional.registros_legado r
          JOIN nsi_operacional.lotes_legado g USING (snapshot_lote_id)
         GROUP BY g.geracao, r.lista, r.classificacao) AS s;

-- @consulta c_status_literal_por_geracao
SELECT COALESCE(jsonb_agg(jsonb_build_object('geracao', s.geracao, 'status_literal', s.status_literal,
                                             'lotes', s.lotes)
                          ORDER BY s.geracao, s.status_literal), '[]'::jsonb)
  FROM (SELECT geracao,
               CASE jsonb_typeof(status_legado -> 'status')
                    WHEN 'string' THEN left(status_legado ->> 'status', 60)
                    WHEN 'null' THEN '(ausente)'
                    ELSE '(' || jsonb_typeof(status_legado -> 'status') || ')' END AS status_literal,
               count(*) AS lotes
          FROM nsi_operacional.lotes_legado
         GROUP BY 1, 2) AS s;

-- @consulta c_lotes_em_andamento
SELECT COALESCE(jsonb_agg(jsonb_build_object(
                    'geracao', s.geracao, 'destino', s.destino,
                    'lotes', s.lotes, 'em_andamento', s.em_andamento,
                    'com_evidencia_de_disparo', s.lotes - s.em_andamento)
                ORDER BY s.geracao, s.destino), '[]'::jsonb)
  FROM (SELECT d.geracao, d.destino, count(*) AS lotes,
               count(*) FILTER (WHERE NOT (
                   COALESCE((d.doc ->> 'status') = 'disparado', false)
                   OR EXISTS (SELECT 1
                                FROM unnest(ARRAY['disparo_whatsapp', 'webhook', 'analise_ia',
                                                  'dashboard', 'pdf']) AS etapa
                               WHERE d.doc -> 'status_pipeline' -> etapa = 'true'::jsonb)
                   OR EXISTS (SELECT 1
                                FROM jsonb_array_elements(d.doc -> 'clientes') AS c
                               WHERE COALESCE(c -> 'data_envio_mensagem', 'null'::jsonb) <> 'null'::jsonb
                                  OR COALESCE(c -> 'status_entrega', 'null'::jsonb) <> 'null'::jsonb
                                  OR COALESCE(c -> 'data_resposta', 'null'::jsonb) <> 'null'::jsonb
                                  OR COALESCE(c -> 'resposta', 'null'::jsonb)
                                     NOT IN ('null'::jsonb, '""'::jsonb)))) AS em_andamento
          FROM (SELECT geracao, destino, convert_from(documento_bruto, 'UTF8')::jsonb AS doc
                  FROM nsi_operacional.lotes_legado) AS d
         GROUP BY d.geracao, d.destino) AS s;

-- @consulta c_intervalo_de_criado_em
SELECT jsonb_build_object(
    'lotes_no_snapshot', (SELECT count(*) FROM nsi_operacional.lotes_legado),
    'registros_no_snapshot', (SELECT count(*) FROM nsi_operacional.registros_legado),
    'lotes_na_projecao', (SELECT count(*) FROM nsi_operacional.lotes),
    'registros_na_projecao', (SELECT count(*) FROM nsi_operacional.registros_coleta),
    'menor_criado_em_bruto', (SELECT left(min(criado_em_bruto COLLATE "C"), 40) FROM nsi_operacional.lotes_legado),
    'maior_criado_em_bruto', (SELECT left(max(criado_em_bruto COLLATE "C"), 40) FROM nsi_operacional.lotes_legado));
