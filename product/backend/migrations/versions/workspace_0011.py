"""追加完整检查方案及按环境确认的绑定；既有保存范围和运行记录原样保留。"""
from alembic import op

revision = 'workspace_0011'
down_revision = 'workspace_0010'
branch_labels = None
depends_on = None

TABLES = (
    """CREATE TABLE check_routine_revisions (
        routine_id VARCHAR(36) NOT NULL, revision INTEGER NOT NULL, project_id VARCHAR(64) NOT NULL,
        name VARCHAR(80) NOT NULL, scope_kind VARCHAR(16) NOT NULL, permission_count INTEGER NOT NULL,
        operation_id VARCHAR(32) NOT NULL, request_fingerprint VARCHAR(64) NOT NULL,
        payload_json TEXT NOT NULL, created_at_us BIGINT NOT NULL,
        CONSTRAINT pk_check_routine_revisions PRIMARY KEY (routine_id, revision),
        CONSTRAINT uq_check_routine_revisions_project_id UNIQUE (project_id, operation_id),
        CONSTRAINT fk_check_routine_revisions_project_id_projects FOREIGN KEY(project_id)
            REFERENCES projects (project_id) ON DELETE RESTRICT
    )""",
    """CREATE TABLE check_routine_bindings (
        binding_id VARCHAR(36) NOT NULL, project_id VARCHAR(64) NOT NULL, routine_id VARCHAR(36) NOT NULL,
        routine_revision INTEGER NOT NULL, environment_id VARCHAR(36) NOT NULL,
        environment_revision INTEGER NOT NULL, request_fingerprint VARCHAR(64) NOT NULL,
        payload_json TEXT NOT NULL, created_at_us BIGINT NOT NULL,
        CONSTRAINT pk_check_routine_bindings PRIMARY KEY (binding_id),
        CONSTRAINT fk_check_routine_bindings_routine_id_check_routine_revisions
            FOREIGN KEY(routine_id, routine_revision) REFERENCES check_routine_revisions (routine_id, revision) ON DELETE RESTRICT,
        CONSTRAINT fk_check_routine_bindings_project_id_projects FOREIGN KEY(project_id)
            REFERENCES projects (project_id) ON DELETE RESTRICT
    )""",
)


def upgrade():
    connection = op.get_bind()
    for statement in TABLES:
        connection.exec_driver_sql(statement)
    connection.exec_driver_sql('CREATE INDEX ix_check_routine_revisions_project_id ON check_routine_revisions (project_id)')
    connection.exec_driver_sql('CREATE INDEX ix_check_routine_bindings_project_id ON check_routine_bindings (project_id)')
    connection.exec_driver_sql("UPDATE workspace_schema SET schema_digest = 'e1aee3e0ff2cd70ecbb35c91384e0b105a70f857db23884bb70b73dfa9df1c34' WHERE singleton = 1")


def downgrade():
    raise RuntimeError('完整检查方案及环境绑定不提供自动降级')
