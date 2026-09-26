# v1.0.0 · 声音工坊网页界面 + 离线交付包

配套代码仓库：`gpt-sovits-toolkit`（公开）。本 Release 放三个大文件，代码本身在仓库里。

## 附件说明

| 附件 | 大小 | 是什么 |
|---|---|---|
| `gptsovits-voiceui-arm64.tar.gz` | 908 MB | **Docker 镜像离线包**（`gptsovits-voiceui:latest`，arm64，CPU 版 torch，约 3.9GB 解开后）。目标机器装好 Docker 后 `gunzip -c xxx.tar.gz \| docker load` 即可 |
| `GPT-SoVITS-Windows-light-installer.zip` | 257 MB | **Windows 轻量安装包**（原文件名 `GPT-SoVITS-Windows-轻量安装包.zip`）。解压后双击 `install.bat`：自动装 Python、建 venv、装依赖、下模型、放入音色权重，并生成 5 个启动器（含网页界面） |
| `voiceui-offline-kit.tar.gz` | 4 KB | 配合镜像包使用的**离线套件**：`docker-compose.yml`、`load_and_run.sh`、`load_and_run.bat`、目录说明 |

## 镜像包怎么用

```bash
tar -xzf voiceui-offline-kit.tar.gz
cd voiceui-offline-kit
gunzip -c ../gptsovits-voiceui-arm64.tar.gz | docker load     # 或直接 ./load_and_run.sh
mkdir -p models/pretrained_models models/G2PWModel models/nltk_data weights references outputs
docker compose up -d
# 打开 http://localhost:8000
```

- 首次启动若 `models/` 为空，容器会从 hf-mirror 自动下载预训练模型（约 3.2GB，`docker compose logs -f` 看进度）
- 音色权重放进 `weights/GPT_weights_*` 与 `weights/SoVITS_weights_*`；参考音色放 `references/`（wav + 同名 txt）
- 想复用机器上已有的模型目录：在 `.env` 里写 `PRETRAINED_DIR=`、`G2PW_DIR=`、`NLTK_DIR=`、`WEIGHTS_DIR=` 绝对路径，并设 `AUTO_FETCH=0`

## Windows 包怎么用

解压整个文件夹 → 双击 `install.bat` → 装完双击 `启动声音工坊.bat`（浏览器自动打开 http://127.0.0.1:8000）。
详细步骤见包内 `使用说明.txt`。

## 校验和（sha256 前 16 位）

```
gptsovits-voiceui-arm64.tar.gz                 fbaa9c826421ee63
GPT-SoVITS-Windows-light-installer.zip         992d90274468e73b
voiceui-offline-kit.tar.gz                     c3de3d80f38ac38f
```

## 重要提醒

- **架构**：镜像包是 **Apple Silicon（arm64）** 导出的。导到 x86_64 服务器会提示架构不匹配，需要在那边用仓库里的 `ui/make_build_dir.sh` + `docker compose up -d --build` 自行构建。
- **资源**：单实例模型常驻约 5GB 内存，建议给 Docker ≥12GB。
- **音色授权**：Windows 包里自带的两套音色权重来自第三方（其中一套为他人训练成果），
  仅限自用；转发、公开或商用前请确认授权，不得用于冒充他人、诈骗等用途。
- **不含预训练模型**：模型体积大且可公开下载，用仓库里的 `fetch_assets.py` / `fetch_models.sh` 获取即可。

## 音色权重的来源与声明

本 Release 的 Windows 安装包内含两套社区流传的 GPT-SoVITS 微调权重，**均非本仓库作者训练**：
一套来自朋友分享，一套取自公开模型仓库（Hugging Face）。
版权与声音相关权利归原始训练者 / 说话人所有，此处仅作为安装包的一部分附带，供个人学习研究使用。

- **禁止**用于冒充他人、诈骗、伪造证据、制作违法违规内容等用途；
- 若权利人认为不妥，请提 Issue 或联系仓库所有者，我们会**立即移除**相应附件；
- 不想用这两套音色时，把 `权重/` 目录里的 `.ckpt` / `.pth` 换成你自己的即可（安装器会自动识别文件名）。

配套代码仓库已重命名并公开：`gpt-sovits-toolkit`。
