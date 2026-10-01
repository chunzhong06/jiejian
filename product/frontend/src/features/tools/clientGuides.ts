// 按官方客户端协议生成不含秘密的配置；地址始终采用当前界鉴实例返回的 endpoint。
export type MCPClientKey = 'codex' | 'dsh' | 'zcode'
export type ClientGuide = { label: string; description: string; openLocation: string; configInstruction: string
  credentialInstruction: string; restartInstruction: string; config: string; secretMode: 'environment' | 'header'; source: string }
export const clientOptions = [{ value: 'codex', label: 'Codex' }, { value: 'dsh', label: 'DSH' }, { value: 'zcode', label: 'ZCode' }]

export function clientGuide(client: MCPClientKey, endpoint: string): ClientGuide {
  if (client === 'codex') return {
    label: 'Codex', description: '通过 Streamable HTTP 连接本机界鉴。',
    openLocation: '打开 Codex 的 MCP 设置，或按 Win + R，输入 %USERPROFILE%\\.codex，打开 config.toml。',
    configInstruction: '添加下面的 jiejian 配置。已有同名服务时更新原条目，不重复添加。',
    credentialInstruction: '打开“开始”菜单，搜索 Windows PowerShell，粘贴复制的命令并执行，将凭据保存为当前用户的 JIEJIAN_MCP_TOKEN 环境变量。',
    restartInstruction: '完全退出 Codex 后重新打开，使客户端读取新配置与环境变量。',
    config: `[mcp_servers.jiejian]\nurl = ${JSON.stringify(endpoint)}\nbearer_token_env_var = "JIEJIAN_MCP_TOKEN"`,
    secretMode: 'environment', source: 'https://learn.chatgpt.com/docs/extend/mcp?surface=cli',
  }
  if (client === 'dsh') return {
    label: 'DSH', description: 'DeepSeek Harness 官方 MCP 客户端扩展。',
    openLocation: '在 DSH 当前使用的 extensions 配置列表中添加一个 MCP 客户端扩展。',
    configInstruction: '粘贴下面的 YAML 条目；每个条目对应一个服务，保留已有扩展。',
    credentialInstruction: '打开 Windows PowerShell，执行复制的命令，保存当前用户的 JIEJIAN_MCP_TOKEN 环境变量。配置通过 !!js 读取它。',
    restartInstruction: '重新启动 DSH，使扩展读取新的环境变量和配置。',
    config: `- id: mcp-jiejian\n  name: '@deepseek-ai/dsh-mcp-client'\n  config:\n    serverName: jiejian\n    transport: streamable-http\n    url: ${JSON.stringify(endpoint)}\n    headers:\n      Authorization: !!js '\`Bearer \${process.env.JIEJIAN_MCP_TOKEN}\`'`,
    secretMode: 'environment', source: 'https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md',
  }
  return {
    label: 'ZCode', description: '智谱 ZCode 的 HTTP MCP 服务连接。',
    openLocation: '打开 ZCode，进入“设置 → MCP 服务器 → 新建”。选择 HTTP，名称填 jiejian。',
    configInstruction: '填写本页连接地址；也可将下面的内容用于“完整配置”导入。不要覆盖其他 MCP 服务。',
    credentialInstruction: '在 Headers 中添加 Authorization，将单独复制的 Bearer 凭据粘贴为值；使用完整配置时替换其中的占位文本。',
    restartInstruction: '保存后启用 jiejian，重新连接服务。',
    config: JSON.stringify({ mcpServers: { jiejian: { type: 'http', url: endpoint, headers: { Authorization: 'Bearer <在界鉴中复制的连接凭据>' } } } }, null, 2),
    secretMode: 'header', source: 'https://zcode.z.ai/cn/docs/mcp-services',
  }
}
