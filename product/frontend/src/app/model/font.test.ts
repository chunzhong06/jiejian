import {afterEach,expect,it,vi} from 'vitest'
import {selectDocumentFont} from './font'

afterEach(()=>{vi.useRealTimers();delete document.documentElement.dataset.uiFont;delete (document as unknown as {fonts?:unknown}).fonts})

it('字体及时就绪时在挂载前选择统一字型',async()=>{
  Object.defineProperty(document,'fonts',{configurable:true,value:{load:vi.fn().mockResolvedValue([{}])}})
  await selectDocumentFont()
  expect(document.documentElement.dataset.uiFont).toBe('misans')
})

it('字体迟到时保持本次文档后备字型，不在菜单出现时再替换',async()=>{
  vi.useFakeTimers()
  let finish!:(faces:object[])=>void
  Object.defineProperty(document,'fonts',{configurable:true,value:{load:()=>new Promise(resolve=>{finish=resolve})}})
  const selected=selectDocumentFont()
  await vi.advanceTimersByTimeAsync(100)
  await selected
  expect(document.documentElement.dataset.uiFont).toBe('system')
  finish([{}])
  await Promise.resolve()
  await selectDocumentFont()
  expect(document.documentElement.dataset.uiFont).toBe('system')
})
