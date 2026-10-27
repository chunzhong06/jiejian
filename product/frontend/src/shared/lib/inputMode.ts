// 在浮层恢复焦点后，仍按当前输入方式区分悬停反馈与键盘焦点。
export function trackInputMode() {
  const root = document.documentElement
  const pointer = () => { root.dataset.inputMode = 'pointer' }
  const keyboard = (event: KeyboardEvent) => {
    if (!event.metaKey && !event.ctrlKey && !event.altKey && !['Shift', 'Control', 'Alt', 'Meta'].includes(event.key)) root.dataset.inputMode = 'keyboard'
  }
  document.addEventListener('pointerdown', pointer, true)
  document.addEventListener('pointermove', pointer, true)
  document.addEventListener('keydown', keyboard, true)
  return () => {
    document.removeEventListener('pointerdown', pointer, true)
    document.removeEventListener('pointermove', pointer, true)
    document.removeEventListener('keydown', keyboard, true)
    delete root.dataset.inputMode
  }
}
