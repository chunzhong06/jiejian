# 默认展示契约验证计划，显式执行时复用正式入口并在失败后停止。
import argparse
import subprocess
import sys
from pathlib import Path
from scripts.quality.catalog import AREAS, plan

def main(argv=None):
    parser=argparse.ArgumentParser(description='按契约选择验证；--run 才执行')
    parser.add_argument('--area',choices=tuple(AREAS),action='append',default=[])
    parser.add_argument('--all',action='store_true',help='全部本地契约，不含真实目标场景')
    parser.add_argument('--list',action='store_true')
    parser.add_argument('--level',choices=['L1','L2','L3','L4'],help='本次需要的最高验证程度，不自动触发真实场景')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--run',action='store_true')
    mode.add_argument('--plan',action='store_true')
    arguments=parser.parse_args(argv)
    if arguments.list or not arguments.area and not arguments.all:
        if arguments.run:parser.error('--run 需要 --area 或 --all，不推测验证范围')
        for name,area in AREAS.items():print(f'{name}: {area.purpose}')
        print('仅列出范围，未执行验证。')
        return 0
    areas=[name for name,area in AREAS.items() if not area.journey] if arguments.all else []
    areas+=arguments.area
    level=int(arguments.level[1:]) if arguments.level else 4
    suites=plan(areas,level)
    if any(AREAS[name].journey for name in areas) and level<4:parser.error('真实场景需要 L4；不能把未执行的场景当作低等级通过')
    root=Path(__file__).resolve().parents[2]
    command=['powershell.exe','-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',str(root/'scripts/dev.ps1')]
    for name in dict.fromkeys(areas):print(f'范围 {name}: {AREAS[name].purpose}',flush=True)
    def invocation(suite):
        return [sys.executable,'-B','-m','scripts.quality.syntax',*suite[1:]] if suite[0]=='syntax' else [*command,*suite]
    for suite in suites:print(subprocess.list2cmdline(invocation(suite)),flush=True)
    if not arguments.run:
        print('这是计划，尚未执行验证；确认范围后追加 --run。')
        return 0
    for suite in suites:
        result=subprocess.run(invocation(suite),cwd=root,check=False)
        if result.returncode:return result.returncode
    return 0

if __name__=='__main__':raise SystemExit(main())
