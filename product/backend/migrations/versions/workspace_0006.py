"""条件权限和逐规则测试数据一起升级，已有规则与报告不重新解释。"""
from alembic import op
import sqlalchemy as sa

revision = 'workspace_0006'
down_revision = 'workspace_0005'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('permission_intent_revisions', sa.Column('conditions_json', sa.Text(), nullable=True))
    op.create_table('rule_case_data',
        sa.Column('intent_id', sa.String(36), primary_key=True),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('projects.project_id', ondelete='CASCADE'), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False))
    op.get_bind().exec_driver_sql("UPDATE workspace_schema SET schema_digest = '678e5405c32cb7e46f74ff2b341c860fa06b58863046020859c7e9d198d4eb24' WHERE singleton = 1")


def downgrade():
    raise RuntimeError('已批准条件权限不提供自动降级')
