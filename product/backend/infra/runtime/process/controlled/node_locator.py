# 只使用启动器已准备的Node路径；不搜索PATH、不安装依赖或执行自选程序。
import json
import hashlib
from pathlib import Path

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.process.controlled.artifact import _read_bounded


def controlled_node_executable(environ) -> Path:
    try:
        if environ.get('JIEJIAN_RUNTIME_MODE') == 'portable':
            root=Path(environ['JIEJIAN_RELEASE_ROOT']).resolve()
            node=root/'runtime/node/node.exe'
            allowed=root/'runtime/node'
            from product.protocols.runtime.portable_release import PortableReleaseManifest
            release=PortableReleaseManifest.model_validate_json(_read_bounded(root/'runtime/release.json',16384))
            with node.open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=release.node_sha256:
                    raise ValueError('portable Node differs from release identity')
        else:
            root=Path(environ.get('JIEJIAN_PROJECT_ROOT',Path(__file__).resolve().parents[6])).resolve()
            receipt=json.loads(_read_bounded(root/'var/runtime/source/receipt.json',262144).decode('utf-8-sig'))
            node=Path(receipt['node']['executable'])
            allowed=root/'var/development/tools/node'
        if (not node.is_absolute() or not node.is_file() or node.is_symlink()
                or not node.resolve().is_relative_to(allowed.resolve()) or node.name.casefold()!='node.exe'):
            raise ValueError('uncontrolled Node path')
        return node.resolve()
    except (OSError,ValueError,KeyError,TypeError):
        raise JiejianError(ErrorCode.RUNTIME_ENVIRONMENT_INVALID,'受控Node运行环境尚未准备好',
            details={'reason':'NODE_RUNTIME_UNAVAILABLE'}) from None
