# 持久登录任务、账号认证代次与唯一执行目标的一次完整升级。
from alembic import op

revision = "workspace_0002"
down_revision = "workspace_0001"
branch_labels = None
depends_on = None

TEST_IDENTITIES = r"""CREATE TABLE test_identities (
	identity_id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(64) NOT NULL, 
	actor_id VARCHAR(36) NOT NULL, 
	actor_revision INTEGER NOT NULL, 
	label VARCHAR(128) NOT NULL, 
	authentication_generation BIGINT NOT NULL, 
	active_preparation_id VARCHAR(37), 
	auth_method VARCHAR(32), 
	bearer_secret_ref VARCHAR(512), 
	prepared_at_us BIGINT, 
	refreshed_at_us BIGINT, 
	created_at_us BIGINT NOT NULL, 
	updated_at_us BIGINT NOT NULL, 
	CONSTRAINT pk_test_identities PRIMARY KEY (identity_id), 
	CONSTRAINT fk_test_identities_actor_id_business_actor_revisions FOREIGN KEY(actor_id, actor_revision) REFERENCES business_actor_revisions (actor_id, revision) ON DELETE RESTRICT, 
	CONSTRAINT ck_test_identities_test_identity_id_format CHECK (length(identity_id) = 36 AND identity_id GLOB 'tid_[0-9a-f]*'), 
	CONSTRAINT ck_test_identities_test_identity_auth_method_value CHECK (auth_method IS NULL OR auth_method IN ('COOKIE_SESSION', 'BEARER')), 
	CONSTRAINT ck_test_identities_test_identity_time_order CHECK (created_at_us >= 0 AND updated_at_us >= created_at_us), 
	CONSTRAINT fk_test_identities_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id)
)"""

JOBS = r"""CREATE TABLE jobs (
	job_id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(64) NOT NULL, 
	run_id VARCHAR(36), 
	recording_id VARCHAR(36), 
	operation_type VARCHAR(64) NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	idempotency_key VARCHAR(128) NOT NULL, 
	request_hash VARCHAR(64) NOT NULL, 
	attempt INTEGER NOT NULL, 
	max_attempts INTEGER NOT NULL, 
	available_at_us BIGINT NOT NULL, 
	lease_owner VARCHAR(128), 
	fencing_token BIGINT NOT NULL, 
	lease_expires_at_us BIGINT, 
	cancel_requested_at_us BIGINT, 
	created_at_us BIGINT NOT NULL, 
	updated_at_us BIGINT NOT NULL, 
	runtime_load_id VARCHAR(36), 
	preflight_id VARCHAR(36), 
	reference_capture_id VARCHAR(36), 
	identity_preparation_id VARCHAR(37), 
	CONSTRAINT pk_jobs PRIMARY KEY (job_id), 
	CONSTRAINT uq_jobs_run_id UNIQUE (run_id), 
	CONSTRAINT uq_jobs_identity_preparation UNIQUE (identity_preparation_id), 
	CONSTRAINT uq_jobs_recording_id UNIQUE (recording_id), 
	CONSTRAINT uq_jobs_runtime_load_id UNIQUE (runtime_load_id), 
	CONSTRAINT uq_jobs_preflight_id UNIQUE (preflight_id), 
	CONSTRAINT uq_jobs_reference_capture_id UNIQUE (reference_capture_id), 
	CONSTRAINT uq_jobs_idempotency_scope UNIQUE (project_id, operation_type, idempotency_key), 
	CONSTRAINT ck_jobs_job_id_format CHECK (length(job_id) = 36 AND substr(job_id, 1, 4) = 'job_' AND substr(job_id, 5) NOT GLOB '*[^0-9a-f]*'), 
	CONSTRAINT ck_jobs_operation_type_format CHECK (length(operation_type) BETWEEN 1 AND 64 AND operation_type NOT GLOB '*[^A-Z0-9_]*'), 
	CONSTRAINT ck_jobs_exactly_one_target CHECK ((run_id IS NOT NULL) + (recording_id IS NOT NULL) + (runtime_load_id IS NOT NULL) + (preflight_id IS NOT NULL) + (reference_capture_id IS NOT NULL) + (identity_preparation_id IS NOT NULL) = 1), 
	CONSTRAINT ck_jobs_runtime_operation_type CHECK (runtime_load_id IS NULL OR operation_type = 'RUNTIME_LOAD'), 
	CONSTRAINT ck_jobs_preflight_operation_type CHECK (preflight_id IS NULL OR operation_type = 'PROOF_PREFLIGHT'), 
	CONSTRAINT ck_jobs_capture_operation_type CHECK ((reference_capture_id IS NOT NULL) = (operation_type = 'REFERENCE_CAPTURE')), 
	CONSTRAINT ck_jobs_capture_single_attempt CHECK (reference_capture_id IS NULL OR max_attempts = 1), 
	CONSTRAINT ck_jobs_identity_operation_type CHECK ((identity_preparation_id IS NOT NULL) = (operation_type = 'IDENTITY_PREPARATION')), 
	CONSTRAINT ck_jobs_identity_single_attempt CHECK (identity_preparation_id IS NULL OR max_attempts = 1), 
	CONSTRAINT ck_jobs_state_value CHECK (state IN ('PENDING', 'RUNNING', 'RETRY_WAIT', 'SUCCEEDED', 'FAILED', 'CANCELLED')), 
	CONSTRAINT ck_jobs_idempotency_key_length CHECK (length(idempotency_key) BETWEEN 1 AND 128), 
	CONSTRAINT ck_jobs_request_hash_format CHECK (length(request_hash) = 64 AND request_hash NOT GLOB '*[^0-9a-f]*'), 
	CONSTRAINT ck_jobs_attempt_bounds CHECK (attempt >= 0 AND max_attempts >= 1 AND attempt <= max_attempts), 
	CONSTRAINT ck_jobs_fencing_nonnegative CHECK (fencing_token >= 0), 
	CONSTRAINT ck_jobs_attempt_fencing_relation CHECK ((attempt = 0 AND fencing_token = 0 AND lease_owner IS NULL AND lease_expires_at_us IS NULL) OR (attempt > 0 AND fencing_token > 0)), 
	CONSTRAINT ck_jobs_lease_pair CHECK ((lease_owner IS NULL AND lease_expires_at_us IS NULL) OR (lease_owner IS NOT NULL AND lease_expires_at_us IS NOT NULL)), 
	CONSTRAINT ck_jobs_running_lease_required CHECK (state <> 'RUNNING' OR (lease_owner IS NOT NULL AND fencing_token > 0 AND lease_expires_at_us IS NOT NULL)), 
	CONSTRAINT ck_jobs_lease_owner_format CHECK (lease_owner IS NULL OR (length(lease_owner) BETWEEN 1 AND 128 AND lease_owner NOT GLOB '*[^A-Za-z0-9._:-]*')), 
	CONSTRAINT ck_jobs_time_bounds CHECK (created_at_us >= 0 AND updated_at_us >= created_at_us AND available_at_us >= 0 AND (lease_expires_at_us IS NULL OR lease_expires_at_us >= 0) AND (cancel_requested_at_us IS NULL OR cancel_requested_at_us >= created_at_us)), 
	CONSTRAINT fk_jobs_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_jobs_run_id_runs FOREIGN KEY(run_id) REFERENCES runs (run_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_jobs_recording_id_recordings FOREIGN KEY(recording_id) REFERENCES recordings (recording_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_jobs_runtime_load_id_runtime_loads FOREIGN KEY(runtime_load_id) REFERENCES runtime_loads (load_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_jobs_preflight_id_proof_preflights FOREIGN KEY(preflight_id) REFERENCES proof_preflights (preflight_id) ON DELETE RESTRICT, 
	CONSTRAINT fk_jobs_reference_capture_id_reference_captures FOREIGN KEY(reference_capture_id) REFERENCES reference_captures (capture_id) ON DELETE RESTRICT
)"""

