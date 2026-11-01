from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.runtime.process.tree import spawn_managed_process, terminate_process_tree
from product.protocols.runtime.node_runtime import NodeBuildArtifact
from product.protocols.runtime.runtime_identity import RuntimeFile,MAX_ARTIFACT_BYTES

MAX_DEPENDENCY_FILES = 30_000
MAX_DEPENDENCY_BYTES = 512 * 1024 * 1024


def npm_plan(root: Path, *, build_script=None, allow_install_scripts=False):
    from product.protocols.runtime.node_runtime import NodePackagePlan

    if not (root / 'package.json').is_file():
        if build_script is not None:
            raise ValueError('a build requires package.json')
        return None
    package = json.loads((root / 'package.json').read_text(encoding='utf-8-sig'))
    lock = json.loads((root / 'package-lock.json').read_text(encoding='utf-8-sig'))
    if lock.get('lockfileVersion') not in (2, 3) or not isinstance(lock.get('packages'), dict):
        raise ValueError('npm lockfile v2 or v3 required')
    if build_script is not None and build_script not in package.get('scripts', {}):
        raise ValueError('selected build script does not exist')
    for name, item in lock['packages'].items():
        resolved = item.get('resolved', '')
        if item.get('link') or resolved and not resolved.startswith('https://registry.npmjs.org/'):
            raise ValueError('only locked public npm registry packages are currently supported')
        if name and (not item.get('integrity') or not item.get('version')):
            raise ValueError('registry dependency requires integrity and version')
    return NodePackagePlan(build_script=build_script, allow_install_scripts=allow_install_scripts)


def dependency_files(root: Path):
    files, total = [], 0
    for directory, directories, names in os.walk(root, followlinks=False):
        for name in directories:
            child = Path(directory) / name
            if child.is_symlink() or child.is_junction():
                raise ValueError('dependency directory cannot be a link')
        for name in names:
            file = Path(directory) / name
            if file.is_symlink() or not file.is_file():
                raise ValueError('dependency must be a regular file')
            total += file.stat().st_size
            if len(files) >= MAX_DEPENDENCY_FILES or total > MAX_DEPENDENCY_BYTES:
                raise ValueError('dependency artifact exceeds budget')
            with file.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            files.append({'path': file.relative_to(root).as_posix(), 'size': file.stat().st_size, 'sha256': digest})
    return sorted(files, key=lambda item: item['path'])


def _write(path, value):
    staging = path.with_suffix('.tmp')
    staging.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    staging.replace(path)


def _run(node, npm, arguments, *, cwd, environment, tree_name, cancelled):
    process = spawn_managed_process([str(node), str(npm), *arguments], tree_name=tree_name,
        cwd=cwd, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    deadline = time.monotonic() + 180
    try:
        while process.poll() is None:
            if cancelled() or time.monotonic() >= deadline:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '依赖准备已取消或超时', details={'reason': 'NPM_PREPARATION_INTERRUPTED'})
            time.sleep(.1)
        if process.returncode:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '锁定依赖安装或构建失败，请核对包清单、锁文件和构建入口', details={'reason': 'NPM_PREPARATION_FAILED'})
    finally:
        terminate_process_tree(process, timeout=5)


def prepare_dependencies(root, manifest, node, var_dir, *, cancelled):
    """Worker 在所属副本安装；缓存只在精确内容核对后复用，不读取个人 npm 配置。"""
    if manifest.package is None:
        return
    from product.backend.infrastructure.maintenance.inventory import exclusive_file
    with exclusive_file(Path(var_dir)/'locks/local-maintenance.lock'):
        return _prepare_dependencies(root,manifest,node,var_dir,cancelled=cancelled)


