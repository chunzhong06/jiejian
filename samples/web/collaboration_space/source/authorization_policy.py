# 协作空间导出动作的授权顺序；官方样例会修改本文件来形成可核验的真实源码变化。

from typing import Literal


AuthorizationOrder = Literal[
    "ENQUEUE_BEFORE_AUTHORIZE",
    "AUTHORIZE_BEFORE_ENQUEUE",
]


def export_authorization_order() -> AuthorizationOrder:
    """返回当前导出实现采用的授权与后台任务顺序。"""

    return "AUTHORIZE_BEFORE_ENQUEUE"
