// 已登记的界面状态统一衔接；只动画展示节点，不改写 React 内容、业务状态或焦点。
import { useEffect } from 'react'
import { metrics } from './tokens'

// 原十二类样稿的正式挂点；操作/选择勾形由 materials 与 useControlMotion 承接，浮层由 Ant Design 承接。
export const motionRegistry = {
  selection: '.module-navigation-list,.check-section-navigation,.boundary-view-tabs,.product-view-tabs,.result-detail-tabs,.result-review-views,.check-run-stages',
  copy: '.product-status,.editorial-heading-row h1,.boundary-action-heading h2,.ant-select-selection-item,.overview-task-copy h2,.proof-focus h2,.material-focus h2,.candidate-selection-row > div > p,.recording-capture-guide h2,.change-rule-association strong',
  preview: '.rule-sentence,.permission-rule-form > h2',
  list: '.light-table tbody,.history-records,.light-permission-list,.result-overview-table tbody,.material-table,.candidate-selection-list,.proof-checks ul,.identity-role-accounts',
  progress: '.flow-spine,.access-progress,.proof-stages,.check-activity-notice,.check-run-title,.check-run-count',
  notice: '.work-receipt,.task-receipt,.check-activity-toast,.notification-card,.agent-assist-message,.runtime-maintenance > .flow-feedback',
  invalid: '.ant-form-item-explain-error,[aria-invalid=true],.permission-rule-form .ant-alert',
  // 材料分组与协助入口保持挂载，关闭详情时也能从原高度衔接到收起状态。
  panel: '.result-investigation-body,.rule-detail-axes,.boundary-action-document,.changes-sample,.candidate-workspace,.check-run-focus,.change-rule-table,.change-basis,.material-group,.agent-assist-entry,.material-editor,.recording-capture,.repair-requirement-columns,.result-repair-comparison,.identity-login-steps,.provided-material-preparation,.light-registration',
  hoverRow: '.overview-entry,.history-record,.action-index button,.proof-index-item,.evidence-material-index > button,.supplemental-list > button,.result-overview-table tbody > tr,.light-table tbody > tr:has(button:not(:disabled),a[href]),.material-row,.change-rule-row:has(button:not(:disabled)),.permission-summary-row:has(button:not(:disabled)),.path-event-list button,.path-range button',
} as const

