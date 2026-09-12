# Web 叶协议的严格基类；独立配置可复用叶模型而不装载旧执行契约。
from pydantic import BaseModel, ConfigDict


class ProtocolModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
