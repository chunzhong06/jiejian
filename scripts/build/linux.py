"""在Linux组装非editable运行包；程序树与可复用工作区分开，复用现有发行身份与文件清单。"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from product.backend import __version__
from product.protocols.runtime.portable_release import PortableReleaseManifest
from scripts.build.resources import write_update_manifest


def run(arguments,environment):
    subprocess.run([str(item) for item in arguments],env=environment,check=True)


def copy_tree(source,destination):
    source=source.resolve()
    def ignore(directory,names):
        return [name for name in names if name in {'__pycache__','.git','.pytest_cache','tests'} or name.endswith(('.pyc','.pyo'))]
    # 依赖包中的内部链接在打包时解引用；发行清单和启动入口仍拒绝任何残留链接。
    shutil.copytree(source,destination,symlinks=False,ignore=ignore)


def build(args):
    if sys.platform!='linux' or platform.machine()!='x86_64':raise ValueError('Linux x64 builder required')
    project=args.project_root.resolve();destination=args.destination.resolve()
    if not destination.is_relative_to(project/'var') or destination.exists():raise ValueError('fresh var build directory required')
    sources=[args.python_source,args.node_source,args.browser_source,args.library_source,args.wheel]
    if any(not source.exists() or source.resolve().is_relative_to(destination) or destination.is_relative_to(source.resolve()) for source in sources):
        raise ValueError('build inputs overlap or missing')
    destination.mkdir(parents=True)
    app=destination/'app';app.mkdir()
    runtime=destination/'runtime';runtime.mkdir()
    environment=os.environ.copy();environment['PYTHONDONTWRITEBYTECODE']='1';environment['PYTHONNOUSERSITE']='1'
    for name in ('JIEJIAN_PROJECT_ROOT','JIEJIAN_RELEASE_ROOT','JIEJIAN_RUNTIME_FINGERPRINT'):
        environment.pop(name,None)
    copy_tree(args.python_source,runtime/'python')
    assemble(args,destination)


def assemble(args,destination):
    """完成已复制解释器的构建暂存树；拒绝覆盖已有发行清单。"""
    project=args.project_root.resolve();destination=destination.resolve()
    if not destination.is_relative_to(project/'var') or (destination/'app/update-manifest.json').exists():
        raise ValueError('only unfinished var staging tree may be assembled')
    app=destination/'app';runtime=destination/'runtime'
    environment=os.environ.copy();environment.update(PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    for name in ('JIEJIAN_PROJECT_ROOT','JIEJIAN_RELEASE_ROOT','JIEJIAN_RUNTIME_FINGERPRINT'):
        environment.pop(name,None)
    python=runtime/'python/bin/python3.13'
    print('installing frozen dependencies in private Python copy',flush=True)
    requirements=app/'runtime-requirements.txt'
    run([args.uv,'--no-config','--quiet','export','--frozen','--no-dev','--no-emit-project','--format','requirements-txt','--output-file',requirements],environment)
    # 只修改新发行树中的解释器副本，与Windows构建器相同；原uv安装及系统Python保持只读。
    install=[args.uv,'--no-config','pip','install','--python',python,'--system','--break-system-packages','--offline']
    if getattr(args,'wheelhouse',None) is not None:
        # 本地wheel仍须满足导出的锁文件哈希；不依赖构建机残留的在线索引元数据。
        wheelhouse=args.wheelhouse.resolve()
        if not wheelhouse.is_dir() or wheelhouse.is_relative_to(destination):
            raise ValueError('external verified wheelhouse required')
        install.extend(['--no-index','--find-links',wheelhouse])
    run([*install,'--require-hashes','-r',requirements],environment)
    run([*install,'--no-deps',args.wheel],environment)
    print('assembling browser and Node',flush=True)
    copy_tree(args.browser_source,runtime/'playwright')
    node=runtime/'node';node.mkdir()
    shutil.copy2(args.node_source/'bin/node',node/'node')
    copy_tree(args.node_source/'lib/node_modules/npm',node/'node_modules/npm')
    shutil.copy2(args.node_source/'LICENSE',node/'LICENSE')
    copy_tree(args.library_source,runtime/'system-libs')
    browser=next((runtime/'playwright').glob('chromium-*/chrome-linux64/chrome'))
    browser.rename(browser.with_name('chrome.bin'))
    browser.write_text('#!/bin/sh\nset -eu\ntask_browser=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\ntask_libs="$task_browser/../../../system-libs/usr/lib/x86_64-linux-gnu"\nexport LD_LIBRARY_PATH="$task_libs"\nexec "$task_browser/chrome.bin" "$@"\n',encoding='utf-8')
    browser.chmod(0o755)
    copy_tree(project/'var/runtime/frontend',app/'product/frontend/dist')
    shutil.copy2(project/'product/launcher/linux/start.sh',destination/'start.sh');(destination/'start.sh').chmod(0o755)
    shutil.copy2(project/'product/launcher/linux/start.py',app/'start.py')
    # 不交付包含构建时绝对解释器路径的console-script；正式入口只使用包内解释器。
    for name in ('jiejian','uvicorn','alembic','playwright','fastapi','mcp'):
        (runtime/'python/bin'/name).unlink(missing_ok=True)
    node_version=subprocess.check_output([node/'node','--version'],text=True).strip().removeprefix('v')
    python_version=subprocess.check_output([python,'-I','-B','-c','import platform; print(platform.python_version())'],text=True).strip()
    manifest=PortableReleaseManifest(version=__version__,package_version=__version__,platform='linux',python_version=python_version,
        playwright_version=importlib.metadata.version('playwright'),chromium_revision=browser.parents[1].name.removeprefix('chromium-'),
        node_version=node_version,node_sha256=hashlib.sha256((node/'node').read_bytes()).hexdigest())
    (app/'release.json').write_text(manifest.model_dump_json(),encoding='utf-8')
    print('verifying migration identities and frozen inventory',flush=True)
    write_update_manifest(destination)
    archive=destination.with_name(destination.name+'.tar.gz')
    with tarfile.open(archive,'w:gz',compresslevel=3) as bundle:bundle.add(destination,arcname=destination.name,recursive=True)
    with archive.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    receipt=dict(directory=str(destination),archive=str(archive),sha256=digest,platform=platform.platform(),release=manifest.model_dump(mode='json'))
    (destination.parent/(destination.name+'.json')).write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser(description='构建界鉴Linux x64运行包')
    for option in ('project-root','destination','python-source','node-source','browser-source','library-source','wheel','uv'):
        parser.add_argument('--'+option,type=Path,required=True)
    parser.add_argument('--wheelhouse',type=Path,help='预先准备的锁定wheel目录；安装仍执行哈希校验')
    build(parser.parse_args())


if __name__=='__main__':main()
