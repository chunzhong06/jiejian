# 从产品启动资源和产品使用文档生成发行文件及许可。
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from product.protocols.runtime.portable_release import PortableReleaseManifest
from scripts.build.common import RELEASE_VERSION


def write_runtime_files(base: Path, metadata: dict[str, str], project_root: Path) -> None:
    launcher = project_root / 'product/launcher/windows'
    guide = (project_root / 'docs/产品/便携版使用.md').read_text('utf-8')
    guide = re.sub(r'^#{1,6}\s+', '', guide, flags=re.M)
    guide = f'界鉴 {RELEASE_VERSION}\n\n' + guide
    startup = (launcher / 'start.ps1').read_text('utf-8-sig')
    (base / "README.txt").write_text(guide, encoding='utf-8-sig')
    app = base / "app"
    app.mkdir(exist_ok=True)
    (app / "start.ps1").write_bytes(
        b"\xef\xbb\xbf" + startup.replace("\n", "\r\n").encode("utf-8")
    )
    release = {
        "schema_version": "3",
        "product": "JieJian Web V1",
        "version": RELEASE_VERSION,
        "package_version": metadata["wheel_version"],
        "platform": "windows",
        "architecture": "x64",
        "runtime_layout_version": "3",
        "python_version": metadata["python_version"],
        "playwright_version": metadata["playwright_version"],
        "chromium_revision": metadata["chromium_revision"],
        "node_version": metadata["node_version"],
        "node_sha256": metadata["node_sha256"],
    }
    release = PortableReleaseManifest.model_validate(release).model_dump(mode='json')
    (app / "release.json").write_text(
        json.dumps(release, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    docs = base / 'docs'
    docs.mkdir(exist_ok=True)
    docs.joinpath('使用说明.txt').write_text(guide, encoding='utf-8-sig')
    docs.joinpath('版本说明.txt').write_text(f'界鉴 {RELEASE_VERSION}\n\n本版本包含本地 Web 应用接入、规则审阅、材料准备、权限检查、原题复验与统一历史。\n程序在发布前构建；根目录的界鉴.exe是日常入口。\n', encoding='utf-8-sig')
    docs.joinpath('第三方许可.txt').write_text('第三方许可证随对应固定组件保留：\nPython：runtime/python 中的 LICENSE 文件。\nNode：runtime/node/LICENSE.txt。\nChromium：runtime/playwright 中各组件的 LICENSE、LICENSES 和 credits 文件。\nPython 依赖：runtime/python/Lib/site-packages 下各 *.dist-info 的 licenses、LICENSE 或 COPYING。\nMiSans 字体：app/product/frontend/dist/assets 中的 MiSans-LICENSE PDF。\n原生启动器：本目录保留 MinGW-w64-COPYING、MinGW-w64-NOTICES、GCC-GPL-3.0、GCC-Runtime-Exception-3.1 与 Conda-forge-GCC-COPYING；来源见 SOURCES.txt。\n', encoding='utf-8-sig')
    for license_file in (launcher / 'licenses').glob('*.txt'):
        shutil.copyfile(license_file, docs / license_file.name)
