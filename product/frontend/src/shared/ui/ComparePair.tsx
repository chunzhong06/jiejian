import type {ReactNode} from 'react'

/** 前后内容相邻阅读；根据实际工作面宽度换行，不压缩成两列窄栏。 */
export function ComparePair({children,className=''}:{children:ReactNode;className?:string}){
  return <div className={'jj-compare-pair '+className}><div className="jj-compare-columns">{children}</div></div>
}
