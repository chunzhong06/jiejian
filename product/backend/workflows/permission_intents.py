# PermissionIntent v2 只读查询；正式写入只允许 BusinessBoundaryService 的 Proposal approval 事务。

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import PermissionIntentRevision
from product.backend.infra.storage import StorageUnitOfWork


class PermissionIntentViewModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class PermissionIntentCellStatus(StrEnum):
    CURRENT = "CURRENT"
    UNAVAILABLE = "UNAVAILABLE"


class PermissionIntentCellView(PermissionIntentViewModel):
    revision: PermissionIntentRevision
    status: PermissionIntentCellStatus = PermissionIntentCellStatus.CURRENT


class PermissionIntentActionView(PermissionIntentViewModel):
    action_id: str
    action_revision: int = Field(ge=1)
    intents: tuple[PermissionIntentCellView, ...] = ()


class PermissionIntentMatrixView(PermissionIntentViewModel):
    project_id: str
    policy_epoch: int = Field(ge=0)
    actions: tuple[PermissionIntentActionView, ...] = ()


class PermissionIntentHistoryView(PermissionIntentViewModel):
    project_id: str
    intent_id: str
    revisions: tuple[PermissionIntentRevision, ...] = Field(max_length=4096)


class PermissionIntentService:
    """提供 v2 revision/history 读取；没有 confirm/proposal/rebind 写方法。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        **_: object,
    ) -> None:
        self._uow_factory = uow_factory

    def current_intents(self, project_id: str) -> tuple[PermissionIntentRevision, ...]:
        with self._uow_factory() as work:
            return work.permission_intents.list_latest(project_id)

    def history(self, project_id: str, intent_id: str) -> PermissionIntentHistoryView:
        with self._uow_factory() as work:
            revisions = tuple(
                item
                for item in work.permission_intents.list_history(project_id)
                if item.intent_id == intent_id
            )
        if not revisions:
            raise JiejianError(ErrorCode.BOUNDARY_PROPOSAL_REFERENCE_INVALID, "权限 revision 不存在")
        return PermissionIntentHistoryView(
            project_id=project_id,
            intent_id=intent_id,
            revisions=revisions,
        )

    def matrix(self, project_id: str) -> PermissionIntentMatrixView:
        with self._uow_factory() as work:
            intents = work.permission_intents.list_latest(project_id)
            state = work.permission_intents.policy_state(project_id)
        grouped: dict[tuple[str, int], list[PermissionIntentRevision]] = {}
        for intent in intents:
            grouped.setdefault((intent.business_action_id, intent.action_revision), []).append(intent)
        return PermissionIntentMatrixView(
            project_id=project_id,
            policy_epoch=0 if state is None else state.policy_epoch,
            actions=tuple(
                PermissionIntentActionView(
                    action_id=action_id,
                    action_revision=revision,
                    intents=tuple(PermissionIntentCellView(revision=item) for item in values),
                )
                for (action_id, revision), values in sorted(grouped.items())
            ),
        )

    def policy_snapshot(self, project_id: str):
        raise JiejianError(
            ErrorCode.STATE_PRECONDITION,
            "当前尚不支持根据业务边界权限运行检查",
            details={"project_id": project_id},
        )


def _required_confirmation_count(_: PermissionIntentMatrixView) -> int:
    return 0


__all__ = [
    "PermissionIntentActionView", "PermissionIntentCellStatus", "PermissionIntentCellView",
    "PermissionIntentHistoryView", "PermissionIntentMatrixView", "PermissionIntentService",
    "_required_confirmation_count",
]
