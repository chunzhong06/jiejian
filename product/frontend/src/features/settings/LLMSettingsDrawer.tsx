// AI 辅助设置抽屉；普通配置只接触后端目录与能力，秘密只短暂驻留表单。

import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Checkbox, Collapse, Drawer, Form, Input, InputNumber, List, Select, Space, Switch, Tag } from 'antd'
import { llmApi, type AIAssistanceSettings, type LLMModelCatalog, type LLMProfile, type LLMProfileWrite, type LLMProvider } from '../../api/llm'
import { ApiError } from '../../api/http'
import MCPAccessCard from './MCPAccessCard'

const providerOptions: { label: string; value: LLMProvider }[] = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: 'Gemini', value: 'gemini' },
]
const advancedProviderOptions: { label: string; value: LLMProvider }[] = [
  ...providerOptions,
  { label: 'OpenAI-compatible（高级）', value: 'openai_compatible' },
]

type FormValues = LLMProfileWrite & { profile_name: string; provider: LLMProvider; model: string }

function statusLabel(profile: LLMProfile | undefined): string {
  if (!profile) return '未连接'
  if (profile.connection_status === 'testing') return '正在测试'
  if (!profile.secret_configured) return '未配置'
  return { configured: '已配置', available: '可用', unavailable: '不可用', unknown: '未知' }[profile.connection_status]
}

