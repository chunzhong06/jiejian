import { useEffect, useState } from 'react'
import { Alert, Button, Card, Checkbox, Drawer, Form, Input, InputNumber, List, Select, Space, Tag, Typography } from 'antd'
import { llmApi, LLMProfile, LLMProfileWrite, LLMProvider } from '../../api/llm'
import { ApiError } from '../../api/http'

const providerOptions: { label: string; value: LLMProvider }[] = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: 'Gemini', value: 'gemini' },
  { label: 'OpenAI-compatible', value: 'openai_compatible' },
]

type FormValues = LLMProfileWrite & { profile_name: string; provider: LLMProvider; model: string }

function statusLabel(profile: LLMProfile): string {
  if (profile.connection_status === 'testing') return '正在测试'
  if (!profile.secret_configured) return '未知'
  return {
    configured: '已配置',
    available: '可用',
    unavailable: '不可用',
    unknown: '未知',
  }[profile.connection_status]
}

export function LLMSettingsDrawer({
  open,
  profiles,
  onClose,
  onChanged,
  onError,
}: {
  open: boolean
  profiles: LLMProfile[]
  onClose: () => void
  onChanged: (profiles: LLMProfile[]) => void
  onError: (error: ApiError) => void
}) {
  const [form] = Form.useForm<FormValues>()
  const [editing, setEditing] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)

  const resetForm = () => {
    form.resetFields()
    form.setFieldsValue({
      profile_name: '', provider: 'openai', model: '', timeout_ms: 30000,
      max_input_bytes: 131072, max_output_bytes: 65536,
      max_budget_microusd: 1000000, enabled: true, allow_local_http: false,
      base_url: undefined, secret_ref: undefined, secret: undefined,
    })
    setEditing(null)
  }

  useEffect(() => { if (open && !editing) resetForm() }, [open])

  const loadProfile = (profile: LLMProfile) => {
    setEditing(profile.profile_name)
    form.setFieldsValue({
      profile_name: profile.profile_name,
      provider: profile.provider,
      model: profile.model,
      base_url: profile.base_url ?? undefined,
      timeout_ms: profile.timeout_ms,
      max_input_bytes: profile.max_input_bytes,
      max_output_bytes: profile.max_output_bytes,
      max_budget_microusd: profile.max_budget_microusd,
      enabled: profile.enabled,
      allow_local_http: profile.allow_local_http,
      secret_ref: profile.secret_ref?.startsWith('env:') ? profile.secret_ref : undefined,
      secret: undefined,
    })
  }

  const save = async (values: FormValues) => {
    if (values.secret && values.secret_ref) {
      form.setFields([{ name: 'secret', errors: ['API Key 与环境变量引用不能同时填写'] }])
      return
    }
    if (values.provider === 'openai_compatible' && !values.base_url) {
      form.setFields([{ name: 'base_url', errors: ['OpenAI-compatible 必须填写 Base URL'] }])
      return
    }
    if (values.base_url?.startsWith('http://')) {
      let localLoopback = false
      try {
        const hostname = new URL(values.base_url).hostname
        const octets = hostname.split('.').map(Number)
        localLoopback = hostname === '::1' || hostname === '[::1]' || (
          octets.length === 4 && octets[0] === 127 && octets.every((octet) => Number.isInteger(octet) && octet >= 0 && octet <= 255)
        )
      } catch { localLoopback = false }
      if (!values.allow_local_http || !localLoopback) {
        form.setFields([{ name: 'base_url', errors: ['HTTP 仅允许显式授权的本机回环地址'] }])
        return
      }
    }
    setSaving(true)
    try {
      const body: LLMProfileWrite = { ...values }
      if (editing) delete body.profile_name
      if (!body.secret) delete body.secret
      if (!body.secret_ref) delete body.secret_ref
      const result = editing ? await llmApi.update(editing, body) : await llmApi.create(body)
      form.setFieldValue('secret', undefined)
      const next = editing
        ? profiles.map((item) => item.profile_name === result.profile_name ? result : item)
        : [...profiles, result].sort((a, b) => a.profile_name.localeCompare(b.profile_name))
      onChanged(next)
      loadProfile(result)
      form.setFieldValue('secret', undefined)
    } catch (error) {
      form.setFieldValue('secret', undefined)
      onError(error as ApiError)
    } finally { setSaving(false) }
  }

  const test = async (profile: LLMProfile) => {
    setTesting(profile.profile_name)
    onChanged(profiles.map((item) => item.profile_name === profile.profile_name ? { ...item, connection_status: 'testing' } : item))
    try {
      const result = await llmApi.test(profile.profile_name)
      onChanged(profiles.map((item) => item.profile_name === result.profile_name ? result : item))
    } catch (error) {
      try {
        const refreshed = await llmApi.profile(profile.profile_name)
        onChanged(profiles.map((item) => item.profile_name === refreshed.profile_name ? refreshed : item))
      } catch {
        onChanged(profiles.map((item) => item.profile_name === profile.profile_name
          ? { ...item, connection_status: 'unknown', error_code: null, error_message: null }
          : item))
      }
      onError(error as ApiError)
    } finally { setTesting(null) }
  }

  return <Drawer
    title="模型服务"
    open={open}
    onClose={() => { form.setFieldValue('secret', undefined); resetForm(); onClose() }}
    width={520}
    destroyOnClose
  >
    <Space direction="vertical" style={{ width: '100%' }}>
      <List
        size="small"
        header="已保存 Profile"
        dataSource={profiles}
        locale={{ emptyText: '尚未配置模型服务，当前离线' }}
        renderItem={(profile) => <List.Item actions={[
          <Button size="small" onClick={() => loadProfile(profile)}>编辑</Button>,
          <Button size="small" loading={testing === profile.profile_name} disabled={testing !== null} onClick={() => void test(profile)}>测试连接</Button>,
        ]}>
          <Space direction="vertical" size={0}>
            <Space><span>{profile.profile_name}</span><Tag>{statusLabel(profile)}</Tag></Space>
            {profile.error_message && <Typography.Text type="secondary">{profile.error_code ? `${profile.error_code}: ` : ''}{profile.error_message}</Typography.Text>}
          </Space>
        </List.Item>}
      />
      <Card size="small" title={editing ? `编辑 ${editing}` : '新增 Profile'}>
        <Form form={form} layout="vertical" onFinish={save}>
          <Space.Compact block>
            <Form.Item name="profile_name" label="Profile 名称" rules={[{ required: true }, { pattern: /^[a-z][a-z0-9_-]{0,127}$/ }]} style={{ width: '50%' }}>
              <Input disabled={Boolean(editing)} />
            </Form.Item>
            <Form.Item name="provider" label="供应商" rules={[{ required: true }]} style={{ width: '50%' }}>
              <Select options={providerOptions} />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="model" label="模型" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="secret" label="API Key（只写入，不回显）"><Input.Password autoComplete="new-password" /></Form.Item>
          <Form.Item name="secret_ref" label="环境变量引用"><Input placeholder="env:NAME" /></Form.Item>
          <Form.Item name="base_url" label="Base URL"><Input placeholder="OpenAI-compatible 必填；默认仅 HTTPS" /></Form.Item>
          <Space.Compact block>
            <Form.Item name="timeout_ms" label="超时 ms"><InputNumber min={100} max={300000} style={{ width: '100%' }} /></Form.Item>
            <Form.Item name="max_input_bytes" label="最大输入字节"><InputNumber min={1} max={1048576} style={{ width: '100%' }} /></Form.Item>
            <Form.Item name="max_output_bytes" label="最大输出字节"><InputNumber min={1} max={1048576} style={{ width: '100%' }} /></Form.Item>
          </Space.Compact>
          <Form.Item name="max_budget_microusd" label="单次预算（微美元）"><InputNumber min={0} max={1000000000} style={{ width: '100%' }} /></Form.Item>
          <Space>
            <Form.Item name="enabled" valuePropName="checked"><Checkbox>允许候选生成使用</Checkbox></Form.Item>
            <Form.Item name="allow_local_http" valuePropName="checked"><Checkbox>允许本机回环 HTTP</Checkbox></Form.Item>
          </Space>
          <Alert type="info" showIcon message="LLM 只生成待审候选，不能直接激活契约或决定漏洞结论。" />
          <Space style={{ marginTop: 16 }}>
            <Button type="primary" htmlType="submit" loading={saving}>保存</Button>
            <Button onClick={resetForm}>清空</Button>
          </Space>
        </Form>
      </Card>
    </Space>
  </Drawer>
}

export default LLMSettingsDrawer
