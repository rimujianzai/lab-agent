"""本地开发启动脚本（推荐用它代替手敲 uvicorn 命令）。

    python dev.py            # 默认 8000 端口
    python dev.py 8010       # 指定端口
    python dev.py --kill     # 先清掉占着 8000 的残留进程，再启动
    python dev.py 8010 --kill

比 `uvicorn app.main:app --reload` 多做三件事：
1. 启动前检查端口，被占用时直接说清「是哪个进程、怎么杀」，
   而不是抛一句看不懂的 winerror 10048；
2. 专门识别 uvicorn --reload 在 Windows 上留下的「孤儿工作进程」——
   父进程被强杀后，multiprocessing.spawn 出来的子进程会活下来，
   它继承了监听 socket，于是端口一直被占着，netstat 里显示的还是那个
   已经不存在的父进程 PID，手动 taskkill 会提示「找不到进程」，很坑；
3. reload 只监听 app/ 目录，不监听 .venv/，避免装包时疯狂自动重载。
"""

from __future__ import annotations

import re
import socket
import subprocess
import sys
from pathlib import Path

import uvicorn

BACKEND_DIR = Path(__file__).resolve().parent

# 项目虚拟环境里的解释器。直接拿 PATH 里的全局 Python 跑本脚本（或手敲 uvicorn），
# 会在 import app.database 时报 ModuleNotFoundError: No module named 'pymysql'，
# 而且 --reload 模式下那段堆栈来自 spawn 出来的子进程，又长又难定位到底谁的问题。
VENV_PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"

# 列出所有 Python / uvicorn 相关进程：PID|进程名|命令行
PS_LIST_PROCESSES = (
    "Get-CimInstance Win32_Process | "
    "Where-Object { $_.Name -match 'python|uvicorn' } | "
    'ForEach-Object { "$($_.ProcessId)|$($_.Name)|$($_.CommandLine)" }'
)

# 只有这些进程才允许被 --kill 结束掉，避免误杀别的程序
KILLABLE_NAMES = ("python.exe", "pythonw.exe", "uvicorn.exe")


