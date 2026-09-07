"""bootstrap vazio - Sprint B (B2.2, ADR-008)

Revision ID: 0001
Revises:
Create Date: 2026-09-06

Migration verdadeiramente vazia - prova a esteira do Alembic ponta a ponta
(criacao automatica de nsi_operacional.alembic_version pelo proprio
Alembic) sem criar nenhuma tabela de negocio.

O schema "nsi_operacional" em si NAO e criado por esta migration nem por
nenhuma outra - e responsabilidade exclusiva do provisionamento
administrativo (scripts/postgres_local/provisionar_dev_teste.sql),
executado antes de qualquer `alembic upgrade` (ver migrations/env.py,
que apenas verifica a existencia do schema).

Tabelas de negocio (claims, eventos_claim, comandos_idempotentes) e as
funcoes SECURITY DEFINER pertencem a Sprint B3 - nao a esta migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bootstrap intencionalmente vazio - nenhuma tabela de negocio criada
    # nesta sprint (B2). O unico efeito real desta migration e permitir que
    # o proprio Alembic crie nsi_operacional.alembic_version, provando a
    # esteira ponta a ponta (Especificacao Tecnica da Sprint B, B2.2).
    pass


def downgrade() -> None:
    # Simetrico ao upgrade - nada para desfazer alem do carimbo de versao
    # que o proprio Alembic ja controla. O schema nsi_operacional nunca e
    # removido por esta migration - e um objeto administrativo, fora do
    # alcance de qualquer downgrade (ver Especificacao Tecnica, Secao 3).
    pass
