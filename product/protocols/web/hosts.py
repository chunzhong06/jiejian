"""本轮本机域名合同：仅 localhost 保留域名，其他主机仍须为 IPv4 字面量。"""
import ipaddress


def target_host(value: str) -> str:
    host = value.strip().lower()
    return host if host == 'localhost' else str(ipaddress.IPv4Address(host))


def target_address(host: str):
    """协议校验只认声明，不解析 DNS；实际解析和逐请求核验由运行边界负责。"""
    return ipaddress.IPv4Address('127.0.0.1' if host == 'localhost' else host)
