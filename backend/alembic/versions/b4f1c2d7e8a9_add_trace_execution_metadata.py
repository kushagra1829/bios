"""add execution metadata to agent traces

Revision ID: b4f1c2d7e8a9
Revises: 23e1de4c1b6b
Create Date: 2026-11-07 09:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4f1c2d7e8a9'
down_revision: Union[str, Sequence[str], None] = '23e1de4c1b6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('agent_execution_traces') as batch_op:
        batch_op.add_column(sa.Column('execution_metadata_json', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('agent_execution_traces') as batch_op:
        batch_op.drop_column('execution_metadata_json')
