"""Criação inicial do banco de dados

Revision ID: 84c3d7a6d960
Revises: 
Create Date: 2024-11-09 23:45:59.593692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '84c3d7a6d960'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('Categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_Categories_id'), 'Categories', ['id'], unique=False)
    op.create_table('Balance',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('date', sa.DateTime(), nullable=False),
    sa.Column('type', sa.Enum('START', 'INCOME', 'OUTCOME', name='typetype', create_constraint=True), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['category_id'], ['Categories.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_Balance_id'), 'Balance', ['id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_Balance_id'), table_name='Balance')
    op.drop_table('Balance')
    op.drop_index(op.f('ix_Categories_id'), table_name='Categories')
    op.drop_table('Categories')
    # ### end Alembic commands ###
