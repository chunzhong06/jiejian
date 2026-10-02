# Portable格式2明确包含Node程序身份；Python与Node来源分别核验，不依赖机器PATH。
from typing import Literal
from pydantic import Field
from product.protocols.runtime_identity import RuntimeModel,Digest


class PortableReleaseManifest(RuntimeModel):
    schema_version:Literal['2']='2'
    product:Literal['JieJian Web V1']='JieJian Web V1'
    version:str=Field(pattern=r'^\d+\.\d+\.\d+$')
    package_version:str=Field(pattern=r'^\d+\.\d+\.\d+$')
    platform:Literal['windows']='windows'
    architecture:Literal['x64']='x64'
    runtime_layout_version:Literal['2']='2'
    python_version:str=Field(pattern=r'^\d+\.\d+\.\d+$')
    playwright_version:str=Field(pattern=r'^\d+\.\d+\.\d+$')
    chromium_revision:str=Field(pattern=r'^\d+$')
    node_version:str=Field(pattern=r'^24\.\d+\.\d+$')
    node_sha256:Digest
