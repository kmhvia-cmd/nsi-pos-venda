# -*- coding: utf-8 -*-
"""
NSI - tests/unit/test_regra_ambiente_ensaio_b6.py
(Sprint B, B6.2 - SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md, Secoes 14 e
15, componente C9)

Prova, com estados SIMULADOS, a regra com que os testes de provisionamento
toleram o banco descartavel nsi_ensaio. O ambiente real so existe durante
uma rodada do ensaio (B6.3) e exige o superusuario para ser criado; por
isso os dois estados - com e sem o ambiente - sao provados aqui.
"""
import pytest

from tests.regra_ambiente_ensaio_b6 import (
    BANCOS_COM_CONCESSAO_DE_FUNCAO,
    BANCOS_DE_NSI_IMPORTACAO,
    concessoes_de_banco_de_nsi_importacao_sao_aceitas as concessoes_aceitas,
    membros_de_nsi_eventos_owner_sao_aceitos as membros_aceitos,
)

TESTE = ("nsi_test", "CONNECT", False)
ENSAIO = ("nsi_ensaio", "CONNECT", False)


def test_sem_ambiente_de_ensaio_vale_exatamente_o_estado_da_b5_3():
    assert concessoes_aceitas([TESTE], False) is True


def test_com_ambiente_de_ensaio_a_concessao_nele_e_obrigatoria():
    assert concessoes_aceitas([TESTE, ENSAIO], True) is True
    assert concessoes_aceitas([ENSAIO, TESTE], True) is True
    assert concessoes_aceitas([TESTE], True) is False, "Ambiente presente sem a concessao nao e o estado especificado."


@pytest.mark.parametrize("concessoes,ensaio_existe", [
    ([TESTE, ENSAIO], False),                                  # concessao orfa: o banco nao existe
    ([], False), ([], True), ([ENSAIO], True),                 # sem o CONNECT de nsi_test
    ([TESTE, ("nsi_dev", "CONNECT", False)], False),           # nunca em nsi_dev
    ([TESTE, ENSAIO, ("nsi_dev", "CONNECT", False)], True),
    ([TESTE, ("postgres", "CONNECT", False)], False),
    ([("nsi_test", "CONNECT", True)], False),                  # com GRANT OPTION
    ([TESTE, ("nsi_ensaio", "CONNECT", True)], True),
    ([TESTE, ("nsi_test", "CREATE", False)], False),           # outro privilegio
    ([TESTE, ENSAIO, ("nsi_ensaio", "TEMPORARY", False)], True),
    ([TESTE, TESTE], False),                                   # linha duplicada
])
def test_qualquer_outro_estado_e_recusado(concessoes, ensaio_existe):
    assert concessoes_aceitas(concessoes, ensaio_existe) is False


def test_aceita_listas_de_listas_como_as_devolvidas_pelo_driver():
    assert concessoes_aceitas([list(TESTE), list(ENSAIO)], True) is True


def test_membros_do_owner_sem_e_com_o_ambiente_de_ensaio():
    dois = [("nsi_dev_migrator", False, True, False), ("nsi_test_migrator", False, True, False)]
    tres = dois + [("nsi_ensaio_migrator", False, True, False)]
    assert membros_aceitos(dois, False) is True
    assert membros_aceitos(tres, True) is True
    assert membros_aceitos(tres, False) is False, "Migrator de ensaio sem o banco de ensaio."
    assert membros_aceitos(dois, True) is False, "Banco de ensaio sem o seu migrator."


@pytest.mark.parametrize("membros", [
    [("nsi_dev_migrator", True, True, False), ("nsi_test_migrator", False, True, False)],    # INHERIT TRUE
    [("nsi_dev_migrator", False, True, True), ("nsi_test_migrator", False, True, False)],    # ADMIN TRUE
    [("nsi_dev_migrator", False, False, False), ("nsi_test_migrator", False, True, False)],  # SET FALSE
    [("nsi_dev_migrator", False, True, False)],
    [("nsi_dev_migrator", False, True, False), ("nsi_test_migrator", False, True, False),
     ("nsi_aplicacao", False, True, False)],
])
def test_membros_do_owner_fora_da_forma_exata_sao_recusados(membros):
    assert membros_aceitos(membros, False) is False


def test_listas_de_bancos_sao_fechadas():
    assert BANCOS_COM_CONCESSAO_DE_FUNCAO == ("nsi_dev", "nsi_test", "nsi_ensaio")
    assert BANCOS_DE_NSI_IMPORTACAO == ("nsi_test", "nsi_ensaio")
    assert "nsi_dev" not in BANCOS_DE_NSI_IMPORTACAO, "nsi_importacao nunca tem CONNECT nem USAGE em nsi_dev."
