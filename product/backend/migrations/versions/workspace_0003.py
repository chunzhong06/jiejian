"""使报告游标排序直接使用索引；保持业务表和历史记录不变。"""
from alembic import op

revision = "workspace_0003"
down_revision = "workspace_0002"
branch_labels = None
depends_on = None

def upgrade():
    connection = op.get_bind()
    connection.exec_driver_sql("DROP INDEX ix_runs_project_created")
    connection.exec_driver_sql("CREATE INDEX ix_runs_project_created ON runs (project_id, created_at_us DESC, run_id)")
    connection.exec_driver_sql("UPDATE workspace_schema SET schema_digest = '19b2de6a4949da2c00413923b8a4148180af7cc30b8c1284030218a196c39100' WHERE singleton = 1")

def downgrade():
    raise RuntimeError("工作区性能修订不提供自动降级")
