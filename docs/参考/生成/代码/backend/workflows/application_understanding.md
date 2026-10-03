# 自动代码参考：backend/workflows/application_understanding

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/application_understanding/__init__.py`

[打开源码](../../../../../../product/backend/workflows/application_understanding/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/application_understanding/analysis/__init__.py`

[打开源码](../../../../../../product/backend/workflows/application_understanding/analysis/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`.analyzer`、`.models`

### `product/backend/workflows/application_understanding/analysis/analyzer.py`

[打开源码](../../../../../../product/backend/workflows/application_understanding/analysis/analyzer.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ApplicationUnderstandingAnalyzer`
- `ApplicationUnderstandingAnalyzer.analyze(self, project_id, source_root) -> ApplicationAnalysisResult`

静态import / dot-source：`.javascript`、`.models`、`.openapi`、`.python`、`__future__`、`collections.abc`、`hashlib`、`os`、`pathlib`、`product.backend.core.applications.models`、`product.backend.core.changes.models`、`product.backend.core.errors`、`product.backend.workflows.onboarding.discovery`、`re`

### `product/backend/workflows/application_understanding/analysis/javascript.py`

[打开源码](../../../../../../product/backend/workflows/application_understanding/analysis/javascript.py) · Python AST；作用域内import不表示每次调用均执行。

- `class JavaScriptAnalysisMixin`

静态import / dot-source：`.models`、`__future__`、`product.backend.core.applications.models`、`product.backend.core.http_routes`

### `product/backend/workflows/application_understanding/analysis/models.py`

[打开源码](../../../../../../product/backend/workflows/application_understanding/analysis/models.py) · Python AST；作用域内import不表示每次调用均执行。

- `_IGNORED_DIRECTORIES`
- `_SOURCE_SUFFIXES`
- `_OPENAPI_NAMES`
- `_SENSITIVE_FILE`
- `_ROLE_CONTEXT`
- `_ROLE_CLASS`
- `_ROLE_GUARD`
- `_JS_ROLE_STRUCTURE`
- `_JS_STRING`
- `_JS_ROUTE`
- `_JS_REQUEST`
- `_FETCH_REQUEST`
- `_CONFIDENCE_RANK`
- `_METHOD_LABEL`
- `class AnalysisModel`
- `class SourceAnalysisLimits`
- `class ApplicationAnalysisResult`

静态import / dot-source：`__future__`、`ast`、`collections.abc`、`hashlib`、`json`、`os`、`pathlib`、`product.backend.core.applications.models`、`product.backend.core.changes.models`、`product.backend.core.errors`、`product.backend.core.http_routes`、`product.backend.workflows.onboarding.discovery`、`pydantic`、`re`、`yaml`

### `product/backend/workflows/application_understanding/analysis/openapi.py`

[打开源码](../../../../../../product/backend/workflows/application_understanding/analysis/openapi.py) · Python AST；作用域内import不表示每次调用均执行。

- `class OpenApiAnalysisMixin`

静态import / dot-source：`.models`、`__future__`、`collections.abc`、`json`、`product.backend.core.applications.models`、`product.backend.core.http_routes`、`product.backend.workflows.onboarding.discovery`、`yaml`

### `product/backend/workflows/application_understanding/analysis/python.py`

[打开源码](../../../../../../product/backend/workflows/application_understanding/analysis/python.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PythonAnalysisMixin`

静态import / dot-source：`.models`、`__future__`、`ast`、`product.backend.core.applications.models`、`product.backend.core.http_routes`

### `product/backend/workflows/application_understanding/endpoints.py`

[打开源码](../../../../../../product/backend/workflows/application_understanding/endpoints.py) · Python AST；作用域内import不表示每次调用均执行。

- `_CONFIG_NAMES`
- `_IGNORED_DIRECTORIES`
- `_URL_LITERAL`
- `_PORT_LITERAL`
- `_COMMAND_PORT`
- `_SOURCE_RANK`
- `_FRAMEWORK_DEFAULTS`
- `class EndpointModel`
- `class EndpointDiscoveryLimits`
- `class EndpointProbeObservation`
- `class EndpointCandidate`
- `class EndpointDiscoveryResult`
- `normalize_loopback_endpoint(value) -> str`
- `class TargetEndpointDiscovery`
- `TargetEndpointDiscovery.discover(self, source_root) -> EndpointDiscoveryResult`
- `TargetEndpointDiscovery.source_fingerprint(self, source_root) -> str`
- `TargetEndpointDiscovery.probe(self, endpoint) -> tuple[str, EndpointProbeObservation]`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`http.client`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.workflows.onboarding.discovery`、`pydantic`、`re`、`socket`、`typing`、`urllib.parse`、`yaml`

### `product/backend/workflows/application_understanding/service.py`

[打开源码](../../../../../../product/backend/workflows/application_understanding/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ApplicationConnectionView`
- `class ApplicationUnderstandingService`
- `ApplicationUnderstandingService.set_permission_binding_refresher(self, refresher) -> None`
- `ApplicationUnderstandingService.connect(self, source_root, project_name) -> ApplicationConnectionView`
- `ApplicationUnderstandingService.get(self, project_id) -> ApplicationUnderstanding`
- `ApplicationUnderstandingService.discover_endpoints(self, project_id) -> EndpointDiscoveryResult`
- `ApplicationUnderstandingService.confirm_endpoint(self, project_id, endpoint, revision) -> ApplicationUnderstanding`
- `ApplicationUnderstandingService.endpoint_status(self, record) -> Literal['NEEDS_CONFIRMATION', 'CONFIRMED', 'UNAVAILABLE']`
- `ApplicationUnderstandingService.authorize_source_analysis(self, project_id, revision, for_controlled_start) -> ApplicationUnderstanding`
- `ApplicationUnderstandingService.analyze_source(self, project_id, revision) -> ApplicationUnderstanding`
- `ApplicationUnderstandingService.analyze_source_for_change(self, project_id, revision) -> ApplicationUnderstanding`
- `ApplicationUnderstandingService.inspect_source_fingerprint(self, project_id) -> str`
- `ApplicationUnderstandingService.scan_source(self, project_id, revision)`
- `ApplicationUnderstandingService.apply_source_analysis(self, work, before, result) -> ApplicationUnderstanding`
- `ApplicationUnderstandingService.decide_role(self, project_id, candidate_id_value, revision, decision, display_name) -> ApplicationUnderstanding`
- `ApplicationUnderstandingService.decide_action(self, project_id, candidate_id_value, revision, decision, display_name) -> ApplicationUnderstanding`
- `ApplicationUnderstandingService.decide_candidates(self, project_id, revision, decisions) -> ApplicationUnderstanding`
- `ApplicationUnderstandingService.add_manual_role(self, project_id, revision, display_name) -> ApplicationUnderstanding`
- `ApplicationUnderstandingService.add_manual_action(self, project_id, revision, display_name, risk_hint) -> ApplicationUnderstanding`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`os`、`pathlib`、`product.backend.core.applications.models`、`product.backend.core.changes.models`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.storage`、`product.backend.workflows.application_understanding.analysis.analyzer`、`product.backend.workflows.application_understanding.endpoints`、`product.backend.workflows.onboarding.discovery`、`product.backend.workflows.onboarding.models`、`product.protocols`、`pydantic`、`re`、`time`、`typing`

<!-- GENERATED:END -->
