#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPT-SoVITS Windows 一键安装器（轻量包：脚本 + 权重；依赖与模型联网下载）

用法：双击「安装.bat」，或在本目录执行  python install.py

流程：
  1. 下载 GPT-SoVITS 源码（GitHub 代理优先，失败回退直连）
  2. 建虚拟环境 venv
  3. 装依赖（torch 分 CPU / CUDA；pip 源自动在清华镜像与官方之间回退）
  4. 下载中文推理所需预训练模型（hf-mirror 优先）+ G2PW + 语种检测模型 + nltk 数据
  5. 放入微调音色权重（老母狮）并写 weight.json（默认加载）
  6. 生成启动脚本（WebUI / 一键克隆 / 批量克隆）、自检合成一次
"""
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(os.path.expanduser("~"), "GPT-SoVITS")

REPO_ZIPS = [
    "https://gh-proxy.com/https://github.com/RVC-Boss/GPT-SoVITS/archive/refs/heads/main.zip",
    "https://ghfast.top/https://github.com/RVC-Boss/GPT-SoVITS/archive/refs/heads/main.zip",
    "https://github.com/RVC-Boss/GPT-SoVITS/archive/refs/heads/main.zip",
]
HF_MIRRORS = ["https://hf-mirror.com", "https://huggingface.co"]
PIP_MIRRORS = [
    ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
    ["-i", "https://mirrors.aliyun.com/pypi/simple"],
    [],
]
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
TORCH_CN_INDEX = "https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/cu121"

# 老母狮微调权重（版本 = v2Pro）
WEIGHT_CKPT = "laomushi-e20.ckpt"
WEIGHT_PTH = "laomushi_v2_e16.pth"

# 需要下载的模型（相对 lj1995/GPT-SoVITS 仓库）
MODEL_FILES = [
    "chinese-hubert-base/config.json",
    "chinese-hubert-base/preprocessor_config.json",
    "chinese-hubert-base/pytorch_model.bin",
    "chinese-roberta-wwm-ext-large/config.json",
    "chinese-roberta-wwm-ext-large/pytorch_model.bin",
    "chinese-roberta-wwm-ext-large/tokenizer.json",
    "gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt",
    "gsv-v2final-pretrained/s2G2333k.pth",
    "s1v3.ckpt",
    "v2Pro/s2Gv2Pro.pth",
    "v2Pro/s2Gv2ProPlus.pth",
    "sv/pretrained_eres2netv2w24s4ep4.ckpt",
]
# 额外素材：G2PWModel.zip、nltk_data.zip、lid.176.bin
EXTRA_BASE = "XXXXRT/GPT-SoVITS-Pretrained"
FASTTEXT_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin"

REQUIREMENTS = [
    "numpy<2.0", "scipy", "tensorboard", "librosa==0.10.2", "numba",
    "pytorch-lightning>=2.4", "gradio<5", "ffmpeg-python", "onnxruntime",
    "cn2an", "pypinyin", "g2p_en", "sentencepiece",
    "transformers>=4.51,<5", "peft<0.18.0", "chardet", "PyYAML", "psutil",
    "jieba", "split-lang", "fast_langdetect>=0.3.1", "wordsegment",
    "rotary_embedding_torch", "opencc", "fastapi[standard]==0.115.6",
    "starlette==0.41.3", "x_transformers", "torchmetrics<=1.5",
    "pydantic<=2.10.6", "ctranslate2>=4.0,<5", "av>=11", "imageio-ffmpeg",
]
OPTIONAL_REQUIREMENTS = ["funasr>=1.3.7", "modelscope"]

LAUNCHER_WEBUI = r"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
title GPT-SoVITS WebUI
set "PATH=%CD%\venv\Scripts;%PATH%"
set "PYTHONPATH=%CD%;%CD%\GPT_SoVITS"
set "HF_ENDPOINT=https://hf-mirror.com"
set "NLTK_DATA=%CD%\nltk_data"
set "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1"
set "GRADIO_ANALYTICS_ENABLED=False"
set "language=zh_CN"
echo ============================================================
echo  GPT-SoVITS WebUI  http://127.0.0.1:9874
echo  首次加载模型 1~2 分钟；关闭本窗口即停止服务
echo ============================================================
venv\Scripts\python.exe -I webui.py zh_CN
pause
"""

