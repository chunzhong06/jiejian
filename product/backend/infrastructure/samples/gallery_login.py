# 官方展馆在独立登录进程中执行固定准备操作；Cookie 仍由原适配器写入 SecretStore，不进入结果正文。
import sys
from urllib.parse import urlsplit

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.identity.browser import IdentityPreparationBrowserAdapter
from product.backend.infrastructure.identity.process import execute_identity_preparation


class GalleryLoginAdapter(IdentityPreparationBrowserAdapter):
    """只为界鉴管理的本机示例登录固定账号，并在资源不存在时创建虚构资料。"""

    def __init__(self, account):
        if account not in {'curator', 'judge'}:
            raise ValueError('unsupported official account')
        self.account = account

    def run(self, request, **options):
        if urlsplit(request.target_scope.base_url).hostname != '127.0.0.1':
            raise JiejianError(ErrorCode.STATE_PRECONDITION, '自动准备仅适用于本机官方示例')

        def prepare(page):
            if options['cancellation_requested']():
                return
            owner = self.account == 'curator'
            origin = request.target_scope.base_url.rstrip('/')
            with page.expect_response(lambda response: response.url == origin + '/api/login') as login:
                page.get_by_role('button', name='负责人登录' if owner else '评审登录', exact=True).click()
            # 核对实际响应的身份；只有按钮点击或拿到 Cookie 都不能当作登录正确。
            response = login.value
            expected = {'id': self.account, 'role': 'owner' if owner else 'reviewer'}
            if response.status != 200 or response.json() != expected:
                raise JiejianError(ErrorCode.IDENTITY_PREPARATION_FAILED, '示例账号与实际登录身份不一致')
            if owner:
                resource = page.goto(origin + '/api/galleries/campus')
                if resource is not None and resource.status == 404:
                    page.goto(origin)
                    with page.expect_response(lambda response: response.url == origin + '/api/galleries') as created:
                        page.get_by_role('button', name='创建示例展馆', exact=True).click()
                    if created.value.status != 201:
                        raise JiejianError(ErrorCode.STATE_PRECONDITION, '示例资料创建未完成')
                    resource = page.goto(origin + '/api/galleries/campus')
                if resource is None or resource.status != 200 or resource.json() != {'resource_id': 'campus', 'owner_id': 'curator'}:
                    raise JiejianError(ErrorCode.STATE_PRECONDITION, '示例资源与负责人对应不一致')
            actual = page.goto(origin + '/api/me')
            if actual is None or actual.status != 200 or actual.json() != expected:
                raise JiejianError(ErrorCode.IDENTITY_PREPARATION_FAILED, '示例登录状态未能继续使用')

        # 用户已点击“使用已提供的测试材料”；固定配方成功后沿原保存、补偿和回读链完成。
        options.update(interaction=prepare, headless=True, save_requested=lambda: True)
        return super().run(request, **options)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {'curator', 'judge'}:
        return 64
    return execute_identity_preparation(stdin=sys.stdin.buffer, stdout=sys.stdout.buffer,
        stderr=sys.stderr, adapter=GalleryLoginAdapter(sys.argv[1]))


if __name__ == '__main__':
    raise SystemExit(main())
