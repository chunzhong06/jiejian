// 按官方客户端协议生成不含秘密的配置；地址始终采用当前界鉴实例返回的 endpoint。
export type MCPClientKey = 'codex' | 'dsh' | 'zcode' | 'trae' | 'codebuddy' | 'qoder'
export type ClientGuide = { label: string; description: string; openLocation: string; configInstruction: string
  credentialInstruction: string; restartInstruction: string; config: string; secretMode: 'environment' | 'header'; source: string }
export const clientOptions = [{ value: 'codex', label: 'Codex' }, { value: 'dsh', label: 'DSH' }, { value: 'zcode', label: 'ZCode' },
  { value: 'trae', label: 'TRAE' }, { value: 'codebuddy', label: 'CodeBuddy Code' }, { value: 'qoder', label: 'Qoder CLI' }]

export type DSHPatchMode = 'insert' | 'entry'
export function clientGuide(client: MCPClientKey, endpoint: string, dshMode: DSHPatchMode = 'insert'): ClientGuide {
  // 不同产品的配置载体各自保留；真实凭据只能由独立复制动作取得。
  const httpConfig = (explicitType = true) => JSON.stringify({ mcpServers: { jiejian: {
    ...(explicitType ? { type: 'http' } : {}), url: endpoint, headers: { Authorization: 'Bearer <在界鉴中复制的连接凭据>' },
  } } }, null, 2)
  const headerInstruction = '将单独复制的 Bearer 凭据替换到 Authorization 的整个占位值中。配置预览不包含真实凭据。'
  if (client === 'trae') return {
    label: 'TRAE', description: 'TRAE IDE 本地 Agent 的 MCP 连接；这里配置的是开发工具，不是豆包聊天页面。',
    openLocation: '在 TRAE IDE 或 Agent 窗口打开“设置 → MCP”。选择“本地”，点击“添加 → 手动添加”。',
    configInstruction: '添加下面的 JSON 配置；如果已有 jiejian，更新原条目，保留其他服务。',
    credentialInstruction: headerInstruction,
    restartInstruction: '保存并启用 jiejian，在本地 Agent 中启用该服务的工具；回到界鉴检查连接。',
    config: httpConfig(false), secretMode: 'header', source: 'https://docs.trae.cn/ide_add-mcp-servers',
  }
  if (client === 'codebuddy') return {
    label: 'CodeBuddy Code', description: '腾讯 CodeBuddy 的命令行开发 Agent，使用用户级 MCP 配置。',
    openLocation: '按 Win + R，输入 %USERPROFILE%\\.codebuddy，打开或新建 .mcp.json。',
    configInstruction: '合并下面的 jiejian 服务到 mcpServers，保留其他服务。CodeBuddy 优先读取 .mcp.json；如果已有旧 mcp.json，请一并保留原服务配置，避免新文件遮蔽旧配置。',
    credentialInstruction: headerInstruction,
    restartInstruction: '重新打开 CodeBuddy Code，用 /mcp 查看 jiejian 状态，再回到界鉴检查连接。',
    config: httpConfig(), secretMode: 'header', source: 'https://www.codebuddy.cn/docs/cli/mcp',
  }
  if (client === 'qoder') return {
    label: 'Qoder CLI', description: 'Qoder 命令行 Agent，通过 HTTP 连接本机界鉴。',
    openLocation: '按 Win + R，输入 %USERPROFILE%\\.qoder，打开或新建 settings.json。',
    configInstruction: '将下面的 jiejian 条目合并到 settings.json 的 mcpServers，保留已有设置。项目中若有同名服务，会覆盖用户级配置。',
    credentialInstruction: headerInstruction,
    restartInstruction: '在 Qoder CLI 中执行 /mcp reload，再用 /mcp 查看服务状态；回到界鉴检查连接。',
    config: httpConfig(), secretMode: 'header', source: 'https://docs.qoder.com/cli/mcp-reference',
  }
  if (client === 'codex') return {
    label: 'Codex', description: '通过 Streamable HTTP 连接本机界鉴。',
    openLocation: '打开 Codex 的 MCP 设置，或按 Win + R，输入 %USERPROFILE%\\.codex，打开 config.toml。',
    configInstruction: '添加下面的 jiejian 配置。已有同名服务时更新原条目，不重复添加。',
    credentialInstruction: '打开“开始”菜单，搜索 Windows PowerShell，粘贴复制的命令并执行，将凭据保存为当前用户的 JIEJIAN_MCP_TOKEN 环境变量。',
    restartInstruction: '完全退出 Codex 后重新打开，使客户端读取新配置与环境变量。',
    config: `[mcp_servers.jiejian]\nurl = ${JSON.stringify(endpoint)}\nbearer_token_env_var = "JIEJIAN_MCP_TOKEN"`,
    secretMode: 'environment', source: 'https://learn.chatgpt.com/docs/extend/mcp?surface=cli',
  }
  if (client === 'dsh') {
    const entry = `- id: mcp-jiejian\n  name: '@deepseek-ai/dsh-mcp-client'\n  config:\n    serverName: jiejian\n    transport: streamable-http\n    url: ${JSON.stringify(endpoint)}\n    headers:\n      Authorization: !!js '\`Bearer \${process.env.JIEJIAN_MCP_TOKEN}\`'`
    return {
    label: 'DSH', description: 'DeepSeek Harness 官方 MCP 客户端扩展。',
    openLocation: '打开当前 DSH profile 的 cordis.patch.yml：$DSH_HOME/profiles/<实际 profile 名>/cordis.patch.yml。使用哪个 profile，就修改哪个文件。',
    configInstruction: dshMode==='insert' ? '首次添加使用下面的 insert 块，追加到现有补丁列表。若已有 mcp-jiejian，请切换“更新原有条目”，避免重复添加。' : '在已有 insert 块内找到 mcp-jiejian，替换该条目的内容并保持原缩进；保留外层 insert 和其他条目。此片段不能单独作为 cordis.patch.yml 的新增补丁。',
    credentialInstruction: '打开 Windows PowerShell，执行复制的命令，保存当前用户的 JIEJIAN_MCP_TOKEN 环境变量。配置通过 !!js 读取它。',
    restartInstruction: '重新启动 DSH，使扩展读取新的环境变量和配置。',
    config: dshMode==='insert' ? `- insert:\n${entry.split('\n').map(line=>`    ${line}`).join('\n')}` : entry,
    secretMode: 'environment', source: 'https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md',
  }
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
