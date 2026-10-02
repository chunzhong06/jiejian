// 接入前说明完整证明所需条件；不读取目标、不根据技术栈名称假定已支持。
import { StatusBadge } from '../../shared/ui/StatusBadge'

export function ConnectionSupport() {
  return <section className="connection-support" aria-label="普通应用的验证条件">
    <div className="connection-support-heading"><h2>先了解这次接入需要什么</h2><StatusBadge kind="preparation" tone="neutral">接入条件</StatusBadge></div>
    <p>可以先保存权限约定。要完整验证自己的应用，还需要满足下面的条件；识别到源码不代表已经可以检查。</p>
    <dl>
      <div><dt>运行方式</dt><dd>当前支持本机 Node ESM 静态模块；先预览入口与依赖，再明确启动受控实例。</dd></div>
      <div><dt>资源读写</dt><dd>需要将受保护资源的实际读写接到通用记录组件。Agent 可以协助修改应用，这项接入有改造成本。</dd></div>
      <div><dt>由你完成</dt><dd>核对规则、准备真实账号与操作演示，并确认读取范围和证明来源的采用。</dd></div>
    </dl>
    <details><summary>查看当前支持边界</summary><p>完整证明覆盖所选资源的有限同步状态变化或 JSON 内容读取。任意外部数据库、文件、后台任务、异步队列和其他技术栈暂不在此范围内。</p><p>已有官方示例使用它自己的证明材料，可沿用官方流程。普通应用最终能否使用，以运行核对和真实预检查为准。</p></details>
  </section>
}
