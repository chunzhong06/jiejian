# 按可观察契约选择最小验证集合；真实目标场景始终显式选择。
from dataclasses import dataclass
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def cases(*selectors):
    result=[]
    for selector in selectors:
        matches=sorted(ROOT.glob(selector)) if "*" in selector else [ROOT/selector]
        files=[item for path in matches for item in (sorted(path.rglob("test_*.py")) if path.is_dir() else [path]) if item.is_file()]
        if not files:raise ValueError(f"验证范围没有实际测试：{selector}")
        result.extend(item.relative_to(ROOT).as_posix() for item in files)
    return tuple(dict.fromkeys(result))

@dataclass(frozen=True)
class Area:
    purpose: str
    backend: tuple[str, ...] = ()
    frontend: tuple[str, ...] = ()
    checks: tuple[str, ...] = ()
    journey: str | None = None
    source: tuple[str, ...] = ()
    backend_level: int = 2

AREAS = {
    'verification': Area('权限结论、对照、因果定位与冻结格式', cases('tests/domain/checks','tests/domain/verification','tests/contracts/protocols','tests/domain/test_errors.py','tests/domain/test_lifecycle.py','tests/domain/test_redaction.py'), source=('product/backend/domain/verification','product/protocols/checks')),
    'rules': Area('候选范围、含义、人工批准、回执与历史', cases('tests/domain/boundaries','tests/application/business_boundaries','tests/contracts/http/boundaries'), source=('product/backend/application/business_boundaries',)),
    'access': Area('本地会话、Host、Origin、MCP授权与HTTP错误', cases('tests/contracts/http/system'),source=('product/backend/interfaces/http/local_control.py',),backend_level=3),
    'preparation': Area('材料、恢复、准备投影与真实账号分配', cases('tests/domain/preparation','tests/application/preparation','tests/application/workspace','tests/contracts/http/preparation','tests/contracts/http/test_workspace.py'), ('src/app/model/useApplication.test.tsx','src/shared/lib/useRead.test.tsx','src/pages/preparation/materials/MaterialEditor.test.tsx'),source=('product/backend/application/preparation',)),
    'connection': Area('应用接入、来源理解、继续、归档与受控加载', cases('tests/application/application_understanding','tests/application/onboarding','tests/application/projects','tests/application/runtime','tests/infrastructure/test_source_identity.py','tests/contracts/http/applications'),source=('product/backend/application/application_understanding',),backend_level=3),
    'recording': Area('录制、Flow、资源、身份与秘密变量', cases('tests/domain/recording','tests/application/recording','tests/application/test_identities','tests/infrastructure/recording','tests/infrastructure/identity'),source=('product/backend/domain/recording',)),
    'checks': Area('提交、关联、结果读取与原题复验', cases('tests/application/checks','tests/application/changes','tests/application/development','tests/contracts/http/checks','tests/contracts/http/changes'), frontend=('src/pages/checks/report/Report.test.tsx',),source=('product/backend/application/checks',),backend_level=3),
    'execution': Area('受控执行、观察、任务、发布、索引和结果读取', cases('tests/infrastructure/execution','tests/infrastructure/observers','tests/infrastructure/runtime/jobs','tests/infrastructure/runtime/worker'),source=('product/backend/infrastructure/runtime','product/backend/infrastructure/artifacts'),backend_level=3),
    'runtime': Area('运行身份、精确进程边界与运行文件', cases('tests/infrastructure/runtime/process','tests/infrastructure/runtime/test_*.py'),source=('product/backend/infrastructure/runtime/process',),backend_level=3),
    'examples': Area('示例管理回执与项目隔离', cases('tests/application/examples','tests/infrastructure/samples'),backend_level=3),
    'secrets': Area('受控引用、秘密存储与补偿',cases('tests/infrastructure/secrets'),backend_level=3),
    'storage': Area('事务、完整工作区、原子初始化与未知结构拒绝', cases('tests/integration/test_transactions.py','tests/infrastructure/storage','tests/contracts/test_fixtures.py'),checks=('schema',),source=('product/backend/infrastructure/storage','product/backend/migrations'),backend_level=3),
    'maintenance': Area('清理计划、引用保护、选择与幂等回执', cases('tests/integration/test_maintenance.py'),source=('product/backend/infrastructure/maintenance',),backend_level=3),
    'lifecycle': Area('部分启动、独立停止、失败保护与释放重试', cases('tests/integration/test_lifecycle.py','tests/integration/bootstrap'),source=('product/backend/bootstrap','product/backend/interfaces/http/app.py'),backend_level=3),
    'cli': Area('产品命令、源码启动与退出契约',cases('tests/contracts/cli','tests/tooling/launch/test_startup.py'),source=('product/backend/interfaces/cli','scripts/startup'),backend_level=3),
    'navigation': Area('面包屑、路由模块与迟到请求', frontend=('src/app/Navigation.test.tsx','src/app/routePage.test.tsx','src/shared/lib/useRead.test.tsx')),
    'controls': Area('键盘、焦点、忙碌与可见操作', frontend=('src/shared/ui/controls.test.tsx','src/shared/api/http.test.ts','src/entities/check/model/checks.test.ts')),
    'appearance': Area('字体、快速切换与减少动效', frontend=('src/app/model/font.test.ts','src/shared/ui/PageSurface.test.tsx')),
    'architecture': Area('领域、入口、只读结果与共享层的依赖',cases('tests/architecture','tests/contracts/test_current.py'),backend_level=1),
    'documentation': Area('本地链接、锚点、任务路由、源码路径和生成参考',cases('tests/tooling/test_documentation.py'),checks=('docs',),source=('scripts/docs',)),
    'tooling': Area('工程准备、发行组装、验证选择、等待与失败停止',cases('tests/tooling/launch/test_development.py','tests/tooling/launch/test_distribution.py','tests/tooling/test_verification_plan.py','tests/tooling/test_runtime_support.py','tests/tooling/test_reporting.py'),source=('scripts/dev','scripts/lib','scripts/build','scripts/editor','scripts/quality','tests/support'),backend_level=3),
    'journey': Area('独立官方示例：材料、检查与报告',journey='baseline'),
    'repair': Area('独立官方示例：原问题、正常功能与复验',journey='repair'),
}

def plan(areas: list[str],level: int=4) -> tuple[tuple[str, ...], ...]:
    selected = [AREAS[name] for name in dict.fromkeys(areas)]
    unique = lambda values: tuple(dict.fromkeys(values))
    commands = [(name,) for name in unique(name for area in selected for name in area.checks)]
    sources=unique(path for area in selected for path in (*area.source,*area.backend))
    if sources:commands.insert(0,('syntax',*sources))
    backend = unique(path for area in selected if area.backend_level<=level for path in area.backend)
    frontend = unique(path for area in selected for path in area.frontend)
    if backend:
        selection='not level4 and not runtime'
        if level<3:selection+=' and not level3'
        commands.append(('test', *backend, '-m', selection, '-q'))
    if frontend and level>=2:
        commands.append(('frontend-test', *frontend))
    elif frontend:
        commands.append(('frontend-test','--types-only'))
    journeys = {area.journey for area in selected if area.journey}
    if journeys and level>=4:
        commands.append(('sample-test', 'official', 'repair' if 'repair' in journeys else 'baseline'))
    return tuple(commands)
