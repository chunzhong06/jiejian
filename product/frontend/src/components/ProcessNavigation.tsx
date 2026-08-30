// 连续流程导航：直接展示后端统一产品状态中的六步事实，route 只表示当前焦点。

import { CheckCircleFilled, HomeOutlined, MenuOutlined } from '@ant-design/icons'
import { Button, Drawer, Typography } from 'antd'
import { useRef, useState } from 'react'
import type { ProductStatusDto } from '../api/projects'
import { processSteps, type AppRoute, type ProcessRoute, type ProcessStepState } from '../app/presentation'

type ProductSteps = ProductStatusDto['steps'] | null

function processState(value: ProductStatusDto['steps'][number]['status'] | undefined): ProcessStepState {
  if (value === 'COMPLETE') return 'complete'
  if (value === 'CURRENT') return 'current'
  return 'upcoming'
}

function ProcessList({ route, steps, onNavigate }: {
  route: AppRoute
  steps: ProductSteps
  onNavigate: (path: AppRoute) => void
}) {
  return <>
    <div className="process-workspace-group">
      <Button className={`process-workspace-link${route === '/workspace' ? ' is-selected' : ''}`} type="text" icon={<HomeOutlined />} aria-current={route === '/workspace' ? 'page' : undefined} onClick={() => onNavigate('/workspace')}>工作台</Button>
    </div>
    <div className="process-flow-group">
      <Typography.Text className="process-group-title">检查流程</Typography.Text>
      <ol className="process-step-list">
        {processSteps.map((step, index) => {
          const backendStep = steps?.find((item) => item.route === step.route)
          const state = processState(backendStep?.status ?? (index === 0 ? 'CURRENT' : undefined))
          const selected = route === step.route
          return <li className={`process-step is-${state}${selected ? ' is-selected' : ''}`} key={step.route}>
            <button type="button" className="process-step-button" aria-current={selected ? 'page' : undefined} onClick={() => onNavigate(step.route)}>
              <span className="process-step-marker" aria-hidden="true">{state === 'complete' ? <CheckCircleFilled /> : index + 1}</span>
              <span className="process-step-copy"><span className="process-step-label">{step.label}</span><span className="process-step-state">{backendStep?.status_label ?? (state === 'current' ? '当前步骤' : '尚未开始')}</span></span>
            </button>
          </li>
        })}
      </ol>
    </div>
  </>
}

export function DesktopProcessNavigation({ route, steps, onNavigate }: {
  route: AppRoute
  steps: ProductSteps
  onNavigate: (path: AppRoute) => void
}) {
  return <aside className="process-navigation" aria-label="界鉴主导航">
    <div className="product-brand"><strong>界鉴</strong><span>安全意图一致性验证</span></div>
    <nav aria-label="安全检查流程"><ProcessList route={route} steps={steps} onNavigate={onNavigate} /></nav>
  </aside>
}

export function MobileProcessNavigation({ route, steps, onNavigate }: {
  route: AppRoute
  steps: ProductSteps
  onNavigate: (path: AppRoute) => void
}) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const recommended = (steps?.find((step) => step.status === 'CURRENT')?.route ?? '/application') as ProcessRoute
  const currentIndex = processSteps.findIndex((step) => step.route === (processSteps.some((item) => item.route === route) ? route : recommended))
  const summary = route.startsWith('/settings/') ? '设置' : currentIndex >= 0 ? `第 ${currentIndex + 1}/6 步 · ${processSteps[currentIndex].label}` : '安全检查流程'
  const navigateFromDrawer = (path: AppRoute) => { setOpen(false); onNavigate(path) }
  return <>
    <div className="mobile-process-summary">
      <Button ref={triggerRef} type="text" icon={<MenuOutlined />} aria-label="打开检查流程" onClick={() => setOpen(true)} />
      <Typography.Text strong>{route === '/workspace' ? '工作台' : summary}</Typography.Text>
    </div>
    <Drawer
      className="process-drawer"
      title="界鉴检查流程"
      placement="left"
      width={320}
      open={open}
      onClose={() => setOpen(false)}
      afterOpenChange={(isOpen) => {
        if (isOpen) (document.querySelector('.process-drawer .process-step.is-current .process-step-button') as HTMLElement | null)?.focus()
        else triggerRef.current?.focus()
      }}
    >
      <nav aria-label="安全检查流程"><ProcessList route={route} steps={steps} onNavigate={navigateFromDrawer} /></nav>
    </Drawer>
  </>
}
