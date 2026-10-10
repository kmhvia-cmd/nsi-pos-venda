# -*- coding: utf-8 -*-
"""
NSI — core/ensaio_sintetico.py
Responsabilidade: gerador da instalacao SINTETICA da Rodada S do ensaio de
corte (SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md, Secoes 9, 16 e 17,
componente C8; decisao D10).

Composicao (D10): as fixtures existentes do legado, acrescidas de lotes
suficientes para exercitar todas as geracoes, todos os destinos alcancaveis
numa execucao sobre um banco vazio, todos os motivos de recusa e de nao
promocao alcancaveis no ambiente de ensaio, e a promocao de lotes a2 e a3.

Junto com os arquivos, o gerador devolve os destinos ESPERADOS de cada lote
(verificacao V5 da Secao 26), declarados antes da execucao e sem valor
pessoal. Eles decorrem da construcao de cada caso e das regras da B5.2 -
nao de uma reimplementacao da classificacao, que e do banco.

O que NAO e alcancavel numa unica execucao sobre banco vazio, e por isso
nao e gerado: 'ja_importado' e 'conflito_de_reimportacao' (exigem uma
segunda execucao - ver origem_da_segunda_passada), 'claim_preexistente' e
'lote_id_legado_em_uso' (exigem o fluxo novo, que nao roda em nsi_ensaio).
Os quatro ja sao cobertos pelos testes da B5.4.

Modulo puro: sem banco e sem configuracao. Todo valor pessoal e sintetico
e marcado (VALORES_PESSOAIS_SINTETICOS) - nunca copiado de data/. A geracao
e deterministica para uma mesma semente.
"""
from __future__ import annotations

import json
import random
import shutil
import uuid
from pathlib import Path

from core.importacao_legado import enumerar_escopo

SUBDIRETORIO_DA_INSTALACAO_SINTETICA = "instalacao_sintetica"
FUSO_DO_CASO_DE_HORARIO_DE_VERAO = "America/Sao_Paulo"

NOME_SINTETICO = "Pessoa Sintetica Ensaio"
PRODUTO_SINTETICO = "Produto Sintetico Ensaio"
PREFIXO_TELEFONE_SINTETICO = "55119765"
VALORES_PESSOAIS_SINTETICOS = (NOME_SINTETICO, PRODUTO_SINTETICO, PREFIXO_TELEFONE_SINTETICO,
                               "Pessoa Sintetica Legado", "Produto Sintetico Legado", "55119876")

_CRIADO_EM = "2026-02-03T09:15:00.250000"

# Destinos das oito fixtures da B5 (tests/fixtures/legado/LEIAME.md), com e
# sem fuso declarado: (geracao, destino, motivo).
_FIXTURES = {
    "lotes/NSI-20260101-A00001/lote.json": ("anterior_a1", "preservado", "geracao_nao_promovivel"),
    "lotes/NSI-20260102-A00002/lote.json": ("a1", "preservado", "geracao_nao_promovivel"),
    "lotes/NSI-20260103-A00003/lote.json": ("a2", "promovido", None),
    "lotes/NSI-20260104-A00004/lote.json": ("a3", "promovido", None),
    "lotes/NSI-20260105-A00005/lote.json": ("formato_desconhecido", "recusado", "formato_desconhecido"),
    "lotes/NSI-20260106-A00006/lote.json": ("formato_desconhecido", "recusado", "formato_desconhecido"),
    "lotes/NSI-20260107-A00007/lote.json": (None, "recusado", "documento_ilegivel"),
    "lotes/NSI-20260108-A00008/lote.json": (None, "recusado", "identidade_divergente"),
}


