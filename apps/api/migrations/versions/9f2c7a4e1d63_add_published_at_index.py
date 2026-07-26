"""add published_at index

Revision ID: 9f2c7a4e1d63
Revises: 31765401e166
Create Date: 2026-07-25

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9f2c7a4e1d63'
down_revision: Union[str, Sequence[str], None] = '31765401e166'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        'ix_press_releases_published_at',
        'press_releases',
        ['published_at'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'ix_press_releases_published_at',
        table_name='press_releases',
    )
