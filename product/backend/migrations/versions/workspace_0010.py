"""增加独立的业务场景修订；既有规则、单动作流程和报告原样保留。"""
from alembic import op

revision='workspace_0010'
down_revision='workspace_0009'
branch_labels=None
depends_on=None

TABLE="""CREATE TABLE business_scenarios (
    scenario_id VARCHAR(36) NOT NULL,
    revision INTEGER NOT NULL,
    project_id VARCHAR(64) NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_us BIGINT NOT NULL,
    reviewed_at_us BIGINT,
    CONSTRAINT pk_business_scenarios PRIMARY KEY (scenario_id, revision),
    CONSTRAINT fk_business_scenarios_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)"""


def upgrade():
    connection=op.get_bind()
    connection.exec_driver_sql(TABLE)
    connection.exec_driver_sql('CREATE INDEX ix_business_scenarios_project_id ON business_scenarios (project_id)')
    connection.exec_driver_sql("UPDATE workspace_schema SET schema_digest = '6de319ecbd4b1a3ee0833a7c6701a998c2e51de48cf5acc46f3bbb3223fdf679' WHERE singleton = 1")


def downgrade():
    raise RuntimeError('业务场景修订不提供自动降级')
