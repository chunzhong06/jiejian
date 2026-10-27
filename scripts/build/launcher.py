# 将产品启动器和共享品牌资源编译为仅依赖系统 DLL 的 Windows 入口。
from __future__ import annotations

import json
import os
from pathlib import Path
from scripts.build.common import RELEASE_VERSION, run


def launcher_icon(base: Path, environment: dict[str, str], project_root: Path) -> Path:
    """将网页现用矢量标志转为多尺寸ICO；离线生成物只进入本次构建目录。"""
    import struct
    from playwright.sync_api import sync_playwright
    mark = (project_root / 'product/frontend/src/assets/brand/jiejian.svg').read_text(encoding='utf-8')
    browsers = [p for p in (base / 'runtime/playwright').rglob('chrome.exe') if 'chromium-' in p.as_posix()]
    if len(browsers) != 1:
        raise RuntimeError('构建图标需要包内唯一Chromium')
    pictures = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(browsers[0]), headless=True, env=environment)
        try:
            page = browser.new_page(offline=True)
            svg = mark
            page.set_content('<style>html,body{margin:0;background:transparent}svg{width:100vw;height:100vh;color:rgb(186,196,249)}</style>' + svg)
            for size in (16, 24, 32, 48, 64, 128, 256):
                page.set_viewport_size({'width': size, 'height': size})
                pictures.append((size, page.screenshot(omit_background=True)))
        finally:
            browser.close()
    offset = 6 + 16 * len(pictures)
    records = []
    for size, picture in pictures:
        records.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(picture), offset))
        offset += len(picture)
    icon = base.parent / 'jiejian.ico'
    icon.write_bytes(struct.pack('<HHH', 0, 1, len(pictures)) + b''.join(records) + b''.join(p[1] for p in pictures))
    (base.parent / 'jiejian-icon-preview.png').write_bytes(pictures[-1][1])
    return icon


def compile_launcher(base: Path, compiler: Path, toolchain: dict, environment: dict[str, str], project_root: Path) -> None:
    """构建一次 Win32 薄入口，运行时仅依赖 Windows 自带 DLL。"""
    import re
    source = project_root / 'product/launcher/windows/launcher.c'
    brand = json.loads(source.with_name('brand.json').read_text('utf-8'))
    rows, palette = brand['art'], brand['colors']
    if not rows or len(palette) != len(rows) or any(len(color) != 3 or any(type(value) is not int or not 0 <= value <= 255 for value in color) for color in palette):
        raise RuntimeError('启动品牌资源无效')
    header = base.parent / 'startup-brand.h'
    header.write_text('/* Generated from product launcher resources. */\n'
        + 'static const wchar_t *brand_version = L' + json.dumps(RELEASE_VERSION) + ';\n'
        + 'static const wchar_t *brand_art[] = {' + ','.join('L' + json.dumps(row) for row in rows) + '};\n'
        + 'static const COLORREF brand_colors[] = {' + ','.join('RGB('+','.join(map(str,color))+')' for color in palette) + '};\n', encoding='utf-8')
    env = {**environment, 'PATH': os.pathsep.join((str(compiler.parent), str(Path(os.environ['SYSTEMROOT']) / 'System32')))}
    config = toolchain['launcher']
    target = run((compiler, '-dumpmachine'), cwd=base, environment=env).strip()
    version = run((compiler, '-dumpfullversion'), cwd=base, environment=env).strip()
    if target != config['target'] or version != config['version']:
        raise RuntimeError('启动器编译器与 toolchain.json 的版本或目标不一致')
    icon = launcher_icon(base, environment, project_root)
    resource = base.parent / 'startup-icon.rc'
    resource.write_text('#pragma code_page(65001)\n1 ICON "' + icon.as_posix() + '"\n', encoding='utf-8')
    resource_object = base.parent / 'startup-icon.o'
    windres = Path(run((compiler, '-print-prog-name=windres'), cwd=base, environment=env).strip())
    if not windres.is_absolute() or not windres.is_file():
        raise RuntimeError('启动器工具链缺少可定位的 windres')
    run((windres, '--codepage=65001', '-i', resource, '-o', resource_object), cwd=base, environment=env)
    run((compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-municode', '-mwindows',
          '-static-libgcc', '-s', '-Wl,--no-insert-timestamp', '-finput-charset=UTF-8',
          '-I', base.parent, source, resource_object, '-o', base / '界鉴.exe', '-lshell32', '-luser32', '-lgdi32'), cwd=base, environment=env)
    objdump = Path(run((compiler, '-print-prog-name=objdump'), cwd=base, environment=env).strip())
    if not objdump.is_absolute() or not objdump.is_file():
        raise RuntimeError('启动器工具链缺少可定位的 objdump')
    imports = run((objdump, '-p', base / '界鉴.exe'), cwd=base, environment=env)
    names = {name.casefold() for name in re.findall(r'DLL Name:\s*(\S+)', imports)}
    if not names or any(name not in {'kernel32.dll', 'msvcrt.dll', 'ucrtbase.dll', 'user32.dll', 'shell32.dll', 'gdi32.dll', 'advapi32.dll'} and not name.startswith('api-ms-win-crt-') for name in names):
        raise RuntimeError('原生入口依赖了非 Windows 系统 DLL')