export function LLMSettingsDrawer({
  open, profiles, projects = [], aiSettings, onClose, onChanged, onSettingsChanged, onError,
}: {
  open: boolean
  profiles: LLMProfile[]
  projects?: { project_id: string; name?: string }[]
  aiSettings?: AIAssistanceSettings
  onClose: () => void
  onChanged: (profiles: LLMProfile[]) => void
  onSettingsChanged?: (settings: AIAssistanceSettings) => void
  onError: (error: ApiError) => void
}) {
  const [form] = Form.useForm<FormValues>()
  const [editing, setEditing] = useState<string | null>(null)
  const [catalog, setCatalog] = useState<LLMModelCatalog | null>(null)
  const [saving, setSaving] = useState(false)
  const [discovering, setDiscovering] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [enabled, setEnabled] = useState(aiSettings?.enabled ?? false)
  const initializedRef = useRef(false)
  const currentModel = Form.useWatch('model', form)

  useEffect(() => { setEnabled(aiSettings?.enabled ?? false) }, [aiSettings?.enabled])

  const resetForm = () => {
    form.resetFields()
    form.setFieldsValue({
      profile_name: 'assistant-default', provider: 'openai', model: '', reasoning_effort: null,
      timeout_ms: 30000, max_input_bytes: 131072, max_output_bytes: 65536,
      max_budget_microusd: 1000000, enabled: true, allow_local_http: false,
      base_url: undefined, secret_ref: undefined, secret: undefined,
    })
    setEditing(null); setCatalog(null); setAdvancedOpen(false)
  }

  const loadProfile = (profile: LLMProfile, openAdvanced = true) => {
    setEditing(profile.profile_name); setCatalog(null); setAdvancedOpen(openAdvanced)
    form.setFieldsValue({
      profile_name: profile.profile_name, provider: profile.provider, model: profile.model,
      reasoning_effort: profile.reasoning_effort, base_url: profile.base_url ?? undefined,
      timeout_ms: profile.timeout_ms, max_input_bytes: profile.max_input_bytes,
      max_output_bytes: profile.max_output_bytes, max_budget_microusd: profile.max_budget_microusd,
      enabled: profile.enabled, allow_local_http: profile.allow_local_http,
      secret_ref: profile.secret_ref?.startsWith('env:') ? profile.secret_ref : undefined, secret: undefined,
    })
  }

  useEffect(() => {
    if (!open) {
      initializedRef.current = false
      return
    }
    if (initializedRef.current) return
    const defaultProfile = aiSettings?.default_profile_name
      ? profiles.find((profile) => profile.profile_name === aiSettings.default_profile_name)
      : undefined
    if (aiSettings?.default_profile_name && !defaultProfile) return
    if (defaultProfile) loadProfile(defaultProfile, false)
    else resetForm()
    initializedRef.current = true
  }, [open, aiSettings?.default_profile_name, profiles])

  const startAdvancedProfile = () => {
    setEditing(null); setAdvancedOpen(true); setCatalog(null)
    form.setFieldsValue({
      profile_name: 'advanced-profile', provider: 'openai_compatible', model: '', reasoning_effort: null,
      timeout_ms: 30000, max_input_bytes: 131072, max_output_bytes: 65536,
      max_budget_microusd: 1000000, enabled: true, allow_local_http: false,
      base_url: undefined, secret_ref: undefined, secret: undefined,
    })
  }

  const changeAdvancedMode = (keys: string | string[]) => {
    const nextOpen = Array.isArray(keys) ? keys.includes('advanced') : keys === 'advanced'
    const defaultProfile = aiSettings?.default_profile_name
      ? profiles.find((profile) => profile.profile_name === aiSettings.default_profile_name)
      : undefined
    if (nextOpen) {
      if (defaultProfile) loadProfile(defaultProfile, true)
      else startAdvancedProfile()
    } else if (defaultProfile) {
      loadProfile(defaultProfile, false)
    } else {
      resetForm()
    }
  }

  const changeProvider = (provider: LLMProvider) => {
    setCatalog(null)
    form.setFieldsValue({
      model: '',
      reasoning_effort: null,
      ...(provider === 'openai_compatible' ? {} : { base_url: undefined, allow_local_http: false }),
    })
  }

  const discover = async () => {
    const values = form.getFieldsValue()
    if (!values.provider) return
    setDiscovering(true)
    try {
      // 新 Key 只在本次表单内短暂驻留；没有新 Key 时改用已保存 profile 的显式刷新。
      const result = values.secret
        ? await llmApi.discoverModels({
          provider: values.provider,
          secret: values.secret,
          ...(values.provider === 'openai_compatible' && values.base_url
            ? { base_url: values.base_url, allow_local_http: values.allow_local_http }
            : {}),
        })
        : editing
          ? await llmApi.refreshModels(editing)
          : null
      if (!result) return
      setCatalog(result)
      if (result.models[0] && !values.model) form.setFieldValue('model', result.models[0].model)
      form.setFieldValue('reasoning_effort', null)
    } catch (error) {
      form.setFieldValue('secret', undefined); onError(error as ApiError)
    } finally { setDiscovering(false) }
  }

  const save = async (values: FormValues) => {
    setSaving(true)
    try {
      const saveAsDefault = !advancedOpen
      const body: LLMProfileWrite = saveAsDefault
        ? {
          provider: values.provider,
          model: values.model,
          reasoning_effort: values.reasoning_effort ?? null,
          ...(values.secret ? { secret: values.secret } : {}),
        }
        : { ...values }
      if (saveAsDefault) delete body.profile_name
      else body.profile_name = editing ?? values.profile_name
      if (!values.secret) delete body.secret
      if (!values.secret_ref) delete body.secret_ref
      else delete body.secret
      const result = saveAsDefault
        ? await llmApi.saveDefault(body)
        : editing === null
          ? await llmApi.create(body)
          : await llmApi.update(editing ?? values.profile_name, { ...body, profile_name: editing ?? values.profile_name })
      form.setFieldValue('secret', undefined)
      const next = editing
        ? profiles.map((item) => item.profile_name === result.profile_name ? result : item)
        : [...profiles.filter((item) => item.profile_name !== result.profile_name), result].sort((a, b) => a.profile_name.localeCompare(b.profile_name))
      onChanged(next)
      const settings = await llmApi.settings()
      if (settings) onSettingsChanged?.(settings)
      loadProfile(result, !saveAsDefault); form.setFieldValue('secret', undefined)
    } catch (error) {
      form.setFieldValue('secret', undefined); onError(error as ApiError)
    } finally { setSaving(false) }
  }

  const toggle = async (nextEnabled: boolean) => {
    setEnabled(nextEnabled)
    try {
      const result = await llmApi.patchSettings({ enabled: nextEnabled, default_profile_name: aiSettings?.default_profile_name ?? profiles[0]?.profile_name ?? null })
      onSettingsChanged?.(result)
    } catch (error) { setEnabled(!nextEnabled); onError(error as ApiError) }
  }

  const test = async (profile: LLMProfile) => {
    setTesting(profile.profile_name)
    onChanged(profiles.map((item) => item.profile_name === profile.profile_name ? { ...item, connection_status: 'testing' } : item))
    try {
      const result = await llmApi.test(profile.profile_name)
      onChanged(profiles.map((item) => item.profile_name === result.profile_name ? result : item))
      if (!aiSettings?.default_profile_name) {
        const settings = await llmApi.patchSettings({ enabled: true, default_profile_name: result.profile_name })
        onSettingsChanged?.(settings)
      }
    } catch (error) {
      try {
        const refreshed = await llmApi.profile(profile.profile_name)
        onChanged(profiles.map((item) => item.profile_name === refreshed.profile_name ? refreshed : item))
      } catch {
        onChanged(profiles.map((item) => item.profile_name === profile.profile_name ? { ...item, connection_status: 'unknown', error_code: null, error_message: null } : item))
      }
      onError(error as ApiError)
    } finally { setTesting(null) }
  }

  const selectedModel = catalog?.models.find((item) => item.model === currentModel)
  const modelOptions = catalog?.models.map((item) => ({ label: item.display_name ? `${item.display_name}（${item.model}）` : item.model, value: item.model }))
    ?? (currentModel ? [{ label: currentModel, value: currentModel }] : [])
  const reasoningOptions = selectedModel?.reasoning_options.map((item) => ({ label: item, value: item })) ?? []
  const currentProfile = editing ? profiles.find((item) => item.profile_name === editing) : undefined

  return <Drawer className="llm-settings-drawer" title="AI 辅助" open={open} onClose={() => { form.setFieldValue('secret', undefined); initializedRef.current = false; resetForm(); onClose() }} width="min(600px, 100vw)" destroyOnClose>
    <Form className="llm-settings-form" form={form} layout="vertical" onFinish={save}>
      <div className="llm-settings-stack">
        <Alert type="info" showIcon message="AI 只在系统确定事实之上提供辅助，不能决定权限要求或检查结论。" />
        <MCPAccessCard open={open} projects={projects} onError={onError} />
        {!advancedOpen && <Card size="small" title="普通设置">
          <div className="llm-settings-section">
            <div className="llm-settings-toggle-row"><Switch checked={enabled} onChange={(value) => void toggle(value)} /><span>AI 辅助</span></div>
            <div className="llm-settings-fields">
              <Form.Item name="provider" label="供应商" rules={[{ required: true }]}><Select options={providerOptions} onChange={changeProvider} /></Form.Item>
              <Form.Item name="secret" label="API Key（只写入，不回显）"><Input.Password autoComplete="new-password" /></Form.Item>
            </div>
            <Button className="llm-settings-discover" loading={discovering} onClick={() => void discover()}>获取当前账号可用模型</Button>
            <div className="llm-settings-fields">
              <Form.Item name="model" label="模型" rules={[{ required: true }]}><Select options={modelOptions} disabled={!catalog} placeholder="先获取当前账号可用模型" /></Form.Item>
              <Form.Item name="reasoning_effort" label="推理强度"><Select allowClear options={[{ label: selectedModel?.reasoning_default_label ?? '跟随模型默认', value: '__default__' }, ...reasoningOptions]} onChange={(value) => { if (value === '__default__') form.setFieldValue('reasoning_effort', null) }} /></Form.Item>
            </div>
            <div className="llm-settings-actions"><Button type="primary" htmlType="submit" loading={saving}>保存并测试</Button><Tag>{statusLabel(currentProfile)}</Tag></div>
          </div>
        </Card>}
      <Collapse destroyOnHidden activeKey={advancedOpen ? ['advanced'] : []} onChange={changeAdvancedMode} items={[{
        key: 'advanced', label: '高级设置', children: advancedOpen ? <Space direction="vertical" style={{ width: '100%' }}>
          <Button onClick={startAdvancedProfile}>新增高级 profile</Button>
          <List size="small" header="已保存的模型服务" dataSource={profiles} locale={{ emptyText: '尚未配置模型服务' }} renderItem={(profile) => <List.Item actions={[<Button size="small" onClick={() => loadProfile(profile)}>编辑</Button>, <Button size="small" loading={testing === profile.profile_name} disabled={testing !== null} onClick={() => void test(profile)}>测试连接</Button>]}><Space><span>{profile.profile_name}</span><Tag>{statusLabel(profile)}</Tag></Space></List.Item>} />
          <Card size="small" title={editing ? `编辑 ${editing}` : '高级 profile 字段'}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Form.Item name="provider" label="供应商（高级）" rules={[{ required: true }]}><Select options={advancedProviderOptions} onChange={changeProvider} /></Form.Item>
              <Form.Item name="secret" label="API Key（只写入，不回显）"><Input.Password autoComplete="new-password" /></Form.Item>
              <Button type="primary" loading={discovering} onClick={() => void discover()}>获取当前账号可用模型</Button>
              <Form.Item name="profile_name" label="profile_name"><Input disabled={Boolean(editing)} /></Form.Item>
              <Form.Item name="model" label="model">
                {catalog?.manual_model_allowed ? <Input placeholder="兼容服务未提供模型目录，请手工填写" /> : <Select options={modelOptions} disabled={!catalog} placeholder="先获取当前账号可用模型" />}
              </Form.Item>
              <Form.Item name="reasoning_effort" label="推理强度"><Select allowClear options={[{ label: selectedModel?.reasoning_default_label ?? '跟随模型默认', value: '__default__' }, ...reasoningOptions]} onChange={(value) => { if (value === '__default__') form.setFieldValue('reasoning_effort', null) }} /></Form.Item>
              <Form.Item name="secret_ref" label="env: secret_ref"><Input placeholder="env:NAME" /></Form.Item>
              <Form.Item name="base_url" label="Base URL"><Input placeholder="OpenAI-compatible 必填" /></Form.Item>
              <Space.Compact block><Form.Item name="timeout_ms" label="timeout_ms"><InputNumber min={100} max={300000} /></Form.Item><Form.Item name="max_input_bytes" label="max_input_bytes"><InputNumber min={1} max={1048576} /></Form.Item><Form.Item name="max_output_bytes" label="max_output_bytes"><InputNumber min={1} max={1048576} /></Form.Item></Space.Compact>
              <Form.Item name="max_budget_microusd" label="budget"><InputNumber min={0} max={1000000000} style={{ width: '100%' }} /></Form.Item>
              <Space><Form.Item name="enabled" valuePropName="checked"><Checkbox>允许 AI 辅助使用</Checkbox></Form.Item><Form.Item name="allow_local_http" valuePropName="checked"><Checkbox>允许本机回环 HTTP</Checkbox></Form.Item></Space>
              <Button type="primary" htmlType="submit" loading={saving}>{editing ? '保存高级配置' : '创建高级 profile'}</Button>
            </Space>
          </Card>
        </Space> : null,
      }]} />
      </div>
    </Form>
  </Drawer>
}

export default LLMSettingsDrawer
