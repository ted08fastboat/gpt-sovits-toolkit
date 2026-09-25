import os, signal, sys, psutil

me = os.getpid()
targets = []
for p in psutil.process_iter(["pid", "cmdline"]):
    try:
        if p.info["pid"] == me:
            continue
        cl = p.info["cmdline"] or []
        # 只匹配真正以 webui.py 作为脚本参数启动的 python 进程
        if len(cl) >= 2 and cl[0].split("/")[-1].startswith("python") and any(a.endswith("webui.py") for a in cl[1:]):
            targets.append(p.info["pid"])
            os.kill(p.info["pid"], signal.SIGTERM)
    except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
        pass
print("killed pids:", targets)
