# -*- coding: utf-8 -*-
"""
NSI - tests/regra_ambiente_ensaio_b6.py

Regra UNICA com que os testes somente leitura de provisionamento toleram o
ambiente de ensaio da B6 (SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md, Secoes
14 e 15, componente C9).

pg_database, pg_auth_members e pg_shdepend sao catalogos COMPARTILHADOS do
cluster: enquanto o banco descartavel nsi_ensaio existir, ele aparece nas
consultas dos testes de provisionamento da B4.3 e da B5.3, que rodam
conectados a nsi_test. A especificacao aceita UM unico estado adicional: a
existencia de nsi_ensaio com exatamente as concessoes da Secao 14 - nunca
uma tolerancia geral. A suite precisa passar com e sem o ambiente presente.

Mesmo padrao de tests/regra_membership_b3_1.py: este modulo nao e um
arquivo de teste (nao comeca com 'test_') e nunca e coletado; a regra e
provada, com estados simulados, em tests/unit/test_regra_ambiente_ensaio_b6.py.
"""

BANCO_DE_ENSAIO = "nsi_ensaio"
MIGRATOR_DE_ENSAIO = "nsi_ensaio_migrator"

# Bancos em que as migrations concedem EXECUTE a roles do projeto: os dois
# permanentes e, enquanto existir, o de ensaio (a 0003, a 0005 e a 0006
# rodam nele e gravam as mesmas concessoes de funcao).
BANCOS_COM_CONCESSAO_DE_FUNCAO = ("nsi_dev", "nsi_test", BANCO_DE_ENSAIO)

# Bancos em que nsi_importacao pode ter CONNECT e USAGE no schema: nsi_test
# (B5.3) e, somente durante uma rodada, nsi_ensaio (ADR-010, Secao 16.2).
BANCOS_DE_NSI_IMPORTACAO = ("nsi_test", BANCO_DE_ENSAIO)

_CONNECT_EM_TESTE = ("nsi_test", "CONNECT", False)
_CONNECT_EM_ENSAIO = (BANCO_DE_ENSAIO, "CONNECT", False)


def concessoes_de_banco_de_nsi_importacao_sao_aceitas(concessoes, banco_de_ensaio_existe: bool) -> bool:
    """'concessoes' e a lista COMPLETA de (banco, privilegio, com_grant_option)
    concedidos a nsi_importacao em todo o cluster.

    Sem o banco de ensaio: exatamente CONNECT em nsi_test (estado da B5.3).
    Com o banco de ensaio: exatamente CONNECT em nsi_test e em nsi_ensaio -
    a concessao no ensaio e obrigatoria, nao opcional, porque o ambiente so
    e aceito na forma exata da especificacao."""
    esperadas = [_CONNECT_EM_TESTE] + ([_CONNECT_EM_ENSAIO] if banco_de_ensaio_existe else [])
    return sorted(map(tuple, concessoes)) == sorted(esperadas)


def membros_de_nsi_eventos_owner_sao_aceitos(membros, banco_de_ensaio_existe: bool) -> bool:
    """'membros' e a lista COMPLETA de (membro, inherit, set, admin) de
    nsi_eventos_owner. Os dois migrators da B3.1, sempre; o migrator de
    ensaio, se e somente se o banco de ensaio existir - todos com INHERIT
    FALSE, SET TRUE, ADMIN FALSE."""
    nomes = ["nsi_dev_migrator", "nsi_test_migrator"] + ([MIGRATOR_DE_ENSAIO] if banco_de_ensaio_existe else [])
    return sorted(map(tuple, membros)) == sorted((nome, False, True, False) for nome in nomes)
