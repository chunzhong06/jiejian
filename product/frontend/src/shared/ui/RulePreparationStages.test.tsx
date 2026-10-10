// 六步共用页首落点；后台刷新与隐藏页不能抢走正在阅读的位置。
import { render } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { WorkPageVisible } from '../runtime/visibility'
import { RulePreparationStages } from './RulePreparationStages'

beforeEach(() => {
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => { callback(0); return 1 })
  vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
})
afterEach(() => vi.restoreAllMocks())

it('六步切换统一回页首，同一步的内容刷新不重复定位', () => {
  const view = render(<RulePreparationStages phase={0} connectionPhase={0}/>)
  view.rerender(<RulePreparationStages phase={0} connectionPhase={1}/>)
  for (const phase of [0, 1, 2, 3]) view.rerender(<RulePreparationStages phase={phase}/>)
  expect(window.scrollTo).toHaveBeenCalledTimes(6)
  expect(window.scrollTo).toHaveBeenLastCalledWith({ top: 0, behavior: 'instant' })
  view.rerender(<RulePreparationStages phase={3} note="内容已刷新"/>)
  expect(window.scrollTo).toHaveBeenCalledTimes(6)
})

it('隐藏页不改变位置，返回工作面时从页首开始', () => {
  const view = render(<WorkPageVisible.Provider value={false}><RulePreparationStages phase={0}/></WorkPageVisible.Provider>)
  view.rerender(<WorkPageVisible.Provider value={false}><RulePreparationStages phase={2}/></WorkPageVisible.Provider>)
  expect(window.scrollTo).not.toHaveBeenCalled()
  view.rerender(<WorkPageVisible.Provider value><RulePreparationStages phase={2}/></WorkPageVisible.Provider>)
  expect(window.scrollTo).toHaveBeenCalledOnce()
})
