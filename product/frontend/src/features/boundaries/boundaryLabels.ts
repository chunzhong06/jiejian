// Business Boundary 用户语言映射：普通页面不直接显示协议 token。

import type { BusinessEffectKind, ProposedPermissionDto } from '../../api/businessBoundaries'

export const effectKindLabels: Record<BusinessEffectKind, string> = {
  STATE_MUTATION: '业务状态发生变化',
  DATA_DISCLOSURE: '受保护数据被读取',
  OBJECT_CREATION: '生成一个新的业务对象或文件',
  EXTERNAL_DISPATCH: '向外部系统发出业务请求',
  RESTRICTED_FUNCTION_INVOCATION: '调用受限制的业务功能',
  CREDENTIAL_ACCESS: '访问受保护凭据',
}

export const relationLabels: Record<ProposedPermissionDto['relation'], string> = {
  OWNS: '自己的资源',
  SAME_ROLE_OTHER_ACCOUNT: '同权限组另一个账号的资源',
  OTHER_ROLE: '其他权限组的资源',
}

export const expectationLabels: Record<ProposedPermissionDto['expectation'], string> = {
  ALLOW: '允许',
  DENY: '拒绝',
}

export const confidenceLabels = {
  HIGH: '识别依据较充分',
  MEDIUM: '识别依据可供确认',
  LOW: '可能相关，需要人工判断',
} as const
