"""环境与净化接口来源的一次完整升级；原报告和业务修订不重写。"""
from alembic import op

revision = 'workspace_0008'
down_revision = 'workspace_0007'
branch_labels = None
depends_on = None

TABLES = {
    'application_understanding': """CREATE TABLE application_understanding (
	project_id VARCHAR(64) NOT NULL, 
	source_root VARCHAR(32768), 
	environment_json TEXT, 
	confirmed_endpoint VARCHAR(2048), 
	endpoint_source_fingerprint VARCHAR(64), 
	endpoint_confirmed_at_us BIGINT, 
	endpoint_last_checked_at_us BIGINT, 
	endpoint_reachable BOOLEAN, 
	source_analysis_authorized BOOLEAN NOT NULL, 
	source_analysis_authorized_at_us BIGINT, 
	source_fingerprint VARCHAR(64), 
	analysis_completed_at_us BIGINT, 
	role_candidates_json TEXT NOT NULL, 
	action_candidates_json TEXT NOT NULL, 
	revision INTEGER NOT NULL, 
	created_at_us BIGINT NOT NULL, 
	updated_at_us BIGINT NOT NULL, 
	CONSTRAINT pk_application_understanding PRIMARY KEY (project_id), 
	CONSTRAINT ck_application_understanding_source_root_length CHECK (source_root IS NULL OR length(source_root) BETWEEN 1 AND 32768), 
	CONSTRAINT ck_application_understanding_endpoint_length CHECK (confirmed_endpoint IS NULL OR length(confirmed_endpoint) BETWEEN 1 AND 2048), 
	CONSTRAINT ck_application_understanding_endpoint_state_complete CHECK ((confirmed_endpoint IS NULL AND endpoint_source_fingerprint IS NULL AND endpoint_confirmed_at_us IS NULL AND endpoint_last_checked_at_us IS NULL AND endpoint_reachable IS NULL) OR (confirmed_endpoint IS NOT NULL AND endpoint_source_fingerprint IS NOT NULL AND endpoint_confirmed_at_us IS NOT NULL AND endpoint_last_checked_at_us IS NOT NULL AND endpoint_reachable IS NOT NULL)), 
	CONSTRAINT ck_application_understanding_endpoint_fingerprint_length CHECK (endpoint_source_fingerprint IS NULL OR length(endpoint_source_fingerprint) = 64), 
	CONSTRAINT ck_application_understanding_analysis_authorization_state CHECK ((source_analysis_authorized = 0 AND source_analysis_authorized_at_us IS NULL) OR (source_analysis_authorized = 1 AND source_analysis_authorized_at_us IS NOT NULL)), 
	CONSTRAINT ck_application_understanding_analysis_result_state CHECK ((source_fingerprint IS NULL AND analysis_completed_at_us IS NULL) OR (source_fingerprint IS NOT NULL AND length(source_fingerprint) = 64 AND analysis_completed_at_us IS NOT NULL AND source_analysis_authorized = 1)), 
	CONSTRAINT ck_application_understanding_roles_json_length CHECK (length(role_candidates_json) BETWEEN 2 AND 1048576), 
	CONSTRAINT ck_application_understanding_actions_json_length CHECK (length(action_candidates_json) BETWEEN 2 AND 2097152), 
	CONSTRAINT ck_application_understanding_revision_range CHECK (revision BETWEEN 0 AND 1000000), 
	CONSTRAINT ck_application_understanding_time_order CHECK (created_at_us >= 0 AND updated_at_us >= created_at_us), 
	CONSTRAINT fk_application_understanding_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)""",
    'runs': """CREATE TABLE runs (
	run_id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(64) NOT NULL, 
	request_hash VARCHAR(64) NOT NULL, 
	plan_fingerprint VARCHAR(64) NOT NULL, 
	source_fingerprint VARCHAR(64), 
	policy_epoch BIGINT NOT NULL, 
	engine_version VARCHAR(64) NOT NULL, 
	lifecycle VARCHAR(24) NOT NULL, 
	verdict VARCHAR(16), 
	created_at_us BIGINT NOT NULL, 
	updated_at_us BIGINT NOT NULL, 
	finished_at_us BIGINT, 
	CONSTRAINT pk_runs PRIMARY KEY (run_id), 
	CONSTRAINT ck_runs_run_id_format CHECK (length(run_id) = 36 AND substr(run_id, 1, 4) = 'run_' AND substr(run_id, 5) NOT GLOB '*[^0-9a-f]*'), 
	CONSTRAINT ck_runs_lifecycle_value CHECK (lifecycle IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED')), 
	CONSTRAINT ck_runs_verdict_value CHECK (verdict IS NULL OR verdict IN ('PASS', 'BLOCK', 'INCONCLUSIVE')), 
	CONSTRAINT ck_runs_lifecycle_verdict_matrix CHECK ((lifecycle = 'COMPLETED' AND verdict IS NOT NULL) OR (lifecycle = 'SAFETY_STOPPED' AND (verdict IS NULL OR verdict IN ('BLOCK', 'INCONCLUSIVE'))) OR (lifecycle NOT IN ('COMPLETED', 'SAFETY_STOPPED') AND verdict IS NULL)), 
	CONSTRAINT ck_runs_policy_epoch_nonnegative CHECK (policy_epoch >= 0), 
	CONSTRAINT ck_runs_engine_version_length CHECK (length(engine_version) BETWEEN 1 AND 64), 
	CONSTRAINT ck_runs_request_hash_format CHECK (length(request_hash) = 64 AND request_hash NOT GLOB '*[^0-9a-f]*'), 
	CONSTRAINT ck_runs_plan_fingerprint_format CHECK (length(plan_fingerprint) = 64 AND plan_fingerprint NOT GLOB '*[^0-9a-f]*'), 
	CONSTRAINT ck_runs_source_fingerprint_format CHECK (length(source_fingerprint) = 64 AND source_fingerprint NOT GLOB '*[^0-9a-f]*'), 
	CONSTRAINT ck_runs_time_order CHECK (created_at_us >= 0 AND updated_at_us >= created_at_us AND (finished_at_us IS NULL OR finished_at_us >= created_at_us)), 
	CONSTRAINT fk_runs_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)""",
    'action_evidence_bindings': """CREATE TABLE action_evidence_bindings (
	effect_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(32) NOT NULL, 
	source_recording_id VARCHAR(36), 
	source_draft_revision INTEGER, 
	source_draft_sha256 VARCHAR(64), 
	step_id VARCHAR(64), 
	request_template_json TEXT, 
	observer_reference_json TEXT, 
	operation_flow_id VARCHAR(36), 
	operation_flow_revision INTEGER, 
	entity_query_json TEXT, 
	business_action_id VARCHAR(36) NOT NULL, 
	action_revision INTEGER NOT NULL, 
	project_id VARCHAR(64) NOT NULL, 
	action_semantic_fingerprint VARCHAR(64) NOT NULL, 
	implementation_fingerprint VARCHAR(64) NOT NULL, 
	source_fingerprint VARCHAR(64), 
	endpoint_fingerprint VARCHAR(64) NOT NULL, 
	subject_test_identity_id VARCHAR(36) NOT NULL, 
	subject_identity_fingerprint VARCHAR(64) NOT NULL, 
	resource_owner_test_identity_id VARCHAR(36) NOT NULL, 
	owner_identity_fingerprint VARCHAR(64) NOT NULL, 
	confirmed_at_us BIGINT NOT NULL, 
	binding_fingerprint VARCHAR(64) NOT NULL, 
	CONSTRAINT pk_action_evidence_bindings PRIMARY KEY (business_action_id, action_revision, effect_id), 
	CONSTRAINT fk_action_evidence_bindings_business_action_id_business_action_revisions FOREIGN KEY(business_action_id, action_revision) REFERENCES business_action_revisions (action_id, revision) ON DELETE RESTRICT, 
	CONSTRAINT ck_action_evidence_bindings_revision_time_bounds CHECK (action_revision >= 1 AND confirmed_at_us >= 0), 
	CONSTRAINT ck_action_evidence_bindings_binding_fingerprint_format CHECK (length(binding_fingerprint) = 64 AND binding_fingerprint NOT GLOB '*[^0-9a-f]*'), 
	CONSTRAINT fk_action_evidence_bindings_source_recording_id_flow_draft_revisions FOREIGN KEY(source_recording_id, source_draft_revision) REFERENCES flow_draft_revisions (recording_id, revision) ON DELETE RESTRICT, 
	CONSTRAINT fk_action_evidence_bindings_operation_flow_id_operation_flow_revisions FOREIGN KEY(operation_flow_id, operation_flow_revision) REFERENCES operation_flow_revisions (flow_id, revision) ON DELETE RESTRICT, 
	CONSTRAINT ck_action_evidence_bindings_evidence_source_matrix CHECK ((kind = 'RECORDED_OBSERVATION' AND source_recording_id IS NOT NULL AND source_draft_revision IS NOT NULL AND source_draft_sha256 IS NOT NULL AND step_id IS NOT NULL AND request_template_json IS NOT NULL AND observer_reference_json IS NULL) OR (kind = 'REGISTERED_OBSERVER' AND source_recording_id IS NULL AND source_draft_revision IS NULL AND source_draft_sha256 IS NULL AND step_id IS NULL AND request_template_json IS NULL AND observer_reference_json IS NOT NULL) OR (kind = 'HTTP_ENTITY_QUERY' AND operation_flow_id IS NOT NULL AND operation_flow_revision IS NOT NULL AND entity_query_json IS NOT NULL AND source_recording_id IS NULL AND source_draft_revision IS NULL AND source_draft_sha256 IS NULL AND step_id IS NULL AND request_template_json IS NULL AND observer_reference_json IS NULL)), 
	CONSTRAINT fk_action_evidence_bindings_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)""",
    'application_environments': """CREATE TABLE application_environments (
	environment_id VARCHAR(36) NOT NULL, 
	revision INTEGER NOT NULL, 
	project_id VARCHAR(64) NOT NULL, 
	payload TEXT NOT NULL, 
	CONSTRAINT pk_application_environments PRIMARY KEY (environment_id, revision), 
	CONSTRAINT fk_application_environments_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)""",
    'api_sources': """CREATE TABLE api_sources (
	source_id VARCHAR(36) NOT NULL, 
	revision INTEGER NOT NULL, 
	project_id VARCHAR(64) NOT NULL, 
	payload TEXT NOT NULL, 
	CONSTRAINT pk_api_sources PRIMARY KEY (source_id, revision), 
	CONSTRAINT fk_api_sources_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)""",
    'api_source_annotations': """CREATE TABLE api_source_annotations (
	source_id VARCHAR(36) NOT NULL, 
	item_id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(64) NOT NULL, 
	revision INTEGER NOT NULL, 
	payload TEXT NOT NULL, 
	CONSTRAINT pk_api_source_annotations PRIMARY KEY (source_id, item_id), 
	CONSTRAINT fk_api_source_annotations_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)""",
    'api_source_imports': """CREATE TABLE api_source_imports (
	candidate_id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(64) NOT NULL, 
	payload TEXT NOT NULL, 
	CONSTRAINT pk_api_source_imports PRIMARY KEY (candidate_id), 
	CONSTRAINT fk_api_source_imports_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT
)""",
}

