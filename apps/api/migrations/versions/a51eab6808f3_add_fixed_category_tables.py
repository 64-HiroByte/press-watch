"""add fixed category tables

Revision ID: a51eab6808f3
Revises: 9f2c7a4e1d63
Create Date: 2026-09-02 23:17:58.254780

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a51eab6808f3'
down_revision: Union[str, Sequence[str], None] = '9f2c7a4e1d63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'fixed_categories',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.CheckConstraint(
            'display_order > 0',
            name='ck_fixed_categories_display_order_positive',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug', name='uq_fixed_categories_slug'),
        sa.UniqueConstraint('name', name='uq_fixed_categories_name'),
        sa.UniqueConstraint(
            'display_order',
            name='uq_fixed_categories_display_order',
        ),
    )
    op.create_table(
        'fixed_category_keywords',
        sa.Column('fixed_category_id', sa.BigInteger(), nullable=False),
        sa.Column('keyword', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ['fixed_category_id'],
            ['fixed_categories.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('fixed_category_id', 'keyword'),
    )
    op.create_table(
        'press_release_fixed_categories',
        sa.Column('press_release_id', sa.BigInteger(), nullable=False),
        sa.Column('fixed_category_id', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ['fixed_category_id'],
            ['fixed_categories.id'],
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['press_release_id'],
            ['press_releases.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('press_release_id', 'fixed_category_id'),
    )
    op.create_index(
        'ix_press_release_fixed_categories_fixed_category_id',
        'press_release_fixed_categories',
        ['fixed_category_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'ix_press_release_fixed_categories_fixed_category_id',
        table_name='press_release_fixed_categories',
    )
    op.drop_table('press_release_fixed_categories')
    op.drop_table('fixed_category_keywords')
    op.drop_table('fixed_categories')
