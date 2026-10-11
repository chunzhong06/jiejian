// 配置可复用与客户端近期活动分开；此处只读配置事实，不能授予项目权限。
import { agentClients, agentConnectionsApi, type AgentConnection, type MCPAccessView } from '../../api/system/mcp'

export const agentAccessChanged = 'jiejian-agent-access-changed'
export const notifyAgentAccessChanged = () => window.dispatchEvent(new Event(agentAccessChanged))
export const configurationFailed = (value?: AgentConnection) => value?.state === 'FAILED' && ['CLIENT_NOT_FOUND','PROFILE_REQUIRED','CONFIG_FORMAT','CONFIG_CONFLICT','CONFIG_CHANGED','CONFIG_UPDATE_REQUIRED','LOCAL_WRITE_FAILED','PROFILE_UNAVAILABLE'].includes(value.code)
export const reusableConnection = (value: AgentConnection) => ['AWAITING_CLIENT','STARTED','CONNECTED','TOOLS_READ','REQUEST_ACCEPTED','DISCONNECTED'].includes(value.state) || value.state === 'FAILED' && ['SERVICE_UNAVAILABLE','SESSION_EXPIRED','CONNECT_TIMEOUT','RESPONSE_TIMEOUT'].includes(value.code)

export async function canHandOff(access: MCPAccessView): Promise<boolean> {
  if (!access.paired || !access.accepting_connections || ['PAUSED','CREDENTIAL_REJECTED'].includes(access.connection_state)) return false
  if (access.connection_state === 'CONNECTED') return true
  // 配对凭据不等于客户端配置存在；重启后没有新请求时，仍需服务端核对实际安装记录。
  const results = await Promise.allSettled(agentClients.map(item => agentConnectionsApi.status(item.key)))
  // TRAE 的安装链接不能证明客户端已确认；没有本次请求时仍保留客户端确认步骤。
  return results.some((result, index) => result.status === 'fulfilled' && result.value.client === agentClients[index].key && result.value.client !== 'trae' && reusableConnection(result.value))
}
