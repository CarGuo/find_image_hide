# Image Forensics Inspector

一个跨平台（Windows + macOS）本地命令行 + 浏览器 UI 的图片取证分析工具，用于**批量扫描本地目录下所有图片**，输出统一的风险等级与可视化证据。所有分析在本机完成，不会上传到任何外部服务。

工具会同时给出：

- 基础信息：文件大小、SHA256、感知哈希 pHash、MIME；
- 元数据：EXIF / XMP / IPTC / PNG 文本块 / JPEG comment / 图库黑名单（Shutterstock、Getty 等关键词）；
- 隐藏内容提取：附加在图像数据末尾的 trailing data（zip / 文本 / 文件签名）+ LSB 比特流文本提取；
- 隐写检测：Westfeld χ² POV、滑动 χ²、SPA 像素对统计；
- 可见水印 OCR：通过 Tesseract 读图上的 Getty / Shutterstock / 仅供预览 等可见水印（可选）；
- 反查参考库：感知哈希 Hamming 距离匹配本地参考目录（可选）；
- AI 来源凭证：C2PA（如系统中存在 `c2patool`）+ 关键词扫描（OpenAI / Gemini / SD / MJ / Adobe Firefly 等）；
- FFT 频域：灰度 + RGB 频谱图、对称峰值检测；
- DCT：8x8 DCT 系数 heatmap、与 Laplace 自然分布的 K-S 检验；
- LSB：R/G/B 位平面图、熵 / 平衡度 / 邻域相关；
- 噪声残差：Gaussian residual、Laplacian、局部噪声不一致度；
- ELA 误差水平分析：再压缩误差，定位拼接 / 修图区域；
- 综合启发式风险评分：LOW / MEDIUM / HIGH / UNKNOWN，每个 tab 按风险染色。

> **重要免责声明**
> 本工具不能证明图片绝对包含或绝对没有水印，也不能证明图片绝对是或绝对不是 AI 生成。所有评分都是 heuristic，不构成法律鉴定结论。SynthID 不在常规 EXIF/XMP 中，本工具默认不做本地 SynthID 判定。

---

## 快速开始

### 依赖

- Python **3.10+**（Windows 上推荐官方安装包，macOS 上 `brew install python@3.11`）；
- 可选：`c2patool`（用于读取 / 验证 C2PA）。如果没有装，工具仍可运行，C2PA 字段会标记 `c2pa_tool_available=false`；
- 可选：`tesseract`（用于读取图片上的可见水印）。未安装时 OCR 段会显示明确的安装指引，不影响其他模块；
- 可选：环境变量 `FORENSICS_PHASH_REFERENCE_DIR`（用于 pHash 参考库反查；指向一个本地目录即可）。

### Windows

```powershell
# 在项目根目录
.\start.bat            # 仅启动 Web UI
.\start.bat --demo     # 自动准备样本 + 跑一次完整 demo + 启动 Web UI（推荐首次使用）
```

脚本会自动创建 `.venv`、安装依赖、启动 Web UI 在 http://127.0.0.1:5050 ，并自动用默认浏览器打开。

### macOS

```bash
chmod +x start.sh
./start.sh             # 仅启动 Web UI
./start.sh --demo      # 自动准备样本 + 跑一次完整 demo + 启动 Web UI（推荐首次使用）
```

### 一键 Demo（最快上手方式）

无需手填路径，直接体验全部检测能力：

```bash
python demo.py                 # 仅准备样本 + 跑分析（CLI 输出每张图风险等级）
python demo.py --serve         # 同上 + 启动 Web UI 并自动打开浏览器
python demo.py --no-download   # 离线模式，只用合成样本
```

