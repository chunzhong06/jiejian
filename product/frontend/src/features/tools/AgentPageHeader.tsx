// 客户端接入是修改与验证的次级配置，不提供另一套开发任务导航。
import { Button } from 'antd'
import { EditorialHeader } from '../../shared/ui/Editorial'
export function AgentPageHeader({onNavigate}:{ onNavigate: (path: string) => void }){
 return <><Button type="link" onClick={()=>onNavigate('/changes')}>← 返回修改与验证</Button><EditorialHeader eyebrow="修改与验证 / 客户端设置" title="连接与授权"><p className="editorial-muted">配置原来的开发客户端，让它在授权范围内读取规则、登记修改和获取检查事实。</p></EditorialHeader></>
}
