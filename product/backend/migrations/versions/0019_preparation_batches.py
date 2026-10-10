# 为已确认材料计划增加持久批次，不修改既有来源、证据或历史表。
from alembic import op
import sqlalchemy as sa

revision = '0019_preparation_batches'
down_revision = '0018_node_sample'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('preparation_batches',
        sa.Column('operation_id', sa.String(32), nullable=False),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('plan_hash', sa.String(64), nullable=False),
        sa.Column('control_session_id', sa.String(64), nullable=False),
        sa.Column('state', sa.String(24), nullable=False),
        sa.Column('cancel_requested', sa.Boolean(), nullable=False),
        sa.Column('created_at_us', sa.BigInteger(), nullable=False),
        sa.Column('updated_at_us', sa.BigInteger(), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.project_id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('operation_id'))


def downgrade():
    raise RuntimeError('STATE_PRECONDITION: preparation batch history requires an explicit backup')