class _Gerador:
    def __init__(self, semente: int) -> None:
        self._aleatorio = random.Random(semente)
        self._sequencia = 0

    def uuid(self) -> str:
        return str(uuid.UUID(int=self._aleatorio.getrandbits(128), version=4))

    def lote_id(self) -> str:
        self._sequencia += 1
        return f"NSI-20260203-{self._sequencia:06X}"

    def valido(self, n: int, com_identidade: bool = True) -> dict:
        registro = {"nome": f"{NOME_SINTETICO} {n}", "telefone": f"{PREFIXO_TELEFONE_SINTETICO}{n:05d}",
                    "produto": PRODUTO_SINTETICO, "resposta": ""}
        return {"registro_coleta_id": self.uuid(), **registro} if com_identidade else registro

    def invalido(self, n: int) -> dict:
        return {"registro_coleta_id": self.uuid(), "nome_bruto": f"{NOME_SINTETICO} Invalido {n}",
                "whatsapp_bruto": f"{PREFIXO_TELEFONE_SINTETICO}{n}", "produto_bruto": PRODUTO_SINTETICO,
                "motivos": ["whatsapp_comprimento_invalido"]}

    def raiz(self, lote_id: str, clientes: list, criado_em: str = _CRIADO_EM) -> dict:
        return {
            "lote_id": lote_id, "empresa": "Empresa Sintetica Ensaio", "nome_lote": "Lote Sintetico Ensaio",
            "data_inicial": "2026-02-01", "data_final": "2026-02-28", "csv_original": "sintetico.csv",
            "criado_em": criado_em, "total_clientes": len(clientes), "status": "aguardando_d8",
            "data_disparo": "2026-02-11T09:15:00.250000",
            "status_pipeline": {"upload": True, "lote_criado": True, "aguardando_d8": False,
                                "disparo_whatsapp": False, "webhook": False, "analise_ia": False,
                                "dashboard": False, "pdf": False},
            "clientes": clientes,
        }

    def anterior_a1(self) -> dict:
        documento = self.raiz(self.lote_id(), [self.valido(1, False), self.valido(2, False)])
        documento["status"] = "pendente"
        return documento

    def a1(self) -> dict:
        return self.raiz(self.lote_id(), [self.valido(1), self.valido(2)])

    def a2(self, criado_em: str = _CRIADO_EM) -> dict:
        clientes, invalidos = [self.valido(1), self.valido(2)], [self.invalido(1)]
        documento = self.raiz(self.lote_id(), clientes, criado_em)
        documento.update({"total_recebido": 3, "total_valido": 2, "total_invalido": 1,
                          "clientes_invalidos": invalidos})
        return documento

    def versao(self, numero: int, status: str) -> dict:
        return {"registro_coleta_versao_id": self.uuid(), "numero_versao": numero, "status_versao": status,
                "processo": "upload_original" if numero == 1 else "upload_correcao_csv",
                "recebido_em": _CRIADO_EM, "nome_bruto": f"{NOME_SINTETICO} Historico",
                "whatsapp_bruto": f"{PREFIXO_TELEFONE_SINTETICO}9", "produto_bruto": PRODUTO_SINTETICO, "motivos": []}

    def a3(self) -> dict:
        documento = self.a2()
        documento["historico_versoes"] = {
            documento["clientes"][0]["registro_coleta_id"]: [self.versao(1, "invalida"), self.versao(2, "valida")],
            documento["clientes_invalidos"][0]["registro_coleta_id"]: [self.versao(1, "invalida"),
                                                                       self.versao(2, "invalida")],
        }
        return documento


def _serializar(documento) -> bytes:
    return json.dumps(documento, ensure_ascii=False, indent=2).encode("utf-8")


def _nao_promovido(fuso, motivo_com_fuso: str) -> tuple:
    """Lote a2/a3 com um criterio de promocao violado. Sem fuso declarado, o
    criterio 'fuso_nao_declarado' vem antes na ordem do item 10.1."""
    return ("preservado", motivo_com_fuso if fuso else "fuso_nao_declarado")


