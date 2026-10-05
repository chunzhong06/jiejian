// 入口搜索只导航到正式可达页面；材料入口使用当前检查已经支持的查询参数。
import { Input, Modal } from 'antd'
import { RightOutlined, SearchOutlined } from '@ant-design/icons'
import { useEffect, useMemo, useState } from 'react'

const entries = [
  { group: '当前应用', label: '应用总览', detail: '当前任务与已有事实', path: '/workspace' },
  { group: '当前应用', label: '权限约定', detail: '正式权限、角色与业务动作', path: '/permissions' },
  { group: '当前应用', label: '当前检查', detail: '核对范围并开始检查', path: '/tests' },
  { group: '当前应用', label: '检查材料', detail: '账号、资源、证明与恢复', path: '/tests?materials=1' },
  { group: '当前应用', label: '测试账号与登录', detail: '查看账号，准备登录状态', path: '/tests?materials=1&identities=1' },
  { group: '当前应用', label: '结果证明来源', detail: '核对实际业务结果的依据', path: '/tests?materials=1&proof_sources=1' },
  { group: '当前应用', label: '检查记录', detail: '已保存的检查和证据', path: '/history' },
  { group: '当前应用', label: '源码改动', detail: '源码变化及其对应检查', path: '/changes' },
  { group: '应用与工具', label: '应用与环境', detail: '应用实例、源码和官方示例', path: '/environment' },
  { group: '应用与工具', label: '接入新应用', detail: '选择本地项目并确认读取范围', path: '/application' },
  { group: '应用与工具', label: '开发工具连接', detail: '连接你正在使用的开发客户端', path: '/tools' },
  { group: '应用与工具', label: '界鉴运行', detail: '本工具的服务状态与维护', path: '/settings/system' },
]

export function EntrySearch({ open, onClose, onNavigate }: { open: boolean; onClose: () => void; onNavigate: (path: string) => void }) {
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const filtered = useMemo(() => entries.filter(item => `${item.label}${item.detail}${item.group}`.includes(query.trim())), [query])
  useEffect(() => { if (open) { setQuery(''); setActive(0) } }, [open])
  useEffect(() => { if (open) document.getElementById(`entry-option-${active}`)?.scrollIntoView?.({ block: 'nearest' }) }, [active, open])
  const choose = (path: string) => { onClose(); onNavigate(path) }
  return <Modal open={open} onCancel={onClose} footer={null} title="查找入口" width={600} className="entry-search" destroyOnHidden afterOpenChange={shown => { if (shown) document.getElementById('entry-search-input')?.focus() }}>
    <Input id="entry-search-input" aria-label="查找入口" placeholder="如：测试账号、检查记录、证明来源" prefix={<SearchOutlined />} value={query}
      role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls="entry-search-results" aria-activedescendant={filtered.length ? `entry-option-${active}` : undefined}
      onChange={event => { setQuery(event.target.value); setActive(0) }} onKeyDown={event => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); setActive(value => filtered.length ? (value + (event.key === 'ArrowDown' ? 1 : -1) + filtered.length) % filtered.length : 0) }
        if (event.key === 'Enter' && filtered[active]) { event.preventDefault(); choose(filtered[active].path) }
      }} />
    <div id="entry-search-results" role="listbox" aria-label="可用入口" className="entry-search-results">
      {filtered.map((item, index) => <div key={item.path} role="presentation">
        {filtered[index - 1]?.group !== item.group && <p className="entry-search-group" aria-hidden="true">{item.group}</p>}
        <button id={`entry-option-${index}`} type="button" role="option" tabIndex={-1} aria-selected={active === index} className="entry-search-choice" onMouseMove={() => setActive(index)} onClick={() => choose(item.path)}>
          <span><strong>{item.label}</strong><small>{item.detail}</small></span><RightOutlined aria-hidden="true" />
        </button>
      </div>)}
    </div>
    {!filtered.length && <p role="status" className="entry-search-empty">没有找到这个入口，试试“材料”或“源码”。</p>}
    <footer className="entry-search-footer">↑ ↓ 选择<span>Enter 进入 · Esc 关闭</span></footer>
  </Modal>
}
