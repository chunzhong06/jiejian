# 同一次只读工作区投影复用相同输入，不跨请求缓存，也不参与写入与执行门禁。
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from collections.abc import Callable, Hashable
from typing import ParamSpec, TypeVar, cast

P = ParamSpec('P')
T = TypeVar('T')
_projection: ContextVar[dict[tuple[int, Hashable], object] | None] = ContextVar(
    'workspace_projection', default=None
)

def projection_read(function: Callable[P, T]) -> Callable[P, T]:
    @wraps(function)
    def read(*args: P.args, **kwargs: P.kwargs) -> T:
        if _projection.get() is not None:
            return function(*args,**kwargs)
        token=_projection.set({})
        try:
            return function(*args,**kwargs)
        finally:
            _projection.reset(token)
    return read

def projected_once(owner: object, key: Hashable, read: Callable[[], T]) -> T:
    scope=_projection.get()
    if scope is None:
        return read()
    identity=(id(owner),key)
    if identity not in scope:
        scope[identity]=read()
    return cast(T, deepcopy(scope[identity]))