IDENTITY_PREPARATIONS = r"""CREATE TABLE identity_preparations (
	preparation_id VARCHAR(37) NOT NULL, 
	project_id VARCHAR(64) NOT NULL, 
	identity_id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	operation_id VARCHAR(32) NOT NULL, 
	request_fingerprint VARCHAR(64) NOT NULL, 
	source_fingerprint VARCHAR(64) NOT NULL, 
	authentication_generation BIGINT NOT NULL, 
	request_json TEXT NOT NULL, 
	official_account VARCHAR(16), 
	save_requested BOOLEAN NOT NULL, 
	phase VARCHAR(32) NOT NULL, 
	error_code VARCHAR(64), 
	created_at_us BIGINT NOT NULL, 
	updated_at_us BIGINT NOT NULL, 
	CONSTRAINT pk_identity_preparations PRIMARY KEY (preparation_id), 
	CONSTRAINT ck_identity_preparations_generation_nonnegative CHECK (authentication_generation >= 0), 
	CONSTRAINT fk_identity_preparations_project_id_projects FOREIGN KEY(project_id) REFERENCES projects (project_id), 
	CONSTRAINT uq_identity_preparations_job_id UNIQUE (job_id)
)"""

def upgrade():
    connection = op.get_bind()
    for name, ddl, defaults in (
        ("test_identities", TEST_IDENTITIES, {"authentication_generation": "0", "active_preparation_id": "NULL"}),
        ("jobs", JOBS, {"identity_preparation_id": "NULL"}),
    ):
        columns = tuple(row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({name})"))
        destination = columns + tuple(defaults)
        expressions = columns + tuple(defaults.values())
        temporary = name + "_next"
        connection.exec_driver_sql(ddl.replace("CREATE TABLE " + name, "CREATE TABLE " + temporary, 1))
        connection.exec_driver_sql(f"INSERT INTO {temporary} ({", ".join(destination)}) SELECT {", ".join(expressions)} FROM {name}")
        connection.exec_driver_sql("DROP TABLE " + name)
        connection.exec_driver_sql(f"ALTER TABLE {temporary} RENAME TO {name}")
    connection.exec_driver_sql(IDENTITY_PREPARATIONS)
    connection.exec_driver_sql('CREATE INDEX ix_test_identities_project_updated ON test_identities (project_id, updated_at_us)')
    connection.exec_driver_sql('CREATE INDEX ix_jobs_state_available ON jobs (state, available_at_us)')
    connection.exec_driver_sql('CREATE INDEX ix_jobs_state_lease_expires ON jobs (state, lease_expires_at_us)')
    connection.exec_driver_sql('CREATE INDEX ix_identity_preparations_identity ON identity_preparations (identity_id, created_at_us)')
    connection.exec_driver_sql('CREATE INDEX ix_identity_preparations_project ON identity_preparations (project_id, created_at_us)')
    connection.exec_driver_sql("UPDATE workspace_schema SET schema_digest = '7728ac02f4242a0ab997edcf07c0763a78973b3b4c7cf202efe85bce9421cbf4' WHERE singleton = 1")

def downgrade():
    raise RuntimeError("持久登录任务不支持有损降级")
