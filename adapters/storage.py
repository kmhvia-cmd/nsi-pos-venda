# -*- coding: utf-8 -*-
"""
NSI - adapters/storage.py
Responsabilidade: salvar e carregar lotes e analises em disco
"""
import csv
import io
import json
import os
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from config import Config


CABECALHOS_CANONICOS_CSV = {"nome", "whatsapp", "produto"}

# Codigos Nacionais destinados no Brasil conforme o Plano Geral de
# Codigos Nacionais da Anatel (67 codigos). ADR-007 SS8 exige "DDD" -
# nao apenas "2 digitos quaisquer": "55" + 2 digitos quaisquer + numero
# local nao comprova que o DDD existe.
DDDS_VALIDOS_BRASIL = {
    11, 12, 13, 14, 15, 16, 17, 18, 19,
    21, 22, 24, 27, 28,
    31, 32, 33, 34, 35, 37, 38,
    41, 42, 43, 44, 45, 46, 47, 48, 49,
    51, 53, 54, 55,
    61, 62, 63, 64, 65, 66, 67, 68, 69,
    71, 73, 74, 75, 77, 79,
    81, 82, 83, 84, 85, 86, 87, 88, 89,
    91, 92, 93, 94, 95, 96, 97, 98, 99,
}


def _valor_ou_ausente(bruto) -> str | None:
    """
    ADR-007 SS8 / Decisao 3 (Sprint A2): ausencia e SOMENTE None
    tecnico (defensivo - o caminho real via csv.reader nunca produz
    isso, apenas strings, inclusive vazias), string vazia, ou string
    composta somente por espacos. Textos literais "nan"/"none"/"null"
    (em qualquer capitalizacao) NUNCA sao tratados como ausencia -
    podem ser nomes ou produtos reais e sao preservados como conteudo.
    """
    if bruto is None:
        return None
    if isinstance(bruto, float) and pd.isna(bruto):
        return None
    texto = str(bruto).strip()
    return None if texto == "" else texto


def _normalizar_whatsapp(bruto: str) -> str:
    """
    Normalizacao TECNICA (ADR-007 SS8, Decisoes 4-8) - nunca valida,
    apenas transforma. Remove espacos, '+', hifens e parenteses. O
    codigo do pais e considerado presente ou ausente PELO COMPRIMENTO
    do numero ja limpo, nunca por ele comecar com "55" isoladamente -
    o DDD 55 (Santa Maria/RS) tornaria essa checagem ambigua.
    """
    apenas_digitos = re.sub(r"[\s\+\-\(\)]", "", bruto)
    if not apenas_digitos.isdigit():
        return apenas_digitos  # validacao seguinte rejeita com motivo especifico
    if len(apenas_digitos) in (10, 11):
        return "55" + apenas_digitos  # nacional sem codigo do pais
    return apenas_digitos  # 12/13: assume-se codigo ja presente; qualquer
                            # outro comprimento e devolvido sem alteracao


def _validar_whatsapp(normalizado: str) -> str | None:
    """
    Cadeia de verificacao EXCLUSIVA - no maximo UM motivo por campo
    whatsapp, nunca cascata (uma falha de caracteres nunca tambem gera
    uma falha de comprimento decorrente dela). Valida o DDD contra o
    conjunto explicito de codigos brasileiros reais (Anatel) - nunca
    apenas "2 digitos quaisquer". NUNCA prova posse real de conta no
    WhatsApp (ADR-007 SS8).
    """
    if not normalizado.isdigit():
        return "whatsapp_caracteres_invalidos"
    if len(normalizado) not in (12, 13):
        return "whatsapp_comprimento_invalido"
    if not normalizado.startswith("55"):
        return "whatsapp_codigo_pais_invalido"
    if int(normalizado[2:4]) not in DDDS_VALIDOS_BRASIL:
        return "whatsapp_ddd_invalido"
    return None


def _validar_linha(nome_bruto, whatsapp_bruto, produto_bruto) -> dict:
    """
    Valida uma linha isoladamente (ADR-007 SS8, Decisao 11) - nunca
    bloqueia por causa de outra linha. Uma linha pode acumular ate tres
    motivos (um por campo), mas cada campo contribui com no maximo um.
    Os valores brutos sao preservados EXATAMENTE como recebidos do
    csv.reader, sem conversao (str(None) fabricaria o texto "None").
    """
    motivos = []

    nome = _valor_ou_ausente(nome_bruto)
    if nome is None:
        motivos.append("nome_ausente")

    produto = _valor_ou_ausente(produto_bruto)
    if produto is None:
        motivos.append("produto_ausente")

    whatsapp_valor = _valor_ou_ausente(whatsapp_bruto)
    telefone_normalizado = None
    if whatsapp_valor is None:
        motivos.append("whatsapp_ausente")
    else:
        telefone_normalizado = _normalizar_whatsapp(whatsapp_valor)
        motivo_whatsapp = _validar_whatsapp(telefone_normalizado)
        if motivo_whatsapp:
            motivos.append(motivo_whatsapp)

    return {
        "valido": len(motivos) == 0,
        "motivos": motivos,
        "nome_bruto": nome_bruto,
        "whatsapp_bruto": whatsapp_bruto,
        "produto_bruto": produto_bruto,
        "nome": nome,
        "telefone": telefone_normalizado,
        "produto": produto,
    }