def gerar_instalacao_sintetica(destino, diretorio_das_fixtures, fuso=None, semente: int = 20260203,
                               lotes_extras: int = 3) -> list:
    """Gera, em 'destino' (que precisa existir vazio), uma instalacao de
    origem sintetica - arquivos do escopo e ruido fora dele - e devolve a
    lista dos lotes esperados: caminho_relativo, geracao, destino e motivo.

    'fuso' e o que sera declarado na execucao (ou None): os destinos
    esperados dependem dele. O caso de horario inexistente so e gerado para
    America/Sao_Paulo, o unico fuso para o qual o instante foi escolhido."""
    raiz = Path(destino)
    if not raiz.is_dir() or any(raiz.iterdir()):
        raise ValueError("o destino da instalacao sintetica precisa existir e estar vazio")
    fixtures = Path(diretorio_das_fixtures)
    encontradas = {a.caminho_relativo for a in enumerar_escopo(fixtures)}
    if not set(_FIXTURES) <= encontradas:
        raise ValueError("diretorio de fixtures incompleto")

    g = _Gerador(semente)
    esperado = []

    def gravar(relativo: str, conteudo: bytes) -> None:
        caminho = raiz / relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(conteudo)

    def lote(documento, geracao, destino_esperado, motivo, diretorio=None, conteudo=None) -> None:
        relativo = f"lotes/{diretorio or documento['lote_id']}/lote.json"
        gravar(relativo, conteudo if conteudo is not None else _serializar(documento))
        esperado.append({"caminho_relativo": relativo, "geracao": geracao, "destino": destino_esperado,
                         "motivo": motivo})

    # 1. Fixtures existentes, copiadas byte a byte (lotes e tentativa recusada).
    for arquivo in sorted(encontradas):
        gravar(arquivo, (fixtures / arquivo).read_bytes())
        if arquivo in _FIXTURES:
            geracao, destino_esperado, motivo = _FIXTURES[arquivo]
            if destino_esperado == "promovido" and not fuso:
                destino_esperado, motivo = "preservado", "fuso_nao_declarado"
            esperado.append({"caminho_relativo": arquivo, "geracao": geracao, "destino": destino_esperado,
                             "motivo": motivo})

    promovido = ("promovido", None) if fuso else ("preservado", "fuso_nao_declarado")

    # 2. Lotes limpos de cada geracao.
    for _ in range(lotes_extras):
        lote(g.anterior_a1(), "anterior_a1", "preservado", "geracao_nao_promovivel")
        lote(g.a1(), "a1", "preservado", "geracao_nao_promovivel")
        lote(g.a2(), "a2", *promovido)
        lote(g.a3(), "a3", *promovido)

    # 3. Cada motivo de nao promocao alcancavel no ensaio (item 10.1).
    d = g.a2()
    d["status"] = "disparado"
    lote(d, "a2", *_nao_promovido(fuso, "evidencia_de_disparo"))

    d = g.a2()
    d["clientes"][0]["data_envio_mensagem"] = "2026-02-11T09:16:00"
    lote(d, "a2", *_nao_promovido(fuso, "evidencia_de_disparo"))

    d = g.a2()
    d["lote_id"] = f"LEGADO-{g.uuid()[:8]}"
    lote(d, "a2", *_nao_promovido(fuso, "lote_id_legado_invalido"))

    lote(g.a2("2026-02-03 09:15:00"), "a2", *_nao_promovido(fuso, "m0_invalido"))
    lote(g.a2("2026-02-03T09:15:00-03:00"), "a2", *_nao_promovido(fuso, "m0_invalido"))

    if fuso == FUSO_DO_CASO_DE_HORARIO_DE_VERAO:
        # 2018-11-04 00:30 nao existiu em America/Sao_Paulo (inicio do horario de verao).
        lote(g.a2("2018-11-04T00:30:00"), "a2", "preservado", "m0_inexistente_ou_ambiguo")

    d = g.a2()
    d["clientes_invalidos"][0]["registro_coleta_id"] = d["clientes"][0]["registro_coleta_id"]
    lote(d, "a2", *_nao_promovido(fuso, "identidade_repetida"))

    # Colisao: o segundo lote, na ordem do caminho, repete um registro do primeiro.
    primeiro, segundo = g.a2(), g.a2()
    segundo["clientes"][0]["registro_coleta_id"] = primeiro["clientes"][0]["registro_coleta_id"]
    lote(primeiro, "a2", *promovido)
    lote(segundo, "a2", *_nao_promovido(fuso, "colisao_de_identidade"))

    d = g.a2()
    d["total_recebido"] = 99
    lote(d, "a2", *_nao_promovido(fuso, "totais_incoerentes"))

    d = g.a3()
    d["historico_versoes"][d["clientes"][0]["registro_coleta_id"]][-1]["status_versao"] = "invalida"
    lote(d, "a3", *_nao_promovido(fuso, "historico_incoerente"))

    d = g.a2()
    d["clientes"][0]["telefone"] = "11976500001"
    lote(d, "a2", *_nao_promovido(fuso, "projecao_incompativel"))

    # 4. Cada motivo de recusa alcancavel numa execucao sobre banco vazio.
    d = g.a2()
    d["campo_nao_previsto"] = 1
    lote(d, "formato_desconhecido", "recusado", "formato_desconhecido")

    d = g.a1()
    del d["clientes"][1]["registro_coleta_id"]
    lote(d, "formato_desconhecido", "recusado", "formato_desconhecido")

    d = g.a2()
    lote(d, None, "recusado", "documento_ilegivel", conteudo=_serializar(d)[:100])

    d = g.a2()
    lote(d, None, "recusado", "identidade_divergente", diretorio=g.lote_id())

    # 5. Tentativa recusada da A3: so entra no manifesto.
    gravar(f"correcoes_rejeitadas/2026-02-04/{g.uuid()}.json",
           _serializar({"motivo": "codigo_tecnico_invalido", "recebido_em": "2026-02-04T08:00:00"}))

    # 6. Ruido fora do escopo: nunca enumerado, nunca copiado para a origem do ensaio.
    gravar(f"respostas/{PREFIXO_TELEFONE_SINTETICO}00001.json", _serializar({"texto": "resposta sintetica"}))
    gravar("empresas/empresa-sintetica/respostas/log.json", b"{}")
    gravar(f"lotes/{esperado[0]['caminho_relativo'].split('/')[1]}/saida_motor.json", b"{}")
    gravar("pdfs/relatorio.pdf", b"%PDF-sintetico")

    return sorted(esperado, key=lambda e: e["caminho_relativo"])