LAUNCHER_API = r"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
title GPT-SoVITS API
set "PATH=%CD%\venv\Scripts;%PATH%"
set "PYTHONPATH=%CD%;%CD%\GPT_SoVITS"
set "HF_ENDPOINT=https://hf-mirror.com"
set "NLTK_DATA=%CD%\nltk_data"
set "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1"
set "language=zh_CN"
echo API 文档: http://127.0.0.1:9880/docs
venv\Scripts\python.exe -I api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml
pause
"""

LAUNCHER_CLONE = r"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
title GPT-SoVITS 一键克隆
set "PATH=%CD%\venv\Scripts;%PATH%"
set "PYTHONPATH=%CD%;%CD%\GPT_SoVITS"
set "HF_ENDPOINT=https://hf-mirror.com"
set "NLTK_DATA=%CD%\nltk_data"
set "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1"
"venv\Scripts\python.exe" clone_win.py
pause
"""

LAUNCHER_UI = r"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 声音工坊 · GPT-SoVITS UI
set "PATH=%CD%;%CD%\venv\Scripts;%PATH%"
set "PYTHONPATH=%CD%;%CD%\GPT_SoVITS"
set "REPO_ROOT=%CD%"
set "REF_DIR=%CD%\参考音频"
set "OUT_DIR=%CD%\输出音频"
set "HF_ENDPOINT=https://hf-mirror.com"
set "NLTK_DATA=%CD%\nltk_data"
set "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1"
set "version=v2Pro"
set "PRELOAD=1"
echo ============================================================
echo  声音工坊（网页界面） http://127.0.0.1:8000
echo  首次启动要加载模型，约 1 分钟；关闭本窗口即停止服务
echo ============================================================
start "" cmd /c "timeout /t 8 >nul & start http://127.0.0.1:8000"
cd /d "%~dp0ui"
"%~dp0venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000
pause
"""

LAUNCHER_BATCH = r"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
title GPT-SoVITS 批量克隆
set "PATH=%CD%\venv\Scripts;%PATH%"
set "PYTHONPATH=%CD%;%CD%\GPT_SoVITS"
set "HF_ENDPOINT=https://hf-mirror.com"
set "NLTK_DATA=%CD%\nltk_data"
set "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1"
"venv\Scripts\python.exe" clone_win.py --batch
pause
"""


def log(msg=""):
    print(msg, flush=True)


def banner(msg):
    log("")
    log("=" * 64)
    log("  " + msg)
    log("=" * 64)


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.1f%s" % (n, unit)
        n /= 1024.0


def download(url, dest, retries=3, timeout=60):
    """带重试与进度显示的下载。"""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(1, retries + 1):
        tmp = dest + ".part"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                last = 0.0
                with open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if total and time.time() - last > 3:
                            last = time.time()
                            pct = done * 100.0 / total
                            print("\r    %s  %5.1f%%  (%s / %s)" % (os.path.basename(dest), pct, human(done), human(total)), end="", flush=True)
                if total and os.path.getsize(tmp) != total:
                    raise IOError("大小不符：%s != %s" % (os.path.getsize(tmp), total))
            if total:
                print("\r    %s  100.0%%  (%s)          " % (os.path.basename(dest), human(os.path.getsize(tmp))))
            os.replace(tmp, dest)
            return True
        except Exception as e:  # noqa: BLE001
            print("\r    [!] 第 %d 次下载失败：%s        " % (attempt, e))
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            time.sleep(3)
    return False


def download_any(urls, dest):
    for u in urls:
        if download(u, dest):
            return True
    return False


def run(cmd, cwd=None, check=True, env=None):
    log("  $ " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=cwd, env=env)
    if check and r.returncode != 0:
        raise RuntimeError("命令失败(%d)：%s" % (r.returncode, " ".join(cmd)))
    return r.returncode


def pip_install(py, args, optional=False):
    for extra in PIP_MIRRORS:
        cmd = [py, "-m", "pip", "install", "--disable-pip-version-check"] + extra + args
        if run(cmd, check=False) == 0:
            return True
        log("  [!] 该 pip 源失败，换下一个源重试…")
    if optional:
        log("  [!] 可选依赖安装失败，跳过（不影响中文合成）")
        return False
    raise RuntimeError("依赖安装失败：%s" % " ".join(args))


def unzip(zip_path, out_dir):
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)


