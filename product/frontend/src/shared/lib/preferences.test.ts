import {expect,it,vi} from 'vitest'
import {readPreference,writePreference} from './preferences'
import {scopedPath} from './navigation'

it('拒绝读写时保持文档内的主题和应用选择，导航仍可明确归属',()=>{
  const get=vi.spyOn(Storage.prototype,'getItem').mockImplementation(()=>{throw new DOMException('denied','SecurityError')})
  const set=vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new DOMException('denied','SecurityError')})
  try{
    expect(readPreference('jiejian.studio.theme')).toBeNull()
    writePreference('jiejian.studio.theme','dark')
    writePreference('jiejian.studio.project','selected-app')
    expect(readPreference('jiejian.studio.theme')).toBe('dark')
    location.hash='#/workspace'
    expect(scopedPath('/permissions')).toBe('/permissions?project_id=selected-app')
    expect(scopedPath('/permissions?project_id=explicit')).toBe('/permissions?project_id=explicit')
  }finally{get.mockRestore();set.mockRestore()}
})

it('额度不足保留本次选择，恢复写入后继续采用持久值',()=>{
  const set=vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new DOMException('full','QuotaExceededError')})
  writePreference('jiejian.studio.theme','light')
  expect(readPreference('jiejian.studio.theme')).toBe('light')
  set.mockRestore()
  writePreference('jiejian.studio.theme','dark')
  localStorage.setItem('jiejian.studio.theme','light')
  expect(readPreference('jiejian.studio.theme')).toBe('light')
})
