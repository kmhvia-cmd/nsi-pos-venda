# -*- coding: utf-8 -*-
"""
NSI - tests/unit/test_regra_membership_b3_1.py

Testes UNITARIOS (sem banco) da regra de membership das quatro roles
funcionais da B3.1, com a excecao unica formalizada na ADR-009, Secao 21.

O cluster real so pode estar em um estado por vez - sozinho, ele nao
prova que os estados ERRADOS seriam reprovados. Estes testes provam isso
com listas sinteticas, exercitando exatamente a mesma funcao que
tests/integration/test_provisionamento_b3_roles.py aplica ao estado real
(tests/regra_membership_b3_1.py) - a regra provada aqui e a regra
aplicada la.
"""
import pytest

from tests.regra_membership_b3_1 import MEMBERSHIPS_ACEITAS, QUATRO_ROLES_FUNCIONAIS, memberships_sao_aceitas

TRES_ROLES_SEM_EXCECAO = ["nsi_eventos_owner", "nsi_expiracao", "nsi_operador_restrito"]


def test_tabela_de_memberships_aceitas_e_fechada():
    """Trava deliberada da lista de permissoes: os demais testes provam o
    comportamento da funcao caso a caso, mas so esta comparacao literal
    detecta um alargamento silencioso da tabela em uma combinacao que
    nenhum caso cobre. Alterar a tabela exige alterar este teste - e,
    antes disso, uma nova evolucao formal da ADR-009 (Secao 21)."""
    assert MEMBERSHIPS_ACEITAS == {
        "nsi_eventos_owner": [[]],
        "nsi_expiracao": [[]],
        "nsi_operador_restrito": [[]],
        "nsi_aplicacao": [[], [("nsi_congelamento", False, True, False)]],
    }
    assert sorted(MEMBERSHIPS_ACEITAS) == sorted(QUATRO_ROLES_FUNCIONAIS)


@pytest.mark.parametrize("nome_role", QUATRO_ROLES_FUNCIONAIS)
def test_aprova_role_sem_nenhuma_membership(nome_role):
    """Regra geral da B3.1 - continua valida para as quatro roles."""
    assert memberships_sao_aceitas(nome_role, []) is True


def test_aprova_nsi_aplicacao_com_a_membership_formalizada():
    assert memberships_sao_aceitas("nsi_aplicacao", [("nsi_congelamento", False, True, False)]) is True


@pytest.mark.parametrize("nome_role", TRES_ROLES_SEM_EXCECAO)
def test_reprova_a_membership_formalizada_em_qualquer_outra_role(nome_role):
    """A excecao e de nsi_aplicacao - nunca das outras tres."""
    assert memberships_sao_aceitas(nome_role, [("nsi_congelamento", False, True, False)]) is False


@pytest.mark.parametrize("membership,descricao", [
    (("nsi_congelamento", True, True, False), "INHERIT TRUE"),
    (("nsi_congelamento", False, True, True), "ADMIN TRUE"),
    (("nsi_congelamento", False, False, False), "SET FALSE"),
])
def test_reprova_nsi_aplicacao_em_nsi_congelamento_com_opcao_errada(membership, descricao):
    assert memberships_sao_aceitas("nsi_aplicacao", [membership]) is False, (
        f"Membership em nsi_congelamento com {descricao} foi aceita - so INHERIT FALSE, SET TRUE, ADMIN FALSE e valido."
    )


@pytest.mark.parametrize("outra_role", ["nsi_eventos_owner", "nsi_operador_restrito", "pg_read_all_data", "postgres"])
def test_reprova_nsi_aplicacao_em_qualquer_outra_role(outra_role):
    """Mesmo com as tres opcoes 'corretas', so nsi_congelamento e aceita."""
    assert memberships_sao_aceitas("nsi_aplicacao", [(outra_role, False, True, False)]) is False


def test_reprova_nsi_aplicacao_com_a_membership_formalizada_mais_uma_segunda():
    memberships = [("nsi_congelamento", False, True, False), ("nsi_eventos_owner", False, True, False)]
    assert memberships_sao_aceitas("nsi_aplicacao", memberships) is False


def test_reprova_nsi_aplicacao_com_duas_linhas_para_nsi_congelamento():
    """PostgreSQL 16+: a mesma membership pode existir em mais de uma
    linha (autores diferentes). Mesmo com as duas linhas 'corretas', a
    excecao e exatamente UMA linha."""
    memberships = [("nsi_congelamento", False, True, False), ("nsi_congelamento", False, True, False)]
    assert memberships_sao_aceitas("nsi_aplicacao", memberships) is False


def test_reprova_linha_duplicada_em_que_so_uma_esta_correta():
    memberships = [("nsi_congelamento", False, True, False), ("nsi_congelamento", True, True, False)]
    assert memberships_sao_aceitas("nsi_aplicacao", memberships) is False


def test_role_fora_das_quatro_da_b3_1_levanta_erro():
    """A regra nao se pronuncia sobre roles que nao conhece - nunca
    'aprova por omissao'."""
    with pytest.raises(ValueError):
        memberships_sao_aceitas("nsi_congelamento", [])
