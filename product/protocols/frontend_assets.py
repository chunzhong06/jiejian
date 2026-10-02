# Vite写入、控制面独立读取的前端资源清单；只描述静态资源身份，不描述产品安全结论。
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrontendAsset(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, hide_input_in_errors=True)
    path: str = Field(pattern=r'^[A-Za-z0-9_./-]+$', min_length=1, max_length=256)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def relative_path(self):
        if self.path.startswith('/') or any(part in {'', '.', '..'} for part in self.path.split('/')):
            raise ValueError('frontend asset must be a bounded relative path')
        return self


class FrontendAssetManifest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, hide_input_in_errors=True)
    schema_version: Literal['1'] = '1'
    build_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    assets: tuple[FrontendAsset, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode='after')
    def unique_entry(self):
        names = [item.path for item in self.assets]
        if 'index.html' not in names or len(set(names)) != len(names):
            raise ValueError('frontend manifest requires one unique index and asset paths')
        return self
