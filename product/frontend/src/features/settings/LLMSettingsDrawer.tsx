// AI 辅助设置抽屉；只呈现单一默认模型连接，秘密只短暂驻留表单。

import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Drawer, Form, Input, Select, Switch, Tag } from 'antd'
import { llmApi, type AIAssistanceSettings, type LLMModelCatalog, type LLMProfile, type LLMProfileWrite, type LLMProvider } from '../../api/llm'
import { ApiError } from '../../api/http'

const providerOptions: { label: string; value: LLMProvider }[] = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: 'Gemini', value: 'gemini' },
]
type FormValues = LLMProfileWrite & { provider: LLMProvider; model: string }

function statusLabel(profile: LLMProfile | undefined): string {
  if (!profile) return '未连接'
  if (profile.connection_status === 'testing') return '正在测试'
  if (!profile.secret_configured) return '未配置'
  return { configured: '已配置', available: '可用', unavailable: '不可用', unknown: '未知' }[profile.connection_status]
}

export function LLMSettingsDrawer({
  open, profiles, aiSettings, onClose, onChanged, onSettingsChanged, onError,
}: {
  open: boolean
  profiles: LLMProfile[]
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
  const [enabled, setEnabled] = useState(aiSettings?.enabled ?? false)
  const initializedRef = useRef(false)
  const currentModel = Form.useWatch('model', form)

  useEffect(() => { setEnabled(aiSettings?.enabled ?? false) }, [aiSettings?.enabled])

  const resetForm = () => {
    form.resetFields()
    form.setFieldsValue({
      provider: 'openai', model: '', reasoning_effort: null, secret: undefined,
    })
    setEditing(null); setCatalog(null)
  }

  const loadProfile = (profile: LLMProfile) => {
    setEditing(profile.profile_name); setCatalog(null)
    form.setFieldsValue({
      provider: profile.provider, model: profile.model, reasoning_effort: null, secret: undefined,
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
    if (defaultProfile) loadProfile(defaultProfile)
    else resetForm()
    initializedRef.current = true
  }, [open, aiSettings?.default_profile_name, profiles])

  const changeProvider = (provider: LLMProvider) => {
    setCatalog(null)
    form.setFieldsValue({ model: '', reasoning_effort: null })
  }

  const discover = async () => {
    const values = form.getFieldsValue()
    if (!values.provider) return
    setDiscovering(true)
    try {
      // 新 Key 只在本次表单内短暂驻留；没有新 Key 时刷新已保存的默认连接。
      const result = values.secret
        ? await llmApi.discoverModels({ provider: values.provider, secret: values.secret })
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
      const body: LLMProfileWrite = {
        provider: values.provider,
        model: values.model,
        reasoning_effort: null,
        ...(values.secret ? { secret: values.secret } : {}),
      }
      const result = await llmApi.saveDefault(body)
      form.setFieldValue('secret', undefined)
      const next = [...profiles.filter((item) => item.profile_name !== result.profile_name), result]
      onChanged(next)
      const settings = await llmApi.settings()
      if (settings) onSettingsChanged?.(settings)
      loadProfile(result); form.setFieldValue('secret', undefined)
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

  const modelOptions = catalog?.models.map((item) => ({ label: item.display_name ? `${item.display_name}（${item.model}）` : item.model, value: item.model }))
    ?? (currentModel ? [{ label: currentModel, value: currentModel }] : [])
  const currentProfile = editing ? profiles.find((item) => item.profile_name === editing) : undefined

  return <Drawer className="llm-settings-drawer" title="AI 辅助" open={open} onClose={() => { form.setFieldValue('secret', undefined); initializedRef.current = false; resetForm(); onClose() }} width="min(600px, 100vw)" destroyOnClose>
    <Form className="llm-settings-form" form={form} layout="vertical" onFinish={save}>
      <div className="llm-settings-stack">
        <Alert type="info" showIcon message="AI 只在系统确定事实之上提供辅助，不能决定权限要求或检查结论。" />
        <Card size="small" title="连接模型服务">
          <div className="llm-settings-section">
            <div className="llm-settings-toggle-row"><Switch checked={enabled} onChange={(value) => void toggle(value)} /><span>AI 辅助</span></div>
            <div className="llm-settings-fields">
              <Form.Item name="provider" label="供应商" rules={[{ required: true }]}><Select options={providerOptions} onChange={changeProvider} /></Form.Item>
              <Form.Item name="secret" label="API Key（只写入，不回显）"><Input.Password autoComplete="new-password" /></Form.Item>
            </div>
            <Button className="llm-settings-discover" loading={discovering} onClick={() => void discover()}>获取当前账号可用模型</Button>
            <Form.Item name="model" label="模型" rules={[{ required: true }]}><Select options={modelOptions} disabled={!catalog} placeholder="先获取当前账号可用模型" /></Form.Item>
            <div className="llm-settings-actions"><Button type="primary" htmlType="submit" loading={saving}>保存并检查连接</Button><Tag>{statusLabel(currentProfile)}</Tag></div>
          </div>
        </Card>
      </div>
    </Form>
  </Drawer>
}

export default LLMSettingsDrawer
