# =============================================================================
# 结果服务组合
#
# 定位
#   ApplicationCore 与 WorkerContainer 共用的结果派生服务组合根。
#
# 职责
#   按固定依赖顺序创建 publication reader、Finding、Gate、Report 和 Finalizer。
#
# 边界
#   只组合既有结果服务，不新增结果语义、持久化表或第二套 Finalizer。
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.results.findings import FindingMaterializer, FindingQueries
from product.backend.workflows.results.finalizer import ResultFinalizer
from product.backend.workflows.results.gating import RegressionGate
from product.backend.workflows.results.published import PublishedResultReader
from product.backend.workflows.results.reporting import ReportBuilder


@dataclass(frozen=True, slots=True)
class ResultServices:
    """一个组合根内唯一的结果服务实例集合。"""

    reader: PublishedResultReader
    materializer: FindingMaterializer
    queries: FindingQueries
    gate: RegressionGate
    reports: ReportBuilder
    finalizer: ResultFinalizer


def build_result_services(
    var_dir: Path,
    uow_factory: Callable[..., StorageUnitOfWork],
    clock_us: Callable[[], int] | None = None,
) -> ResultServices:
    """按 reader→materializer→queries→gate→reports→finalizer 顺序完成装配。"""

    reader = PublishedResultReader(var_dir, uow_factory)
    materializer = FindingMaterializer(uow_factory, reader, utc_now_us=clock_us)
    queries = FindingQueries(uow_factory)
    gate = RegressionGate(uow_factory, reader, queries, clock_us=clock_us)
    reports = ReportBuilder(var_dir, reader, queries, gate, uow_factory)
    finalizer = ResultFinalizer(
        var_dir,
        uow_factory,
        reader,
        materializer,
        report_builder=reports,
        utc_now_us=clock_us,
    )
    return ResultServices(
        reader=reader,
        materializer=materializer,
        queries=queries,
        gate=gate,
        reports=reports,
        finalizer=finalizer,
    )
