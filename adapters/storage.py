# -*- coding: utf-8 -*-
"""
NSI - adapters/storage.py
Responsabilidade: salvar e carregar lotes e analises em disco
"""
import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from config import Config


def salvar_lote(arquivo, empresa="", nome="", data_inicio="", data_fim="") -> dict:
    lote_id = f"NSI-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
    lote_dir = Path(Config.LOTES_DIR) / lote_id
    lote_dir.mkdir(parents=True, exist_ok=True)

    nome_arquivo = arquivo.filename
    if nome_arquivo.endswith(".csv"):
        df = pd.read_csv(arquivo, encoding="utf-8")
    else:
        df = pd.read_excel(arquivo)

    colunas = [c.lower().strip() for c in df.columns]
    colunas_req = ["nome", "telefone"]
    faltando = [c for c in colunas_req if c not in colunas]
    if faltando:
        return {"erro": f"Colunas ausentes no CSV: {faltando}"}

    clientes = []
    for _, row in df.iterrows():
        clientes.append({
            "nome":     str(row.iloc[0]).strip(),
            "telefone": str(row.iloc[1]).strip(),
            "produto":  str(row.iloc[2]).strip() if len(row) > 2 else "",
            "resposta": str(row.iloc[3]).strip() if len(row) > 3 else "",
        })

    meta = {
        "lote_id":          lote_id,
        "empresa":          empresa,
        "nome_lote":        nome,
        "data_inicial":     data_inicio,
        "data_final":       data_fim,
        "csv_original":     nome_arquivo,
        "criado_em":        datetime.now().isoformat(),
        "total_clientes":   len(clientes),
        "status":            "aguardando_d8",
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
        "clientes": clientes
    }

    with open(lote_dir / "lote.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return {"lote_id": lote_id, "total_clientes": len(clientes), "mensagem": "lote_criado"}


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
    """
    caminho = Path(Config.LOTES_DIR) / lote_id / "lote.json"
    with _obter_lock_lote(lote_id):
        caminho_tmp = caminho.with_suffix(".json.tmp")
        with open(caminho_tmp, "w", encoding="utf-8") as f:
            json.dump(lote, f, ensure_ascii=False, indent=2)
        os.replace(caminho_tmp, caminho)


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