def salvar_lote(arquivo, empresa="", nome="", data_inicio="", data_fim="") -> dict:
    """
    ADR-007 Secao 6: o CSV original possui EXCLUSIVAMENTE tres campos -
    nome, WhatsApp, produto. Apenas arquivos .csv sao aceitos (a decisao
    aprovada fala em CSV, nao em Excel). Ordem das colunas e livre,
    desde que os tres cabecalhos canonicos estejam presentes, sem
    duplicatas e sem colunas extras - o mapeamento e sempre por NOME de
    coluna, nunca por posicao (row.iloc[N]).

    A entrada empresarial usa o cabecalho "whatsapp"; internamente o
    campo permanece "telefone", preenchido a partir da coluna
    "whatsapp" - e um MAPEAMENTO documentado, nao uma divergencia de
    nomenclatura.

    Sprint A1 (Parte 4 do plano de implementacao): apenas identidade
    por linha e validacao ESTRUTURAL do cabecalho. Normalizacao de
    whatsapp, validacao de conteudo, separacao de validos/invalidos e
    versionamento pertencem as Sprints A2/A3 - nao implementadas aqui.

    Nenhum diretorio de lote e criado antes de a validacao estrutural
    do arquivo e do cabecalho ser concluida com sucesso - um arquivo
    rejeitado (extensao errada, vazio, cabecalho invalido ou linha com
    numero de campos incorreto) nunca deixa efeito persistente em disco.

    UM UNICO PARSER e usado para interpretar o CSV: csv.reader (modulo
    padrao), sobre o conteudo completo, respeitando aspas e virgulas
    internas corretamente (nunca split(",") manual). O pandas e usado
    apenas para construir o DataFrame a partir das linhas JA
    interpretadas e validadas pelo csv.reader - nunca para reler o
    texto bruto de forma independente. Isso elimina o risco,
    comprovado empiricamente, de o pandas reinterpretar silenciosamente
    uma linha com campo excedente como indice implicito, produzindo uma
    leitura divergente da que foi validada.
    """
    nome_arquivo = arquivo.filename
    if not nome_arquivo.lower().endswith(".csv"):
        return {"erro": "Apenas arquivos .csv sao aceitos (ADR-007 SS6) - Excel nao e suportado nesta etapa"}

    # Le o conteudo inteiro uma unica vez, com utf-8-sig - aceita tanto
    # UTF-8 puro quanto UTF-8 com BOM (comum em exportacoes do Excel)
    # sem que o BOM vire parte do nome da primeira coluna. Nenhum valor
    # real e alterado - utf-8-sig apenas remove o marcador BOM quando
    # presente, sem efeito quando ausente.
    conteudo_bruto = arquivo.read()
    if isinstance(conteudo_bruto, bytes):
        try:
            conteudo_texto = conteudo_bruto.decode("utf-8-sig")
        except UnicodeDecodeError:
            return {"erro": "CSV nao pode ser interpretado como UTF-8"}
    else:
        # arquivo.read() ja retornou str (texto) - o conteudo real e
        # preservado integralmente; remove-se somente um eventual BOM
        # inicial (U+FEFF), nunca qualquer outro caractere.
        conteudo_texto = conteudo_bruto.lstrip(chr(0xFEFF))

    if not conteudo_texto.strip():
        return {"erro": "CSV vazio - nenhum cabecalho encontrado"}

    try:
        linhas_parseadas = list(csv.reader(io.StringIO(conteudo_texto)))
    except csv.Error:
        return {"erro": "Nao foi possivel interpretar o CSV"}

    if not linhas_parseadas:
        return {"erro": "CSV vazio - nenhum cabecalho encontrado"}

    cabecalho_bruto, linhas_de_dados = linhas_parseadas[0], linhas_parseadas[1:]
    colunas_normalizadas = [c.strip().lower() for c in cabecalho_bruto]

    if len(colunas_normalizadas) != len(set(colunas_normalizadas)):
        return {"erro": "CSV contem cabecalhos duplicados"}

    if len(colunas_normalizadas) != 3 or set(colunas_normalizadas) != CABECALHOS_CANONICOS_CSV:
        faltando = sorted(CABECALHOS_CANONICOS_CSV - set(colunas_normalizadas))
        extras = sorted(set(colunas_normalizadas) - CABECALHOS_CANONICOS_CSV)
        detalhe = []
        if faltando:
            detalhe.append(f"faltando: {faltando}")
        if extras:
            detalhe.append(f"nao reconhecidos: {extras}")
        return {"erro": f"CSV deve conter exatamente os cabecalhos nome, whatsapp, produto - {'; '.join(detalhe)}"}

    def _linha_em_branco(linha: list) -> bool:
        return linha == [] or (len(linha) == 1 and linha[0].strip() == "")

    linhas_de_dados_validas = [linha for linha in linhas_de_dados if not _linha_em_branco(linha)]

    # Cada linha de dados precisa ter EXATAMENTE 3 campos. Uma linha com
    # campo excedente (ou faltando) nunca e reinterpretada por nenhum
    # mecanismo implicito - o upload inteiro e recusado de forma
    # estrutural. A separacao linha a linha entre conteudo valido e
    # invalido pertence a Sprint A2, nao a esta.
    for numero_linha, linha in enumerate(linhas_de_dados_validas, start=2):
        if len(linha) != 3:
            return {"erro": f"Linha {numero_linha} do CSV possui {len(linha)} campo(s), esperado exatamente 3"}

    # DataFrame construido a partir das MESMAS linhas ja interpretadas
    # e validadas pelo csv.reader - nao ha uma segunda leitura do texto
    # bruto pelo parser proprio do pandas.
    df = pd.DataFrame(linhas_de_dados_validas, columns=colunas_normalizadas)

    # Sprint A2: cada linha e validada isoladamente e separada entre
    # validos e invalidos (ADR-007 SS8, Decisao 11) - a existencia de
    # invalidos nunca bloqueia os validos. registro_coleta_id e gerado
    # ANTES da validacao e preservado igualmente em ambos os grupos.
    clientes_validos = []
    clientes_invalidos = []
    for _, row in df.iterrows():
        registro_coleta_id = str(uuid.uuid4())
        resultado_linha = _validar_linha(row["nome"], row["whatsapp"], row["produto"])

        if resultado_linha["valido"]:
            clientes_validos.append({
                "registro_coleta_id": registro_coleta_id,
                "nome":     resultado_linha["nome"],
                "telefone": resultado_linha["telefone"],
                "produto":  resultado_linha["produto"],
                "resposta": "",
            })
        else:
            clientes_invalidos.append({
                "registro_coleta_id": registro_coleta_id,
                "nome_bruto":     resultado_linha["nome_bruto"],
                "whatsapp_bruto": resultado_linha["whatsapp_bruto"],
                "produto_bruto":  resultado_linha["produto_bruto"],
                "motivos": resultado_linha["motivos"],
            })

    # Lote sem nenhum registro valido e criado e preservado normalmente
    # - NUNCA tratado como erro de upload (o arquivo foi estruturalmente
    # aceito). Recebe status proprio para que nunca fique elegivel a
    # disparo (bloqueio implementado em core/scheduler.py).
    status_lote = "sem_registros_validos" if len(clientes_validos) == 0 else "aguardando_d8"

    # Identidade e diretorio do lote so sao criados AQUI - depois que
    # toda a validacao estrutural e o parsing ja foram concluidos com
    # sucesso (correcao vinculante da Sprint A1).
    lote_id = f"NSI-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
    lote_dir = Path(Config.LOTES_DIR) / lote_id
    lote_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "lote_id":          lote_id,
        "empresa":          empresa,
        "nome_lote":        nome,
        "data_inicial":     data_inicio,
        "data_final":       data_fim,
        "csv_original":     nome_arquivo,
        "criado_em":        datetime.now().isoformat(),
        # total_clientes: CAMPO LEGADO, mantido por compatibilidade com
        # consumidores existentes - corresponde a total_valido, NUNCA
        # ao total recebido.
        "total_clientes":   len(clientes_validos),
        "total_recebido":   len(clientes_validos) + len(clientes_invalidos),
        "total_valido":     len(clientes_validos),
        "total_invalido":   len(clientes_invalidos),
        "status":            status_lote,
        "data_disparo":      (datetime.now() + timedelta(days=8)).isoformat(),
        "status_pipeline": {
            "upload":             True,
            "lote_criado":        True,
            "aguardando_d8":      False,
            "disparo_whatsapp":   False,
            "webhook":            False,
            "analise_ia":         False,
            "dashboard":          False,
            "pdf":                False
        },
        "clientes": clientes_validos,
        "clientes_invalidos": clientes_invalidos,
    }

    with open(lote_dir / "lote.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return {
        "lote_id": lote_id,
        "total_clientes": len(clientes_validos),
        "total_recebido": len(clientes_validos) + len(clientes_invalidos),
        "total_valido": len(clientes_validos),
        "total_invalido": len(clientes_invalidos),
        "status": status_lote,
        "mensagem": "lote_criado",
    }


