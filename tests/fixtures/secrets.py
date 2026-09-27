# 提供测试内存秘密存储；仅替换凭据持久化边界，不构造产品配置或安全结论。
from __future__ import annotations

class InMemorySecretStore:
    """测试边界内保存不透明值；正式配置和运行工件仍只接收引用。"""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def configured(self, secret_ref: str) -> bool:
        return secret_ref in self.values

    def read(self, secret_ref: str) -> str | None:
        return self.values.get(secret_ref)

    def write(self, secret_ref: str, value: str) -> None:
        self.values[secret_ref] = value

    def delete(self, secret_ref: str) -> None:
        self.values.pop(secret_ref, None)