def check_interpreter() -> bool:
    """确认当前解释器就是项目 venv 里的那个。

    用系统全局 Python 启动时，报错发生在 uvicorn 的 spawn 子进程里，
    看起来像是项目代码出了问题，实际上只是没走虚拟环境。这里提前拦下来。
    """
    if not VENV_PYTHON.exists():
        print(f"[x] 没找到虚拟环境：{VENV_PYTHON}")
        print("    先创建虚拟环境并装依赖，再重新启动：")
        print("      python -m venv .venv")
        print(f"      {VENV_PYTHON} -m pip install -r requirements.txt")
        return False

    if Path(sys.executable).resolve() == VENV_PYTHON.resolve():
        return True

    print(f"[x] 当前解释器不是项目虚拟环境：{sys.executable}")
    print("    这个解释器里没装项目依赖，启动时会报")
    print("    ModuleNotFoundError: No module named 'pymysql'。")
    print("    请改用虚拟环境启动：")
    print(f"      {VENV_PYTHON} dev.py")
    return False


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _run(cmd: list[str]) -> str:
    """执行命令并返回 stdout；中文 Windows 上编码可能是 GBK，坏字符直接替换。"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        return result.stdout
    except Exception:
        return ""


def processes() -> list[tuple[int, str, str]]:
    """返回本机所有 python / uvicorn 进程的 (PID, 进程名, 命令行)。"""
    out = _run(["powershell", "-NoProfile", "-Command", PS_LIST_PROCESSES])
    procs: list[tuple[int, str, str]] = []
    for line in out.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        pid_text, name, cmdline = (p.strip() for p in parts)
        if pid_text.isdigit():
            procs.append((int(pid_text), name, cmdline))
    return procs


def port_owners(port: int) -> list[int]:
    """用 netstat 找出占用端口的 PID。

    注意：如果占用者是「孤儿工作进程」，这里返回的会是那个已经不存在的父进程 PID。
    """
    out = _run(["netstat", "-ano"])
    pids: set[int] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0].upper() != "TCP":
            continue
        if not parts[1].endswith(f":{port}") or not parts[-1].isdigit():
            continue
        pid = int(parts[-1])
        # PID 0 是内核的系统进程，不是真正的占用者，别显示出来吓人
        if pid > 0:
            pids.add(pid)
    return sorted(pids)


def orphan_workers() -> list[tuple[int, int]]:
    """找出 uvicorn --reload 留下的孤儿工作进程。

    uvicorn 在 Windows 上通过 multiprocessing.spawn 启动服务子进程，命令行形如
        python.exe -c "from multiprocessing.spawn import spawn_main; spawn_main(parent_pid=88708, ...)"
    只有当它的父进程已经不存在时，它才是「孤儿」——这时端口被它占着，
    而 netstat 显示的却是那个已经消失的父进程 PID。

    注意：服务正常运行时，父进程（reloader）是活着的，它的 spawn 子进程是**正常工作进程**，
    千万不能当成残留杀掉。
    """
    alive = {pid for pid, _, _ in processes()}
    workers: list[tuple[int, int]] = []
    for pid, _name, cmdline in processes():
        if "spawn_main" not in cmdline:
            continue
        match = re.search(r"parent_pid=(\d+)", cmdline)
        if not match:
            continue
        parent = int(match.group(1))
        # 只看父进程是否还活着；父进程活着 = 正常服务，不动它
        if parent not in alive:
            workers.append((pid, parent))
    return sorted(set(workers))


def collect_blockers(port: int) -> tuple[list[int], list[tuple[int, int]]]:
    return port_owners(port), orphan_workers()


def print_blockers(port: int, owners: list[int], orphans: list[tuple[int, int]]) -> None:
    alive = {pid for pid, _, _ in processes()}
    print(f"[x] 端口 {port} 已被占用，服务起不来（uvicorn 会报 winerror 10048）。")

    gone = [pid for pid in owners if pid not in alive]
    live = [pid for pid in owners if pid in alive]

    if gone:
        print("    netstat 显示占用者是 PID "
              + ", ".join(str(p) for p in gone)
              + "，但这些进程其实已经不存在了 ——")
        print("    它们留下的监听 socket 被下面的孤儿子进程继承着，端口才一直放不掉：")

    if orphans:
        for pid, parent in orphans:
            print(f"      PID {pid}（父进程 {parent} 已退出）  "
                  f"结束它：taskkill /PID {pid} /T /F")
        print("    一键清理： python dev.py --kill"
              + (f" {port}" if port != 8000 else ""))
    elif live:
        # 这些进程还活着，说明是「正在运行的服务」，不是残留，别乱杀
        print(f"    正在监听该端口的是正在运行的服务，进程：{', '.join(str(p) for p in live)}")
        print("    请到它自己的终端里按 Ctrl + C 正常退出；实在找不到那个终端，再执行：")
        for pid in live:
            print(f"      taskkill /PID {pid} /T /F")
        print("    （务必带 /T，否则会留下孤儿进程继续占着端口）")
    else:
        print("    没能定位到具体进程，可在任务管理器里结束残留的 python.exe。")

    print(f"    或者换个端口启动： python dev.py {port + 1}")


def kill_blockers(port: int) -> int:
    owners, orphans = collect_blockers(port)
    pids = {pid for pid, _ in orphans}
    alive_names = {pid: name for pid, name, _ in processes()}
    for pid in owners:
        if alive_names.get(pid, "").lower() in KILLABLE_NAMES:
            pids.add(pid)

    if not pids:
        print(f"[*] 端口 {port} 上没有发现可清理的残留进程。")
        return 0

    for pid in sorted(pids):
        print(f"[*] 结束进程 {pid} ...")
        _run(["taskkill", "/PID", str(pid), "/T", "/F"])
    return len(pids)


def main() -> int:
    # 中文 Windows 控制台默认是 GBK，输出中文提示可能报 UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    args = sys.argv[1:]
    do_kill = "--kill" in args
    args = [a for a in args if a != "--kill"]
    port = int(args[0]) if args else 8000
    host = "127.0.0.1"

    if do_kill:
        kill_blockers(port)
        # taskkill 之后 socket 需要一点时间回收
        import time

        for _ in range(20):
            if not port_in_use(host, port):
                break
            time.sleep(0.25)

    # 放在 --kill 之后：清理端口残留不需要项目依赖，用错解释器也照样能清
    if not check_interpreter():
        return 1

    if port_in_use(host, port):
        owners, orphans = collect_blockers(port)
        print_blockers(port, owners, orphans)
        return 1

    print(f"[*] 启动中：http://{host}:{port}   （接口文档 http://{host}:{port}/docs）")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=True,
        # 只监听业务代码，不监听 .venv
        reload_dirs=[str(BACKEND_DIR / "app")],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