# ============================================================
# Sprint A3 - fluxo de correcao append-only (ADR-007 SS9)
#
# Funcoes INTERNAS apenas - nenhuma rota HTTP e criada nesta sprint.
# Rotas, autenticacao e MFA do Operador Interno pertencem a Sprint D.
# ============================================================

CABECALHOS_CANONICOS_CORRECAO = {"codigo_tecnico", "nome", "whatsapp", "produto"}
PROCESSO_CORRECAO = "upload_correcao_csv"
RECEBIDO_POR_PROVISORIO = "operador_interno_nao_autenticado"


def _normalizar_codigo_tecnico(bruto: str) -> tuple[str | None, str | None]:
    """
    Valida e normaliza um codigo_tecnico ANTES de qualquer busca (local
    ou global). Retorna (codigo_normalizado, None) em sucesso, ou
    (None, motivo) em falha - "codigo_tecnico_ausente" ou
    "codigo_tecnico_invalido". Um codigo ausente ou malformado nunca
    dispara busca alguma - a invalidez e puramente sintatica.
    """
    valor = (bruto or "").strip()
    if not valor:
        return None, "codigo_tecnico_ausente"
    try:
        codigo_uuid = uuid.UUID(valor)
    except (ValueError, AttributeError, TypeError):
        return None, "codigo_tecnico_invalido"
    if codigo_uuid.version != 4:
        return None, "codigo_tecnico_invalido"
    return str(codigo_uuid), None


