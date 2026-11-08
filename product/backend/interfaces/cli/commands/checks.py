"""无模型检查命令；准确方案引用、原请求恢复和退出码共享正式产品事实。"""
import re

import typer
from pydantic import ValidationError

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.interfaces.cli.check_client import CheckClient, execution_exit
from product.backend.interfaces.cli.presentation import emit_command, fail
from product.protocols.checks.routine_reference import RoutineReference


checks_group = typer.Typer(help='通过当前本机服务运行已批准的准确检查方案', no_args_is_help=True)


def _reference(plan, revision, binding):
    try:
        return RoutineReference(routine_id=plan, revision=revision, binding_id=binding)
    except ValidationError as exc:
        raise JiejianError(ErrorCode.INPUT_INVALID, '请提供准确的方案ID、修订和环境绑定ID') from exc


def _fingerprint(value):
    if not re.fullmatch(r'[0-9a-f]{64}', value):
        raise JiejianError(ErrorCode.INPUT_INVALID, '预览指纹必须为64位小写十六进制')
    return value


def _request_id(value):
    if not re.fullmatch(r'[0-9a-f]{32}', value):
        raise JiejianError(ErrorCode.INPUT_INVALID, '请求标识必须为32位小写十六进制；重试沿用原标识')
    return value


@checks_group.command('preview')
def preview(project: str = typer.Option(...), plan: str = typer.Option(...), revision: int = typer.Option(..., min=1),
    binding: str = typer.Option(...), endpoint: str = typer.Option('http://127.0.0.1:8765')):
    """只读预览准确方案；未就绪退出3，不执行或自动补充授权。"""
    try:
        reference = _reference(plan, revision, binding)
        with CheckClient(endpoint) as client:
            result = client.preview(project, reference)
        emit_command('check-preview', result)
        if not result['can_execute']:
            raise typer.Exit(3)
    except JiejianError as exc:
        fail(exc)


@checks_group.command('run')
def run(project: str = typer.Option(...), plan: str = typer.Option(...), revision: int = typer.Option(..., min=1),
    binding: str = typer.Option(...), fingerprint: str = typer.Option(...), request_id: str = typer.Option(...),
    endpoint: str = typer.Option('http://127.0.0.1:8765')):
    """仅提交已预览的准确范围；异步回执成功不代表检查通过。"""
    try:
        reference = _reference(plan, revision, binding)
        _fingerprint(fingerprint)
        _request_id(request_id)
        with CheckClient(endpoint) as client:
            result = client.run(project, reference, fingerprint, request_id)
        emit_command('check-submitted', {**result, 'request_id':request_id, 'routine':reference.model_dump(mode='json')})
    except JiejianError as exc:
        fail(exc)


@checks_group.command('request')
def request(project: str = typer.Option(...), plan: str = typer.Option(...), revision: int = typer.Option(..., min=1),
    binding: str = typer.Option(...), fingerprint: str = typer.Option(...), request_id: str = typer.Option(...),
    endpoint: str = typer.Option('http://127.0.0.1:8765')):
    """只读查询原运行提交；未查到退出6，不自动重发。"""
    try:
        reference = _reference(plan, revision, binding)
        _fingerprint(fingerprint)
        _request_id(request_id)
        with CheckClient(endpoint) as client:
            result = client.receipt(project, reference, fingerprint, request_id)
        emit_command('check-request', {'request_id':request_id, 'receipt':result})
        if result is None:
            raise typer.Exit(6)
    except JiejianError as exc:
        fail(exc)


@checks_group.command('execute')
def execute(project: str = typer.Option(...), plan: str = typer.Option(...), revision: int = typer.Option(..., min=1),
    binding: str = typer.Option(...), fingerprint: str = typer.Option(...), request_id: str = typer.Option(...),
    timeout: float = typer.Option(600, min=0, max=86400), endpoint: str = typer.Option('http://127.0.0.1:8765')):
    """CI路径：提交已批准指纹并等待；先查原回执，不需要模型或界面点击。"""
    try:
        reference = _reference(plan, revision, binding)
        _fingerprint(fingerprint)
        _request_id(request_id)
        with CheckClient(endpoint) as client:
            previous = client.receipt(project, reference, fingerprint, request_id)
            if previous is None:
                submitted = client.run(project, reference, fingerprint, request_id)
                run_id = submitted['run']['run_id']
            else:
                run_id = previous['run']['run_id']
            result, timed_out = client.wait(project, run_id, timeout=timeout)
        emit_command('check-execution', {**result, 'request_id':request_id, 'wait_timed_out':timed_out})
        raise typer.Exit(execution_exit(result))
    except JiejianError as exc:
        fail(exc)


@checks_group.command('status')
def status(project: str = typer.Option(...), run_id: str = typer.Option(...),
    endpoint: str = typer.Option('http://127.0.0.1:8765')):
    """读取生命周期、正式结论和发布完整性；退出码表达当前事实。"""
    _observe('status', project, run_id, endpoint)


@checks_group.command('wait')
def wait(project: str = typer.Option(...), run_id: str = typer.Option(...),
    timeout: float = typer.Option(600, min=0, max=86400), endpoint: str = typer.Option('http://127.0.0.1:8765')):
    """有界等待已存在的运行；超时退出6，保留原运行继续查询。"""
    _observe('wait', project, run_id, endpoint, timeout)


@checks_group.command('cancel')
def cancel(project: str = typer.Option(...), run_id: str = typer.Option(...),
    endpoint: str = typer.Option('http://127.0.0.1:8765')):
    """请求取消原运行；完成前仍报告其真实生命周期。"""
    _observe('cancel', project, run_id, endpoint)


def _observe(kind, project, run_id, endpoint, timeout=0):
    try:
        if not re.fullmatch(r'run_[0-9a-f]{32}', run_id):
            raise JiejianError(ErrorCode.INPUT_INVALID, '运行ID格式无效')
        with CheckClient(endpoint) as client:
            if kind == 'wait':
                result, timed_out = client.wait(project, run_id, timeout=timeout)
            else:
                result = client.cancel(project, run_id) if kind == 'cancel' else client.status(project, run_id)
                timed_out = False
        emit_command('check-'+kind, {**result, 'wait_timed_out':timed_out})
        raise typer.Exit(execution_exit(result))
    except JiejianError as exc:
        fail(exc)
