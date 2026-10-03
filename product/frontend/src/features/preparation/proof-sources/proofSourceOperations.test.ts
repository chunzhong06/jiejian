// 旧恢复定位继续可读，并只保存本项目的操作身份；损坏定位不形成新写请求。
import {afterEach,expect,it} from 'vitest'
import {clearProofOperation,readProofOperation,saveProofOperation,type PendingProofOperation} from './proofSourceOperations'

afterEach(() => sessionStorage.clear())

it('沿用原键读取旧记录并隔离项目',() => {
  const pending={kind:'GRANT_SCOPE',operation:'a'.repeat(32)}
  sessionStorage.setItem('jiejian-proof-operation:app_a',JSON.stringify(pending))
  expect(readProofOperation('app_a')).toEqual(pending)
  expect(readProofOperation('app_b')).toBeUndefined()
  clearProofOperation('app_b')
  expect(readProofOperation('app_a')).toEqual(pending)
})

it('新增的表单字段不会进入恢复存储',() => {
  const pending={kind:'SAVE_SOURCE',operation:'b'.repeat(32),draft:'编辑正文不属于操作定位'} as PendingProofOperation
  saveProofOperation('app_a',pending)
  expect(JSON.parse(sessionStorage.getItem('jiejian-proof-operation:app_a')!)).toEqual({kind:'SAVE_SOURCE',operation:'b'.repeat(32)})
  clearProofOperation('app_a')
  expect(readProofOperation('app_a')).toBeUndefined()
})

it('损坏和未知操作定位不用于恢复',() => {
  for (const value of ['{','null',JSON.stringify({kind:'UNKNOWN',operation:'c'.repeat(32)}),JSON.stringify({kind:'SAVE_SOURCE',operation:'short'})]) {
    sessionStorage.setItem('jiejian-proof-operation:app_a',value)
    expect(readProofOperation('app_a')).toBeUndefined()
  }
})
