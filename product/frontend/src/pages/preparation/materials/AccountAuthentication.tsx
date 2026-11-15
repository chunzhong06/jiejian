import {useEffect,useState} from 'react'
import {testIdentitiesApi, type AuthenticationProfile, type TestIdentityDto} from '../../../entities/preparation/api/testIdentities'
import {Choice} from '../../../shared/ui/Choice'
import {TaskSurface} from '../../../shared/ui/TaskSurface'
import {Button} from '../../../shared/ui/actions'
import {Field,SectionHeading} from '../../../shared/ui/layout'
import {editorDraft,rememberEditorDraft,editorDraftGeneration,clearSubmittedDraft,useDraftProtection} from '../../../entities/runtime/model/handoff'
import {ErrorNote,Loading} from '../../../shared/ui/feedback'
import {useRead} from '../../../shared/lib/useRead'

const initialProfile = (): AuthenticationProfile => ({method:'BROWSER_SESSION',login_path:'/',username_field:'username',password_field:'password',token_path:['token'],verification:{path:'/api/me',subject_path:['id'],role_path:['role'],expected_subject:'',expected_role:''}})

export function AccountAuthentication({identity,onClose,onSaved}:{identity:TestIdentityDto;onClose:()=>void;onSaved:()=>void}) {
    const options = useRead('authentication-options:'+identity.identity_id, signal=>testIdentitiesApi.authenticationOptions(identity.identity_id,signal))
    // 非秘密配置草稿只在当前文档内接续；修订变化后重新核对已保存设置。
    const draftKey='account-auth:'+identity.identity_id+':'+identity.updated_at_us
    const [restored]=useState(()=>editorDraft<{profile:AuthenticationProfile;templateId?:string}>(draftKey,identity.project_id))
    const [edited,setEdited] = useState<AuthenticationProfile|undefined>(restored?.profile)
    const [templateId,setTemplateId] = useState<string|undefined>(restored?.templateId)
    const [busy,setBusy] = useState(false), [error,setError] = useState<unknown>()
    const templates = options.data?.templates ?? []
    const selected = templateId ?? (identity.authentication ? 'custom' : templates[0]?.identity_id ?? 'custom')
    const template = templates.find(item=>item.identity_id===selected)
    const value = edited ?? identity.authentication ?? (template ? {...template.profile,verification:{...template.profile.verification,expected_subject:'',expected_role:template.expected_role??''}} : initialProfile())
    useEffect(()=>{if(edited)rememberEditorDraft(draftKey,{profile:edited,templateId},identity.project_id)},[draftKey,identity.project_id,edited,templateId])
    useDraftProtection(Boolean(edited))
    const update = (next:Partial<AuthenticationProfile>) => setEdited({...value,...next})
    const verification = (label:string,key:keyof AuthenticationProfile['verification']) => <Field measure="standard" label={label}><input value={Array.isArray(value.verification[key])?(value.verification[key] as string[]).join('.'):value.verification[key]??''} onChange={event=>update({verification:{...value.verification,[key]:key.endsWith('_path')?event.target.value.split('.'):event.target.value}})}/></Field>
    const field = (label:string,key:'login_path'|'username_field'|'password_field') => <Field measure="standard" label={label}><input value={value[key]} onChange={event=>update({[key]:event.target.value})}/></Field>
    const ready = !options.loading&&Boolean(value.verification.expected_subject.trim()&&(value.principal_kind==='SERVICE'||value.verification.expected_role?.trim())&&value.verification.path.trim())
    return <TaskSurface width="wide" title="设置账号登录" context={identity.actor_display_name+' · '+identity.label} description="先确认要使用的账号身份，再核对登录与身份查询方式。密码或令牌在独立登录窗口中输入。" onBack={onClose} backLabel="返回账号核对" backDisabled={busy} actions={<><Button disabled={busy} onClick={()=>{rememberEditorDraft(draftKey,undefined);onClose()}}>取消</Button><Button kind="primary" disabled={!ready||Boolean(options.error)} busy={busy} onClick={async()=>{setBusy(true);const submitted=editorDraftGeneration(draftKey,identity.project_id);try{await testIdentitiesApi.configureAuthentication(identity,value);clearSubmittedDraft(draftKey,identity.project_id,submitted);onSaved();onClose()}catch(e){setError(e)}finally{setBusy(false)}}}>保存配置</Button></>}>
        {options.loading?<Loading>正在读取这个应用的登录设置</Loading>:<fieldset disabled={busy} className="jj-auth-configuration jj-auth-task">
            <section className="jj-auth-account"><SectionHeading title="确认这个账号的身份" level={2}/><p className="jj-small jj-muted">这里填写应用中的公开账号编号和角色值，用于核对实际登录身份。</p><div className="jj-form-grid">{verification('应用中的账号编号','expected_subject')}{value.verification.expected_role!==null&&verification('应用中的角色值','expected_role')}</div></section>
            <section className="jj-auth-method"><SectionHeading title="登录与核对方式" level={2}/>
            {!!templates.length&&<Field measure="standard" label="登录设置"><Choice value={selected} onValueChange={id=>{
                setTemplateId(id)
                const chosen=templates.find(item=>item.identity_id===id)
                setEdited(chosen?{...chosen.profile,verification:{...chosen.profile.verification,expected_subject:value.verification.expected_subject,expected_role:chosen.expected_role??value.verification.expected_role}}:{...value})
            }}>{templates.map(item=><option key={item.identity_id} value={item.identity_id}>沿用 {item.label} 的设置</option>)}<option value="custom">单独设置</option></Choice></Field>}
            <Field measure="standard" label="登录方式"><Choice value={value.method} onValueChange={method=>update({method:method as AuthenticationProfile['method'],token_path:method.startsWith('OAUTH2_')?['access_token']:['token'],oauth_client_id:method.startsWith('OAUTH2_')?value.oauth_client_id:null,oauth_scope:method.startsWith('OAUTH2_')?value.oauth_scope:null,...(method==='OAUTH2_CLIENT_CREDENTIALS'?{principal_kind:'SERVICE',verification:{...value.verification,role_path:[],expected_role:null}}:{})})}><option value="BROWSER_SESSION">在应用页面中登录</option><option value="BEARER">填写访问令牌（Bearer）</option><option value="API_LOGIN">通过接口提交账号和密码</option><option value="OAUTH2_CLIENT_CREDENTIALS">OAuth2 客户端凭据</option><option value="OAUTH2_REFRESH">OAuth2 刷新访问令牌</option></Choice></Field>
            {template?<dl className="jj-facts" data-layout="columns"><div><dt>登录位置</dt><dd>{value.method==='BEARER'?'单独录入访问令牌':value.login_path}</dd></div><div><dt>身份核对</dt><dd>{value.verification.path}</dd></div></dl>:<div className="jj-form-grid">{value.method!=='BEARER'&&field(value.method==='BROWSER_SESSION'?'登录页面地址':'登录或令牌接口路径','login_path')}{verification('核对当前账号的地址','path')}</div>}
            <Field measure="short" label="主体类型"><Choice measure="short" value={value.principal_kind??'USER'} onValueChange={kind=>update({principal_kind:kind as 'USER'|'SERVICE',verification:{...value.verification,role_path:kind==='SERVICE'?[]:['role'],expected_role:kind==='SERVICE'?null:''}})}><option value="USER">人员账号</option><option value="SERVICE">服务身份</option></Choice></Field>
            {value.method.startsWith('OAUTH2_')&&<div className="jj-form-grid"><Field measure="standard" label="客户端标识"><input value={value.oauth_client_id??''} onChange={event=>update({oauth_client_id:event.target.value||null})}/></Field><Field measure="standard" label="OAuth2 scope（可选）"><input value={value.oauth_scope??''} onChange={event=>update({oauth_scope:event.target.value||null})}/></Field><p className="jj-small jj-muted">令牌地址使用上方登录接口路径，限定在当前目标范围。客户端密钥或刷新令牌在独立窗口输入；更新后仍核验实际主体。</p></div>}
            </section>
            <details className="jj-auth-details"><summary>{template?'调整沿用的设置':'字段对应与接口细节'}</summary><div className="jj-form-grid">
                {template&&<>{value.method!=='BEARER'&&field(value.method==='BROWSER_SESSION'?'登录页面地址':'登录或令牌接口路径','login_path')}{verification('核对当前账号的地址','path')}</>}
                {verification('账号编号对应字段','subject_path')}{value.verification.expected_role!==null&&verification('角色对应字段','role_path')}
                {value.method==='API_LOGIN'&&<>{field('登录请求的账号字段','username_field')}{field('登录请求的密码字段','password_field')}<Field measure="standard" label="返回令牌的字段"><input value={value.token_path.join('.')} onChange={event=>update({token_path:event.target.value.split('.')})}/></Field></>}
            </div></details>
            {options.error&&<ErrorNote error={options.error} onRetry={options.reload} retryLabel="重新读取账号配置"/>}
            {Boolean(error)&&<ErrorNote error={error}/>}
        </fieldset>}
    </TaskSurface>
}

