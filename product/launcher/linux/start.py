"""Linux运行包入口；先以标准库核对完整程序树，再装配同一产品CLI。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path,PurePosixPath


def verify_files(root):
    path=root/'app/update-manifest.json'
    with path.open('rb') as stream:raw=stream.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise ValueError('manifest budget')
    value=json.loads(raw)
    if value.get('schema_version')!='2' or value.get('document_type')!='jiejian.portable-update' or not 1<=len(value.get('files',[]))<=30000:
        raise ValueError('manifest identity')
    expected=set()
    for item in value['files']:
        relative=item['relative_path'];parts=PurePosixPath(relative)
        if parts.is_absolute() or parts.as_posix()!=relative or any(part in {'.','..'} or '\\' in part or ':' in part for part in parts.parts) or not re.fullmatch(r'[0-9a-f]{64}',item['sha256']):
            raise ValueError('manifest member')
        if relative in expected:raise ValueError('duplicate manifest member')
        expected.add(relative)
    actual={'start.sh'}
    if not stat.S_ISREG((root/'start.sh').lstat().st_mode):raise ValueError('linked program entry')
    scanned=0
    def reject_walk_error(error):
        raise error
    # 先逐目录核对链接和完整集合，再逐文件验摘要；避免为每个文件重复解析全部祖先。
    for name in ('app','runtime'):
        if not stat.S_ISDIR((root/name).lstat().st_mode):raise ValueError('linked program root')
        for directory,folders,files in os.walk(root/name,followlinks=False,onerror=reject_walk_error):
            scanned+=len(folders)+len(files)
            if scanned>60000:raise ValueError('program tree budget')
            for filename in folders:
                if not stat.S_ISDIR((Path(directory)/filename).lstat().st_mode):raise ValueError('linked program tree')
            for filename in files:
                if not stat.S_ISREG((Path(directory)/filename).lstat().st_mode):raise ValueError('linked program member')
            actual.update((Path(directory)/filename).relative_to(root).as_posix() for filename in files
                if (Path(directory)/filename)!=path)
    if expected!=actual:raise ValueError('program inventory')
    for item in value['files']:
        with root.joinpath(*PurePosixPath(item['relative_path']).parts).open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=item['sha256']:raise ValueError('program identity')
    return value


def parse_arguments(arguments):
    parser=argparse.ArgumentParser(description='界鉴Linux运行包：默认启动本机服务；启动选项放在--cli之前，其后转交产品命令')
    parser.add_argument('--var-dir',type=Path)
    parser.add_argument('--cli',action='store_true')
    # --cli 是入口与产品命令的边界，不能由启动器截走产品的 --help 等选项。
    if '--cli' in arguments:
        index=arguments.index('--cli')
        return parser.parse_args(arguments[:index]+['--cli']),arguments[index+1:]
    return parser.parse_known_args(arguments)


def main():
    root=Path(__file__).resolve().parent.parent
    try:
        if sys.platform!='linux':raise ValueError('unsupported platform')
        verify_files(root)
        release=json.loads((root/'app/release.json').read_text(encoding='utf-8'))
        if release.get('schema_version')!='3' or release.get('platform')!='linux':raise ValueError('release platform')
        options,forwarded=parse_arguments(sys.argv[1:])
        workspace=(options.var_dir or root/'var').resolve()
        if any(workspace.is_relative_to(root/part) for part in ('app','runtime')):raise ValueError('workspace in program tree')
        environment={
            'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1',
            'JIEJIAN_RUNTIME_MODE':'portable','JIEJIAN_RELEASE_ROOT':str(root),
            'JIEJIAN_PYTHON_EXECUTABLE':str(Path(sys.executable).resolve()),
            'JIEJIAN_PYTHON_ENVIRONMENT_PATH':str(Path(sys.prefix).resolve()),'JIEJIAN_PYTHON_ENVIRONMENT_TYPE':'uv-managed',
            'PLAYWRIGHT_BROWSERS_PATH':str(root/'runtime/playwright'),
            'JIEJIAN_PLAYWRIGHT_EXECUTABLE':str(root/'runtime/playwright'/('chromium-'+release['chromium_revision'])/'chrome-linux64/chrome'),
            'JIEJIAN_NODE_EXECUTABLE':str(root/'runtime/node/node'),'JIEJIAN_VAR_DIR':str(workspace)}
        for name in ('PYTHONPATH','PYTHONHOME','JIEJIAN_PROJECT_ROOT','JIEJIAN_RUNTIME_FINGERPRINT'):
            os.environ.pop(name,None)
        os.environ.update(environment)
        os.chdir(root)
        # 文件树已核验后才导入产品；后续Worker仍独立核对同一环境指纹及冻结代码身份。
        from product.backend.infrastructure.runtime.process.controlled.identity import require_python_environment
        report=require_python_environment()
        os.environ['JIEJIAN_RUNTIME_FINGERPRINT']=report['runtime_fingerprint']
    except Exception:
        print('运行包未通过平台、文件完整性或Python来源核对；请使用完整且匹配平台的运行包。',file=sys.stderr)
        return 40
    from product.backend.interfaces.cli.app import main as cli_main
    sys.argv=['jiejian','--var-dir',str(workspace),*(forwarded if options.cli else ['serve','--frontend-dir',str(root/'app/product/frontend/dist'),*forwarded])]
    cli_main()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