export function useProductMotion(mode: 'full' | 'soft' | 'off') {
  useEffect(() => {
    // 关闭动效时不安装观察器，也不为隐藏页面和静态内容持续测量布局。
    if (mode === 'off' || typeof Element.prototype.animate !== 'function') return
    const running = new Map<Element, Animation>()
    const copies = new WeakMap<Element, string>()
    const selections = new WeakMap<HTMLElement, Element>()
    const rows = new WeakMap<Element, Map<Element, {x:number;y:number}>>()
    const panels = new WeakMap<HTMLElement,{height:number;text:string}>()
    const hoverHosts = new Map<HTMLElement,HTMLElement>()
    const seen = new WeakSet<Element>()
    let frame = 0
    const visible = (node: Element) => !node.closest('[hidden],[inert]') && Boolean(node.getClientRects().length)
    const play = (node: Element, keyframes: Keyframe[], duration: number = metrics.motion.content, delay = 0) => {
      if (!visible(node)) return
      running.get(node)?.cancel()
      const animation = node.animate(mode === 'soft' ? [{opacity:.8},{opacity:1}] : keyframes,
        {duration:mode === 'soft' ? metrics.motion.fast : duration,delay:mode === 'soft' ? 0 : delay,easing:metrics.ease})
      running.set(node, animation)
      const finish = () => { if (running.get(node) === animation) running.delete(node) }
      animation.onfinish = finish; animation.oncancel = finish
    }
    const reveal = (node: Element, delay = 0) => play(node,[{opacity:.65,transform:'translateY(6px)'},{opacity:1,transform:'none'}],metrics.motion.content,delay)
    const scan = () => {
      frame = 0
      for (const [node, animation] of running) if (!node.isConnected || !visible(node)) { animation.cancel(); running.delete(node) }
      for (const [host,row] of hoverHosts) {
        if (!host.isConnected || !row.isConnected) { delete host.dataset.motionHover;hoverHosts.delete(host) }
        else if (row.matches(':hover') || row.contains(document.activeElement)) point(row)
        else host.style.setProperty('--row-opacity','0')
      }
      document.querySelectorAll<HTMLElement>(motionRegistry.selection).forEach(track => {
        const selected = track.querySelector<HTMLElement>('[aria-current=page],[aria-current=step],[aria-pressed=true],[aria-selected=true]')
        if (!selected || !visible(track)) return
        const outer = track.getBoundingClientRect(), rect = selected.getBoundingClientRect()
        const previous = selections.get(track)
        // 主导航保留自身定位线，只反馈新选中文字，避免整组导航随正文跳动。
        if (track.matches('.module-navigation-list')) {
          const label = selected.querySelector('.module-navigation-label')
          if (previous && previous !== selected && label) play(label,[{transform:'translateY(0)'},{transform:'translateY(-2px)',offset:.4},{transform:'translateY(0)'}],metrics.motion.selection)
          selections.set(track,selected)
          return
        }
        // 单一装饰线由 CSS 变量定位，React 子树保持原样；窗口缩放只重新对齐。
        track.style.setProperty('--selection-x',`${rect.left-outer.left+track.scrollLeft}px`)
        track.style.setProperty('--selection-width',`${rect.width}px`)
        track.dataset.motionTrack = 'true'
        if (previous && previous !== selected) reveal(selected)
        selections.set(track,selected)
      })
      document.querySelectorAll(`${motionRegistry.copy},${motionRegistry.preview},${motionRegistry.progress}`).forEach(node => {
        if (!visible(node)) return
        const value = node.textContent ?? '', before = copies.get(node)
        if (before !== undefined && value !== before) {
          if (node.matches('.ant-select-selection-item')) play(node,[{transform:'none'},{transform:'translateY(-1px)',offset:.4},{transform:'none'}],metrics.motion.copy)
          else reveal(node)
        }
        copies.set(node,value)
      })
      document.querySelectorAll<HTMLElement>(motionRegistry.panel).forEach(node=>{
        if (!visible(node)) return
        // 一个嵌套区域只由最外层登记面管理尺寸，避免父子同时拉伸造成正文交叠。
        if (node.parentElement?.closest(motionRegistry.panel)) return
        const text=node.textContent ?? '',previous=panels.get(node)
        if (previous?.text === text) return
        const moving=running.get(node),before=moving ? node.getBoundingClientRect().height : previous?.height
        moving?.cancel()
        const height=node.offsetHeight
        if (!previous) reveal(node)
        else if (mode==='full' && before && Math.abs(before-height)>1)
          play(node,[{height:`${before}px`,overflow:'clip'},{height:`${height}px`,overflow:'clip'}],metrics.motion.layout)
        else play(node,[{opacity:.75},{opacity:1}],metrics.motion.fast)
        panels.set(node,{height,text})
      })
      document.querySelectorAll(motionRegistry.list).forEach(list => {
        if (!visible(list)) return
        const previous = rows.get(list), next = new Map<Element,{x:number;y:number}>()
        const children = Array.from(list.children).filter(node=>!node.matches('.history-columns,.history-date,.material-table-head') && visible(node))
        const oldOrder = previous ? [...previous.keys()] : []
        const reordered = children.length !== oldOrder.length || children.some((node,index)=>node !== oldOrder[index])
        const outer=list.getBoundingClientRect()
        children.forEach((node,index) => {
          // 坐标相对当前列表，并扣除自身动画位移；上方页面重排不能被误当成行位置变化。
          const current=getComputedStyle(node).transform,matrix=current==='none' ? new DOMMatrixReadOnly() : new DOMMatrixReadOnly(current)
          const rect=node.getBoundingClientRect()
          const position = {x:rect.left-outer.left-matrix.m41,y:rect.top-outer.top-matrix.m42}, before = previous?.get(node)
          next.set(node,position)
          if (node.matches(motionRegistry.panel)) return
          if (!before) reveal(node,Math.min(index*28,112))
          else if (mode === 'full' && reordered && (Math.abs(before.x-position.x) + Math.abs(before.y-position.y) > 1)) {
            play(node,[{transform:`translate(${before.x+matrix.m41-position.x}px,${before.y+matrix.m42-position.y}px)`},{transform:'none'}],metrics.motion.layout)
          }
        })
        rows.set(list,next)
      })
      document.querySelectorAll(`${motionRegistry.notice},${motionRegistry.invalid}`).forEach(node => {
        if (seen.has(node) || !visible(node)) return
        seen.add(node)
        if (node.matches(motionRegistry.invalid)) play(node,[{opacity:.6},{opacity:1}],metrics.motion.copy)
        else reveal(node)
      })
    }
    const schedule = () => { if (!frame) frame = requestAnimationFrame(scan) }
    // 权限、历史和材料含分组包装；高亮属于整份可见清单，跨组仍用同一层衔接。
    const hoverHost = (row: HTMLElement) => row.closest<HTMLElement>('.light-permission-list,.history-records,.material-table') ?? row.parentElement
    const point = (row: HTMLElement) => {
      if (row.matches(':disabled,[aria-disabled=true]') || !visible(row)) return
      const host=hoverHost(row)
      if (!host) return
      const outer=host.getBoundingClientRect(),rect=row.getBoundingClientRect()
      host.dataset.motionHover='true';hoverHosts.set(host,row)
      for (const [key,value] of Object.entries({x:rect.left-outer.left-host.clientLeft,y:rect.top-outer.top-host.clientTop+host.scrollTop,width:rect.width,height:rect.height}))
        host.style.setProperty(`--row-${key}`,`${value}px`)
      host.style.setProperty('--row-opacity','1')
    }
    const enter = (event: Event) => { if (event.target instanceof Element) { const row=event.target.closest<HTMLElement>(motionRegistry.hoverRow);if(row)point(row) } }
    const leave = (event: Event) => {
      if (!(event.target instanceof Element)) return
      const row=event.target.closest<HTMLElement>(motionRegistry.hoverRow)
      const host=row ? hoverHost(row) : null
      const next=(event as MouseEvent | FocusEvent).relatedTarget
      // 标题、日期等非交互空隙也应退出高亮，不能只在离开整个列表时清除。
      const nextRow=next instanceof Element ? next.closest<HTMLElement>(motionRegistry.hoverRow) : null
      if (host && (!nextRow || hoverHost(nextRow) !== host || nextRow.matches(':disabled,[aria-disabled=true]'))) host.style.setProperty('--row-opacity','0')
    }
    const refreshIcon = (event: Event) => {
      const button=event.target instanceof Element ? event.target.closest('button:not(:disabled):not(.ant-btn-loading)') : null
      const icon=button?.querySelector('.anticon-reload,.anticon-sync')
      if (icon) play(icon,[{transform:getComputedStyle(icon).transform},{transform:'rotate(180deg)'}],metrics.motion.layout)
    }
    // 仅检查已登记节点；不观察 style，防止自身动画与定位产生递归扫描。
    const observer = new MutationObserver(records => {
      if (records.some(record => {
        if (record.attributeName === 'hidden') return true
        const target = record.target instanceof Element ? record.target : record.target.parentElement
        return target && !target.closest('[hidden],[inert]')
      })) schedule()
    })
    observer.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['aria-current','aria-selected','aria-pressed','aria-invalid','hidden']})
    window.addEventListener('resize',schedule)
    document.addEventListener('pointerover',enter);document.addEventListener('focusin',enter)
    document.addEventListener('pointerout',leave);document.addEventListener('focusout',leave)
    document.addEventListener('click',refreshIcon)
    schedule()
    return () => {
      observer.disconnect();window.removeEventListener('resize',schedule);cancelAnimationFrame(frame);running.forEach(animation=>animation.cancel())
      document.removeEventListener('pointerover',enter);document.removeEventListener('focusin',enter)
      document.removeEventListener('pointerout',leave);document.removeEventListener('focusout',leave);document.removeEventListener('click',refreshIcon)
      hoverHosts.forEach((_,host)=>{delete host.dataset.motionHover;host.style.removeProperty('--row-opacity')})
      document.querySelectorAll<HTMLElement>('[data-motion-track]').forEach(track=>{
        delete track.dataset.motionTrack;track.style.removeProperty('--selection-x');track.style.removeProperty('--selection-width')
      })
    }
  },[mode])
}
