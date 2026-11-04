# 固定试运行入口只接受当前Job尝试目录；报告不含响应原文。
import argparse
import os
from pathlib import Path
from functools import partial
from product.backend.infrastructure.artifacts.checks.check_packages import read_check_bytes,reject_check_links
from product.backend.infrastructure.storage import StorageUnitOfWork,create_session_factory,create_sqlite_engine,default_database_path
from product.backend.infrastructure.storage.db import require_current_database
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.runtime.trial_runner.executor import execute_trial
from product.protocols.preparation.flow_trial import FlowTrialRunnerInput
from product.protocols.preparation.proof_sources import proof_bytes


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True)
    arguments=parser.parse_args();var_dir=Path(os.environ['JIEJIAN_VAR_DIR']).resolve()
    input=FlowTrialRunnerInput.model_validate_json(read_check_bytes(arguments.input),strict=True)
    directory=RuntimePaths(var_dir).jobs/input.job_id/'attempts'/f'{input.attempt}-{input.fencing_token}'
    reject_check_links(var_dir,directory)
    if arguments.input.absolute()!=directory/'trial-input.json':return 64
    require_current_database(default_database_path(var_dir));engine=create_sqlite_engine(default_database_path(var_dir))
    try:
        report=execute_trial(input,
            uow_factory=partial(StorageUnitOfWork,create_session_factory(engine)),environ=os.environ,
            cancellation_requested=lambda:(directory/'cancel.requested').exists())
        with (directory/'trial-report.json').open('xb') as stream:
            stream.write(proof_bytes(report));stream.flush();os.fsync(stream.fileno())
        return 0
    finally:engine.dispose()


if __name__=='__main__':raise SystemExit(main())
