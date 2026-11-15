/** 持久录制已结束执行后停止轮询；待审阅仍保留人工确认，不等同于保存完成。 */
export const recordingEnded=(state:string|undefined)=>['COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'].includes(state??'')
export const recordingNeedsPolling=(state:string|undefined)=>Boolean(state)&&!recordingEnded(state)&&state!=='PENDING_REVIEW'