def _parsear_csv_correcao(conteudo_bruto) -> tuple[list, str | None]:
    """
    Parser INDEPENDENTE do CSV de correcao - nunca importa nem
    reutiliza salvar_lote. Mesma disciplina da Sprint A1: csv.reader
    UNICO sobre o conteudo completo, utf-8-sig para BOM, cabecalho
    canonico exato em ordem livre, sem duplicatas nem colunas extras,
    4 campos exatos por linha. Um CSV so com cabecalho (ou apenas
    linhas em branco depois dele) e recusado com
    "csv_correcao_sem_registros" - nenhuma tentativa de correcao
    individual foi apresentada. Funcao PURA - nunca cria diretorio ou
    arquivo, mesmo em falha estrutural.
    """
    if isinstance(conteudo_bruto, bytes):
        try:
            conteudo_texto = conteudo_bruto.decode("utf-8-sig")
        except UnicodeDecodeError:
            return [], "CSV de correcao nao pode ser interpretado como UTF-8"
    else:
        conteudo_texto = conteudo_bruto.lstrip(chr(0xFEFF))

    if not conteudo_texto.strip():
        return [], "CSV de correcao vazio - nenhum cabecalho encontrado"

    try:
        linhas_parseadas = list(csv.reader(io.StringIO(conteudo_texto)))
    except csv.Error:
        return [], "Nao foi possivel interpretar o CSV de correcao"

    if not linhas_parseadas:
        return [], "CSV de correcao vazio - nenhum cabecalho encontrado"

    cabecalho_bruto, linhas_de_dados = linhas_parseadas[0], linhas_parseadas[1:]
    colunas_normalizadas = [c.strip().lower() for c in cabecalho_bruto]

    if len(colunas_normalizadas) != len(set(colunas_normalizadas)):
        return [], "CSV de correcao contem cabecalhos duplicados"

    if len(colunas_normalizadas) != 4 or set(colunas_normalizadas) != CABECALHOS_CANONICOS_CORRECAO:
        faltando = sorted(CABECALHOS_CANONICOS_CORRECAO - set(colunas_normalizadas))
        extras = sorted(set(colunas_normalizadas) - CABECALHOS_CANONICOS_CORRECAO)
        detalhe = []
        if faltando:
            detalhe.append(f"faltando: {faltando}")
        if extras:
            detalhe.append(f"nao reconhecidos: {extras}")
        return [], (f"CSV de correcao deve conter exatamente os cabecalhos "
                     f"codigo_tecnico, nome, whatsapp, produto - {'; '.join(detalhe)}")

    def _linha_em_branco(linha: list) -> bool:
        return linha == [] or (len(linha) == 1 and linha[0].strip() == "")

    linhas_de_dados_validas = [l for l in linhas_de_dados if not _linha_em_branco(l)]

    if not linhas_de_dados_validas:
        return [], "csv_correcao_sem_registros"

    for numero_linha, linha in enumerate(linhas_de_dados_validas, start=2):
        if len(linha) != 4:
            return [], f"Linha {numero_linha} do CSV de correcao possui {len(linha)} campo(s), esperado exatamente 4"

    idx = {nome: colunas_normalizadas.index(nome) for nome in CABECALHOS_CANONICOS_CORRECAO}

    linhas = [
        {
            "codigo_tecnico": linha[idx["codigo_tecnico"]],
            "nome": linha[idx["nome"]],
            "whatsapp": linha[idx["whatsapp"]],
            "produto": linha[idx["produto"]],
        }
        for linha in linhas_de_dados_validas
    ]
    return linhas, None


