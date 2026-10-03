# 编排确定性文档参考与检查；先解析全体输入，不运行产品。
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path
if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.docs.registrations import api_routes, mcp_tools, migration_rows, schema_entries, worker_branches
from scripts.docs.sources import ROOT_INPUTS, describe, grouped_sources

START = '<!-- GENERATED:START -->'
END = '<!-- GENERATED:END -->'
GENERATED_DIR = 'docs/参考/生成'


def _document(title: str, body: str) -> str:
    return f'# {title}\n\n> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。\n\n{START}\n\n{body.rstrip()}\n\n{END}\n'


def render(root: Path) -> dict[str, str]:
    """在内存完成全部输出；解析失败不会改写原参考。"""
    outputs = {}
    groups = grouped_sources(root)
    index = ['## 如何查询', '', '从功能指南确定owner，用rg搜索本目录的路径或符号，只读取命中的分片。静态import只表示依赖；运行条件和完整业务调用需读源码。', '',
             '## 覆盖与限制', '', '覆盖product、scripts中的源码、脚本、样式、HTML及JSON/YAML/TOML/INI配置，另含根入口与测试catalog。Schema由注册参考覆盖。依赖锁、二进制资源、缓存、node_modules、dist、coverage不作符号索引；测试按tests/suites.toml及指南定位。', '',
             'Python使用AST；JS/TS/PowerShell为有限词法提取；配置/样式只记录位置。每个受管文件恰有一个分片，空包仍列出；解析失败拒绝生成。', '',
             '根输入：' + '、'.join(f'`{name}`' for name in ROOT_INPUTS), '',
             '## 分片', '', '| 分片 | 文件数 |', '| --- | ---: |']
    for group, files in groups.items():
        relative = f'{GENERATED_DIR}/代码/{group}.md'
        body = []
        for path in files:
            name = path.relative_to(root).as_posix()
            symbols, imports, limit = describe(path)
            link = os.path.relpath(path, (root / relative).parent).replace('\\', '/')
            body += [f'### `{name}`', '', f'[打开源码]({link}) · {limit}', '']
            body += ['- `' + symbol.replace('|', '&#124;') + '`' for symbol in symbols]
            if imports:
                body += ['', '静态import / dot-source：' + '、'.join(f'`{value}`' for value in imports)]
            body.append('')
        outputs[relative] = _document('自动代码参考：' + group, '\n'.join(body))
        index.append(f'| [{group}](代码/{group}.md) | {len(files)} |')
    index += ['', f'合计：{sum(map(len, groups.values()))}个文件、{len(groups)}个分片。', '', '[注册与格式](注册与格式.md) · [数据库迁移](数据库迁移.md)。仅读源码文本，不import产品、打开数据库或读取var运行数据。']
    outputs[f'{GENERATED_DIR}/README.md'] = _document('生成参考入口', '\n'.join(index))
    api, mcp, workers, schemas = api_routes(root), mcp_tools(root), worker_branches(root), schema_entries(root)
    registration = ['## API显式装配', '', '只沿create_app和显式include_router工厂展开；未列出的声明不能据此认定不存在，动态表达式标注未静态确定。', '', '| 调用者 | 工厂 | 依据 |', '| --- | --- | --- |']
    registration += [f'| `{a}` | `{b}` | {c} |' for a, b, c in api]
    registration += ['', '## MCP已注册工具', '', '从build_mcp_control及显式register函数提取；授权语义仍查MCP指南。', '', '| 工具 | 位置 |', '| --- | --- |']
    registration += [f'| `{name}` | `{source}` |' for name, source in mcp]
    registration += ['', '## Worker执行分支', '', '通用Worker与运行加载专用Worker分开；条件装配仍需读源码。', '', '| 分支 | 注册表达式 | 来源 |', '| --- | --- | --- |']
    registration += [f'| {kind} | `{expression}` | `{source}` |' for kind, expression, source in workers]
    registration += ['', '## Schema注册与根版本', '', '读取SCHEMA_REGISTRY与签入JSON；只沿根属性和联合提取版本，Schema与Python语义一致性仍由dev.ps1 schema验证。', '', '| Schema（product/protocols/schemas下） | 注册模型/函数 | 根版本 |', '| --- | --- | --- |']
    registration += [f'| `{path}` | `{target}` | {version} |' for path, target, version in schemas]
    registration += ['', f'静态投影：{len(api)}条API装配关系、{len(mcp)}项MCP工具、{len(schemas)}项Schema。数量为生成事实，不是验收门槛。']
    outputs[f'{GENERATED_DIR}/注册与格式.md'] = _document('生产注册与公共格式', '\n'.join(registration))
    migrations, declared = migration_rows(root)
    body = [f'源码声明的当前数据库head：`{declared or "未声明"}`。', '', '来源为db.py与签入Alembic元数据；本页不执行DDL。升级与数据保留条件须读具体migration及数据库指南。', '', '| revision | down_revision | 文件 |', '| --- | --- | --- |']
    body += [f'| `{revision}` | `{parent or "无（基线）"}` | `{path}` |' for revision, parent, path in migrations]
    outputs[f'{GENERATED_DIR}/数据库迁移.md'] = _document('数据库迁移链', '\n'.join(body))
    return outputs


def generate(root: Path, update: bool) -> list[Path]:
    """只管理带生成标记的专用目录；检查模式只读，不自动修正。"""
    root = root.resolve()
    try:
        outputs = render(root)
    except (ValueError, OSError, KeyError) as error:
        raise SystemExit(f'文档静态提取失败：{error}') from error
    expected = {root / name: text for name, text in outputs.items()}
    base = root / GENERATED_DIR
    if base.is_symlink() or not base.resolve().is_relative_to(root):
        raise SystemExit('生成目录越出仓库或属于链接')
    for path in expected:
        if not path.resolve().is_relative_to(base.resolve()):
            raise SystemExit('生成目标越出受管目录')
    actual = set(base.rglob('*.md')) if base.exists() else set()
    failures, changed = [], []
    for path in actual:
        if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):
            failures.append(f'生成目录存在链接或越界路径：{path.relative_to(root)}')
        elif START not in path.read_text(encoding='utf-8'):
            failures.append(f'生成目录存在非受管文件：{path.relative_to(root)}')
    if failures:
        raise SystemExit('\n'.join(failures))
    for path, document in expected.items():
        before = path.read_text(encoding='utf-8') if path.exists() else None
        if before != document:
            if update:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(document, encoding='utf-8', newline='\n')
                changed.append(path)
            else:
                failures.append(f'代码参考漂移：{path.relative_to(root)}')
    for path in sorted(actual - set(expected)):
        if update:
            path.unlink()
            changed.append(path)
        else:
            failures.append(f'过期生成参考：{path.relative_to(root)}')
    if update and base.exists():
        # 文件迁出后的空分片目录没有读者；仅清理已确认在生成边界内的空目录。
        for directory in sorted((p for p in base.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            if not directory.is_symlink() and directory.resolve().is_relative_to(base.resolve()) and not any(directory.iterdir()):
                directory.rmdir()
    if not update:
        from tests.docs.checks import check_documentation
        notices = []
        failures.extend(check_documentation(root, notices=notices))
        if notices:
            print('测试命令静态检查的跳过项（占位/动态路径，不代表已验证）：')
            for notice in sorted(set(notices)):
                print('- ' + notice)
    if failures:
        raise SystemExit('\n'.join(failures))
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description='生成界鉴分片参考与注册事实')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--update', action='store_true')
    args = parser.parse_args()
    generate(args.root, args.update)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
