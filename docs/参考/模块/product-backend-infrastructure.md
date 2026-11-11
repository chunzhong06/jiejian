# product/backend/infrastructure 模块

<!-- generated:modules -->

[返回总索引](../模块索引.md)

按目录定位后读取对应小节；每个文件有独立标题，源码链接用于核对声明与直接消费者。行数和公开声明由静态提取，不表示运行验收。

按目录定位：[根目录](#根目录)（2 个文件）、[artifacts](#artifacts)（7 个文件）、[artifacts/checks](#artifactschecks)（6 个文件）、[execution](#execution)（5 个文件）、[execution/web](#executionweb)（6 个文件）、[identity](#identity)（4 个文件）、[integrations](#integrations)（1 个文件）、[maintenance](#maintenance)（4 个文件）、[observers](#observers)（5 个文件）、[observers/adapters](#observersadapters)（8 个文件）、[observers/checks](#observerschecks)（15 个文件）、[observers/records](#observersrecords)（10 个文件）、[recording](#recording)（10 个文件）、[runtime](#runtime)（14 个文件）、[runtime/capture_runner](#runtimecapture_runner)（4 个文件）、[runtime/check_runner](#runtimecheck_runner)（4 个文件）、[runtime/jobs](#runtimejobs)（15 个文件）、[runtime/process](#runtimeprocess)（7 个文件）、[runtime/process/controlled](#runtimeprocesscontrolled)（13 个文件）、[runtime/process/records](#runtimeprocessrecords)（3 个文件）、[runtime/proof_runner](#runtimeproof_runner)（4 个文件）、[runtime/trial_runner](#runtimetrial_runner)（4 个文件）、[runtime/worker](#runtimeworker)（4 个文件）、[samples](#samples)（2 个文件）、[samples/official](#samplesofficial)（5 个文件）、[secrets](#secrets)（5 个文件）、[storage](#storage)（7 个文件）、[storage/applications](#storageapplications)（5 个文件）、[storage/boundaries](#storageboundaries)（4 个文件）、[storage/changes](#storagechanges)（4 个文件）、[storage/execution](#storageexecution)（6 个文件）、[storage/preparation](#storagepreparation)（14 个文件）、[storage/results](#storageresults)（4 个文件）、[storage/runtime](#storageruntime)（5 个文件）、[storage/settings](#storagesettings)（2 个文件）。

## 根目录

### __init__.py

[源码](../../../product/backend/infrastructure/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### source_identity.py

[源码](../../../product/backend/infrastructure/source_identity.py)（67 行）。公开声明：`GitSourceContext`、`inspect_git_source`。

## artifacts

### artifacts/__init__.py

[源码](../../../product/backend/infrastructure/artifacts/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### artifacts/capture_baselines.py

[源码](../../../product/backend/infrastructure/artifacts/capture_baselines.py)（36 行）。公开声明：`save_capture_baseline`、`read_capture_baseline`。

### artifacts/capture_guard.py

[源码](../../../product/backend/infrastructure/artifacts/capture_guard.py)（36 行）。公开声明：`capture_inputs_current`。

### artifacts/proof_artifacts.py

[源码](../../../product/backend/infrastructure/artifacts/proof_artifacts.py)（128 行）。公开声明：`ProofArtifactContent`、`ProofArtifactStore`、`CaptureReportStore`。

### artifacts/proof_reports.py

[源码](../../../product/backend/infrastructure/artifacts/proof_reports.py)（44 行）。公开声明：`ProofReportStore`。

### artifacts/run_packages.py

[源码](../../../product/backend/infrastructure/artifacts/run_packages.py)（35 行）。公开声明：`AttemptPaths`、`attempt_paths_for`。

### artifacts/trial_guard.py

[源码](../../../product/backend/infrastructure/artifacts/trial_guard.py)（32 行）。公开声明：`trial_inputs_current`。

## artifacts/checks

### artifacts/checks/__init__.py

[源码](../../../product/backend/infrastructure/artifacts/checks/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### artifacts/checks/check_packages.py

[源码](../../../product/backend/infrastructure/artifacts/checks/check_packages.py)（171 行）。公开声明：`CheckPackage`、`check_final_directory`、`reject_check_links`、`read_check_bytes`、`validate_check_package`。

### artifacts/checks/check_publication.py

[源码](../../../product/backend/infrastructure/artifacts/checks/check_publication.py)（157 行）。公开声明：`CheckPublisher`。

### artifacts/checks/check_validation.py

[源码](../../../product/backend/infrastructure/artifacts/checks/check_validation.py)（128 行）。公开声明：`check_publication_budget_reason`、`validate_check_inputs`、`validate_check_decisions`。

### artifacts/checks/fact_validation.py

[源码](../../../product/backend/infrastructure/artifacts/checks/fact_validation.py)（113 行）。公开声明：`validate_scenario_bindings`、`validate_frozen_facts`。

### artifacts/checks/scenario_progress.py

[源码](../../../product/backend/infrastructure/artifacts/checks/scenario_progress.py)（36 行）。公开声明：`read_scenario_journal`。

## execution

### execution/__init__.py

[源码](../../../product/backend/infrastructure/execution/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### execution/business_scenario.py

[源码](../../../product/backend/infrastructure/execution/business_scenario.py)（174 行）。公开声明：`execute_business_scenario`。

### execution/check_executor.py

[源码](../../../product/backend/infrastructure/execution/check_executor.py)（335 行）。公开声明：`CheckExecutionOutput`、`CheckExecutor`。

### execution/creation_check.py

[源码](../../../product/backend/infrastructure/execution/creation_check.py)（135 行）。公开声明：`execute_creation_case`、`recover_created`。

### execution/scenario_journal.py

[源码](../../../product/backend/infrastructure/execution/scenario_journal.py)（71 行）。公开声明：`ScenarioJournal`。

## execution/web

### execution/web/__init__.py

[源码](../../../product/backend/infrastructure/execution/web/__init__.py)（3 行）。公开声明：包、内部机制或样式。

### execution/web/adapter.py

[源码](../../../product/backend/infrastructure/execution/web/adapter.py)（644 行）。公开声明：`HttpResponse`、`AuthorizedTarget`、`WebTargetGuard`、`HttpExecutionAdapter`、`extract_response_value`。

### execution/web/batch.py

[源码](../../../product/backend/infrastructure/execution/web/batch.py)（51 行）。公开声明：`execute_batch`。

### execution/web/check_runtime.py

[源码](../../../product/backend/infrastructure/execution/web/check_runtime.py)（242 行）。公开声明：`CheckWebRuntime`、`check_secret_names`。

### execution/web/file_entity.py

[源码](../../../product/backend/infrastructure/execution/web/file_entity.py)（63 行）。公开声明：`FileEntityPolicy`、`FileEntityReceipt`、`receive_file_entity`。

### execution/web/identity.py

[源码](../../../product/backend/infrastructure/execution/web/identity.py)（260 行）。公开声明：`IdentityTokenState`、`HttpIdentityRuntime`。

## identity

### identity/__init__.py

[源码](../../../product/backend/infrastructure/identity/__init__.py)（5 行）。公开声明：包、内部机制或样式。

### identity/browser.py

[源码](../../../product/backend/infrastructure/identity/browser.py)（500 行）。公开声明：`IdentityPreparationBrowserAdapter`。

### identity/control.py

[源码](../../../product/backend/infrastructure/identity/control.py)（79 行）。公开声明：`IdentityPreparationControlPaths`、`identity_preparation_control_paths`、`write_identity_preparation_marker`、`valid_identity_preparation_marker`。

### identity/process.py

[源码](../../../product/backend/infrastructure/identity/process.py)（124 行）。公开声明：`execute_identity_preparation`、`main`。

## integrations

### integrations/github.py

[源码](../../../product/backend/infrastructure/integrations/github.py)（69 行）。公开声明：`GitHubIssues`。

## maintenance

### maintenance/__init__.py

[源码](../../../product/backend/infrastructure/maintenance/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### maintenance/inventory.py

[源码](../../../product/backend/infrastructure/maintenance/inventory.py)（325 行）。公开声明：`linked`、`safe_tree`、`read_record`、`children`、`overlaps`、`component_in_use`、`exclusive_file`、`Asset`等。

### maintenance/models.py

[源码](../../../product/backend/infrastructure/maintenance/models.py)（27 行）。公开声明：`MaintenanceCandidate`、`MaintenancePlan`。

### maintenance/service.py

[源码](../../../product/backend/infrastructure/maintenance/service.py)（770 行）。公开声明：`LocalMaintenanceService`。

## observers

### observers/__init__.py

[源码](../../../product/backend/infrastructure/observers/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### observers/artifacts.py

[源码](../../../product/backend/infrastructure/observers/artifacts.py)（13 行）。公开声明：`write_atomic`。

### observers/coordinator.py

[源码](../../../product/backend/infrastructure/observers/coordinator.py)（148 行）。公开声明：`TargetCaseSession`、`ObserverCoordinator`、`default_observer_registry`。

### observers/effect_projector.py

[源码](../../../product/backend/infrastructure/observers/effect_projector.py)（663 行）。公开声明：`EffectProjection`、`EffectProjector`。

### observers/registry.py

[源码](../../../product/backend/infrastructure/observers/registry.py)（31 行）。公开声明：`ObserverRegistry`。

## observers/adapters

### observers/adapters/__init__.py

[源码](../../../product/backend/infrastructure/observers/adapters/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### observers/adapters/async_task.py

[源码](../../../product/backend/infrastructure/observers/adapters/async_task.py)（450 行）。公开声明：`AsyncTaskObserverResult`、`child_main`、`run_async_task_observer`、`main`。

### observers/adapters/audit_log.py

[源码](../../../product/backend/infrastructure/observers/adapters/audit_log.py)（729 行）。公开声明：`AuditLogObserverResult`、`child_main`、`run_audit_log_observer`、`main`。

### observers/adapters/azure_blob.py

[源码](../../../product/backend/infrastructure/observers/adapters/azure_blob.py)（700 行）。公开声明：`BlobObserverResult`、`child_main`、`run_azure_blob_observer`、`main`。

### observers/adapters/azure_queue.py

[源码](../../../product/backend/infrastructure/observers/adapters/azure_queue.py)（517 行）。公开声明：`QueueObserverResult`、`child_main`、`run_azure_queue_observer`、`main`。

### observers/adapters/json_source.py

[源码](../../../product/backend/infrastructure/observers/adapters/json_source.py)（93 行）。公开声明：`SourceReadError`、`strict_json`、`scalar`、`mapped_values`、`JsonHistoryFact`、`project_history`。

### observers/adapters/owner_api.py

[源码](../../../product/backend/infrastructure/observers/adapters/owner_api.py)（122 行）。公开声明：`OwnerApiObserverAdapter`。

### observers/adapters/sqlite.py

[源码](../../../product/backend/infrastructure/observers/adapters/sqlite.py)（363 行）。公开声明：`SqliteObserverResult`、`child_main`、`run_sqlite_observer`、`main`。

## observers/checks

### observers/checks/__init__.py

[源码](../../../product/backend/infrastructure/observers/checks/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### observers/checks/async_export.py

[源码](../../../product/backend/infrastructure/observers/checks/async_export.py)（92 行）。公开声明：`AsyncExportResult`、`observe_export`。

### observers/checks/check_disclosure.py

[源码](../../../product/backend/infrastructure/observers/checks/check_disclosure.py)（38 行）。公开声明：`protected_projection`、`disclosure_proof`。

### observers/checks/check_records.py

[源码](../../../product/backend/infrastructure/observers/checks/check_records.py)（151 行）。公开声明：`observe_records`。

### observers/checks/check_runtime.py

[源码](../../../product/backend/infrastructure/observers/checks/check_runtime.py)（260 行）。公开声明：`CheckObserverRuntime`。

### observers/checks/check_trace.py

[源码](../../../product/backend/infrastructure/observers/checks/check_trace.py)（92 行）。公开声明：`build_check_trace`。

### observers/checks/creation_evidence.py

[源码](../../../product/backend/infrastructure/observers/checks/creation_evidence.py)（95 行）。公开声明：`collection_digest`、`response_resource`、`observe_creation`。

### observers/checks/disclosure_evidence.py

[源码](../../../product/backend/infrastructure/observers/checks/disclosure_evidence.py)（62 行）。公开声明：`collect_disclosure_evidence`。

### observers/checks/file_evidence.py

[源码](../../../product/backend/infrastructure/observers/checks/file_evidence.py)（46 行）。公开声明：`collect_file_evidence`。

### observers/checks/http_entity.py

[源码](../../../product/backend/infrastructure/observers/checks/http_entity.py)（72 行）。公开声明：`selected`、`entity_fields`、`observe_http_entity`。

### observers/checks/managed_trace.py

[源码](../../../product/backend/infrastructure/observers/checks/managed_trace.py)（50 行）。公开声明：`managed_execution_trace`。

### observers/checks/models.py

[源码](../../../product/backend/infrastructure/observers/checks/models.py)（13 行）。公开声明：`CheckObservedSource`。

### observers/checks/record_evidence.py

[源码](../../../product/backend/infrastructure/observers/checks/record_evidence.py)（69 行）。公开声明：`collect_record_evidence`、`identity_facts`。

### observers/checks/relationship_facts.py

[源码](../../../product/backend/infrastructure/observers/checks/relationship_facts.py)（42 行）。公开声明：`collect_relationship_conditions`。

### observers/checks/sealed_facts.py

[源码](../../../product/backend/infrastructure/observers/checks/sealed_facts.py)（57 行）。公开声明：`finalize_facts`。

## observers/records

### observers/records/__init__.py

[源码](../../../product/backend/infrastructure/observers/records/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### observers/records/database_capture.py

[源码](../../../product/backend/infrastructure/observers/records/database_capture.py)（260 行）。公开声明：`connection`、`query`、`installation_path`、`read_database_receipt`、`read_installation`、`save_database_receipt`、`definitions`、`validate_table`等。

### observers/records/database_sql.py

[源码](../../../product/backend/infrastructure/observers/records/database_sql.py)（86 行）。公开声明：`capture_key`、`quote`、`qualified`、`statements`、`maintenance_plan`。

### observers/records/record_facts.py

[源码](../../../product/backend/infrastructure/observers/records/record_facts.py)（96 行）。公开声明：`record_value`、`field_value`、`transaction_fact`、`request_fact`、`resource_operations`。

### observers/records/record_history.py

[源码](../../../product/backend/infrastructure/observers/records/record_history.py)（103 行）。公开声明：`encode_frame`、`read_history`。

### observers/records/record_preflight.py

[源码](../../../product/backend/infrastructure/observers/records/record_preflight.py)（45 行）。公开声明：`managed_source_checks`。

### observers/records/record_source.py

[源码](../../../product/backend/infrastructure/observers/records/record_source.py)（144 行）。公开声明：`record_provider`、`read_record_source`、`read_managed_record`、`read_request_activity`。

### observers/records/source_contracts.py

[源码](../../../product/backend/infrastructure/observers/records/source_contracts.py)（61 行）。公开声明：`audit_source_contract`。

### observers/records/sqlite_source.py

[源码](../../../product/backend/infrastructure/observers/records/sqlite_source.py)（141 行）。公开声明：`sqlite_selection`、`read_sqlite_source`。

### observers/records/transaction_store.py

[源码](../../../product/backend/infrastructure/observers/records/transaction_store.py)（444 行）。公开声明：`RecordStoreError`、`TransactionRecordStore`。

## recording

### recording/__init__.py

[源码](../../../product/backend/infrastructure/recording/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### recording/browser.py

[源码](../../../product/backend/infrastructure/recording/browser.py)（442 行）。公开声明：`RecordingPage`、`RecordingBrowserSession`、`BrowserRecordingAdapter`。

### recording/control.py

[源码](../../../product/backend/infrastructure/recording/control.py)（79 行）。公开声明：`RecordingControlPaths`、`control_paths_for_attempt`、`write_control_marker`、`valid_control_marker`。

### recording/events.py

[源码](../../../product/backend/infrastructure/recording/events.py)（712 行）。公开声明：`RecordingEventCollector`。

### recording/flows.py

[源码](../../../product/backend/infrastructure/recording/flows.py)（80 行）。公开声明：`recorded_flow_path`、`read_recorded_flow`、`publish_recorded_flow`、`canonical_flow_bytes`。

### recording/process.py

[源码](../../../product/backend/infrastructure/recording/process.py)（171 行）。公开声明：`execute_recording_runner`、`main`。

### recording/request_store.py

[源码](../../../product/backend/infrastructure/recording/request_store.py)（131 行）。公开声明：`RecordingRequestStore`。

### recording/sanitization.py

[源码](../../../product/backend/infrastructure/recording/sanitization.py)（194 行）。公开声明：`RecordingSanitizer`。

### recording/transport.py

[源码](../../../product/backend/infrastructure/recording/transport.py)（251 行）。公开声明：`BoundedHTTPResponse`、`is_file_response`、`BoundedRouteTransport`。

### recording/ui_capture.py

[源码](../../../product/backend/infrastructure/recording/ui_capture.py)（63 行）。公开声明：`install_ui_capture`。

## runtime

### runtime/__init__.py

[源码](../../../product/backend/infrastructure/runtime/__init__.py)（4 行）。公开声明：包、内部机制或样式。

### runtime/agent_process.py

[源码](../../../product/backend/infrastructure/runtime/agent_process.py)（131 行）。公开声明：`run_codex`。

### runtime/diagnostics.py

[源码](../../../product/backend/infrastructure/runtime/diagnostics.py)（540 行）。公开声明：`DoctorCheck`、`DoctorReport`、`runtime_environment_details`、`run_doctor`。

### runtime/frontend_assets.py

[源码](../../../product/backend/infrastructure/runtime/frontend_assets.py)（60 行）。公开声明：`frontend_asset_identity`。

### runtime/generated_files.py

[源码](../../../product/backend/infrastructure/runtime/generated_files.py)（61 行）。公开声明：`register_generated_file`、`generated_file_owner`、`forget_generated_file`。

### runtime/logging.py

[源码](../../../product/backend/infrastructure/runtime/logging.py)（140 行）。公开声明：`request_trace_id`、`request_log_context`、`OwnedRotatingFileHandler`、`JsonFormatter`、`configure_logging`。

### runtime/paths.py

[源码](../../../product/backend/infrastructure/runtime/paths.py)（176 行）。公开声明：`RuntimePaths`。

### runtime/serve_lock.py

[源码](../../../product/backend/infrastructure/runtime/serve_lock.py)（92 行）。公开声明：`ServeLock`。

### runtime/service_lifetime.py

[源码](../../../product/backend/infrastructure/runtime/service_lifetime.py)（25 行）。公开声明：`serve_owner_is_alive`。

### runtime/session_secrets.py

[源码](../../../product/backend/infrastructure/runtime/session_secrets.py)（60 行）。公开声明：`SessionSecretOverlay`。

### runtime/settings.py

[源码](../../../product/backend/infrastructure/runtime/settings.py)（152 行）。公开声明：`Settings`、`LoadedSettings`、`default_config_path`、`load_settings`。

### runtime/system_status.py

[源码](../../../product/backend/infrastructure/runtime/system_status.py)（76 行）。公开声明：`SystemRuntimeView`。

### runtime/updates.py

[源码](../../../product/backend/infrastructure/runtime/updates.py)（288 行）。公开声明：`file_digest`、`read_root`、`package_files`、`verify_package`、`PortableUpdateService`、`finish_after_exit`。

### runtime/workflow_timing.py

[源码](../../../product/backend/infrastructure/runtime/workflow_timing.py)（128 行）。公开声明：`WorkflowTimings`、`workflow_timings`、`link_workflow`、`workflow_phase`、`timed_workflow`。

## runtime/capture_runner

### runtime/capture_runner/__init__.py

[源码](../../../product/backend/infrastructure/runtime/capture_runner/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### runtime/capture_runner/__main__.py

[源码](../../../product/backend/infrastructure/runtime/capture_runner/__main__.py)（33 行）。公开声明：`main`。

### runtime/capture_runner/executor.py

[源码](../../../product/backend/infrastructure/runtime/capture_runner/executor.py)（133 行）。公开声明：`execute_capture`。

### runtime/capture_runner/supervisor.py

[源码](../../../product/backend/infrastructure/runtime/capture_runner/supervisor.py)（84 行）。公开声明：`ReferenceCaptureHandler`。

## runtime/check_runner

### runtime/check_runner/__init__.py

[源码](../../../product/backend/infrastructure/runtime/check_runner/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### runtime/check_runner/__main__.py

[源码](../../../product/backend/infrastructure/runtime/check_runner/__main__.py)（26 行）。公开声明：`main`。

### runtime/check_runner/executor.py

[源码](../../../product/backend/infrastructure/runtime/check_runner/executor.py)（82 行）。公开声明：`execute_check_attempt`。

### runtime/check_runner/supervisor.py

[源码](../../../product/backend/infrastructure/runtime/check_runner/supervisor.py)（131 行）。公开声明：`CheckRunnerSupervisor`、`CheckJobHandler`。

## runtime/jobs

### runtime/jobs/__init__.py

[源码](../../../product/backend/infrastructure/runtime/jobs/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### runtime/jobs/attempts.py

[源码](../../../product/backend/infrastructure/runtime/jobs/attempts.py)（443 行）。公开声明：`JobAttempts`。

### runtime/jobs/check_requests.py

[源码](../../../product/backend/infrastructure/runtime/jobs/check_requests.py)（104 行）。公开声明：`CheckRequestStore`。

### runtime/jobs/dispatch.py

[源码](../../../product/backend/infrastructure/runtime/jobs/dispatch.py)（157 行）。公开声明：`WorkerDispatcher`。

### runtime/jobs/events.py

[源码](../../../product/backend/infrastructure/runtime/jobs/events.py)（37 行）。公开声明：`append_job_event`。

### runtime/jobs/factory.py

[源码](../../../product/backend/infrastructure/runtime/jobs/factory.py)（95 行）。公开声明：`WorkerHandlerFactory`。

### runtime/jobs/handlers.py

[源码](../../../product/backend/infrastructure/runtime/jobs/handlers.py)（79 行）。公开声明：`JobHandler`、`JobHandlerRegistry`。

### runtime/jobs/lookup.py

[源码](../../../product/backend/infrastructure/runtime/jobs/lookup.py)（10 行）。公开声明：`require_job`。

### runtime/jobs/models.py

[源码](../../../product/backend/infrastructure/runtime/jobs/models.py)（328 行）。公开声明：`JobEventType`、`RetryableFailureCode`、`FatalFailureCode`、`RecoveryProofType`、`RecoveryOperator`、`RecoveryReasonCode`、`WorkerControlModel`、`RetryPolicy`等。

### runtime/jobs/ports.py

[源码](../../../product/backend/infrastructure/runtime/jobs/ports.py)（61 行）。公开声明：`JobAttemptPort`。

### runtime/jobs/queue.py

[源码](../../../product/backend/infrastructure/runtime/jobs/queue.py)（293 行）。公开声明：`JobQueue`。

### runtime/jobs/recording.py

[源码](../../../product/backend/infrastructure/runtime/jobs/recording.py)（408 行）。公开声明：`RecordingSubmissionPort`、`RecordingJobHandler`、`RecordingJobTargetHandler`。

### runtime/jobs/recovery.py

[源码](../../../product/backend/infrastructure/runtime/jobs/recovery.py)（203 行）。公开声明：`JobRecovery`。

### runtime/jobs/registration.py

[源码](../../../product/backend/infrastructure/runtime/jobs/registration.py)（32 行）。公开声明：`recording_job_targets`、`current_check_and_recording_targets`、`runtime_load_targets`。

### runtime/jobs/targets.py

[源码](../../../product/backend/infrastructure/runtime/jobs/targets.py)（280 行）。公开声明：`JobTargetType`、`JobTargetOutcome`、`JobTargetHandler`、`JobTargetRegistry`、`RunJobTargetHandler`、`CheckJobTargetHandler`、`ProofPreflightTargetHandler`、`ReferenceCaptureTargetHandler`等。

## runtime/process

### runtime/process/__init__.py

[源码](../../../product/backend/infrastructure/runtime/process/__init__.py)（32 行）。公开声明：包、内部机制或样式。

### runtime/process/control.py

[源码](../../../product/backend/infrastructure/runtime/process/control.py)（156 行）。公开声明：`force_terminate_process_tree`、`AttemptProcessControl`。

### runtime/process/environment.py

[源码](../../../product/backend/infrastructure/runtime/process/environment.py)（585 行）。公开声明：`ProcessEnvironmentRole`、`process_environment_failure_summary`、`minimal_process_environment`、`confirmed_python_executable`、`python_module_command`、`spawn_python_module`、`run_python_module`。

### runtime/process/exclusive_file.py

[源码](../../../product/backend/infrastructure/runtime/process/exclusive_file.py)（27 行）。公开声明：`open_exclusive_record_file`。

### runtime/process/listeners.py

[源码](../../../product/backend/infrastructure/runtime/process/listeners.py)（39 行）。公开声明：`ipv4_listeners`。

### runtime/process/lock.py

[源码](../../../product/backend/infrastructure/runtime/process/lock.py)（59 行）。公开声明：`try_lock_stream`、`unlock_stream`、`lock_is_available`。

### runtime/process/tree.py

[源码](../../../product/backend/infrastructure/runtime/process/tree.py)（463 行）。公开声明：`ProcessTreeController`、`spawn_managed_process`、`controller_for`、`release_process_tree`、`terminate_process_tree`、`process_tree_has_exited`、`kernel_tree_has_exited`、`kernel_process_created_at`。

## runtime/process/controlled

### runtime/process/controlled/__init__.py

[源码](../../../product/backend/infrastructure/runtime/process/controlled/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### runtime/process/controlled/artifact.py

[源码](../../../product/backend/infrastructure/runtime/process/controlled/artifact.py)（157 行）。公开声明：`inspect_runtime_files`、`create_runtime_artifact`、`create_node_runtime_artifact`、`execution_files`、`verify_runtime_artifact`、`read_runtime_manifest`、`python_runtime_files`。

### runtime/process/controlled/bootstrap.py

[源码](../../../product/backend/infrastructure/runtime/process/controlled/bootstrap.py)（41 行）。公开声明：`main`。

### runtime/process/controlled/correspondence.py

[源码](../../../product/backend/infrastructure/runtime/process/controlled/correspondence.py)（41 行）。公开声明：`runtime_artifact_store`、`runtime_corresponds`。

### runtime/process/controlled/database_capture.mjs

[源码](../../../product/backend/infrastructure/runtime/process/controlled/database_capture.mjs)（142 行）。公开声明：`instrumentMysqlPromise`、`instrumentPgClient`、`instrumentPgPool`。

### runtime/process/controlled/identity.py

[源码](../../../product/backend/infrastructure/runtime/process/controlled/identity.py)（346 行）。公开声明：`python_environment_report`、`require_python_environment`。

### runtime/process/controlled/node_locator.py

[源码](../../../product/backend/infrastructure/runtime/process/controlled/node_locator.py)（38 行）。公开声明：`controlled_node_executable`。

### runtime/process/controlled/node_owned.py

[源码](../../../product/backend/infrastructure/runtime/process/controlled/node_owned.py)（199 行）。公开声明：`node_artifact_store`、`read_node_manifest`、`node_execution_identity`、`node_executor_fingerprint`、`node_reference_matches`、`node_process_alive`、`node_corresponds`、`OwnedNodeProcess`等。

### runtime/process/controlled/node_target.mjs

[源码](../../../product/backend/infrastructure/runtime/process/controlled/node_target.mjs)（424 行）。公开声明：`openCollection`。

### runtime/process/controlled/npm.py

[源码](../../../product/backend/infrastructure/runtime/process/controlled/npm.py)（189 行）。公开声明：`npm_plan`、`dependency_files`、`prepare_dependencies`、`execution_fingerprint`、`verify_dependencies`。

### runtime/process/controlled/sqlite_capture.mjs

[源码](../../../product/backend/infrastructure/runtime/process/controlled/sqlite_capture.mjs)（86 行）。公开声明：`instrumentDatabase`。

### runtime/process/controlled/sqlite_capture.py

[源码](../../../product/backend/infrastructure/runtime/process/controlled/sqlite_capture.py)（59 行）。公开声明：`prepare_sqlite_copies`。

### runtime/process/controlled/target.py

[源码](../../../product/backend/infrastructure/runtime/process/controlled/target.py)（41 行）。公开声明：`main`。

## runtime/process/records

### runtime/process/records/__init__.py

[源码](../../../product/backend/infrastructure/runtime/process/records/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### runtime/process/records/record_capabilities.py

[源码](../../../product/backend/infrastructure/runtime/process/records/record_capabilities.py)（44 行）。公开声明：`save_record_capability`、`read_record_capability`、`discard_record_capability`。

### runtime/process/records/record_server.py

[源码](../../../product/backend/infrastructure/runtime/process/records/record_server.py)（188 行）。公开声明：`record_store_path`、`record_provider_fingerprint`、`OwnedRecordServer`。

## runtime/proof_runner

### runtime/proof_runner/__init__.py

[源码](../../../product/backend/infrastructure/runtime/proof_runner/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### runtime/proof_runner/__main__.py

[源码](../../../product/backend/infrastructure/runtime/proof_runner/__main__.py)（42 行）。公开声明：`main`。

### runtime/proof_runner/executor.py

[源码](../../../product/backend/infrastructure/runtime/proof_runner/executor.py)（112 行）。公开声明：`execute_preflight`。

### runtime/proof_runner/supervisor.py

[源码](../../../product/backend/infrastructure/runtime/proof_runner/supervisor.py)（92 行）。公开声明：`ProofPreflightHandler`。

## runtime/trial_runner

### runtime/trial_runner/__init__.py

[源码](../../../product/backend/infrastructure/runtime/trial_runner/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### runtime/trial_runner/__main__.py

[源码](../../../product/backend/infrastructure/runtime/trial_runner/__main__.py)（33 行）。公开声明：`main`。

### runtime/trial_runner/executor.py

[源码](../../../product/backend/infrastructure/runtime/trial_runner/executor.py)（74 行）。公开声明：`execute_trial`。

### runtime/trial_runner/supervisor.py

[源码](../../../product/backend/infrastructure/runtime/trial_runner/supervisor.py)（80 行）。公开声明：`FlowTrialHandler`。

## runtime/worker

### runtime/worker/__init__.py

[源码](../../../product/backend/infrastructure/runtime/worker/__init__.py)（20 行）。公开声明：包、内部机制或样式。

### runtime/worker/lifetime.py

[源码](../../../product/backend/infrastructure/runtime/worker/lifetime.py)（162 行）。公开声明：`worker_lifetime_path`、`worker_tree_identity_path`、`worker_tree_name`、`write_worker_tree_identity`、`WorkerLifetimeLock`。

### runtime/worker/runtime_supervisor.py

[源码](../../../product/backend/infrastructure/runtime/worker/runtime_supervisor.py)（172 行）。公开声明：`LocalRuntimeSupervisor`。

### runtime/worker/supervisor.py

[源码](../../../product/backend/infrastructure/runtime/worker/supervisor.py)（560 行）。公开声明：`LocalWorkerSupervisor`。

## samples

### samples/__init__.py

[源码](../../../product/backend/infrastructure/samples/__init__.py)（13 行）。公开声明：包、内部机制或样式。

### samples/gallery_login.py

[源码](../../../product/backend/infrastructure/samples/gallery_login.py)（62 行）。公开声明：`GalleryLoginAdapter`、`main`。

## samples/official

### samples/official/__init__.py

[源码](../../../product/backend/infrastructure/samples/official/__init__.py)（5 行）。公开声明：包、内部机制或样式。

### samples/official/artifacts.py

[源码](../../../product/backend/infrastructure/samples/official/artifacts.py)（241 行）。公开声明：包、内部机制或样式。

### samples/official/installation.py

[源码](../../../product/backend/infrastructure/samples/official/installation.py)（115 行）。公开声明：包、内部机制或样式。

### samples/official/manager.py

[源码](../../../product/backend/infrastructure/samples/official/manager.py)（482 行）。公开声明：`OfficialSampleManager`。

### samples/official/models.py

[源码](../../../product/backend/infrastructure/samples/official/models.py)（64 行）。公开声明：`OfficialSampleInstallation`、`OfficialSampleRuntime`。

## secrets

### secrets/__init__.py

[源码](../../../product/backend/infrastructure/secrets/__init__.py)（26 行）。公开声明：`default_secret_store`。

### secrets/refs.py

[源码](../../../product/backend/infrastructure/secrets/refs.py)（42 行）。公开声明：`credential_ref`、`validate_credential_secret_ref`。

### secrets/session.py

[源码](../../../product/backend/infrastructure/secrets/session.py)（112 行）。公开声明：`EphemeralSecretStore`。

### secrets/store.py

[源码](../../../product/backend/infrastructure/secrets/store.py)（39 行）。公开声明：`SecretStore`、`UnavailableSecretStore`。

### secrets/windows.py

[源码](../../../product/backend/infrastructure/secrets/windows.py)（117 行）。公开声明：`WindowsCredentialManagerSecretStore`。

## storage

### storage/__init__.py

[源码](../../../product/backend/infrastructure/storage/__init__.py)（28 行）。公开声明：包、内部机制或样式。

### storage/base.py

[源码](../../../product/backend/infrastructure/storage/base.py)（136 行）。公开声明：`Base`、`StorageRecord`、`ensure_storage_payload_safe`、`acquire_write_lock`。

### storage/db.py

[源码](../../../product/backend/infrastructure/storage/db.py)（179 行）。公开声明：`default_database_path`、`configure_sqlite_engine`、`create_sqlite_engine`、`create_session_factory`、`prepare_database`、`require_current_database`。

### storage/orm_registry.py

[源码](../../../product/backend/infrastructure/storage/orm_registry.py)（55 行）。公开声明：`load_storage_orm_mappings`。

### storage/schema.py

[源码](../../../product/backend/infrastructure/storage/schema.py)（77 行）。公开声明：`sqlite_schema_signature`、`normalize_table_sql`、`normalize_sql`。

### storage/unit_of_work.py

[源码](../../../product/backend/infrastructure/storage/unit_of_work.py)（226 行）。公开声明：`StorageUnitOfWork`。

### storage/workspace.py

[源码](../../../product/backend/infrastructure/storage/workspace.py)（93 行）。公开声明：`WorkspaceRevision`、`WorkspaceSchemaRow`、`current_schema_signature`、`current_schema_digest`、`workspace_matches`、`require_workspace`。

## storage/applications

### storage/applications/__init__.py

[源码](../../../product/backend/infrastructure/storage/applications/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### storage/applications/api_sources.py

[源码](../../../product/backend/infrastructure/storage/applications/api_sources.py)（98 行）。公开声明：`ApiSourceRow`、`SourceAnnotationRow`、`ApiImportRow`、`ApiSourceRepository`。

### storage/applications/application_understanding.py

[源码](../../../product/backend/infrastructure/storage/applications/application_understanding.py)（210 行）。公开声明：`ApplicationUnderstandingRow`、`ApplicationUnderstandingRepository`。

### storage/applications/environments.py

[源码](../../../product/backend/infrastructure/storage/applications/environments.py)（54 行）。公开声明：`EnvironmentRow`、`EnvironmentRepository`。

### storage/applications/projects.py

[源码](../../../product/backend/infrastructure/storage/applications/projects.py)（156 行）。公开声明：`ProjectRow`、`ProjectRecord`、`ProjectRepository`。

## storage/boundaries

### storage/boundaries/__init__.py

[源码](../../../product/backend/infrastructure/storage/boundaries/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### storage/boundaries/business_boundaries.py

[源码](../../../product/backend/infrastructure/storage/boundaries/business_boundaries.py)（434 行）。公开声明：`BusinessActorRevisionRow`、`BusinessActorRow`、`BusinessActionRevisionRow`、`BusinessActionRow`、`BoundaryProposalRow`、`BoundaryProposalDecisionRow`、`ActorImplementationBindingRow`、`ActionImplementationBindingRow`等。

### storage/boundaries/permission_intents.py

[源码](../../../product/backend/infrastructure/storage/boundaries/permission_intents.py)（177 行）。公开声明：`PermissionIntentRevisionRow`、`ProjectPolicyStateRow`、`PermissionIntentRepository`。

### storage/boundaries/rule_candidates.py

[源码](../../../product/backend/infrastructure/storage/boundaries/rule_candidates.py)（214 行）。公开声明：`RuleCandidateRow`、`RuleCandidateRevisionRow`、`RuleCandidateVisibilityRow`、`RuleCandidateProposalRow`、`RuleCandidateReceiptRow`、`RuleCandidateDecisionRow`、`RuleCandidateApprovalMappingRow`、`RuleCandidateRepository`。

## storage/changes

### storage/changes/__init__.py

[源码](../../../product/backend/infrastructure/storage/changes/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### storage/changes/code_observations.py

[源码](../../../product/backend/infrastructure/storage/changes/code_observations.py)（82 行）。公开声明：`CodeObservationRow`、`ChangeCodeObservationRow`、`RunCodeObservationRow`、`CodeObservationRepository`。

### storage/changes/development.py

[源码](../../../product/backend/infrastructure/storage/changes/development.py)（214 行）。公开声明：`DevelopmentTaskRow`、`DevelopmentContextRow`、`DevelopmentAcceptanceRow`、`DevelopmentDeliveryRow`、`DevelopmentReceiptRow`、`DevelopmentCheckRunRow`、`DevelopmentRepository`。

### storage/changes/source_changes.py

[源码](../../../product/backend/infrastructure/storage/changes/source_changes.py)（428 行）。公开声明：`SourceRevisionSnapshotRow`、`ChangeManifestRow`、`SourceChangeSetRow`、`ChangeImpactAssessmentRow`、`RuleChangeTargetRow`、`SourceChangeRepository`。

## storage/execution

### storage/execution/__init__.py

[源码](../../../product/backend/infrastructure/storage/execution/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### storage/execution/check_routines.py

[源码](../../../product/backend/infrastructure/storage/execution/check_routines.py)（40 行）。公开声明：`CheckRoutineRow`、`CheckRoutineRepository`。

### storage/execution/job_control.py

[源码](../../../product/backend/infrastructure/storage/execution/job_control.py)（597 行）。公开声明：`JobControlRepository`。

### storage/execution/jobs.py

[源码](../../../product/backend/infrastructure/storage/execution/jobs.py)（614 行）。公开声明：`JobRow`、`JobEventRow`、`QueueCapacity`、`JobRecord`、`JobEventRecord`、`JobRepository`、`JobEventRepository`。

### storage/execution/routine_revisions.py

[源码](../../../product/backend/infrastructure/storage/execution/routine_revisions.py)（129 行）。公开声明：`RoutineRevisionRow`、`RoutineBindingRow`、`RoutineRevisionRepository`。

### storage/execution/runs.py

[源码](../../../product/backend/infrastructure/storage/execution/runs.py)（257 行）。公开声明：`RunRow`、`RunRecord`、`RunRepository`。

## storage/preparation

### storage/preparation/__init__.py

[源码](../../../product/backend/infrastructure/storage/preparation/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### storage/preparation/action_preparation.py

[源码](../../../product/backend/infrastructure/storage/preparation/action_preparation.py)（286 行）。公开声明：`ActionExecutionBindingRow`、`ActionResourceBindingRow`、`ActionEvidenceBindingRow`、`ActionRecoveryBindingRow`、`ActionAllowControlBindingRow`、`ActionPreparationRepository`、`RuleCaseDataRow`。

### storage/preparation/batches.py

[源码](../../../product/backend/infrastructure/storage/preparation/batches.py)（59 行）。公开声明：`PreparationBatchRow`、`PreparationBatchRepository`。

### storage/preparation/business_scenarios.py

[源码](../../../product/backend/infrastructure/storage/preparation/business_scenarios.py)（78 行）。公开声明：`BusinessScenarioRow`、`BusinessScenarioRepository`。

### storage/preparation/flow_trials.py

[源码](../../../product/backend/infrastructure/storage/preparation/flow_trials.py)（48 行）。公开声明：`FlowTrialRow`、`FlowTrialRepository`。

### storage/preparation/identity_preparations.py

[源码](../../../product/backend/infrastructure/storage/preparation/identity_preparations.py)（71 行）。公开声明：`IdentityPreparationRow`、`IdentityPreparationRepository`。

### storage/preparation/operation_flows.py

[源码](../../../product/backend/infrastructure/storage/preparation/operation_flows.py)（52 行）。公开声明：`OperationFlowRow`、`OperationFlowRepository`。

### storage/preparation/preparation_recovery.py

[源码](../../../product/backend/infrastructure/storage/preparation/preparation_recovery.py)（74 行）。公开声明：`PreparationReceiptRow`、`PreparationDraftRow`、`PreparationCandidateRecordingRow`、`PreparationRecoveryRepository`。

### storage/preparation/proof_artifacts.py

[源码](../../../product/backend/infrastructure/storage/preparation/proof_artifacts.py)（155 行）。公开声明：`ProofArtifactInputRow`、`ReferenceCaptureAuthorizationRow`、`ReferenceCaptureRow`、`ProofArtifactReferenceRow`、`ProofArtifactRepository`。

### storage/preparation/proof_sources.py

[源码](../../../product/backend/infrastructure/storage/preparation/proof_sources.py)（152 行）。公开声明：`ProofSourceRow`、`ProofSourceRevisionRow`、`ProofReadScopeRow`、`ProofPreflightRow`、`ProofSourceRepository`。

### storage/preparation/recordings.py

[源码](../../../product/backend/infrastructure/storage/preparation/recordings.py)（503 行）。公开声明：`RecordingRow`、`FlowDraftRevisionRow`、`RecordingSummary`、`RecordingRecord`、`FlowDraftRevisionRecord`、`RecordingRepository`、`FlowDraftRevisionRepository`。

### storage/preparation/suggestions.py

[源码](../../../product/backend/infrastructure/storage/preparation/suggestions.py)（85 行）。公开声明：`PreparationSuggestionRow`、`PreparationSuggestionRevisionRow`、`PreparationSuggestionReceiptRow`、`PreparationSuggestionRepository`。

### storage/preparation/supplemental_materials.py

[源码](../../../product/backend/infrastructure/storage/preparation/supplemental_materials.py)（88 行）。公开声明：`SupplementalMaterialRevisionRow`、`SupplementalMaterialReceiptRow`、`SupplementalMaterialRepository`。

### storage/preparation/test_identities.py

[源码](../../../product/backend/infrastructure/storage/preparation/test_identities.py)（252 行）。公开声明：`TestIdentityRow`、`TestIdentityCookieRow`、`TestIdentityRepository`。

## storage/results

### storage/results/__init__.py

[源码](../../../product/backend/infrastructure/storage/results/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### storage/results/check_publications.py

[源码](../../../product/backend/infrastructure/storage/results/check_publications.py)（55 行）。公开声明：`CheckPublicationRow`、`CheckPublicationRecord`、`CheckPublicationRepository`。

### storage/results/evidence.py

[源码](../../../product/backend/infrastructure/storage/results/evidence.py)（161 行）。公开声明：`EvidenceIndexRow`、`EvidenceIndexRecord`、`EvidenceIndexRepository`。

### storage/results/rule_history.py

[源码](../../../product/backend/infrastructure/storage/results/rule_history.py)（136 行）。公开声明：`RuleCheckIndexRow`、`RuleHistoryRunRow`、`RuleHistoryCoverageRow`、`RuleHistoryReceiptRow`、`RuleHistoryRepository`。

## storage/runtime

### storage/runtime/__init__.py

[源码](../../../product/backend/infrastructure/storage/runtime/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### storage/runtime/collaboration.py

[源码](../../../product/backend/infrastructure/storage/runtime/collaboration.py)（135 行）。公开声明：`CollaborationRow`、`CollaborationRepository`。

### storage/runtime/environment_operations.py

[源码](../../../product/backend/infrastructure/storage/runtime/environment_operations.py)（57 行）。公开声明：`EnvironmentOperationRow`、`EnvironmentOperationRepository`。

### storage/runtime/runtime_loads.py

[源码](../../../product/backend/infrastructure/storage/runtime/runtime_loads.py)（91 行）。公开声明：`RuntimeLoadRow`、`RuntimeLoadRepository`。

### storage/runtime/sample_workspaces.py

[源码](../../../product/backend/infrastructure/storage/runtime/sample_workspaces.py)（84 行）。公开声明：`SampleWorkspaceRow`、`SampleInstanceRow`、`SampleReconciliationRow`、`SampleWorkspaceRepository`。

## storage/settings

### storage/settings/__init__.py

[源码](../../../product/backend/infrastructure/storage/settings/__init__.py)（1 行）。公开声明：包、内部机制或样式。

### storage/settings/llm.py

[源码](../../../product/backend/infrastructure/storage/settings/llm.py)（61 行）。公开声明：`LLMProfileRow`、`AIAssistanceSettingsRow`。