def _prepare_dependencies(root,manifest,node,var_dir,*,cancelled):
    for name in ('application-dependencies','npm-downloads'):
        directory=Path(var_dir)/'cache'/name
        directory.mkdir(parents=True,exist_ok=True)
        _write(directory/'.application-owned.json',dict(schema_version='1',kind='application-cache',name=name))
    npm = node.parent / 'node_modules/npm/bin/npm-cli.js'
    if not npm.is_file():
        raise JiejianError(ErrorCode.RUNTIME_ENVIRONMENT_INVALID, '包内 npm 不可用', details={'reason': 'NPM_RUNTIME_UNAVAILABLE'})
    source = root / 'source'
    plan = manifest.package
    npm_plan(source, build_script=plan.build_script, allow_install_scripts=plan.allow_install_scripts)
    identity = hashlib.sha256(('npm-ci-windows-v2' + manifest.interpreter_fingerprint + (source / 'package-lock.json').read_text(encoding='utf-8-sig')
        + (source / 'package.json').read_text(encoding='utf-8-sig') + str(plan.allow_install_scripts)).encode()).hexdigest()
    cache = Path(var_dir) / 'cache/application-dependencies' / identity
    node_modules = source / 'node_modules'
    receipt = cache / 'receipt.json'
    state = root / 'dependency-state.json'
    _write(state, {'stage': 'INSTALLING', 'cache_reused': False})
    if receipt.is_file():
        expected = json.loads(receipt.read_text(encoding='utf-8'))
        if expected.get('identity') != identity or dependency_files(cache / 'node_modules') != expected.get('files'):
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '依赖缓存与已记录内容不符，请在本地存储中清理后重试', details={'reason': 'NPM_CACHE_CHANGED'})
        shutil.copytree(cache / 'node_modules', node_modules)
        reused = True
    else:
        configuration = root / 'npm-empty.conf'
        configuration.write_text('', encoding='utf-8')
        global_configuration = root / 'npm-global-empty.conf'
        global_configuration.write_text('', encoding='utf-8')
        temporary = root / 'npm-temp'
        temporary.mkdir()
        environment = {key: value for key, value in os.environ.items() if key.upper() in {'SYSTEMROOT', 'WINDIR'}}
        environment.update(PATH=str(node.parent) + os.pathsep + str(Path(environment.get('SYSTEMROOT', 'C:/Windows')) / 'System32'),
            TEMP=str(temporary), TMP=str(temporary), npm_config_userconfig=str(configuration), npm_config_globalconfig=str(global_configuration),
            npm_config_cache=str(Path(var_dir).resolve() / 'cache/npm-downloads'), npm_config_update_notifier='false')
        arguments = ['ci', '--no-audit', '--no-fund', '--bin-links=true', '--ignore-scripts=' + ('false' if plan.allow_install_scripts else 'true')]
        _run(node, npm, arguments, cwd=source, environment=environment,
            tree_name='jiejian-npm-' + manifest.instance_id, cancelled=cancelled)
        node_modules.mkdir(exist_ok=True)
        files = dependency_files(node_modules)
        # receipt 最后发布；未完成的安装不进入可复用集合。
        cache.mkdir(parents=True, exist_ok=True)
        if (cache / 'node_modules').exists():
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '发现未完成的依赖缓存，请清理后重试', details={'reason': 'NPM_CACHE_INCOMPLETE'})
        shutil.copytree(node_modules, cache / 'node_modules')
        _write(receipt, {'identity': identity, 'files': files})
        reused = False
    if plan.build_script is not None:
        _write(state, {'stage': 'BUILDING', 'cache_reused': reused})
        configuration = root / 'npm-empty.conf'
        configuration.write_text('', encoding='utf-8')
        global_configuration = root / 'npm-global-empty.conf'
        global_configuration.write_text('', encoding='utf-8')
        environment = {key: value for key, value in os.environ.items() if key.upper() in {'SYSTEMROOT', 'WINDIR'}}
        environment.update(PATH=str(node.parent)+os.pathsep+str(Path(environment.get('SYSTEMROOT','C:/Windows'))/'System32'),
            npm_config_userconfig=str(configuration),npm_config_globalconfig=str(global_configuration),
            npm_config_cache=str(Path(var_dir).resolve()/'cache/npm-downloads'),npm_config_update_notifier='false')
        environment.update(TEMP=str(root/'build-temp'),TMP=str(root/'build-temp'))
        (root/'build-temp').mkdir(exist_ok=True)
        _run(node, npm, ['run', plan.build_script, '--ignore-scripts'], cwd=source, environment=environment,
            tree_name='jiejian-build-' + manifest.instance_id, cancelled=cancelled)
        files=[]
        for directory,directories,names in os.walk(source,followlinks=False):
            directories[:]=[name for name in directories if name!='node_modules']
            if any((Path(directory)/name).is_symlink() or (Path(directory)/name).is_junction() for name in directories):raise ValueError('build output contains linked directory')
            for name in names:
                path=Path(directory)/name
                if path.is_symlink() or not path.is_file() or path.suffix.lower() not in {'.mjs','.cjs','.js','.ts','.tsx','.jsx','.mts','.cts','.json','.html','.css','.svg','.map'}:
                    raise ValueError('build output contains unsupported file')
                size=path.stat().st_size
                if size>MAX_ARTIFACT_BYTES or sum(item.size for item in files)+size>MAX_ARTIFACT_BYTES or len(files)>=512:
                    raise ValueError('build output exceeds budget')
                files.append(RuntimeFile(relative_path=path.relative_to(source).as_posix(),size=size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        files=tuple(sorted(files,key=lambda item:(item.relative_path.casefold(),item.relative_path)))
        if manifest.entry not in {item.relative_path for item in files}:raise ValueError('build did not produce selected entry')
        original={item.relative_path:item for item in manifest.files}
        if any(item!=original[item.relative_path] for item in files if item.relative_path in {'package.json','package-lock.json'}):
            raise ValueError('build changed its frozen package input')
        artifact=NodeBuildArtifact(instance_id=manifest.instance_id,source_fingerprint=manifest.source_fingerprint,files=files)
        _write(root/'execution.json',artifact.model_dump(mode='json'))
    _write(root / 'dependencies.json', {'schema_version': '1', 'identity': identity, 'files': dependency_files(node_modules)})
    _write(state, {'stage': 'READY', 'cache_reused': reused})


def execution_fingerprint(root,manifest):
    if manifest.package is None:return None
    inputs=(root/'dependencies.json').read_bytes()
    if manifest.package.build_script is not None:inputs+=(root/'execution.json').read_bytes()
    return hashlib.sha256(inputs).hexdigest()


def verify_dependencies(root, manifest):
    if manifest.package is None:
        return
    receipt = json.loads((root / 'dependencies.json').read_text(encoding='utf-8'))
    if receipt.get('schema_version') != '1' or receipt.get('files') != dependency_files(root / 'source/node_modules'):
        raise ValueError('actual npm dependency artifact changed')