# --------------------------------------------------------------------------
def step_repo():
    banner("步骤 1/6：下载 GPT-SoVITS 源码")
    if os.path.exists(os.path.join(TARGET, "webui.py")):
        log("  已存在源码，跳过：%s" % TARGET)
        return
    if os.path.exists(TARGET):
        log("  目标目录已存在但内容不完整，备份为 GPT-SoVITS.bak-<时间>")
        os.rename(TARGET, TARGET + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
    tmp_zip = os.path.join(HERE, "_repo.zip")
    if not download_any(REPO_ZIPS, tmp_zip):
        raise RuntimeError("源码下载失败，请检查网络（或手动下载 GPT-SoVITS 解压到 %s）" % TARGET)
    log("  解压源码…")
    unzip(tmp_zip, HERE)
    extracted = os.path.join(HERE, "GPT-SoVITS-main")
    if not os.path.isdir(extracted):
        cands = [d for d in os.listdir(HERE) if d.startswith("GPT-SoVITS") and os.path.isdir(os.path.join(HERE, d)) and d != "_repo"]
        if not cands:
            raise RuntimeError("解压后找不到源码目录")
        extracted = os.path.join(HERE, cands[0])
    os.rename(extracted, TARGET)
    os.remove(tmp_zip)
    log("  ✅ 源码已就绪：%s" % TARGET)


def step_jieba_shim():
    src = os.path.join(HERE, "jieba_fast")
    if os.path.isdir(src):
        dst = os.path.join(TARGET, "jieba_fast")
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        log("  ✅ 已放置 jieba_fast 兼容层（免编译）")


def step_venv():
    banner("步骤 2/6：创建 Python 虚拟环境")
    py = os.path.join(TARGET, "venv", "Scripts", "python.exe")
    if os.path.exists(py):
        log("  已存在 venv，跳过")
        return py
    run([sys.executable, "-m", "venv", os.path.join(TARGET, "venv")])
    run([py, "-m", "pip", "install", "--disable-pip-version-check", "-U", "pip", "setuptools", "wheel"], check=False)
    log("  ✅ venv 就绪：%s" % py)
    return py


def step_deps(py, use_cuda):
    banner("步骤 3/6：安装依赖（torch 等，约 1~2GB）")
    if use_cuda:
        log("  已选择 CUDA 版 torch（需要 NVIDIA 显卡）")
        pip_install(py, ["torch==2.6.0", "torchaudio==2.6.0"])
    else:
        log("  使用 CPU 版 torch（体积小；有 NVIDIA 显卡可重跑并选择 CUDA）")
        ok = run([py, "-m", "pip", "install", "--disable-pip-version-check",
                  "--index-url", TORCH_CPU_INDEX, "torch==2.6.0", "torchaudio==2.6.0"], check=False) == 0
        if not ok:
            log("  [!] CPU 源不可用，回退到普通源安装（会带 CUDA 运行时，体积更大）")
            pip_install(py, ["torch==2.6.0", "torchaudio==2.6.0"])
    log("  正在安装其余依赖…")
    pip_install(py, REQUIREMENTS)
    log("  安装可选依赖（ASR，失败不影响合成）…")
    pip_install(py, OPTIONAL_REQUIREMENTS, optional=True)
    log("  ✅ 依赖安装完成")


def step_models():
    banner("步骤 4/6：下载预训练模型（约 3GB，走 hf-mirror）")
    pm = os.path.join(TARGET, "GPT_SoVITS", "pretrained_models")
    os.makedirs(pm, exist_ok=True)

    def fetch(rel_mirror_path, dest):
        if os.path.exists(dest) and os.path.getsize(dest) > 1024:
            log("  已存在，跳过：%s" % os.path.basename(dest))
            return True
        enc = urllib.parse.quote(rel_mirror_path)
        urls = ["%s/lj1995/GPT-SoVITS/resolve/main/%s" % (m, enc) for m in HF_MIRRORS]
        if not download_any(urls, dest):
            raise RuntimeError("模型下载失败：%s" % rel_mirror_path)
        return True

    for rel in MODEL_FILES:
        log("  -> %s" % rel)
        fetch(rel, os.path.join(pm, rel))

    # G2PWModel（中文多音字消歧，必需）
    g2pw_dir = os.path.join(TARGET, "GPT_SoVITS", "text", "G2PWModel")
    if not os.path.isdir(g2pw_dir):
        log("  -> G2PWModel.zip（约 590MB）")
        z = os.path.join(HERE, "_G2PWModel.zip")
        if not download_any(["%s/%s/resolve/main/G2PWModel.zip" % (m, EXTRA_BASE) for m in HF_MIRRORS], z):
            raise RuntimeError("G2PWModel 下载失败（中文合成必需）")
        log("     解压中…")
        unzip(z, os.path.join(TARGET, "GPT_SoVITS", "text"))
        os.remove(z)
        if not os.path.isdir(g2pw_dir):
            for d in os.listdir(os.path.join(TARGET, "GPT_SoVITS", "text")):
                if d.lower().startswith("g2pw"):
                    os.rename(os.path.join(TARGET, "GPT_SoVITS", "text", d), g2pw_dir)
                    break

    # 语种检测模型（LangSegmenter 必需）
    lid = os.path.join(pm, "fast_langdetect", "lid.176.bin")
    if not os.path.exists(lid):
        log("  -> lid.176.bin（语种检测，约 130MB）")
        if not download_any([FASTTEXT_URL], lid):
            log("  [!] lid.176.bin 下载失败，中文合成可能报错；可稍后重跑安装器补齐")

    # NLTK 数据（英文 G2P 备用）
    if not os.path.isdir(os.path.join(TARGET, "nltk_data")):
        log("  -> nltk_data.zip（约 10MB）")
        z = os.path.join(HERE, "_nltk_data.zip")
        if download_any(["%s/%s/resolve/main/nltk_data.zip" % (m, EXTRA_BASE) for m in HF_MIRRORS], z):
            unzip(z, TARGET)
            os.remove(z)
    log("  ✅ 模型就绪")


def step_weights():
    banner("步骤 5/6：安装音色权重（老母狮 v2Pro）+ 生成启动脚本")
    wdir = os.path.join(HERE, "权重")
    gpt_dir = os.path.join(TARGET, "GPT_weights_v2Pro")
    sovits_dir = os.path.join(TARGET, "SoVITS_weights_v2Pro")
    os.makedirs(gpt_dir, exist_ok=True)
    os.makedirs(sovits_dir, exist_ok=True)

    ckpts = [f for f in os.listdir(wdir) if f.endswith(".ckpt")] if os.path.isdir(wdir) else []
    pths = [f for f in os.listdir(wdir) if f.endswith(".pth")] if os.path.isdir(wdir) else []
    for f in ckpts:
        shutil.copy2(os.path.join(wdir, f), os.path.join(gpt_dir, f))
    for f in pths:
        shutil.copy2(os.path.join(wdir, f), os.path.join(sovits_dir, f))
    ckpt_name = ckpts[0] if ckpts else WEIGHT_CKPT
    pth_name = pths[0] if pths else WEIGHT_PTH
    log("  GPT 权重 : %s" % ckpt_name)
    log("  SoVITS权重: %s" % pth_name)

    # weight.json：让 WebUI 启动即加载这套权重
    import json
    wj = os.path.join(TARGET, "weight.json")
    data = {"GPT": {}, "SoVITS": {}}
    if os.path.exists(wj):
        try:
            data = json.load(open(wj, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    data.setdefault("GPT", {})["v2Pro"] = "GPT_weights_v2Pro/" + ckpt_name
    data.setdefault("SoVITS", {})["v2Pro"] = "SoVITS_weights_v2Pro/" + pth_name
    json.dump(data, open(wj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log("  ✅ 已写入 weight.json（v2Pro 默认用这套权重）")

    # 参考音频 / 台词 / 合成脚本
    for name in ("参考音频", "输出音频"):
        src = os.path.join(HERE, name)
        dst = os.path.join(TARGET, name)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
    # 网页界面（声音工坊）
    ui_src = os.path.join(HERE, "ui")
    if os.path.isdir(ui_src):
        ui_dst = os.path.join(TARGET, "ui")
        if os.path.exists(ui_dst):
            shutil.rmtree(ui_dst)
        shutil.copytree(ui_src, ui_dst)
        log("  ✅ 已安装网页界面：%s" % ui_dst)
    else:
        log("  [!] 包内没有 ui 目录，跳过网页界面")

    for f in ("tts_clone.py", "clone_win.py", "台词.txt", "使用说明.txt"):
        src = os.path.join(HERE, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(TARGET, f))

    # ffmpeg.exe（来自 imageio-ffmpeg，供格式转换/UVR5 使用）
    try:
        py = os.path.join(TARGET, "venv", "Scripts", "python.exe")
        r = subprocess.run([py, "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
                           capture_output=True, text=True)
        ff = r.stdout.strip()
        if ff and os.path.exists(ff):
            shutil.copy2(ff, os.path.join(TARGET, "ffmpeg.exe"))
            log("  ✅ 已放置 ffmpeg.exe")
    except Exception as e:  # noqa: BLE001
        log("  [!] ffmpeg 复制失败：%s（只影响音频格式转换/人声分离）" % e)

    # 启动脚本
    for name, content in (
        ("启动WebUI.bat", LAUNCHER_WEBUI),
        ("启动API.bat", LAUNCHER_API),
        ("一键克隆.bat", LAUNCHER_CLONE),
        ("批量克隆.bat", LAUNCHER_BATCH),
        ("启动声音工坊.bat", LAUNCHER_UI),
    ):
        with open(os.path.join(TARGET, name), "w", encoding="utf-8", newline="\r\n") as f:
            f.write(content)
    log("  ✅ 已生成：启动WebUI.bat / 启动API.bat / 一键克隆.bat / 批量克隆.bat")


def step_verify():
    banner("步骤 6/6：自检（真实合成一句中文）")
    py = os.path.join(TARGET, "venv", "Scripts", "python.exe")
    ref_wav = os.path.join(TARGET, "参考音频", "ref.wav")
    ref_txt = os.path.join(TARGET, "参考音频", "ref.txt")
    if not (os.path.exists(ref_wav) and os.path.exists(ref_txt)):
        log("  [!] 参考音频缺失，跳过自检")
        return
    txt = os.path.join(TARGET, "自检台词.txt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write("安装完成，现在可以用这个声音说话了。")
    env = dict(os.environ)
    env.update({
        "PATH": os.path.join(TARGET, "venv", "Scripts") + os.pathsep + env.get("PATH", ""),
        "PYTHONPATH": TARGET + os.pathsep + os.path.join(TARGET, "GPT_SoVITS"),
        "HF_ENDPOINT": "https://hf-mirror.com",
        "NLTK_DATA": os.path.join(TARGET, "nltk_data"),
        "TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD": "1",
        "language": "zh_CN",
        "version": "v2Pro",
        "gpt_path": os.path.join(TARGET, "GPT_weights_v2Pro", WEIGHT_CKPT),
        "sovits_path": os.path.join(TARGET, "SoVITS_weights_v2Pro", WEIGHT_PTH),
    })
    out = os.path.join(TARGET, "test", "out-verify")
    r = subprocess.run([py, os.path.join(TARGET, "tts_clone.py"),
                        "--text-file", txt, "--out-dir", out,
                        "--ref-wav", ref_wav, "--ref-text-file", ref_txt,
                        "--variants", "1", "--prefix", "verify"], cwd=TARGET, env=env)
    got = os.path.join(out, "verify_v1-默认.wav")
    if r.returncode == 0 and os.path.exists(got):
        log("  ✅ 自检通过：%s" % got)
        try:
            import winsound  # type: ignore
            winsound.PlaySound(got, winsound.SND_FILENAME)
        except Exception:  # noqa: BLE001
            pass
    else:
        log("  ⚠️ 自检未产出音频（退出码 %s），请把上面的输出发回排查。" % r.returncode)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    banner("GPT-SoVITS Windows 安装器")
    log("安装目录：%s" % TARGET)
    log("系统：%s %s / Python %s" % (platform.system(), platform.machine(), platform.python_version()))
    if platform.system() != "Windows":
        log("")
        log("⚠️ 本安装器是为 Windows 写的，当前系统不是 Windows。仅用于查看流程。")
    if sys.version_info < (3, 9):
        log("❌ 需要 Python 3.9 以上。")
        return 1

    disk = shutil.disk_usage(os.path.expanduser("~")).free
    log("可用空间：%s（需要约 12GB）" % human(disk))
    if disk < 12 * 1024 ** 3:
        log("⚠️ 空间可能不足，建议先清理。")

    use_cuda = False
    if "--cuda" in sys.argv:
        use_cuda = True
    elif "--no-cuda" in sys.argv:
        use_cuda = False
    elif platform.system() == "Windows":
        ans = input("\n你的电脑有 NVIDIA 独立显卡吗？(y/N，直接回车=没有) ").strip().lower()
        use_cuda = ans in ("y", "yes", "是")

    step_repo()
    step_jieba_shim()
    py = step_venv()
    step_deps(py, use_cuda)
    step_models()
    step_weights()
    step_verify()

    banner("安装完成")
    log("启动方式：")
    log("  图形界面 : %s" % os.path.join(TARGET, "启动WebUI.bat"))
    log("            （浏览器打开 http://127.0.0.1:9874）")
    log("  网页界面 : %s" % os.path.join(TARGET, "启动声音工坊.bat"))
    log("            （浏览器打开 http://127.0.0.1:8000，推荐用这个）")
    log("  一键克隆 : %s" % os.path.join(TARGET, "一键克隆.bat"))
    log("  使用说明 : %s" % os.path.join(TARGET, "使用说明.txt"))
    log("")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print("")
        print("=" * 64)
        print("  安装失败：%s" % exc)
        print("  请把上面整段输出复制发回，以便排查。")
        print("=" * 64)
        sys.exit(1)