也可以在 Web UI 首页点击「**一键运行 Demo**」按钮，等价于 `POST /api/demo`：自动扫描内置 [tools/test_images](file:///d:/workspace/project/find_image_hide/tools/test_images)，覆盖正常图、LSB 隐写、附加 ZIP / 文本、AI 元数据、版权图（Shutterstock / Getty 元数据 + 可见水印）、洗图反查（pHash 命中本地参考库）等典型场景。

> 真实样本来自 picsum.photos / Wikimedia Commons / NASA 等公开免费来源（见 [tools/download_test_images.py](file:///d:/workspace/project/find_image_hide/tools/download_test_images.py)）；可见水印 / 版权图样本基于这些真实图叠加生成（见 [tools/make_test_images.py](file:///d:/workspace/project/find_image_hide/tools/make_test_images.py)）。

### 手动启动（任意平台）

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
python webapp.py --host 127.0.0.1 --port 5050
```

> **关于端口**：默认端口是 `5050`。早期版本默认用 5000，但 macOS Monterey 起 5000 端口被系统的 AirPlay Receiver 占用，浏览器访问会被系统服务直接 403 拦截；Windows 上 5000 通常没被系统占用，但为了跨平台脚本一致，统一改成 5050。如果 5050 也被占，可手动指定其它端口，例如 `python webapp.py --port 5060`，并把浏览器地址同步改成 `http://127.0.0.1:5060`。

> **从手机 / Android 浏览器访问同一台电脑上的 Web UI**：默认 `--host 127.0.0.1` 只监听本机回环，手机访问不到。改为 `python webapp.py --host 0.0.0.0 --port 5050`，再让手机和电脑接到同一 Wi-Fi，用电脑的局域网 IP 访问，例如 `http://192.168.1.23:5050`。注意一旦绑到 `0.0.0.0`，同一网络下其它设备也能访问，**不要放到公网**，且最好仅在受信任网络下临时启用。

---

## 使用方式

启动后浏览器访问 http://127.0.0.1:5050 ，首页一共有三种触发扫描的方式：

### 方式一：把文件夹直接拖进来（推荐，最直观）

1. 启动 Web UI；
2. 从 Windows 资源管理器或 macOS Finder 里，把要扫描的整个文件夹拖到首页的虚线方框里；
3. 浏览器会递归读取该文件夹下所有支持的图片（JPG / PNG / WebP / BMP / TIFF / GIF），并以 multipart 一次性 POST 到本机 `/api/scan_upload`；
4. 上传过程中页面会显示进度条；上传完成后自动跳转到对应的 job 页，分析任务会立刻在后台开始；
5. 点方框的话也可以打开"选择文件夹"对话框（基于 `<input type="file" webkitdirectory>`），效果与拖拽一致；
6. 子目录结构会被保留：上传的文件被放到 `analysis_output/<job_id>/_uploaded/<原相对路径>` 下。

注意：

- 浏览器出于安全模型不会暴露被拖入文件的本地绝对路径，因此这种方式必然要"上传到本机后端"。整条数据流都在 127.0.0.1 内，不出网；
- 默认上传体积上限为 1 GB（[webapp.py 中的 `MAX_UPLOAD_BYTES`](file:///d:/workspace/project/find_image_hide/webapp.py#L24-L24)）。如果一次要扫的图集超过这个大小，请改用方式二；
- 服务端会自动忽略不支持的扩展名，并把跳过的文件数返回给前端展示。

### 方式二：填一个本机绝对路径

适合"原图就放在本机一个目录里、不想再上传一遍"的情况：

1. 在首页"方式二：填本地目录路径"卡片里输入目录绝对路径（Windows 例：`D:\photos`，macOS 例：`/Users/me/Pictures`）；
2. 勾选是否递归扫描，设置 worker 并发数；
3. 点「开始扫描」，进入扫描结果页（支持文件名筛选、风险等级筛选）；
4. 点击单条记录的「详情」查看每张图的 12 个分析模块。

### 方式三：一键 Demo

首页第三张卡片直接点「一键运行 Demo」即可，跑项目自带的样本集。

不论用哪种方式，详情页都会包含：

- 综合评估（badge：高风险 / 中风险 / 低风险 / 未知）；
- 12 个 tab：隐藏内容提取 / 版权 · 图库 / 隐写检测 / 元数据 / AI 来源 / 频域 (FFT) / DCT 频域 / LSB 位平面 / 噪声残差 / ELA 误差 / 证据汇总 / 原始 JSON；
- 每个 tab 按各自模块的风险等级染色（红 / 黄 / 绿 / 灰），命中风险时还会显示小圆点；
- 每个 tab 顶部都有一段中文通俗解释，告诉你这一步在做什么、什么样的指标可疑；
- OCR / pHash 等可选模块未启用时会展示中文友好引导卡，包含完整的三步安装步骤。

所有结果保存在 `analysis_output/<job_id>/` 下，**目录扫描期间数据不会上传**到任何外部服务；只有"方式一"会让本地浏览器把文件 POST 给本机 webapp 进程。

### 命令行（仅 CLI）

```bash
# 单张图
python analyze_image.py --input ./test.jpg --output ./analysis_output

# 批量目录
python analyze_image.py --input ./photos --output ./analysis_output --recursive --workers 4
```

输出目录结构：

```
analysis_output/
  summary.json                     # 整批汇总
  _uploaded/                       # 仅当通过 Web UI 拖拽上传时存在
  <slug>__<hash>/
    report.json                    # 单图完整报告
    ai_provenance.json
    visualizations/
      spectrum.png, r/g/b_spectrum.png
      dct_mean_heatmap.png, dct_histogram.png
      lsb_r.png, lsb_g.png, lsb_b.png
      residual.png, laplacian.png
```

---

## HTTP API 速览

webapp 启动后会暴露以下 HTTP 接口（仅监听 127.0.0.1）：

| Method | Path | 用途 |
| --- | --- | --- |
| POST | `/api/scan` | 提交一个**本机绝对路径**的扫描任务，body 为 `{ "directory": "...", "recursive": true, "workers": 2 }` |
| POST | `/api/scan_upload` | 拖拽 / 选择文件夹后，前端用 multipart 上传文件，字段为 `files[]` 与配套的 `paths[]`（保留相对路径），可选 `recursive`、`workers` |
| POST | `/api/demo` | 一键运行内置 demo |
| GET | `/api/jobs/<job_id>` | 查询 job 状态、已完成 / 总数 / 最新 50 条结果 |
| GET | `/api/jobs/<job_id>/summary` | 取整批 `summary.json` |
| GET | `/api/jobs/<job_id>/image/<slug>/report` | 取单图完整 report |
| GET | `/jobs/<job_id>` | 任务页（HTML） |
| GET | `/jobs/<job_id>/image/<slug>` | 单图详情页（HTML） |

`/api/scan_upload` 对路径做了严格清洗（拒绝 `..`、去掉盘符与起始斜杠、扩展名白名单），文件最终落到 `analysis_output/<job_id>/_uploaded/` 下，不会逃出该目录。

---

## report.json schema 速览

```json
{
  "schema_version": "0.1.0",
  "input": { "file_name": "...", "format": "PNG", "sha256": "...", ... },
  "overall": {
    "risk_level": "LOW|MEDIUM|HIGH|UNKNOWN",
    "confidence": 0.0,
    "summary": "...",
    "module_scores": { "fft": 0.0, "dct": 0.0, "lsb": 0.0, "noise": 0.0, "metadata": 0.0, "provenance": 0.0 }
  },
  "metadata": { ... },
  "ai_provenance": { "status": "NO_PROVENANCE_FOUND", ... },
  "frequency_analysis": { ... },
  "dct_analysis": { ... },
  "lsb_analysis": { ... },
  "noise_analysis": { ... },
  "evidence_items": [ ... ]
}
```

---

## AI Provenance / C2PA 说明

- 如果系统中存在 `c2patool`（PATH 可见），工具会自动调用并解析 manifest；
- 否则只做关键词扫描（`OpenAI` / `Gemini` / `Imagen` / `SynthID` / `Stable Diffusion` / `Midjourney` / ...）；
- 状态码：
  - `VERIFIED_AI_GENERATED` / `VERIFIED_AI_EDITED`：C2PA 验证通过 + action 表明生成 / 编辑；
  - `PROVENANCE_PRESENT_BUT_UNVERIFIED`：有 C2PA 但未验证；
  - `POSSIBLE_AI_BUT_UNVERIFIED`：仅有元数据关键词；
  - `NO_PROVENANCE_FOUND`：没有任何来源凭证。

---

## 安全 / 隐私

- webapp 默认只监听 `127.0.0.1`，不接受来自局域网或公网的请求。如果手动用 `--host 0.0.0.0`，请自己评估风险，工具不做任何鉴权；
- 所有图片处理、hash 计算、元数据读取都在本机完成，不会发往外部服务；
- C2PA 验证依赖系统中是否安装了 `c2patool`，本工具不会替你向 C2PA 服务做远程查询；
- pHash 反查仅与你在 `FORENSICS_PHASH_REFERENCE_DIR` 指向的本地目录比对，不会查云端图库；
- 拖拽上传场景：浏览器把文件 POST 给本机 webapp，整段 TCP 都在 127.0.0.1，不出本机；
- 上传体积默认上限 1 GB，超过会被 Flask 拒绝。若需要扫更大数据集，请改用「方式二：填本机绝对路径」。

---

## 限制

- 这个工具不会移除、破解或绕过任何水印；
- 不会伪造 C2PA 或 provenance metadata；
- 不能替代官方 SynthID 检测；
- FFT / DCT / LSB / Noise 异常都是统计启发式，不能直接证明 SynthID 或私有水印的存在；
- JPEG 等有损格式上 LSB 分析的可信度被自动降低；
- 拖拽上传依赖 Chromium / WebKit 系浏览器的 `webkitGetAsEntry` 能力，老版本浏览器可能只能拿到顶层文件；这种情况下请改用「方式二」。

---

## 目录结构

```
find_image_hide/
  requirements.txt
  analyze_image.py            # CLI 入口
  webapp.py                   # Flask Web UI（含 /api/scan、/api/scan_upload、/api/demo）
  demo.py                     # 一键 demo
  start.bat / start.sh        # 跨平台启动脚本
  image_forensics/            # 分析引擎
    basic_info.py
    metadata_analysis.py
    ai_provenance_analysis.py
    fft_analysis.py
    dct_analysis.py
    lsb_analysis.py
    noise_analysis.py
    extraction.py             # trailing data + LSB 文本流提取
    steganalysis.py           # χ² POV / SPA 等
    visible_watermark_ocr.py
    phash_match.py
    ela.py
    scoring.py
    analyzer.py
    batch.py
    utils.py
  tools/
    download_test_images.py   # 真实公开样本下载
    make_test_images.py       # 合成 + 版权图样本
    check_results.py          # 期望表回归
    test_images/              # demo 样本（运行后生成）
    phash_reference/          # demo 参考库（运行后生成）
  webui/
    templates/                # Jinja2 模板（index.html / job.html / image.html）
    static/                   # app.css / app.js / image.js / job.js
  analysis_output/            # 扫描结果（运行时生成）
    <job_id>/
      _uploaded/              # 拖拽上传场景下的原始文件副本
      summary.json
      <slug>__<hash>/...
```
