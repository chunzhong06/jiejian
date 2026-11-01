import {useState} from 'react'
import {testIdentitiesApi, type AuthenticationProfile, type TestIdentityDto} from '../../../entities/preparation/api/testIdentities'
import {Choice} from '../../../shared/ui/Choice'
import {Dialog} from '../../../shared/ui/Dialog'
import {Button} from '../../../shared/ui/actions'
import {Field} from '../../../shared/ui/layout'
import {ErrorNote,Loading} from '../../../shared/ui/feedback'
import {useRead} from '../../../shared/lib/useRead'

const initialProfile = (): AuthenticationProfile => ({method:'BROWSER_SESSION',login_path:'/',username_field:'username',password_field:'password',token_path:['token'],verification:{path:'/api/me',subject_path:['id'],role_path:['role'],expected_subject:'',expected_role:''}})

export function AccountAuthentication({identity,onClose,onSaved}:{identity:TestIdentityDto;onClose:()=>void;onSaved:()=>void}) {
    const options = useRead('authentication-options:'+identity.identity_id, signal=>testIdentitiesApi.authenticationOptions(identity.identity_id,signal))
    const [edited,setEdited] = useState<AuthenticationProfile>()
    const [templateId,setTemplateId] = useState<string>()
    const [busy,setBusy] = useState(false), [error,setError] = useState<unknown>()
    const templates = options.data?.templates ?? []
    const selected = templateId ?? (identity.authentication ? 'custom' : templates[0]?.identity_id ?? 'custom')
    const template = templates.find(item=>item.identity_id===selected)
    const value = edited ?? identity.authentication ?? (template ? {...template.profile,verification:{...template.profile.verification,expected_subject:'',expected_role:template.expected_role??''}} : initialProfile())
    const update = (next:Partial<AuthenticationProfile>) => setEdited({...value,...next})
    const verification = (label:string,key:keyof AuthenticationProfile['verification']) => <Field label={label}><input value={Array.isArray(value.verification[key])?(value.verification[key] as string[]).join('.'):value.verification[key]} onChange={event=>update({verification:{...value.verification,[key]:key.endsWith('_path')?event.target.value.split('.'):event.target.value}})}/></Field>
    const field = (label:string,key:'login_path'|'username_field'|'password_field') => <Field label={label}><input value={value[key]} onChange={event=>update({[key]:event.target.value})}/></Field>
    const ready = !options.loading&&Boolean(value.verification.expected_subject.trim()&&value.verification.expected_role.trim()&&value.verification.path.trim())
    return <Dialog title="设置账号登录" onClose={onClose} actions={dismiss=><><Button disabled={busy} onClick={dismiss}>取消</Button><Button kind="primary" disabled={!ready} busy={busy} onClick={async()=>{setBusy(true);try{await testIdentitiesApi.configureAuthentication(identity,value);onSaved();dismiss()}catch(e){setError(e)}finally{setBusy(false)}}}>保存配置</Button></>}>
        {options.loading?<Loading>正在读取这个应用的登录设置</Loading>:<div className="jj-auth-configuration">
            <div className="jj-item-heading"><h3>{identity.label}</h3><span className="jj-muted">{identity.actor_display_name}</span></div>
            {!!templates.length&&<Field label="登录设置"><Choice value={selected} onValueChange={id=>{
                setTemplateId(id)
                const chosen=templates.find(item=>item.identity_id===id)
                setEdited(chosen?{...chosen.profile,verification:{...chosen.profile.verification,expected_subject:value.verification.expected_subject,expected_role:chosen.expected_role??value.verification.expected_role}}:{...value})
            }}>{templates.map(item=><option key={item.identity_id} value={item.identity_id}>沿用 {item.label} 的设置</option>)}<option value="custom">单独设置</option></Choice></Field>}
            <Field label="登录方式"><Choice value={value.method} onValueChange={method=>update({method:method as AuthenticationProfile['method']})}><option value="BROWSER_SESSION">在应用页面中登录</option><option value="BEARER">填写访问令牌（Bearer）</option><option value="API_LOGIN">通过接口提交账号和密码</option></Choice></Field>
            {template?<dl className="jj-auth-reused jj-facts is-stacked"><div><dt>登录位置</dt><dd>{value.method==='BEARER'?'单独录入访问令牌':value.login_path}</dd></div><div><dt>身份核对</dt><dd>{value.verification.path}</dd></div></dl>:<div className="jj-form-grid">{value.method!=='BEARER'&&field(value.method==='API_LOGIN'?'登录接口地址':'登录页面地址','login_path')}{verification('核对当前账号的地址','path')}</div>}
            <section className="jj-auth-account"><h3>确认这个账号的身份</h3><div className="jj-form-grid">{verification('应用中的账号编号','expected_subject')}{verification('应用中的角色值','expected_role')}</div></section>
            <details className="jj-auth-details"><summary>{template?'调整沿用的设置':'字段对应与接口细节'}</summary><div className="jj-form-grid">
                {template&&<>{value.method!=='BEARER'&&field(value.method==='API_LOGIN'?'登录接口地址':'登录页面地址','login_path')}{verification('核对当前账号的地址','path')}</>}
                {verification('账号编号对应字段','subject_path')}{verification('角色对应字段','role_path')}
                {value.method==='API_LOGIN'&&<>{field('登录请求的账号字段','username_field')}{field('登录请求的密码字段','password_field')}<Field label="返回令牌的字段"><input value={value.token_path.join('.')} onChange={event=>update({token_path:event.target.value.split('.')})}/></Field></>}
            </div></details>
            <p className="jj-small jj-muted">密码或令牌在下一步的独立登录窗口中输入。保存设置后，仍会核对实际登录身份。</p>
            {options.error&&<ErrorNote error={options.error} onRetry={options.reload}/>}
            {Boolean(error)&&<ErrorNote error={error}/>}
        </div>}
    </Dialog>
}

