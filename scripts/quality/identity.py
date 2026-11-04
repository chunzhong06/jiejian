"""将测试回执绑定到实际输入内容；身份只用于证据查重，不复用产品安全结论。"""
import hashlib
import json
import sys
from pathlib import Path


def tree_identity(root, folders):
    digest = hashlib.sha256()
    count = 0
    for folder in folders:
        base=root/folder
        for path in ([base] if base.is_file() else sorted(base.rglob('*'))):
            if not path.is_file() or set(path.parts) & {'node_modules', '__pycache__', '.vite', 'dist'}:
                continue
            if path.suffix in {'.pyc', '.tsbuildinfo'}:
                continue
            digest.update(path.relative_to(root).as_posix().encode() + b'\0')
            digest.update(hashlib.sha256(path.read_bytes()).digest())
            count += 1
    return dict(sha256=digest.hexdigest(), files=count)


def input_identity(root):
    manifest = root / 'var/runtime/frontend/frontend-manifest.json'
    return dict(source=tree_identity(root, ('product',)),
        tests=tree_identity(root, ('tests',)), tooling=tree_identity(root, ('scripts',)),
        dependencies=tree_identity(root, ('pyproject.toml','uv.lock')),
        fixtures=tree_identity(root, ('tests/support','samples')),
        frontend_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.is_file() else None)


if __name__ == '__main__':
    Path(sys.argv[1]).write_text(json.dumps(dict(schema_version='1',
        inputs=input_identity(Path(__file__).resolve().parents[2]))), encoding='utf-8')
