import type { RegistrationPreview } from '../api/sourceChanges';
import './styles.css';
import { Badge } from '../../../shared/ui/feedback';

export function ChangePreview({ value }: { value: RegistrationPreview }) {
    return <section className="jj-change-preview"><header><h3>实际文件变化</h3><span className="jj-small jj-muted">{value.files.length} 个文件</span></header>{value.files.length ? <ul>{value.files.map(file => <li key={file.path}><Badge>{({ ADDED: '新增', MODIFIED: '修改', REMOVED: '删除' })[file.status]}</Badge><span className="jj-path">{file.path}</span></li>)}</ul> : <p className="jj-small jj-muted">与上一次登记相比，没有新的文件变化。</p>}</section>;
}