def _buscar_em_clientes(lote: dict, registro_coleta_id: str) -> dict | None:
    """
    Usa .get("registro_coleta_id") - nunca c["registro_coleta_id"] -
    para que a busca (inclusive a diagnostica em outros lotes, possivelmente
    anteriores a Sprint A1) nunca lance KeyError ao atravessar registros
    legados sem essa chave. Um cliente sem a chave simplesmente nunca
    corresponde (comparado a None), sem quebrar a iteracao.
    """
    return next((c for c in lote.get("clientes", []) if c.get("registro_coleta_id") == registro_coleta_id), None)


def _buscar_em_clientes_invalidos(lote: dict, registro_coleta_id: str) -> dict | None:
    return next((c for c in lote.get("clientes_invalidos", []) if c.get("registro_coleta_id") == registro_coleta_id), None)


def _existe_em_outro_lote(lote_id_atual: str, registro_coleta_id: str) -> bool:
    """
    Diagnostico secundario - le outros lotes SEM adquirir os locks
    deles. NUNCA usado para aceitar uma correcao - somente para
    distinguir "registro_de_outra_operacao" de "codigo_inexistente" na
    mensagem de recusa. registro_coleta_id -> lote e uma associacao
    imutavel desde a criacao (um codigo nunca migra de lote), entao a
    ausencia de lock nesta leitura nao produz resultado incorreto -
    apenas verifica presenca, nunca contagens ou estado. Atravessa
    lotes legados sem registro_coleta_id sem lancar excecao (busca por
    .get(), nunca por indexacao direta).
    """
    for item in listar_lotes():
        if item["lote_id"] == lote_id_atual:
            continue
        outro = carregar_lote(item["lote_id"])
        if _buscar_em_clientes(outro, registro_coleta_id) or _buscar_em_clientes_invalidos(outro, registro_coleta_id):
            return True
    return False


def _inicializar_historico_se_necessario(lote: dict, registro_coleta_id: str, original: dict) -> None:
    """
    Materializa a v1 de um registro criado antes desta sprint (Sprint
    A2). Distingue tres momentos, nunca confundidos:
      - recebido_em: quando o registro ORIGINAL foi de fato recebido
        (M0/criado_em do lote) - nunca "agora".
      - representacao_historica_criada_em: quando esta materializacao
        tardia foi de fato criada - sempre "agora".
      - representacao_historica_reconstituida: True - esta v1 nao foi
        criada no momento do upload original, foi reconstruida
        retroativamente a partir de dados ja existentes.
    A identidade de quem recebeu o upload original nunca foi
    registrada pelo codigo da Sprint A1/A2 - "recebido_por" reflete
    esse fato honestamente ("nao_registrado_legado"), em vez de
    atribuir retroativamente uma identidade que so passou a existir
    como conceito nesta sprint (A3).
    """
    historico = lote.setdefault("historico_versoes", {})
    if registro_coleta_id in historico:
        return
    historico[registro_coleta_id] = [{
        "registro_coleta_versao_id": str(uuid.uuid4()),
        "numero_versao": 1,
        "versao_anterior_id": None,
        "status_versao": "invalida",
        "processo": "upload_original",
        "recebido_por": "nao_registrado_legado",
        "recebido_em": lote["criado_em"],
        "representacao_historica_criada_em": datetime.now().isoformat(),
        "representacao_historica_reconstituida": True,
        "nome_bruto": original["nome_bruto"],
        "whatsapp_bruto": original["whatsapp_bruto"],
        "produto_bruto": original["produto_bruto"],
        "motivos": original["motivos"],
    }]


