from __future__ import annotations

import json
from pathlib import Path

from product.backend.workflows.contracts.http_binding_candidates import (
    build_openapi_http_binding_candidates,
    build_recording_http_binding_candidates,
)
from product.protocols import (
    Flow,
    FlowStep,
    HttpBindingCandidateBatch,
    HttpBindingCandidateSource,
    HttpOutcomeClassifier,
    HttpRequestTemplate,
    JsonBody,
    ResponseExtractor,
    ResponseExtractorKind,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _openapi() -> dict:
    return {
        "openapi": "3.1.0",
        "security": [{"BearerAuth": []}],
        "paths": {
            "/projects": {
                "post": {
                    "operationId": "createProject",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string", "example": "secret-value"}
                                    },
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "headers": {"Location": {"schema": {"type": "string"}}},
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"project_id": {"type": "string"}},
                                    }
                                }
                            },
                            "links": {
                                "project": {
                                    "operationId": "getProject",
                                    "parameters": {
                                        "project_id": "$response.body#/project_id"
                                    },
                                }
                            },
                        }
                    },
                }
            },
            "/projects/{project_id}": {
                "get": {
                    "operationId": "getProject",
                    "parameters": [
                        {"name": "project_id", "in": "path", "required": True},
                        {"name": "verbose", "in": "query"},
                        {"name": "X-Trace", "in": "header"},
                    ],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"project_id": {"type": "string"}},
                                    }
                                }
                            }
                        }
                    },
                }
            },
        },
    }


def test_openapi_http_candidates_are_separate_confirmable_execution_hints() -> None:
    batch = build_openapi_http_binding_candidates(_openapi())
    create = next(item for item in batch.candidates if item.operation_id == "createProject")
    read = next(item for item in batch.candidates if item.operation_id == "getProject")
    assert create.source is HttpBindingCandidateSource.OPENAPI_LINK
    assert create.source_priority < read.source_priority
    assert {link.kind.value for link in create.producer_consumer_links} == {
        "OPENAPI_LINK",
        "LOCATION_HEADER",
    }
    assert read.path_fields == ("project_id",)
    assert read.query_fields == ("verbose",)
    assert read.header_fields == ("X-Trace",)
    assert read.security_scheme_ids == ("BearerAuth",)
    assert all(item.requires_confirmation for item in batch.candidates)
    assert "secret-value" not in batch.model_dump_json()


def test_recording_candidates_have_highest_source_priority() -> None:
    flow = Flow(
        id="recorded-flow",
        steps=(
            FlowStep(
                id="create-project",
                identity_id="owner",
                resource_id="project",
                alternate_identity_id="attacker",
                alternate_resource_id="foreign-project",
                request_template=HttpRequestTemplate(
                    method="POST",
                    path="/projects",
                    body=JsonBody(value={"name": "bounded"}),
                    response_extractors=(
                        ResponseExtractor(
                            extractor_id="project-id",
                            kind=ResponseExtractorKind.JSON_PATH,
                            json_path="$.project_id",
                        ),
                    ),
                ),
                classifier=HttpOutcomeClassifier(),
            ),
        ),
    )
    candidate = build_recording_http_binding_candidates(flow).candidates[0]
    assert candidate.source is HttpBindingCandidateSource.RECORDING
    assert candidate.source_priority == 0
    assert candidate.requires_confirmation is True


def test_checked_in_http_binding_candidate_schema_has_no_drift() -> None:
    checked_in = json.loads(
        (
            PROJECT_ROOT
            / "product"
            / "protocols"
            / "schemas"
            / "execution"
            / "http-binding-candidate.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert checked_in == HttpBindingCandidateBatch.model_json_schema()
