// 仅为用户刚改变的选择提供反馈；不包装 React 文本节点，也不改写业务值和提交时序。
import { useEffect } from 'react'
import { metrics } from './tokens'

export function useControlMotion(motion: 'full' | 'soft' | 'off') {
  useEffect(() => {
    if (motion === 'off') return
    const running = new Map<Element, Animation>()
    const frames = new Set<number>()
    const marks = new Map<HTMLElement, ReturnType<typeof setTimeout>>()
    const onChange = (event: Event) => {
      const input = event.target
      if (!(input instanceof HTMLInputElement) || !['checkbox', 'radio'].includes(input.type) || input.disabled) return
      const label = input.closest('label')
      const caption = label?.querySelector<HTMLElement>('.ant-checkbox-label, .ant-radio-label, .ant-segmented-item-label, .choice-caption')
        ?? (label?.matches('.ant-radio-button-wrapper') ? label.querySelector<HTMLElement>('span:last-child') : null)
      if (!caption || !caption.animate) return
      running.get(caption)?.cancel()
      const previousMark = label?.querySelector<HTMLElement>('.ant-checkbox-inner,.ant-radio-inner')
      if (previousMark) { clearTimeout(marks.get(previousMark)); delete previousMark.dataset.choiceFeedback; marks.delete(previousMark) }
      // 等受控输入提交选中状态后再播放；快速反向取消旧动画，取消选中不重放上浮。
      const frame = requestAnimationFrame(() => {
        frames.delete(frame)
        if (!input.isConnected || !input.checked) return
        const animation = caption.animate(motion === 'full'
          ? [{ transform: 'translateY(0)' }, { transform: 'translateY(-2px)', offset: .4 }, { transform: 'translateY(0)' }]
          : [{ opacity: .78 }, { opacity: 1 }], { duration: motion === 'full' ? metrics.motion.selection : metrics.motion.fast, easing: metrics.ease })
        running.set(caption, animation)
        animation.onfinish = () => { if (running.get(caption) === animation) running.delete(caption) }
        const mark = label?.querySelector<HTMLElement>('.ant-checkbox-inner,.ant-radio-inner')
        if (mark && !input.indeterminate) {
          // 只动内部勾形，不旋转圆圈或方框；临时样式标记不参与 React 业务状态。
          mark.dataset.choiceFeedback = motion
          marks.set(mark, setTimeout(() => { delete mark.dataset.choiceFeedback; marks.delete(mark) }, metrics.motion.copy))
        }
      })
      frames.add(frame)
    }
    document.addEventListener('change', onChange)
    return () => { document.removeEventListener('change', onChange); frames.forEach(cancelAnimationFrame); running.forEach(animation => animation.cancel()); marks.forEach((timer, mark) => { clearTimeout(timer); delete mark.dataset.choiceFeedback }) }
  }, [motion])
}
