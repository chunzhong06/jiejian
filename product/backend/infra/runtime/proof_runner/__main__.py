# 固定Runner入口仅接受本次Job尝试目录，读取数据库授权后执行有界GET，并保存无原始响应的报告。
import argparse
import os
from pathlib import Path
from functools import partial

from product.backend.infra.artifacts.checks.check_packages import read_check_bytes, reject_check_links
from product.backend.infra.storage import StorageUnitOfWork, create_session_factory, create_sqlite_engine, default_database_path
from product.backend.infra.storage.db import require_current_database
from product.backend.infra.runtime.proof_runner.executor import execute_preflight
from product.protocols.preparation.proof_sources import ProofRunnerInput, proof_bytes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    arguments = parser.parse_args()
    var_dir = Path(os.environ['JIEJIAN_VAR_DIR']).resolve()
    input = ProofRunnerInput.model_validate_json(read_check_bytes(arguments.input))
    # 使用统一RuntimePaths路径，拒绝任意输入位置以及链接重定向。
    from product.backend.infra.runtime.paths import RuntimePaths
    directory = RuntimePaths(var_dir).jobs / input.job_id / 'attempts' / f'{input.attempt}-{input.fencing_token}'
    reject_check_links(var_dir, directory)
    if arguments.input.absolute() != directory / 'proof-input.json':
        return 1
    require_current_database(default_database_path(var_dir))
    engine = create_sqlite_engine(default_database_path(var_dir))
    try:
        report = execute_preflight(input, var_dir=var_dir,
            uow_factory=partial(StorageUnitOfWork, create_session_factory(engine)), environ=os.environ,
            cancellation_requested=lambda: (directory / 'cancel.requested').exists())
        with (directory / 'proof-report.json').open('xb') as stream:
            stream.write(proof_bytes(report))
            stream.flush()
            os.fsync(stream.fileno())
        return 0
    finally:
        engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