def resumir_esperado(esperado: list) -> dict:
    """Totais esperados por geracao e destino e por motivo - a mesma forma do
    relatorio do executor, para a verificacao V5."""
    por_geracao_e_destino, nao_promocao, recusa = {}, {}, {}
    for item in esperado:
        geracao = item["geracao"] or "nao_classificado"
        por_destino = por_geracao_e_destino.setdefault(geracao, {})
        por_destino[item["destino"]] = por_destino.get(item["destino"], 0) + 1
        if item["destino"] == "preservado":
            nao_promocao[item["motivo"]] = nao_promocao.get(item["motivo"], 0) + 1
        elif item["destino"] == "recusado":
            recusa[item["motivo"]] = recusa.get(item["motivo"], 0) + 1
    return {"lotes": len(esperado), "por_geracao_e_destino": por_geracao_e_destino,
            "motivos_de_nao_promocao": dict(sorted(nao_promocao.items())),
            "motivos_de_recusa": dict(sorted(recusa.items()))}


def comparar_com_esperado(esperado: list, obtido: list) -> dict:
    """Verificacao V5: os destinos e motivos obtidos (linhas do registro
    tecnico, lidas pela auditoria) contra os esperados, lote a lote."""
    e = {i["caminho_relativo"]: (i["geracao"], i["destino"], i["motivo"]) for i in esperado}
    o = {i["caminho_relativo"]: (i["geracao"], i["destino"], i["motivo"]) for i in obtido}
    divergentes = sorted(c for c in e if c in o and e[c] != o[c])
    return {
        "confere": e == o,
        "esperados": len(e), "obtidos": len(o),
        "divergentes": divergentes,
        "ausentes": sorted(c for c in e if c not in o),
        "inesperados": sorted(c for c in o if c not in e),
    }


def origem_da_segunda_passada(origem_congelada, destino) -> list:
    """Copia a origem congelada alterando um unico lote ja preservado, para
    uma SEGUNDA execucao sobre o mesmo banco: todo lote antes preservado ou
    promovido vira 'ja_importado', e o alterado vira recusa
    'conflito_de_reimportacao'. Devolve os caminhos alterados."""
    fonte, alvo = Path(origem_congelada), Path(destino)
    if not alvo.is_dir() or any(alvo.iterdir()):
        raise ValueError("o destino da segunda passada precisa existir e estar vazio")
    for arquivo in enumerar_escopo(fonte):
        caminho = alvo / arquivo.caminho_relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fonte / arquivo.caminho_relativo, caminho)
        caminho.chmod(0o644)
    alterado = "lotes/NSI-20260102-A00002/lote.json"
    documento = json.loads((alvo / alterado).read_bytes())
    documento["nome_lote"] = "Lote Sintetico Alterado"
    (alvo / alterado).write_bytes(_serializar(documento))
    return [alterado]
