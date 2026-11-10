#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""声音工坊扩展接口：模型管理 / 音色库 / 合成日志。

跟 compat_api.py 一样，是被 main.py 挂载进来的独立模块，不反向依赖 main。
所有路径都以引擎的 repo_root（/repo）为基准。
"""
import glob
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from urllib.parse import quote
import uuid

from fastapi import Body, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

# ------------------------------------------------------------------ 配置
PM = "GPT_SoVITS/pretrained_models"
MIRROR = os.environ.get("MODEL_MIRROR", "https://hf-mirror.com/lj1995/GPT-SoVITS/resolve/main/")

# 底模预设：version / GPT 权重 / SoVITS 权重 / 需要的文件
PRESETS = [
    {
        "id": "v2",
        "label": "v2 底模",
        "version": "v2",
        "gpt": "%s/gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt" % PM,
        "sovits": "%s/gsv-v2final-pretrained/s2G2333k.pth" % PM,
        "note": "最通用的一代，速度最快，音色还原度一般",
        "files": [],
    },
    {
        "id": "v2Pro",
        "label": "v2Pro 底模",
        "version": "v2Pro",
        "gpt": "%s/s1v3.ckpt" % PM,
        "sovits": "%s/v2Pro/s2Gv2Pro.pth" % PM,
        "note": "音质比 v2 好一档，速度居中",
        "files": [],
    },
    {
        "id": "v2ProPlus",
        "label": "v2ProPlus 底模",
        "version": "v2ProPlus",
        "gpt": "%s/s1v3.ckpt" % PM,
        "sovits": "%s/v2Pro/s2Gv2ProPlus.pth" % PM,
        "note": "气声与情绪更自然，CPU 上略慢",
        "files": [],
    },
    {
        "id": "v3",
        "label": "v3 底模",
        "version": "v3",
        "gpt": "%s/s1v3.ckpt" % PM,
        "sovits": "%s/s2Gv3.pth" % PM,
        "note": "细节更多，但要跑 32 步采样，CPU 上一句话要一两分钟",
        "files": [
            {"rel": "%s/s2Gv3.pth" % PM, "hf": "s2Gv3.pth", "size": 769035145},
            # v3 走 BigVGAN 声码器，缺了会在合成时报 repo id 错误
            {"rel": "%s/models--nvidia--bigvgan_v2_24khz_100band_256x/config.json" % PM,
             "hf": "models--nvidia--bigvgan_v2_24khz_100band_256x/config.json", "size": 1402},
            {"rel": "%s/models--nvidia--bigvgan_v2_24khz_100band_256x/bigvgan_generator.pt" % PM,
             "hf": "models--nvidia--bigvgan_v2_24khz_100band_256x/bigvgan_generator.pt", "size": 450088331},
        ],
    },
    {
        "id": "v4",
        "label": "v4 底模",
        "version": "v4",
        "gpt": "%s/s1v3.ckpt" % PM,
        "sovits": "%s/gsv-v4-pretrained/s2Gv4.pth" % PM,
        "note": "最新一代，需配套声码器；CPU 上比 v3 更慢，建议有 GPU 再用",
        "files": [
            {"rel": "%s/gsv-v4-pretrained/s2Gv4.pth" % PM, "hf": "gsv-v4-pretrained/s2Gv4.pth", "size": 769025545},
            {"rel": "%s/gsv-v4-pretrained/vocoder.pth" % PM, "hf": "gsv-v4-pretrained/vocoder.pth", "size": 57781109},
        ],
    },
]

TASKS = {}
TASK_LOCK = threading.Lock()

HISTORY_FILE = os.environ.get("HISTORY_FILE", "/data/history/history.jsonl")
HIST_LOCK = threading.Lock()
HIST_MAX_LINES = 4000

PRESET_DIR = os.environ.get("PRESET_DIR", "/data/presets")
PRESET_INDEX = os.path.join(PRESET_DIR, "presets.json")


# ------------------------------------------------------------------ 日志本
def record(text, voice="", dur=None, file=None, source="网页"):
    """记录一条合成历史（供日志本查看）。失败不影响主流程。"""
    rec = {
        "ts": time.time(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "text": (text or "").strip(),
        "voice": voice or "",
        "dur": round(dur, 2) if isinstance(dur, (int, float)) else dur,
        "file": file or "",
        "source": source,
    }
    try:
        d = os.path.dirname(HISTORY_FILE)
        if d:
            os.makedirs(d, exist_ok=True)
        with HIST_LOCK:
            with open(HISTORY_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            _trim_history()
    except Exception:  # noqa: BLE001
        pass


def _trim_history():
    try:
        if not os.path.exists(HISTORY_FILE) or os.path.getsize(HISTORY_FILE) < 4 * 1024 * 1024:
            return
        with open(HISTORY_FILE, encoding="utf-8") as f:
            lines = f.readlines()
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines[-HIST_MAX_LINES:])
    except Exception:  # noqa: BLE001
        pass


def read_history(limit=300, q=None):
    if not os.path.exists(HISTORY_FILE):
        return []
    with HIST_LOCK:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            lines = f.readlines()
    out = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if q and q.lower() not in (rec.get("text", "") + rec.get("voice", "")).lower():
            continue
        out.append(rec)
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------ 工具
def _size(path):
    try:
        return os.path.getsize(path)
    except Exception:  # noqa: BLE001
        return 0


def _dur(path):
    try:
        import soundfile as sf
        info = sf.info(path)
        return round(info.frames / info.samplerate, 2)
    except Exception:  # noqa: BLE001
        return None


def _safe(name, default="voice"):
    base = os.path.splitext(os.path.basename(name or ""))[0].strip() or default
    out = "".join(ch for ch in base if ch.isalnum() or ch in "-_.·" or "\u4e00" <= ch <= "\u9fff")
    return out[:48] or default


def _rss_mb():
    """当前进程常驻内存（MB）——卸载模型前后对比最直观。"""
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except Exception:  # noqa: BLE001
        pass
    return None


def _disk(path):
    try:
        st = os.statvfs(path)
        return {"free_gb": round(st.f_bavail * st.f_frsize / 2 ** 30, 1),
                "total_gb": round(st.f_blocks * st.f_frsize / 2 ** 30, 1)}
    except Exception:  # noqa: BLE001
        return {}


def _download(url, dest, key):
    """下载到 dest（先写 .part），进度写进 TASKS[key]。"""
    # urllib 只接受 ASCII URL，含中文的链接要先做百分号编码（已编码的不会二次编码）
    url = quote(url.strip(), safe=":/?&=#%[]@!$&'()*+,;~")
    with TASK_LOCK:                      # 临时任务也要有占位，否则进度写入会 KeyError
        TASKS.setdefault(key, {"status": "running", "done": 0, "total": 0})
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "voiceui/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with TASK_LOCK:
            TASKS[key].update({"total": total, "done": 0, "status": "running"})
        last = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            now = time.time()
            if now - last > 0.4:
                last = now
                with TASK_LOCK:
                    TASKS[key].update({"done": done, "total": total or done})
    os.replace(tmp, dest)
    return dest


def _task(key, msg, **kw):
    with TASK_LOCK:
        t = TASKS.setdefault(key, {"status": "idle", "done": 0, "total": 0})
        t.update(kw)
        if msg:
            t["msg"] = msg
        t["ts"] = time.time()


def install_ui_api(app, engine, ref_dir, out_dir, state_loader=None, state_saver=None):
    repo = engine.repo_root

    def _state():
        try:
            return state_loader() or {}
        except Exception:  # noqa: BLE001
            return {}

    def _save_state(st):
        try:
            if state_saver:
                state_saver(st)
        except Exception:  # noqa: BLE001
            pass

    def _rel(path):
        return os.path.relpath(path, repo)

    def _abs(rel_path):
        p = rel_path if os.path.isabs(rel_path) else os.path.join(repo, rel_path)
        p = os.path.abspath(p)
        if not p.startswith(os.path.abspath(repo) + os.sep):
            raise HTTPException(400, "路径越界：%s" % rel_path)
        return p

    def _finetuned():
        gpt, sovits = [], []
        for d in sorted(glob.glob(os.path.join(repo, "GPT_weights*"))):
            for f in sorted(glob.glob(os.path.join(d, "**", "*.ckpt"), recursive=True)):
                gpt.append(_rel(f))
        for d in sorted(glob.glob(os.path.join(repo, "SoVITS_weights*"))):
            for f in sorted(glob.glob(os.path.join(d, "**", "*.pth"), recursive=True)):
                sovits.append(_rel(f))
        return gpt, sovits

    def _version():
        try:
            return getattr(engine, "version", None)
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------ 模型清单
    @app.get("/api/models")
    def models():
        st = _state()
        gpt_list, sovits_list = _finetuned()
        g_fallback = gpt_list[0] if gpt_list else ""
        s_fallback = sovits_list[0] if sovits_list else ""
        active_gpt = st.get("gpt") or g_fallback
        active_sovits = st.get("sovits") or s_fallback

        presets = []
        for p in PRESETS:
            need = [p["sovits"]] + [f["rel"] for f in p.get("files", [])]
            missing = [n for n in need if not os.path.exists(_abs(n))]
            # 预设用的 GPT 权重可能也缺（v1 底模之类），一并检查
            if not os.path.exists(_abs(p["gpt"])):
                missing.append(p["gpt"])
            size = sum(_size(_abs(n)) for n in [p["gpt"], p["sovits"]] if os.path.exists(_abs(n)))
            for _f in p.get("files", []):          # 未下载的部分按清单体积预估
                if not os.path.exists(_abs(_f["rel"])):
                    size += _f.get("size", 0)
            presets.append({
                "id": p["id"], "label": p["label"], "version": p["version"],
                "gpt": p["gpt"], "sovits": p["sovits"],
                "note": p["note"], "installed": not missing, "missing": missing,
                "size": size,
                "active": (active_gpt == p["gpt"] and active_sovits == p["sovits"]),
                "files": p.get("files", []),
            })

        with TASK_LOCK:
            tasks = json.loads(json.dumps(TASKS))
        return {
            "active": {"gpt": active_gpt, "sovits": active_sovits},
            "version": _version(),
            "loaded": bool(getattr(engine, "loaded", None)),
            "rss_mb": _rss_mb(),
            "gpt_weights": gpt_list,
            "sovits_weights": sovits_list,
            "presets": presets,
            "tasks": tasks,
            "mirror": MIRROR,
            "disk": _disk(repo),
        }

    @app.post("/api/models/activate")
    def activate(payload: dict = Body(default={})):
        gpt = (payload.get("gpt") or "").strip()
        sovits = (payload.get("sovits") or "").strip()
        if not gpt or not sovits:
            raise HTTPException(400, "需要同时指定 gpt 与 sovits 权重")
        gp, sp = _abs(gpt), _abs(sovits)
        if not os.path.exists(gp):
            raise HTTPException(400, "GPT 权重不存在：%s" % gpt)
        if not os.path.exists(sp):
            raise HTTPException(400, "SoVITS 权重不存在：%s（可能需要先下载底模）" % sovits)
        try:
            engine.ensure_weights(gp, sp)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, "加载失败：%s" % exc) from exc
        st = _state()
        st.update({"gpt": gpt, "sovits": sovits})
        _save_state(st)
        return {"ok": True, "version": _version(), "gpt": gpt, "sovits": sovits}

    @app.post("/api/models/unload")
    def model_unload():
        """把模型从内存里卸掉（不删文件）。下次合成或切换权重会自动重新加载。"""
        fn = getattr(engine, "unload", None)
        if fn is None:
            raise HTTPException(501, "当前引擎不支持卸载（synth.py 版本太旧）")
        before = _rss_mb()
        try:
            freed = fn()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, "卸载失败：%s" % exc) from exc
        after = _rss_mb()
        return {
            "ok": True,
            "freed": freed,
            "rss_before_mb": before,
            "rss_after_mb": after,
            "released_mb": round(before - after, 1) if (before and after) else None,
        }

    @app.post("/api/models/download")
    def model_download(payload: dict = Body(default={})):
        pid = payload.get("id")
        preset = next((p for p in PRESETS if p["id"] == pid), None)
        if not preset:
            raise HTTPException(404, "没有这个模型：%s" % pid)
        files = [f for f in preset.get("files", []) if not os.path.exists(_abs(f["rel"]))]
        if not files:
            raise HTTPException(400, "该模型的文件都已存在")
        key = "model:%s" % pid
        with TASK_LOCK:
            cur = TASKS.get(key, {})
            if cur.get("status") == "running":
                raise HTTPException(409, "已经在下载中")
        _task(key, "准备下载", status="running", done=0, total=sum(f["size"] for f in files), kind="model", id=pid)

        def run():
            total = sum(f["size"] for f in files)
            base = 0
            try:
                for f in files:
                    dest = _abs(f["rel"])
                    _task(key, "下载 %s" % os.path.basename(f["rel"]))
                    req = urllib.request.Request(MIRROR + f["hf"], headers={"User-Agent": "voiceui/1.0"})
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    tmp = dest + ".part"
                    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as out:
                        got = 0
                        last = 0.0
                        while True:
                            chunk = r.read(1 << 20)
                            if not chunk:
                                break
                            out.write(chunk)
                            got += len(chunk)
                            now = time.time()
                            if now - last > 0.4:
                                last = now
                                with TASK_LOCK:
                                    TASKS[key].update({"done": base + got, "total": total})
                    os.replace(tmp, dest)
                    base += f["size"]
                    with TASK_LOCK:
                        TASKS[key].update({"done": base})
                _task(key, "完成", status="done", done=total)
            except Exception as exc:  # noqa: BLE001
                _task(key, "失败：%s" % exc, status="error")
                for f in files:
                    p = _abs(f["rel"]) + ".part"
                    if os.path.exists(p):
                        try:
                            os.remove(p)
                        except OSError:
                            pass

        threading.Thread(target=run, daemon=True).start()
        return {"ok": True, "task": key}

    @app.post("/api/models/delete")
    def model_delete(payload: dict = Body(default={})):
        rel = (payload.get("path") or "").strip()
        if not rel:
            raise HTTPException(400, "缺少 path")
        target = _abs(rel)
        if not os.path.exists(target):
            raise HTTPException(404, "文件不存在")
        ok_prefix = (
            target.startswith(os.path.join(repo, PM) + os.sep)
            or os.path.basename(os.path.dirname(target)).startswith("GPT_weights")
            or os.path.basename(os.path.dirname(target)).startswith("SoVITS_weights")
        )
        if not ok_prefix:
            raise HTTPException(400, "只能删除预训练模型或音色权重目录下的文件")
        st = _state()
        if rel in (st.get("gpt"), st.get("sovits")):
            raise HTTPException(400, "这是当前正在使用的权重，请先切换到别的模型再删除")
        freed = _size(target)
        os.remove(target)
        # 目录空了顺手删掉
        parent = os.path.dirname(target)
        try:
            if os.path.isdir(parent) and not os.listdir(parent):
                os.rmdir(parent)
        except OSError:
            pass
        return {"ok": True, "freed_mb": round(freed / 2 ** 20, 1)}

    # ------------------------------------------------------------ 音色库
    def _preset_index():
        try:
            with open(PRESET_INDEX, encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return []

    def _refs():
        out = []
        for wav in sorted(glob.glob(os.path.join(ref_dir, "**", "*.wav"), recursive=True)):
            name = os.path.relpath(wav, ref_dir)
            txt = os.path.splitext(wav)[0] + ".txt"
            text = ""
            if os.path.exists(txt):
                try:
                    with open(txt, encoding="utf-8") as f:
                        text = f.read().strip()
                except Exception:  # noqa: BLE001
                    pass
            out.append({"name": name, "dur": _dur(wav), "size": _size(wav), "text": text})
        return out

    def _write_voice(src, name, text=""):
        """把任意音频转成 32k 单声道 wav，并写同名 txt。"""
        safe = _safe(name)
        wav = os.path.join(ref_dir, safe + ".wav")
        tmp_out = wav + ".tmp.wav"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error", "-i", src,
            "-af", "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse,"
                   "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse",
            "-ac", "1", "-ar", "32000", "-c:a", "pcm_s16le", "-t", "12", tmp_out,
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=180)
        if r.returncode != 0 or not os.path.exists(tmp_out):
            # 去掉静音裁剪再试一次（某些编码不支持该滤镜链）
            cmd2 = ["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", "32000",
                    "-c:a", "pcm_s16le", "-t", "12", tmp_out]
            r = subprocess.run(cmd2, capture_output=True, timeout=180)
            if r.returncode != 0:
                raise HTTPException(400, "音频转码失败：%s" % (r.stderr.decode("utf-8", "ignore")[:200]))
        os.replace(tmp_out, wav)
        with open(os.path.splitext(wav)[0] + ".txt", "w", encoding="utf-8") as f:
            f.write((text or "").strip())
        return {"name": os.path.basename(wav), "dur": _dur(wav), "text": text or ""}

    @app.get("/api/voices/presets")
    def voice_presets():
        refs = _refs()
        have = {r["name"] for r in refs}
        items = []
        for p in _preset_index():
            fname = _safe(p.get("name") or p.get("id") or "preset")
            items.append({
                "id": p.get("id") or fname,
                "name": p.get("name") or fname,
                "text": p.get("text", ""),
                "note": p.get("note", ""),
                "license": p.get("license", ""),
                "kind": "网络" if p.get("url") else "内置",
                "url": p.get("url", ""),
                "file": p.get("file", ""),
                "installed": (fname + ".wav") in have,
            })
        return {"presets": items, "dir": PRESET_DIR, "installed": refs,
                "current": _state().get("ref")}

    @app.post("/api/voices/preset_install")
    def preset_install(payload: dict = Body(default={})):
        pid = payload.get("id")
        item = next((p for p in _preset_index() if (p.get("id") or p.get("name")) == pid), None)
        if not item:
            raise HTTPException(404, "没有这个音色：%s" % pid)
        tmp = os.path.join("/tmp", "vc_%s" % uuid.uuid4().hex[:8])
        try:
            if item.get("url"):
                _download(item["url"], tmp, "voice:%s" % pid)
            else:
                src = os.path.join(PRESET_DIR, item.get("file", ""))
                if not os.path.exists(src):
                    raise HTTPException(404, "内置音色文件缺失：%s" % item.get("file"))
                shutil.copyfile(src, tmp)
            res = _write_voice(tmp, item.get("name") or pid, item.get("text", ""))
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        st = _state()
        st["ref"] = res["name"]
        _save_state(st)
        return {"ok": True, **res}

    @app.post("/api/voices/from_url")
    def voice_from_url(payload: dict = Body(default={})):
        url = (payload.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            raise HTTPException(400, "需要 http/https 直链")
        name = payload.get("name") or ("在线音色_" + time.strftime("%m%d%H%M"))
        tmp = os.path.join("/tmp", "vc_%s" % uuid.uuid4().hex[:8])
        try:
            _download(url, tmp, "voice:adhoc")
            res = _write_voice(tmp, name, payload.get("text", ""))
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, "下载失败：%s" % exc) from exc
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        st = _state()
        st["ref"] = res["name"]
        _save_state(st)
        return {"ok": True, **res}

    # ------------------------------------------------------------ 日志本
    @app.get("/api/history")
    def history(limit: int = 300, q: str = ""):
        items = read_history(limit=max(1, min(limit, 2000)), q=q or None)
        return {"items": items, "count": len(items), "file": HISTORY_FILE}

    @app.delete("/api/history")
    def history_clear():
        try:
            if os.path.exists(HISTORY_FILE):
                open(HISTORY_FILE, "w").close()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, "清空失败：%s" % exc) from exc
        return {"ok": True}

    @app.get("/api/history/export")
    def history_export():
        path = HISTORY_FILE
        if not os.path.exists(path):
            raise HTTPException(404, "还没有任何记录")
        return FileResponse(path, media_type="text/plain",
                            filename="tts-history-%s.jsonl" % time.strftime("%Y%m%d"))

    return app
