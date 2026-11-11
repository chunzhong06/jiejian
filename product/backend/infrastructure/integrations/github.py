"""GitHub工单元数据适配；不重试创建、不跟随重定向，不把上游正文带入异常。"""
from __future__ import annotations

import httpx
import time

from product.backend.domain.errors import ErrorCode, JiejianError


class GitHubIssues:
    def __init__(self, *, transport=None):
        self.transport = transport

    def _request(self, method, repository, token, *, page=None, body=None):
        deadline=time.monotonic()+12
        with httpx.Client(transport=self.transport, trust_env=False, follow_redirects=False,
                          timeout=httpx.Timeout(10, connect=5)) as client:
            with client.stream(method, 'https://api.github.com/repos/'+repository+'/issues',
                headers={'Authorization':'Bearer '+token, 'Accept':'application/vnd.github+json',
                         'X-GitHub-Api-Version':'2022-11-28', 'User-Agent':'JieJian'},
                params=None if page is None else {'state':'all','sort':'created','direction':'desc','per_page':100,'page':page},
                json=body) as response:
                if response.status_code >= 400:
                    # 只有确定的请求拒绝才作为已知失败；5xx可能发生在创建成功之后。
                    if 400 <= response.status_code < 500:
                        error=JiejianError(ErrorCode.STATE_PRECONDITION,'GitHub拒绝了工单请求，请核对仓库权限或请求额度',
                            details={'upstream_status':response.status_code})
                        # 明确的权限/额度拒绝不应被协作恢复器显示成未知；不会自动重试创建。
                        raise error.not_accepted() if response.status_code in (403,429) else error
                    raise RuntimeError('GitHub outcome unknown')
                if response.status_code not in {200,201}:
                    raise RuntimeError('GitHub outcome unknown')
                data=bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data)>4*1024*1024 or time.monotonic()>deadline:
                        raise RuntimeError('GitHub response exceeds budget')
                import json
                return json.loads(data)

    @staticmethod
    def receipt(repository, value, marker):
        if not isinstance(value,dict) or 'pull_request' in value or marker not in (value.get('body') or ''):
            raise RuntimeError('GitHub association not verified')
        number=value.get('number')
        expected='https://github.com/'+repository+'/issues/'+str(number)
        if type(number) is not int or number<1 or value.get('html_url','').casefold()!=expected.casefold():
            raise RuntimeError('GitHub receipt identity invalid')
        return {'repository':repository,'number':number,'url':value['html_url'],
                'remote_state':'closed' if value.get('state')=='closed' else 'open',
                'boundary':'远端工单状态不改变界鉴的权限结论或修复状态'}

    def create(self, repository, token, title, body, marker):
        value=self._request('POST',repository,token,body={'title':title,'body':body+'\n\n'+marker})
        return self.receipt(repository,value,marker)

    def reconcile(self, repository, token, marker):
        # 无匹配不能证明没有创建，分页预算耗尽也不能触发另一次POST。
        found=[]
        for page in range(1,6):
            values=self._request('GET',repository,token,page=page)
            if not isinstance(values,list):raise RuntimeError('GitHub association response invalid')
            for value in values:
                if isinstance(value,dict) and marker in (value.get('body') or '') and 'pull_request' not in value:
                    found.append(self.receipt(repository,value,marker))
            if len(values)<100:break
        if len(found)>1:
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'找到多个原工单标记，请人工核对；不会重复创建')
        return found[0] if found else None
