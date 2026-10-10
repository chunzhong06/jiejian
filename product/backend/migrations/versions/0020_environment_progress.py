# 保存环境操作阶段和续用命令；旧回执保留原状态，不推断未完成步骤。
from alembic import op
import sqlalchemy as sa

revision = '0020_environment_progress'
down_revision = '0019_preparation_batches'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('environment_operations') as batch:
        batch.add_column(sa.Column('progress', sa.Text(), server_default='{}', nullable=False))
        batch.drop_constraint(op.f('ck_environment_operations_operation'), type_='check')
        batch.create_check_constraint('operation', "operation IN ('start','reset','stop','resume')")


def downgrade():
    raise RuntimeError('STATE_PRECONDITION: environment operation history requires an explicit backup')
