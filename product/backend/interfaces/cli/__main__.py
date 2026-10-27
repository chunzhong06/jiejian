# 允许固定项目解释器通过 python -B -m product.backend.interfaces.cli 启动当前源码 CLI。

from product.backend.interfaces.cli import main


if __name__ == "__main__":
    main()
