# 声音工坊 · GPT-SoVITS 本地部署工具链

把 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) 从"能跑"做到"好用"的一整套脚本与界面：
**macOS 原生安装、Windows 轻量安装包、Docker 镜像 + 网页 UI**，全部在 Apple Silicon Mac 上实测跑通。

> 只包含代码、脚本与文档。**预训练模型和音色权重不在此仓库**（体积大、且音色涉及授权），
> 仓库内提供了自动下载脚本，见下文「模型与权重」。

## 目录结构

```
scripts/   macOS 原生方案
  ├─ 安装.command / install_home.sh     一键装到 ~/GPT-SoVITS（含路径修复、自检）
  ├─ fetch_models.sh / fetch_extras.sh  从 hf-mirror 下载预训练模型与素材
  ├─ requirements-mac.txt               macOS(arm64) 依赖清单（含踩坑后的版本钉住）
  ├─ tts_clone.py / say.sh     合成引擎（多变体、自动增益、批量）
  ├─ 一键克隆.command / 批量克隆.command  双击即用的桌面工具
  ├─ ref_pick_asr.py / ref_from_video.py  从视频里自动挑「干净人声」当参考音
  ├─ asr_sensevoice.py / asr_ref.sh     语音识别（给参考音配文字）
  ├─ timbre_compare.py / f0_analyze.py   音色相似度与基频的客观核对
  ├─ vocals_split.py                    UVR5 人声分离调用封装
  └─ install_user_weights.sh            载入第三方训练权重并做配对校验

win/       Windows 轻量安装包（脚本 + 权重，依赖联网下载）
  ├─ 安装.bat / install.bat / install.py  主安装器（Python 编写，避免批处理坑）
  ├─ clone_win.py                        一键/批量克隆
  └─ jieba_fast/                         免编译兼容层（Windows 装不上 jieba_fast）

ui/        声音工坊网页界面 + Docker 封装
  ├─ app/                                FastAPI 后端 + 单文件前端（无 CDN 依赖）
  ├─ run_local.sh / 启动声音工坊.command   macOS/Linux 本机启动
  ├─ docker/                             Dockerfile / compose / entrypoint / 模型下载器
  ├─ make_build_dir.sh                   组装 Docker 构建目录（含 wheel 预下载）
  └─ export_image.sh                     把镜像导出成离线包给别的机器
```

## 快速开始

### macOS（Apple Silicon）

```bash
bash scripts/fetch_models.sh          # 下模型到工作区
bash scripts/fetch_extras.sh          # G2PW / nltk / 语种检测模型
bash scripts/install_home.sh          # 组装环境到 ~/GPT-SoVITS 并做合成自检
~/GPT-SoVITS/start-webui.sh           # 官方 WebUI（http://127.0.0.1:9874）
```

### Windows

把 `win/` 整个目录拷到 Windows，双击 `install.bat`：自动装 Python（缺的话）、
建 venv、装依赖、下模型、放入权重、生成 5 个启动器，并做一次合成自检。

### Docker

```bash
cd ui && ./make_build_dir.sh
cd build && docker compose up -d --build     # 打开 http://localhost:8000
```

离线交付：`ui/export_image.sh` 会把镜像 + 权重 + 参考音色打成一个离线包，
对方 `./load_and_run.sh` 即可（含 Windows 的 `load_and_run.bat`）。

### 声音工坊网页界面

`http://127.0.0.1:8000`：输入台词合成、切换/上传参考音色、编辑参考文字、试听/下载/删除输出。
模型常驻内存，首次加载约 1 分钟，之后每次合成 5~20 秒。

## 模型与权重（不在仓库内）

```bash
python ui/docker/fetch_assets.py --repo /path/to/GPT-SoVITS     # 跨平台下载器
# 或
bash scripts/fetch_models.sh && bash scripts/fetch_extras.sh
```

需要的目录布局（相对仓库根）：

```
GPT_SoVITS/pretrained_models/{chinese-roberta-wwm-ext-large,chinese-hubert-base,v2Pro,sv,...}
GPT_SoVITS/pretrained_models/fast_langdetect/lid.176.bin
GPT_SoVITS/text/G2PWModel/
nltk_data/
GPT_weights_v2Pro/*.ckpt       ← 你训练/收集的音色权重
SoVITS_weights_v2Pro/*.pth
```

**音色权重同样不在仓库里**：把任意 GPT-SoVITS 微调权重（一个 `.ckpt` + 一个 `.pth`）放进上面的目录即可，
`scripts/say.sh`、桌面工具和网页界面都会自动发现，按 `v2ProPlus → v2Pro → v4 → v3 → v2 → v1`
的顺序取第一个可用的；也可以显式指定：

```bash
gpt_path=/path/a.ckpt sovits_path=/path/b.pth version=v2Pro bash scripts/say.sh 台词.txt
```

## 实测环境

macOS 27 / Apple Silicon(arm64) · Python 3.11.14 · torch 2.6.0 · torchaudio 2.6.0 ·
numpy 1.26.4 · gradio 4.44.1 · transformers 4.57.6 · starlette 0.41.3（**必须钉住**，新版与 gradio 4.44 不兼容）

## 几个踩过的坑（脚本里已处理）

1. `starlette >= 1.0` 改了 `TemplateResponse` 签名 → gradio 4.44 的 `GET /` 直接 500，必须降到 `0.41.3`
2. 官方 `inference_cli.py` 的 `change_sovits_weights` 是 **generator**，直接调用等于没切换模型 → 用环境变量 `gpt_path`/`sovits_path` 指定，或把 generator 排空
3. `jieba_fast` 在部分平台无 wheel → 用纯 Python 兼容层顶替（`win/jieba_fast/`）
4. `pyopenjtalk` 在 arm64 上需自行编译 → 中文/英文不受影响（代码里是 try/except 导入）
5. macOS 沙箱/权限下 `~/Downloads`、`~/Desktop`、`~/Documents` 读不了 → 参考音与输出目录用工作区路径
6. `download.pytorch.org` 国内易卡死 → 改用阿里云 pytorch-wheels 镜像 + 本地 wheel 离线安装
7. 硬链接（`cp -Rl`）省空间时，某些安全策略会拒绝打开多重链接文件 → 装完记得真实复制关键目录

## 注意

- **音色授权**：训练/收集的音色权重可能包含他人声音（真人、配音演员或角色）。
  上传、转发、商用前请确认授权，不要用于冒充他人、诈骗等用途。
- **版权**：从视频/歌曲里提取的参考音频受原作品版权约束，不要连同公开分发。
- GPT-SoVITS 本体是 MIT 协议；本仓库的脚本同样以 MIT 发布（见 `LICENSE`）。
