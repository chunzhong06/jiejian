# 持久协作任务保存目标、决定和原业务回执引用，不复制业务生命周期或权限结论。
from alembic import op
import sqlalchemy as sa

revision = 'workspace_0005'
down_revision = 'workspace_0004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('collaboration_tasks',
        sa.Column('task_id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('projects.project_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('state', sa.String(24), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('updated_at_us', sa.BigInteger(), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False))
    op.create_index('ix_collaboration_tasks_project_id', 'collaboration_tasks', ['project_id'])
    op.get_bind().exec_driver_sql("UPDATE workspace_schema SET schema_digest = '6d2ab926e75b0d1a7447e3b9a82c827064c50eb6f2aaebbaa8f74b93926d238b' WHERE singleton = 1")


def downgrade():
    raise RuntimeError('持久协作任务不提供自动降级')
