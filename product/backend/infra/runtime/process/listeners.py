# 读取Windows内核TCP表确认监听地址与PID；端口可访问不等于属于本次受控进程。
import ctypes
from ctypes import wintypes
import os
import socket
import struct


def ipv4_listeners(port: int) -> tuple[tuple[str, int], ...]:
    """有界只读查询；非Windows或无法稳定取得表时失败，不用目标自报信息回退。"""
    if os.name != "nt" or type(port) is not int or not 1 <= port <= 65535:
        raise OSError("TCP ownership query unavailable")
    query = ctypes.WinDLL("iphlpapi", use_last_error=True).GetExtendedTcpTable
    query.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
        wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
    query.restype = wintypes.DWORD
    size = wintypes.DWORD(0)
    code = query(None, ctypes.byref(size), False, 2, 5, 0)
    if code not in (0, 122):
        raise OSError("TCP ownership query failed")
    for _ in range(3):
        if not 4 <= size.value <= 4 * 1024 * 1024:
            raise OSError("TCP ownership table exceeds budget")
        buffer = ctypes.create_string_buffer(size.value)
        code = query(buffer, ctypes.byref(size), False, 2, 5, 0)
        if code == 122:
            continue
        if code:
            raise OSError("TCP ownership query failed")
        count = struct.unpack_from("<I", buffer)[0]
        if 4 + count * 24 > len(buffer):
            raise OSError("TCP ownership table incomplete")
        result = []
        for index in range(count):
            state, address, local_port, _, _, pid = struct.unpack_from("<6I", buffer, 4 + index * 24)
            if state == 2 and socket.ntohs(local_port & 0xffff) == port:
                result.append((socket.inet_ntoa(address.to_bytes(4, "little")), pid))
        return tuple(result)
    raise OSError("TCP ownership table changed repeatedly")
