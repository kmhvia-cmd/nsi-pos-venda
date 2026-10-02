# -*- coding: utf-8 -*-
"""
NSI - tests/regra_membership_b3_1.py

Regra de membership das quatro roles funcionais da B3.1, em forma de
funcao pura (sem banco, sem I/O) - implementacao UNICA, compartilhada por:

    tests/integration/test_provisionamento_b3_roles.py
        (aplica a regra ao estado real do cluster)
    tests/unit/test_regra_membership_b3_1.py
        (prova a regra com listas sinteticas)

Regra geral (B3.1): nenhuma role funcional pertence a nenhuma outra role.

Excecao unica (ADR-009, Secao 21 - "Formalizacao da Excecao Unica a Regra
de Membership da B3.1"): nsi_aplicacao pode ser membro de
nsi_congelamento, exclusivamente com INHERIT FALSE, SET TRUE e
ADMIN FALSE. Qualquer membership fora dessa excecao continua sendo
inesperada.

Este modulo nao e um arquivo de teste (nao comeca com 'test_') - nunca e
coletado pelo pytest.
"""

QUATRO_ROLES_FUNCIONAIS = ["nsi_eventos_owner", "nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito"]

# (role-grupo, inherit_option, set_option, admin_option) - exatamente as
# colunas de pg_auth_members que definem o efeito de uma membership.
MEMBERSHIP_FORMALIZADA_ADR_009 = ("nsi_congelamento", False, True, False)

# Tabela FECHADA: para cada role, as listas COMPLETAS de memberships
# aceitas. Uma lista lida do banco so e aceita se for identica a uma
# destas - nunca por contagem, nunca por "contem".
#
# nsi_aplicacao aceita DOIS estados (sem membership, ou com a membership
# formalizada). Essa dupla aceitacao existe APENAS para preservar a
# compatibilidade entre ambientes anteriores e posteriores a B4.3 (role
# nsi_congelamento ainda nao provisionada, ou ja provisionada) - nao e
# uma tolerancia geral. Exigir que a membership EXISTA nao pertence a
# esta regra: pertence ao teste de provisionamento da propria role
# nsi_congelamento (B4.3, Etapa 1).
MEMBERSHIPS_ACEITAS = {
    "nsi_eventos_owner": [[]],
    "nsi_expiracao": [[]],
    "nsi_operador_restrito": [[]],
    "nsi_aplicacao": [[], [MEMBERSHIP_FORMALIZADA_ADR_009]],
}


def memberships_sao_aceitas(nome_role, memberships) -> bool:
    """
    Decide se a lista COMPLETA de memberships de 'nome_role' e aceita.

    'memberships' e a lista de TODAS as linhas de pg_auth_members em que
    'nome_role' e o membro, cada uma como
    (role-grupo, inherit_option, set_option, admin_option) - sem agrupar e
    sem remover duplicatas: no PostgreSQL 16+ a mesma membership pode
    existir em mais de uma linha (concedida por autores diferentes, com
    opcoes diferentes), e uma linha repetida precisa reprovar.

    A comparacao e por igualdade da lista inteira (a ordem das linhas e
    irrelevante; a quantidade e o conteudo de cada linha, nao).

    Uma role fora das quatro da B3.1 levanta ValueError - a regra nao se
    pronuncia sobre roles que nao conhece.
    """
    if nome_role not in MEMBERSHIPS_ACEITAS:
        raise ValueError(f"Role {nome_role!r} nao pertence as quatro roles funcionais da B3.1.")

    encontradas = sorted(tuple(linha) for linha in memberships)
    return any(encontradas == sorted(aceita) for aceita in MEMBERSHIPS_ACEITAS[nome_role])
