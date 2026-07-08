#!/usr/bin/env python3
"""查看电脑系统配置（精简版，无需额外依赖）"""

import platform
import sys
import os
from datetime import datetime

def get_size(bytes):
    """字节转可读大小"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024

print("=" * 60)
print("         电脑系统配置信息")
print("=" * 60)
print(f"采集时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# 1. 系统信息
print("【系统信息】")
print(f"  操作系统: {platform.system()} {platform.release()}")
print(f"  系统版本: {platform.version()}")
print(f"  架构:     {platform.machine()}")
print(f"  处理器:   {platform.processor()}")
print(f"  主机名:   {platform.node()}")
print()

# 2. Python 信息
print("【Python 环境】")
print(f"  Python 版本: {sys.version}")
print(f"  解释器路径: {sys.executable}")
print()

# 3. 环境变量 PATH
print("【环境 PATH（前5个）】")
path = os.environ.get('PATH', '')
paths = path.split(os.pathsep)
for i, p in enumerate(paths[:5]):
    print(f"  {i+1}. {p}")
print()

# 4. 当前工作目录
print("【目录信息】")
print(f"  当前目录: {os.getcwd()}")
print(f"  脚本位置: {os.path.abspath(__file__)}")
print()

# 5. 磁盘使用情况（使用 os 模块）
print("【磁盘使用情况】")
if platform.system() == "Windows":
    import string
    from ctypes import c_ulonglong, windll, byref, create_unicode_buffer
    drives = []
    bitmask = windll.kernel32.GetLogicalDrives()
    for letter in string.ascii_uppercase:
        if bitmask & 1:
            drives.append(letter + ":\\")
        bitmask >>= 1
    for drive in drives:
        try:
            free_bytes = c_ulonglong(0)
            total_bytes = c_ulonglong(0)
            windll.kernel32.GetDiskFreeSpaceExW(
                drive, byref(free_bytes), byref(total_bytes), None
            )
            total = total_bytes.value
            free = free_bytes.value
            used = total - free
            if total > 0:
                pct = (used / total) * 100
                print(f"  {drive}")
                print(f"    总计: {get_size(total)}")
                print(f"    已用: {get_size(used)} ({pct:.1f}%)")
                print(f"    可用: {get_size(free)}")
        except:
            pass
else:
    # Unix: 使用 os.statvfs
    try:
        st = os.statvfs('/')
        total = st.f_frsize * st.f_blocks
        free = st.f_frsize * st.f_bavail
        used = total - free
        pct = (used / total) * 100
        print(f"  根目录 /")
        print(f"    总计: {get_size(total)}")
        print(f"    已用: {get_size(used)} ({pct:.1f}%)")
        print(f"    可用: {get_size(free)}")
    except:
        print("  (无法获取磁盘信息)")
print()

# 6. 运行时间
print("【进程信息】")
print(f"  进程ID: {os.getpid()}")
print()

print("=" * 60)
print("信息采集完毕！")
print("=" * 60)