def _aplicar_versao_correcao(lote: dict, registro_coleta_id: str,
                              nome_bruto, whatsapp_bruto, produto_bruto) -> dict:
    """
    Cria a proxima versao (append-only) a partir de uma correcao
    RECEBIDA NESTA SPRINT - processo/recebido_por refletem isso
    honestamente, distintos da v1 reconstruida (funcao acima). Nenhum
    campo mutavel "corrente"/"substituida" - a versao corrente e
    sempre a de maior numero_versao (ultima do array).
    """
    resultado = _validar_linha(nome_bruto, whatsapp_bruto, produto_bruto)
    versoes = lote["historico_versoes"][registro_coleta_id]
    versao = {
        "registro_coleta_versao_id": str(uuid.uuid4()),
        "numero_versao": len(versoes) + 1,
        "versao_anterior_id": versoes[-1]["registro_coleta_versao_id"],
        "status_versao": "valida" if resultado["valido"] else "invalida",
        "processo": PROCESSO_CORRECAO,
        "recebido_por": RECEBIDO_POR_PROVISORIO,
        "recebido_em": datetime.now().isoformat(),
        "representacao_historica_reconstituida": False,
        "nome_bruto": nome_bruto,
        "whatsapp_bruto": whatsapp_bruto,
        "produto_bruto": produto_bruto,
        "motivos": resultado["motivos"],
    }
    versoes.append(versao)

    lote["clientes_invalidos"] = [c for c in lote["clientes_invalidos"] if c.get("registro_coleta_id") != registro_coleta_id]
    lote["clientes"] = [c for c in lote["clientes"] if c.get("registro_coleta_id") != registro_coleta_id]
    if resultado["valido"]:
        lote["clientes"].append({
            "registro_coleta_id": registro_coleta_id,
            "nome": resultado["nome"],
            "telefone": resultado["telefone"],
            "produto": resultado["produto"],
            "resposta": "",
        })
    else:
        lote["clientes_invalidos"].append({
            "registro_coleta_id": registro_coleta_id,
            "nome_bruto": nome_bruto,
            "whatsapp_bruto": whatsapp_bruto,
            "produto_bruto": produto_bruto,
            "motivos": resultado["motivos"],
        })
    return versao


def _recalcular_contagens_e_status(lote: dict) -> None:
    """total_recebido NUNCA e tocado aqui - permanece imutavel desde o
    upload original (ADR-007 SS11)."""
    lote["total_valido"] = len(lote["clientes"])
    lote["total_invalido"] = len(lote["clientes_invalidos"])
    lote["total_clientes"] = lote["total_valido"]
    if lote["total_valido"] > 0:
        lote["status"] = "aguardando_d8"
    elif lote["total_invalido"] > 0:
        lote["status"] = "sem_registros_validos"


def _registrar_tentativa_rejeitada(lote_id: str, codigo_tecnico_bruto: str,
                                     nome_bruto: str, whatsapp_bruto: str,
                                     produto_bruto: str, motivo: str) -> None:
    """
    Auditoria PROVISORIA (sera substituida por persistencia real na
    Sprint B). Um arquivo por tentativa (nome unico via UUID4) sob
    Config.DATA_DIR - isolamento total em testes via tmp_path/monkeypatch.
    Escrita atomica (tmp + os.replace). NUNCA altera lote.json. Preserva
    o valor BRUTO do codigo_tecnico recebido, mesmo quando ausente ou
    malformado.
    """
    pasta = Path(Config.DATA_DIR) / "correcoes_rejeitadas" / datetime.now().strftime("%Y-%m-%d")
    pasta.mkdir(parents=True, exist_ok=True)
    evento_id = str(uuid.uuid4())
    caminho = pasta / f"{evento_id}.json"
    caminho_tmp = caminho.with_suffix(".json.tmp")
    dado = {
        "evento_id": evento_id,
        "recebido_em": datetime.now().isoformat(),
        "processo": PROCESSO_CORRECAO,
        "recebido_por": RECEBIDO_POR_PROVISORIO,
        "lote_id_informado": lote_id,
        "codigo_tecnico_informado": codigo_tecnico_bruto,
        "nome_bruto": nome_bruto,
        "whatsapp_bruto": whatsapp_bruto,
        "produto_bruto": produto_bruto,
        "motivo": motivo,
    }
    with open(caminho_tmp, "w", encoding="utf-8") as f:
        json.dump(dado, f, ensure_ascii=False, indent=2)
    os.replace(caminho_tmp, caminho)


