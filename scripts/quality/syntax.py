# 只读解析选择范围的 Python 源码，不导入产品或生成字节码。
import argparse
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def check(paths,root=ROOT):
    files=set()
    for name in paths:
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not path.exists():raise ValueError('语法检查路径不存在或越界')
        for candidate in path.rglob('*.py') if path.is_dir() else (path,):
            if '__pycache__' in candidate.parts:continue
            if not candidate.resolve().is_relative_to(root):raise ValueError('语法检查拒绝越界链接')
            if candidate.suffix=='.py':files.add(candidate)
    for path in sorted(files):ast.parse(path.read_text('utf-8-sig'),filename=str(path.relative_to(root)))
    return len(files)

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('paths',nargs='+')
    args=parser.parse_args(argv)
    try:count=check(args.paths)
    except (ValueError,OSError,SyntaxError) as error:
        print(f'语法检查失败：{error.__class__.__name__}')
        return 1
    print(f'Python 语法检查通过：{count} 个文件')
    return 0

if __name__=='__main__':raise SystemExit(main())
