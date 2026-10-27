# 录制能力叶模块包；导入包根不会加载浏览器依赖。
# Recording 应用服务公共导入面。

from product.backend.application.recording.credentials import RecordingCredentialProvider

__all__ = ["RecordingCredentialProvider"]