INDEXES = [
    'CREATE INDEX ix_application_understanding_source_root ON application_understanding (source_root)',
    'CREATE INDEX ix_application_understanding_updated ON application_understanding (updated_at_us)',
    'CREATE INDEX ix_runs_lifecycle_updated ON runs (lifecycle, updated_at_us)',
    'CREATE INDEX ix_runs_project_created ON runs (project_id, created_at_us DESC, run_id)',
    'CREATE INDEX ix_application_environments_project_id ON application_environments (project_id)',
    'CREATE INDEX ix_api_sources_project_id ON api_sources (project_id)',
    'CREATE INDEX ix_api_source_annotations_project_id ON api_source_annotations (project_id)',
    'CREATE INDEX ix_api_source_imports_project_id ON api_source_imports (project_id)',
]

def upgrade():
    connection = op.get_bind()
    for name in ('application_understanding', 'runs', 'action_evidence_bindings'):
        columns = tuple(row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info({name})'))
        temporary = name + '_next'
        connection.exec_driver_sql(TABLES[name].replace('CREATE TABLE ' + name, 'CREATE TABLE ' + temporary, 1))
        names = ', '.join(columns)
        connection.exec_driver_sql(f'INSERT INTO {temporary} ({names}) SELECT {names} FROM {name}')
        connection.exec_driver_sql('DROP TABLE ' + name)
        connection.exec_driver_sql(f'ALTER TABLE {temporary} RENAME TO {name}')
    for name in ('application_environments', 'api_sources', 'api_source_annotations', 'api_source_imports'):
        connection.exec_driver_sql(TABLES[name])
    for statement in INDEXES:
        connection.exec_driver_sql(statement)
    connection.exec_driver_sql("UPDATE workspace_schema SET schema_digest = 'e17d5d2e27bbd3831d879a36333b6896cc7cf71916575ad89e25d29509c7a46c' WHERE singleton = 1")


def downgrade():
    raise RuntimeError("环境与来源修订不提供自动降级")
