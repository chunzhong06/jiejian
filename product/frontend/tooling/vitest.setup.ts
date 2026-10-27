import '@testing-library/jest-dom/vitest'
import {cleanup} from '@testing-library/react'
import {afterEach,vi} from 'vitest'

afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();localStorage.clear();sessionStorage.clear()})
Object.defineProperty(window,'matchMedia',{writable:true,value:(query:string)=>({matches:false,media:query,onchange:null,addListener(){},removeListener(){},addEventListener(){},removeEventListener(){},dispatchEvent(){return false}})})
class ResizeObserverStub{observe(){}unobserve(){}disconnect(){}}
Object.defineProperty(globalThis,'ResizeObserver',{writable:true,value:ResizeObserverStub})
Object.defineProperty(window,'scrollTo',{writable:true,value:()=>{}})
Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(this:HTMLDialogElement){this.open=true}})
Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:function(this:HTMLDialogElement){this.open=false}})
const nativeStyle=window.getComputedStyle.bind(window)
window.getComputedStyle=(element:Element)=>nativeStyle(element)