def gerar_relatorio_correcao_csv(lote_id: str) -> str:
    """
    Gera SOMENTE o conteudo CSV em memoria - nenhuma rota HTTP, nenhum
    arquivo em disco (rotas ficam para a Sprint D, com autenticacao).
    Usa csv.writer para tratar corretamente virgulas, aspas e quebras
    de linha. Nunca inclui lote_id no conteudo.

    Inclui SOMENTE registros atualmente invalidos que possuam um
    codigo_tecnico UUID4 valido (reaproveita _normalizar_codigo_tecnico,
    ja testada). Registros legados (anteriores a Sprint A1, sem
    registro_coleta_id) sao OMITIDOS - nunca recebem um codigo inventado
    ou atribuido retroativamente, e o acesso via .get() garante que a
    ausencia da chave nunca lanca KeyError. Se nenhum invalido possuir
    codigo, o CSV contem somente o cabecalho.
    """
    lote = carregar_lote(lote_id)
    buffer = io.StringIO()
    escritor = csv.writer(buffer, lineterminator="\n")
    escritor.writerow(["codigo_tecnico", "nome", "whatsapp", "produto"])
    for c in lote.get("clientes_invalidos", []):
        codigo, motivo = _normalizar_codigo_tecnico(c.get("registro_coleta_id") or "")
        if motivo is not None:
            continue  # legado sem codigo tecnico valido - omitido, nunca inventado
        escritor.writerow([
            codigo,
            c.get("nome_bruto", ""),
            c.get("whatsapp_bruto", ""),
            c.get("produto_bruto", ""),
        ])
    return buffer.getvalue()


def _escrever_lote_em_disco(lote_id: str, lote: dict) -> None:
    """
    Escreve lote.json de forma atomica (tmp + os.replace) SEM adquirir
    nenhum lock - pressupoe que o chamador ja detem
    _obter_lock_lote(lote_id). Nunca chamar fora de uma secao critica
    ja protegida (evita o deadlock de _obter_lock_lote readquirido -
    threading.Lock nao e reentrante).
    """
    caminho = Path(Config.LOTES_DIR) / lote_id / "lote.json"
    caminho_tmp = caminho.with_suffix(".json.tmp")
    with open(caminho_tmp, "w", encoding="utf-8") as f:
        json.dump(lote, f, ensure_ascii=False, indent=2)
    os.replace(caminho_tmp, caminho)


def carregar_lote(lote_id: str) -> dict:
    caminho = Path(Config.LOTES_DIR) / lote_id / "lote.json"
    if not caminho.exists():
        raise FileNotFoundError(f"Lote {lote_id} nao encontrado")
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def salvar_analise(lote_id: str, cliente_id: str, dados: dict):
    resp_dir = Path(Config.RESPOSTAS_DIR) / lote_id
    resp_dir.mkdir(parents=True, exist_ok=True)
    caminho = resp_dir / f"{cliente_id}.json"
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def carregar_analises_lote(lote_id: str) -> list:
    resp_dir = Path(Config.RESPOSTAS_DIR) / lote_id
    if not resp_dir.exists():
        return []
    analises = []
    for arquivo in sorted(resp_dir.glob("*.json")):
        with open(arquivo, encoding="utf-8") as f:
            analises.append(json.load(f))
    return analises


def listar_lotes() -> list:
    lotes_dir = Path(Config.LOTES_DIR)
    lotes = []
    if not lotes_dir.exists():
        return lotes
    for pasta in sorted(lotes_dir.iterdir()):
        meta = pasta / "lote.json"
        if meta.exists():
            with open(meta, encoding="utf-8") as f:
                d = json.load(f)
                lotes.append({"lote_id": d.get("lote_id"), "empresa": d.get("empresa"), "nome_lote": d.get("nome_lote"), "total_clientes": d.get("total_clientes"), "criado_em": d.get("criado_em"), "status_pipeline": d.get("status_pipeline")})
    return lotes


def gerar_slug_empresa(nome: str) -> str:
    import unicodedata
    nome = nome.lower().strip()
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(c for c in nome if not unicodedata.combining(c))
    nome = nome.replace(" ", "_")
    return nome


_locks_por_lote: dict[str, threading.Lock] = {}
_locks_por_lote_guard = threading.Lock()


def _obter_lock_lote(lote_id: str) -> threading.Lock:
    """
    Um lock por lote_id, para serializar escritas concorrentes ao mesmo
    lote.json dentro do mesmo processo. Nao protege contra multiplos
    processos/workers (ex.: servidor WSGI de producao com varios workers)
    - essa e uma limitacao conhecida, documentada na auditoria, a ser
    tratada quando a migracao de servidor for decidida.
    """
    with _locks_por_lote_guard:
        if lote_id not in _locks_por_lote:
            _locks_por_lote[lote_id] = threading.Lock()
        return _locks_por_lote[lote_id]


