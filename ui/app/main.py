#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPT-SoVITS 声音工坊 —— 本地 Web UI（FastAPI）

功能：
  · 输入台词一键合成（可调语速 / 参数变体）
  · 管理参考音色（上传 wav + 填文字、切换默认音色、试听）
  · 管理音色权重（自动扫描 GPT_weights_* / SoVITS_weights_*）
  · 输出音频列表：在线试听、下载、删除

环境变量：
  REPO_ROOT  GPT-SoVITS 仓库根目录（默认 /repo）
  REF_DIR    参考音色目录（默认 <本文件目录>/references）
  OUT_DIR    输出音频目录（默认 <本文件目录>/outputs）
  PRELOAD    1=启动即加载模型（默认 1）
"""
import glob
import json
import os
import queue
import shutil
import sys
import threading
import time
import uuid

import soundfile as sf
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from synth import Engine  # noqa: E402

REPO_ROOT = os.path.abspath(os.environ.get("REPO_ROOT", "/repo"))
REF_DIR = os.path.abspath(os.environ.get("REF_DIR", os.path.join(HERE, "references")))
OUT_DIR = os.path.abspath(os.environ.get("OUT_DIR", os.path.join(HERE, "outputs")))
STATE_FILE = os.path.join(HERE, "ui_state.json")

os.makedirs(REF_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

app = FastAPI(title="GPT-SoVITS 声音工坊")
engine = Engine(REPO_ROOT)
jobs = {}
job_queue = queue.Queue()
state_lock = threading.Lock()


# ------------------------------------------------------------------ 工具
def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def save_state(d):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        pass


def wav_duration(path):
    try:
        info = sf.info(path)
        return round(info.frames / info.samplerate, 2)
    except Exception:  # noqa: BLE001
        return None


def list_references():
    out = []
    for wav in sorted(glob.glob(os.path.join(REF_DIR, "**", "*.wav"), recursive=True)):
        name = os.path.relpath(wav, REF_DIR)
        txt = os.path.splitext(wav)[0] + ".txt"
        text = ""
        if os.path.exists(txt):
            try:
                text = open(txt, encoding="utf-8").read().strip()
            except Exception:  # noqa: BLE001
                pass
        out.append({
            "name": name,
            "dur": wav_duration(wav),
            "text": text,
            "size": os.path.getsize(wav),
        })
    return out


def list_weights():
    gpt, sovits = [], []
    for pat in ("GPT_weights*",):
        for d in sorted(glob.glob(os.path.join(REPO_ROOT, pat))):
            for f in sorted(glob.glob(os.path.join(d, "*.ckpt"))):
                gpt.append(os.path.relpath(f, REPO_ROOT))
    for d in sorted(glob.glob(os.path.join(REPO_ROOT, "SoVITS_weights*"))):
        for f in sorted(glob.glob(os.path.join(d, "*.pth"))):
            sovits.append(os.path.relpath(f, REPO_ROOT))
    return gpt, sovits


def default_weights(gpt_list, sovits_list):
    """优先读 weight.json 里的 v2Pro 配置，其次取 v2Pro 目录下的文件。"""
    st = load_state()
    if st.get("gpt") and st["gpt"] in gpt_list and st.get("sovits") in sovits_list:
        return st["gpt"], st["sovits"]
    wj = os.path.join(REPO_ROOT, "weight.json")
    if os.path.exists(wj):
        try:
            d = json.load(open(wj, encoding="utf-8"))
            g = d.get("GPT", {}).get("v2Pro")
            s = d.get("SoVITS", {}).get("v2Pro")
            if g in gpt_list and s in sovits_list:
                return g, s
        except Exception:  # noqa: BLE001
            pass
    g = next((x for x in gpt_list if "v2Pro" in x), gpt_list[0] if gpt_list else "")
    s = next((x for x in sovits_list if "v2Pro" in x), sovits_list[0] if sovits_list else "")
    return g, s


def list_outputs():
    out = []
    for wav in sorted(glob.glob(os.path.join(OUT_DIR, "*.wav")), key=os.path.getmtime, reverse=True):
        out.append({
            "name": os.path.basename(wav),
            "dur": wav_duration(wav),
            "size": os.path.getsize(wav),
            "mtime": time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(wav))),
        })
    return out


# ------------------------------------------------------------------ 后台任务
def worker():
    while True:
        job_id, payload = job_queue.get()
        job = jobs[job_id]
        try:
            job["status"] = "running"
            job["log"].append("开始合成…")
            ref_wav = os.path.join(REF_DIR, payload["ref"])
            ref_txt = os.path.splitext(ref_wav)[0] + ".txt"
            ref_text = ""
            if os.path.exists(ref_txt):
                ref_text = open(ref_txt, encoding="utf-8").read().strip()

            def progress(done, total):
                job["log"].append("生成中…第 %d 段" % done)

            t0 = time.time()
            audio, sr = engine.synth(
                text=payload["text"],
                ref_wav=ref_wav,
                ref_text=ref_text,
                gpt=os.path.join(REPO_ROOT, payload["gpt"]),
                sovits=os.path.join(REPO_ROOT, payload["sovits"]),
                variant=payload.get("variant", "默认"),
                speed=payload.get("speed"),
                cut=payload.get("cut", "按标点符号切"),
                progress=progress,
            )
            safe = "".join(ch for ch in payload["text"][:12] if ch.isalnum() or "\u4e00" <= ch <= "\u9fff") or "line"
            fname = "%s_%s.wav" % (safe, time.strftime("%H%M%S"))
            path = os.path.join(OUT_DIR, fname)
            engine.save_wav(audio, sr, path)
            job["files"] = [fname]
            job["log"].append("完成，用时 %.1f 秒，音频 %.2f 秒" % (time.time() - t0, len(audio) / sr))
            job["status"] = "done"
        except Exception as exc:  # noqa: BLE001
            import traceback
            job["status"] = "error"
            job["error"] = str(exc)
            job["log"].append(traceback.format_exc(limit=6))
        finally:
            job_queue.task_done()


threading.Thread(target=worker, daemon=True).start()
if os.environ.get("PRELOAD", "1") == "1":
    threading.Thread(target=engine.preload, daemon=True).start()


# ------------------------------------------------------------------ 接口
@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(HERE, "static", "index.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/state")
def api_state():
    gpt_list, sovits_list = list_weights()
    g, s = default_weights(gpt_list, sovits_list)
    refs = list_references()
    st = load_state()
    cur_ref = st.get("ref") if st.get("ref") in [r["name"] for r in refs] else (refs[0]["name"] if refs else None)
    return {
        "repo_root": REPO_ROOT,
        "ref_dir": REF_DIR,
        "out_dir": OUT_DIR,
        "references": refs,
        "current_ref": cur_ref,
        "gpt_weights": gpt_list,
        "sovits_weights": sovits_list,
        "gpt": g,
        "sovits": s,
        "variants": ["默认", "更稳", "更活"],
        "loaded": engine.loaded,
        "log": engine.log[-8:],
    }


@app.post("/api/select")
def api_select(payload: dict):
    st = load_state()
    if payload.get("ref"):
        st["ref"] = payload["ref"]
    if payload.get("gpt"):
        st["gpt"] = payload["gpt"]
    if payload.get("sovits"):
        st["sovits"] = payload["sovits"]
    save_state(st)
    return {"ok": True, "state": st}


@app.post("/api/refs/upload")
async def api_upload_ref(file: UploadFile = File(...), text: str = Form(""), name: str = Form("")):
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "空文件")
    base = (name or os.path.splitext(os.path.basename(file.filename or "ref"))[0]).strip() or "ref"
    safe = "".join(ch for ch in base if ch.isalnum() or ch in "-_." or "\u4e00" <= ch <= "\u9fff") or "ref"
    ext = os.path.splitext(file.filename or ".wav")[1].lower() or ".wav"
    work = os.path.join(REF_DIR, safe + ext)
    with open(work, "wb") as f:
        f.write(raw)
    wav = work
    if ext != ".wav":                     # 非 wav 用 ffmpeg 转码
        wav = os.path.join(REF_DIR, safe + ".wav")
        rc = os.system('ffmpeg -y -loglevel error -i "%s" -ac 1 -ar 32000 -c:a pcm_s16le "%s"' % (work, wav))
        if rc != 0 or not os.path.exists(wav):
            raise HTTPException(400, "转码失败（需要 ffmpeg，且文件是有效音频）")
        os.remove(work)
    with open(os.path.splitext(wav)[0] + ".txt", "w", encoding="utf-8") as f:
        f.write(text.strip())
    st = load_state()
    st["ref"] = os.path.basename(wav)
    save_state(st)
    return {"ok": True, "name": os.path.basename(wav), "text": text.strip(), "dur": wav_duration(wav)}


@app.post("/api/refs/text")
def api_ref_text(payload: dict):
    name = payload.get("name")
    text = payload.get("text", "")
    if not name:
        raise HTTPException(400, "缺少 name")
    wav = os.path.join(REF_DIR, name)
    if not os.path.exists(wav):
        raise HTTPException(404, "参考音色不存在")
    with open(os.path.splitext(wav)[0] + ".txt", "w", encoding="utf-8") as f:
        f.write(text.strip())
    return {"ok": True}


@app.post("/api/refs/delete")
def api_ref_delete(payload: dict):
    name = payload.get("name")
    if not name:
        raise HTTPException(400, "缺少 name")
    for p in (os.path.join(REF_DIR, name), os.path.splitext(os.path.join(REF_DIR, name))[0] + ".txt"):
        if os.path.exists(p):
            os.remove(p)
    return {"ok": True}


@app.post("/api/synth")
def api_synth(payload: dict):
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "台词不能为空")
    if not payload.get("ref"):
        raise HTTPException(400, "请先选择参考音色")
    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {"id": job_id, "status": "queued", "files": [], "log": [], "error": None, "text": text}
    job_queue.put((job_id, payload))
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
def api_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    job["log"] = job["log"][-40:]
    return job


@app.get("/api/outputs")
def api_outputs():
    return {"outputs": list_outputs()}


@app.delete("/api/outputs/{name}")
def api_delete_output(name: str):
    p = os.path.join(OUT_DIR, os.path.basename(name))
    if os.path.exists(p):
        os.remove(p)
    return {"ok": True}


@app.get("/media/ref/{name:path}")
def media_ref(name: str):
    p = os.path.join(REF_DIR, name)
    if not os.path.exists(p):
        raise HTTPException(404, "不存在")
    return FileResponse(p, media_type="audio/wav")


@app.get("/media/out/{name:path}")
def media_out(name: str):
    p = os.path.join(OUT_DIR, os.path.basename(name))
    if not os.path.exists(p):
        raise HTTPException(404, "不存在")
    return FileResponse(p, media_type="audio/wav")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
