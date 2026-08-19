# 允许固定项目解释器通过 python -B -m product.backend.cli 启动当前源码 CLI。

from product.backend.cli import main


if __name__ == "__main__":
    main()
