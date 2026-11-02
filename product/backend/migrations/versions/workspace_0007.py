# 保存可重复使用的检查范围，历史报告和准备绑定保持原样。
from alembic import op
import sqlalchemy as sa

revision = 'workspace_0007'
down_revision = 'workspace_0006'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('check_routines',
        sa.Column('routine_id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('projects.project_id', ondelete='CASCADE'), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False))
    op.create_index('ix_check_routines_project_id', 'check_routines', ['project_id'])
    op.get_bind().exec_driver_sql("UPDATE workspace_schema SET schema_digest = '1c82934014174e94781634182cbd0611262447d49a3988a8e7668c76a787d761' WHERE singleton = 1")


def downgrade():
    raise RuntimeError('已保存检查方案不提供自动降级')
