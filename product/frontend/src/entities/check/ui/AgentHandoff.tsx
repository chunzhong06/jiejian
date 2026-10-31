import { useState } from 'react';
import type { RepairReference } from '../api/repairs';
import { Button } from '../../../shared/ui/actions';
import { Notice } from '../../../shared/ui/feedback';
import { Dialog } from '../../../shared/ui/Dialog';

export function AgentHandoff({ projectId, runId, caseId, targets = [], repair = false, onClose }: {
    projectId: string; runId: string; caseId?: string|null; targets?: RepairReference[]; repair?: boolean; onClose: () => void;
}) {
    const [copied, setCopied] = useState(false), [error, setError] = useState(false);
    const request = `请${repair ? '协助修复下面指定的权限问题' : '解读下面指定的界鉴检查报告'}。\nproject_id=${projectId}\nrun_id=${runId}${caseId ? '\ncase_id=' + caseId : ''}\n报告入口：#/reports?run_id=${runId}${caseId ? '&case_id=' + caseId : ''}\n先用 jiejian_result_show 读取这一轮记录，用 jiejian_evidence_show 核对引用证据。不得用最近一次检查代替指定报告。\n${targets.length ? '原题引用：' + JSON.stringify(targets) + '\n' : ''}用 jiejian_repair_show 按原题引用读取要求，再仅携带 project_id 读取当前问题历史。分别说明原违规是否消除、正常操作及相关功能是否保留；证明条件变化或缺少证据时明确指出。\n${repair ? '按证据定位并提出修复，保持已批准的权限要求。修改完成后读取 jiejian_change_registration_preview，以稳定 operation_id 调用 jiejian_change_register，一次登记实际涉及的 rule_targets。回执未知时查询原操作，不另建重复修改。预览材料影响与准确原题复验范围，经用户确认后执行。' : '先解释结果和下一步，不自动修改源码、权限、材料或提交检查。'}\n提交说明不代表修复完成；只有原题及正常功能的确定性复验可以验收修复。`;
    return <Dialog title={repair ? '交给 Agent 修复' : '交给 Agent 解读'} onClose={onClose} actions={dismiss => <><Button onClick={dismiss}>关闭</Button><Button kind="primary" onClick={() => void navigator.clipboard.writeText(request).then(() => { setCopied(true); setError(false); }).catch(() => setError(true))}>{copied ? '已复制请求' : '复制请求'}</Button></>}>
        <p>将请求粘贴到已连接界鉴的开发工具。请求固定本次报告、原问题和正常功能要求。</p>
        {copied && <Notice tone="positive">已复制，尚未发送给 Agent。</Notice>}{error && <Notice>复制未完成，可展开请求手动复制。</Notice>}
        <details><summary>查看请求内容</summary><pre>{request}</pre></details>
    </Dialog>;
}