def salvar_lote_atomico(lote_id: str, lote: dict) -> None:
    """
    Funcao publica e oficial para persistir o dict do lote de volta em
    lote.json. Escreve em arquivo temporario e substitui via os.replace
    (atomico no SO), serializada por lote_id via _obter_lock_lote. Todo
    escritor de lote.json que precisar de escrita segura/atomica deve
    reutilizar esta funcao, em vez de abrir o arquivo diretamente.

    CORRIGIDO na Sprint A3: a escrita em si foi extraida para
    _escrever_lote_em_disco - chamadores que ja detem o lock (ex.:
    processamento de correcao) devem chamar aquela funcao diretamente,
    NUNCA esta, para evitar deadlock (threading.Lock nao e reentrante).
    """
    with _obter_lock_lote(lote_id):
        _escrever_lote_em_disco(lote_id, lote)


def salvar_resposta_cliente(lote_id: str, telefone: str, texto: str) -> dict:
    from datetime import datetime
    lote = carregar_lote(lote_id)
    empresa_nome = lote.get("empresa", "empresa_desconhecida")
    slug = gerar_slug_empresa(empresa_nome)
    cliente = next(
        (c for c in lote.get("clientes", [])
         if c.get("telefone", "").replace(" ", "") == telefone.replace(" ", "")),
        None
    )
    if not cliente:
        return {"erro": f"Cliente nao encontrado para telefone {telefone}"}

    data_resposta_iso = datetime.now().isoformat()

    # Fonte oficial: atualiza o registro do cliente dentro do proprio
    # lote.json. E o unico dado que integration/nsi_integration.py le
    # para montar o Motor - "o NSI nunca inventa fatos": este e o
    # momento exato em que o fato (a resposta chegou) e registrado.
    cliente["resposta"] = texto
    cliente["data_resposta"] = data_resposta_iso
    cliente["status_entrega"] = "respondido"
    salvar_lote_atomico(lote_id, lote)

    # Log bruto de auditoria - NAO e fonte de verdade, NAO e lido pelo
    # Motor nem por nenhum outro modulo. Existe apenas como rastro do
    # payload recebido, por decisao explicita do projeto.
    resposta = {
        "empresa": empresa_nome,
        "lote_id": lote_id,
        "cliente_id": telefone,
        "nome": cliente.get("nome", ""),
        "telefone": telefone,
        "produto": cliente.get("produto", ""),
        "resposta": texto,
        "data_resposta": data_resposta_iso,
        "analisado": False
    }
    pasta = Path(Config.DATA_DIR) / "empresas" / slug / "respostas"
    pasta.mkdir(parents=True, exist_ok=True)
    nome_arquivo = f"{lote_id}_{telefone}.json"
    with open(pasta / nome_arquivo, "w", encoding="utf-8") as f:
        json.dump(resposta, f, ensure_ascii=False, indent=2)

    return {"salvo": True, "arquivo": nome_arquivo, "cliente": cliente.get("nome")}


def buscar_lote_por_telefone(telefone: str) -> str | None:
    telefone = telefone.replace(" ", "")
    lotes = listar_lotes()
    for item in lotes:
        try:
            lote = carregar_lote(item["lote_id"])
            for cliente in lote.get("clientes", []):
                if cliente.get("telefone", "").replace(" ", "") == telefone:
                    return item["lote_id"]
        except Exception:
            continue
    return None


def salvar_saida_motor(lote_id: str, saida_dict: dict) -> Path:
    """
    Persiste a saída agregada do Motor NSI (SaidaMotorCompleta já
    serializada via outputs.output_builder.saida_para_dict) para um
    lote. Salva ao lado de lote.json, no mesmo diretório do lote —
    é um resultado do lote como um todo, não uma análise por cliente
    (por isso não reutiliza salvar_analise/RESPOSTAS_DIR, que tem um
    formato incompatível: um arquivo por cliente).
    """
    lote_dir = Path(Config.LOTES_DIR) / lote_id
    lote_dir.mkdir(parents=True, exist_ok=True)
    caminho = lote_dir / "saida_motor.json"
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(saida_dict, f, ensure_ascii=False, indent=2)
    return caminho


def carregar_saida_motor(lote_id: str) -> dict | None:
    """
    Carrega a saída do Motor NSI já processada para um lote, se existir.
    Retorna None se o lote ainda não foi processado pelo Motor.
    """
    caminho = Path(Config.LOTES_DIR) / lote_id / "saida_motor.json"
    if not caminho.exists():
        return None
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)