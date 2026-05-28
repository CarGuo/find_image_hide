# Image Forensics Inspector 跨平台图片取证工具完整提示词

## 项目目标

我要开发一个跨平台桌面工具，名字暂定为 **Image Forensics Inspector**，用于分析图片是否可能被植入不可见水印、频域水印、隐写信息，或者是否包含 OpenAI、Google Gemini、Imagen、Adobe Firefly、Stable Diffusion、Midjourney 等 AI 生成工具相关的来源凭证与元数据信号。

这个工具的核心定位不是“100% 判断图片有没有水印”，而是提供一套严谨的图片取证分析工作台：

- 展示肉眼看不到的频域、DCT、LSB、噪声残差等取证视图；
- 分析图片是否包含 C2PA / Content Credentials 等可验证来源凭证；
- 分析图片是否包含 OpenAI、Google、Gemini、Imagen、SynthID、Stable Diffusion、ComfyUI、Midjourney 等 AI 工具痕迹；
- 给出模块化可疑性评分、证据项和报告；
- 明确声明工具的局限：没有发现水印或元数据，不代表图片一定不是 AI 生成，也不代表图片一定没有隐写或水印。

请你作为资深跨平台客户端架构师、图像取证算法工程师、安全取证产品经理和 Flutter 桌面应用工程师，帮我从零设计并实现这个工具的 MVP。

---

## 产品定位

产品名称：

**Image Forensics Inspector**

产品一句话定位：

**一个跨平台图片取证分析工具，用于可视化分析不可见水印、频域异常、隐写痕迹和 AI 生成来源凭证。**

产品边界：

这个工具不能保证“绝对检测出所有水印”，也不能证明“一张图一定没有水印”。它只能基于以下证据链给出取证线索：

1. 图片元数据与来源凭证；
2. C2PA / Content Credentials 可验证信息；
3. OpenAI / Google / Gemini / Imagen / Adobe / Stable Diffusion 等 AI 工具痕迹；
4. FFT / DFT 频域异常；
5. DCT / JPEG 频域系数异常；
6. LSB 位平面异常；
7. 噪声残差异常；
8. 外部官方验证器建议。

最终输出应该是：

- 可疑性评分；
- 证据视图；
- 模块解释；
- 报告；
- 免责声明。

不要把工具描述成“AI 图片检测器”或“水印破解工具”。更准确的说法是：

**图片来源与隐写水印取证分析工具。**

---

## 总体技术栈

请优先按照下面的技术路线设计 MVP：

- Flutter Desktop：负责 macOS / Windows / Linux UI；
- Python CLI：负责图像算法原型和取证分析；
- Flutter 通过 `Process` 调用 Python CLI；
- Python 输出 `report.json` 和可视化图片；
- Flutter 读取 `report.json` 并展示结果；
- 后续可以将 Python 核心迁移到 Rust，以便优化性能、打包体积和跨平台分发体验。

MVP 阶段优先使用：

- Flutter stable；
- Material 3；
- Python 3.10+；
- Pillow；
- OpenCV；
- NumPy；
- SciPy；
- matplotlib；
- piexif / exifread；
- 可选 c2patool；
- 可选 imagehash。

---

## MVP 功能边界

第一版 MVP 支持：

### 输入

- 单张 JPG / JPEG；
- PNG；
- WebP；
- BMP；
- TIFF；
- 后续再考虑批量任务。

### 输出

- 图片基础信息；
- 元数据；
- AI provenance 分析；
- C2PA 检测结果；
- FFT 频谱图；
- RGB 频谱图；
- DCT heatmap；
- LSB bit-plane 图；
- 噪声残差图；
- JSON 报告；
- Markdown 报告；
- HTML 报告。

### 暂不做

第一版先不要做：

- 真实水印解码；
- SynthID 本地解码；
- OpenAI / Google 官方私有水印本地解码；
- 云端 AI 真假图分类；
- 批量任务；
- PDF 报告；
- 自动定论；
- 水印移除；
- 水印破解；
- 反取证。

---

## 核心设计原则

实现时请坚持以下原则：

1. **不要承诺绝对判断**

   工具不能输出：

   - `NOT_AI_GENERATED`
   - `NO_WATERMARK`
   - `DEFINITELY_CLEAN`

   应该使用：

   - `NO_PROVENANCE_FOUND`
   - `NO_OBVIOUS_WATERMARK_SIGNAL_FOUND`
   - `UNKNOWN`
   - `LOW_RISK`
   - `MEDIUM_RISK`
   - `HIGH_RISK`

2. **区分两条证据链**

   频域取证和 AI 来源凭证是两套不同证据链：

   - FFT / DCT / LSB / Noise：分析图像统计异常；
   - C2PA / Content Credentials / Provider metadata：分析来源凭证。

   不要把 FFT 异常解释成 SynthID 证据。

3. **SynthID 不做伪检测**

   SynthID 不是普通 EXIF 字段，也不能通过普通 FFT 可视化可靠判断。

   默认：

   ```json
   {
     "local_detection_supported": false,
     "external_verification_required": true
   }
   ```

4. **C2PA 是可读可验证来源凭证，但可能被移除**

   C2PA 可以通过 c2patool 或相关库读取和验证，但它可能在截图、上传下载、压缩、格式转换、社交平台重编码中丢失。

5. **所有评分都是 heuristic**

   每个模块输出都必须说明：

   - score 是启发式评分；
   - 不能作为法律鉴定结论；
   - 需要结合原图、来源链、平台信息、官方验证器进一步判断。

---

## Flutter UI 功能要求

请用 Flutter Desktop 实现跨平台 UI。

### 页面结构

主窗口分为：

1. 左侧任务区；
2. 中间图片预览区；
3. 右侧结果摘要区；
4. 下方或右侧 Tab 分析区。

### 页面 Tab

需要包含以下 Tab：

1. Overview；
2. Metadata；
3. AI Provenance；
4. FFT Spectrum；
5. DCT Analysis；
6. LSB Analysis；
7. Noise Residual；
8. Report。

### Home / Overview

展示：

- 文件名；
- 路径；
- 文件大小；
- 图片尺寸；
- MIME 类型；
- 格式；
- 色彩模式；
- 通道数；
- 是否有 alpha；
- SHA256；
- perceptual hash；
- 总体风险等级；
- 总体解释。

### Metadata Tab

展示：

- EXIF；
- XMP；
- IPTC；
- PNG chunks；
- JPEG comments；
- WebP metadata；
- Software；
- CreatorTool；
- Description；
- Comment；
- DateTime；
- GPS；
- 其他原始字段。

### AI Provenance Tab

新增一个专门的 AI 来源分析页。

展示：

- `ai_provenance.status`
- `c2pa_present`
- `c2pa_verified`
- `c2pa_tool_available`
- `detected_providers`
- `detected_models_or_tools`
- `claim_generator`
- `producer`
- `issuer`
- `actions`
- `ingredients`
- `metadata_ai_keywords`
- `synthid.local_detection_supported`
- `synthid.external_verification_required`
- `synthid.note`

页面结构：

1. 顶部状态卡片

   - AI Provenance Status；
   - C2PA Present；
   - C2PA Verified；
   - Detected Provider；
   - Detected Tool / Model。

2. C2PA 区域

   - 是否发现 C2PA；
   - 是否验证通过；
   - Claim Generator；
   - Producer；
   - Issuer；
   - Actions；
   - Ingredients。

3. Provider Signals 区域

   - OpenAI signals；
   - Google / Gemini signals；
   - Adobe / Firefly signals；
   - Stable Diffusion / ComfyUI signals；
   - Midjourney signals。

4. SynthID 区域

   - 本地检测：默认不支持；
   - 说明：SynthID 需要官方检测能力；
   - 操作按钮：
     - Open Content Credentials Verify；
     - Open OpenAI verification guide；
     - Open Gemini / SynthID verification guide。

5. Disclaimer 区域

   - 没有 metadata 不代表不是 AI 图；
   - 有 metadata 也需要验证签名；
   - 频域异常不是 SynthID 证据；
   - SynthID 不是普通 EXIF / XMP 字段。

### FFT Spectrum Tab

展示：

- grayscale spectrum；
- R spectrum；
- G spectrum；
- B spectrum；
- frequency peak list；
- symmetric peak pairs；
- spectrum anomaly score；
- explanation；
- limitations。

### DCT Analysis Tab

展示：

- 8x8 DCT mean heatmap；
- DCT coefficient histogram；
- low / mid / high frequency stats；
- DCT anomaly score；
- JPEG compression notes；
- explanation；
- limitations。

### LSB Analysis Tab

展示：

- lsb_r.png；
- lsb_g.png；
- lsb_b.png；
- entropy；
- 0/1 ratio；
- neighborhood correlation；
- randomness score；
- LSB anomaly score；
- explanation；
- limitations。

### Noise Residual Tab

展示：

- residual.png；
- laplacian.png；
- local noise inconsistency score；
- explanation；
- limitations。

### Report Tab

展示：

- Markdown 报告预览；
- HTML 报告预览；
- 导出按钮；
- 打开输出目录按钮。

---

## Flutter 工程结构

请生成以下 Flutter 目录结构：

```text
image_forensics_inspector/
  pubspec.yaml
  README.md
  lib/
    main.dart
    app.dart
    models/
      analysis_task.dart
      analysis_status.dart
      risk_level.dart
      evidence_item.dart
      visualization_asset.dart
      image_basic_info.dart
      metadata_result.dart
      ai_provenance_result.dart
      frequency_analysis_result.dart
      dct_analysis_result.dart
      lsb_analysis_result.dart
      noise_analysis_result.dart
      analysis_report.dart
    services/
      image_import_service.dart
      analysis_service.dart
      external_engine_service.dart
      report_export_service.dart
      app_settings_service.dart
    pages/
      home_page.dart
    widgets/
      image_drop_zone.dart
      image_preview_panel.dart
      overview_tab.dart
      metadata_tab.dart
      ai_provenance_tab.dart
      fft_spectrum_tab.dart
      dct_analysis_tab.dart
      lsb_analysis_tab.dart
      noise_residual_tab.dart
      report_tab.dart
      risk_badge.dart
      evidence_list.dart
      visualization_viewer.dart
  python_engine/
    requirements.txt
    analyze_image.py
    image_forensics/
      __init__.py
      basic_info.py
      metadata_analysis.py
      ai_provenance_analysis.py
      fft_analysis.py
      dct_analysis.py
      lsb_analysis.py
      noise_analysis.py
      scoring.py
      report_writer.py
      utils.py
```

---

## Flutter 推荐依赖

请根据实际可用情况选择稳定依赖，优先考虑：

```yaml
dependencies:
  flutter:
    sdk: flutter
  desktop_drop: any
  file_picker: any
  path: any
  path_provider: any
  process_run: any
  crypto: any
  mime: any
  provider: any
  flutter_markdown: any
  url_launcher: any
  window_manager: any
```

要求：

- 不要把图像重计算放在 Flutter UI isolate；
- Flutter 只负责调用 Python CLI、读 JSON、展示图片；
- 支持取消任务；
- 支持错误展示；
- 支持配置 Python 路径；
- 支持打开输出目录；
- 所有 UI 错误要可读。

---

## Python CLI 设计

Python CLI 用法：

```bash
python analyze_image.py --input ./test.jpg --output ./analysis_output
```

输出：

```text
analysis_output/
  report.json
  report.md
  report.html
  visualizations/
    original_preview.png
    spectrum.png
    r_spectrum.png
    g_spectrum.png
    b_spectrum.png
    dct_mean_heatmap.png
    dct_histogram.png
    lsb_r.png
    lsb_g.png
    lsb_b.png
    residual.png
    laplacian.png
  ai_provenance.json
```

### Python requirements

```text
pillow
numpy
opencv-python
scipy
matplotlib
piexif
exifread
imagehash
```

c2patool 是可选外部命令，不一定通过 pip 安装。

---

## Python 分析模块要求

### basic_info.py

实现：

- 文件大小；
- 图片格式；
- 宽高；
- 通道数；
- 色彩模式；
- 是否有 alpha；
- SHA256；
- perceptual hash；
- MIME 类型。

输出字段：

```json
{
  "file_name": "test.jpg",
  "file_path": "./test.jpg",
  "file_size_bytes": 123456,
  "mime_type": "image/jpeg",
  "format": "JPEG",
  "width": 1024,
  "height": 768,
  "mode": "RGB",
  "channels": 3,
  "has_alpha": false,
  "sha256": "...",
  "perceptual_hash": "..."
}
```

---

### metadata_analysis.py

实现：

1. 读取 EXIF；
2. 读取 XMP；
3. 读取 IPTC；
4. 读取 PNG tEXt / iTXt / zTXt；
5. 读取 JPEG APP segments；
6. 读取 JPEG comment；
7. 读取 WebP metadata chunks；
8. 搜索可疑字段；
9. 输出原始 metadata 和摘要。

重点关键词：

- Software；
- CreatorTool；
- Comment；
- Description；
- AI；
- OpenAI；
- ChatGPT；
- DALL·E；
- DALL-E；
- GPT-4o；
- Gemini；
- Imagen；
- SynthID；
- Stable Diffusion；
- ComfyUI；
- Automatic1111；
- Midjourney；
- Adobe Firefly；
- C2PA；
- Content Credentials。

---

### ai_provenance_analysis.py

实现一个 AI Provenance 检测模块，用来分析图片是否包含 AI 生成工具相关的来源信息。

这个模块不要和传统 FFT / DCT / LSB 隐写检测混为一谈。它专门处理以下信息：

1. C2PA / Content Credentials；
2. OpenAI provenance signals；
3. Google / Gemini / Imagen provenance signals；
4. Adobe Firefly / Content Credentials signals；
5. Stable Diffusion / ComfyUI / Automatic1111 metadata；
6. Midjourney / Ideogram / Leonardo 等工具痕迹；
7. SynthID 外部验证建议。

功能要求：

#### 1. 读取普通元数据

读取：

- EXIF；
- XMP；
- IPTC；
- PNG tEXt / iTXt / zTXt；
- JPEG APP segments；
- WebP metadata chunks。

#### 2. 搜索 AI 来源关键词

包括但不限于：

```text
OpenAI
ChatGPT
DALL·E
DALL-E
GPT-4o
GPT Image
Google
Gemini
Imagen
DeepMind
SynthID
C2PA
Content Credentials
Adobe Firefly
Midjourney
Stable Diffusion
ComfyUI
Automatic1111
AUTOMATIC1111
InvokeAI
Leonardo
Ideogram
```

#### 3. C2PA 检测

- 检查文件中是否存在 C2PA manifest 或相关 box / chunk / segment；
- 如果本地环境有 `c2patool`，则调用 `c2patool` 读取和验证；
- 如果没有 `c2patool`，返回 `c2pa_tool_available=false`；
- 即使没有 `c2patool`，也要保留普通 metadata 扫描结果；
- 解析 c2patool JSON 输出；
- 提取：
  - producer；
  - issuer；
  - claim_generator；
  - actions；
  - ingredients；
  - signature 状态。

#### 4. OpenAI 检测

- 如果 C2PA 中出现 OpenAI、ChatGPT、DALL·E、GPT-4o、GPT Image 等来源信息，则标记为 `possible_openai_generated_or_edited`；
- 如果 C2PA 签名可验证，则标记为 `verified_openai_provenance`；
- 不要尝试本地伪造 SynthID 检测结论；
- 如果没有 C2PA 但用户怀疑 OpenAI 来源，输出 unknown，并建议使用 OpenAI 官方验证工具或官方说明路径。

#### 5. Google / Gemini 检测

- 如果 C2PA 或 metadata 中出现 Google、Gemini、Imagen、DeepMind 等来源信息，则标记为 `possible_google_ai_generated_or_edited`；
- 如果 C2PA 签名可验证，则标记为 `verified_google_provenance`；
- 对 SynthID 只做说明：
  - `local_synthid_detection_supported=false`
  - `external_verification_required=true`
  - `recommended_external_check=Gemini app or official SynthID verification`
- 不要把 FFT 频谱异常解释成 SynthID 证据。

#### 6. 输出字段

```json
{
  "ai_provenance": {
    "status": "NO_PROVENANCE_FOUND",
    "risk_level": "UNKNOWN",
    "c2pa_present": false,
    "c2pa_verified": null,
    "c2pa_tool_available": false,
    "detected_providers": [],
    "detected_models_or_tools": [],
    "claim_generator": null,
    "producer": null,
    "issuer": null,
    "actions": [],
    "ingredients": [],
    "metadata_ai_keywords": [],
    "raw_c2pa": null,
    "synthid": {
      "local_detection_supported": false,
      "possible_provider": null,
      "external_verification_required": true,
      "note": "SynthID is not a normal EXIF/XMP metadata field. Reliable detection requires official verification support."
    },
    "external_verification": {
      "content_credentials_verify_recommended": true,
      "openai_verification_recommended": true,
      "gemini_synthid_check_recommended": true
    },
    "limitations": [
      "No provenance metadata found does not prove the image is not AI-generated.",
      "C2PA metadata may be stripped by screenshots, format conversion, social platforms, or image recompression.",
      "Local FFT/DCT/LSB analysis cannot reliably determine whether a SynthID watermark is present."
    ]
  }
}
```

#### 7. 结论逻辑

使用以下状态，不允许输出 `NOT_AI_GENERATED`：

```text
VERIFIED_AI_GENERATED
VERIFIED_AI_EDITED
PROVENANCE_PRESENT_BUT_UNVERIFIED
NO_PROVENANCE_FOUND
PROVENANCE_STRIPPED_OR_UNKNOWN
POSSIBLE_AI_BUT_UNVERIFIED
```

规则：

- 如果 C2PA 可验证且 action 表明 generated / produced / created：
  - `VERIFIED_AI_GENERATED`
- 如果 C2PA 可验证且 action 表明 edited / transformed / modified：
  - `VERIFIED_AI_EDITED`
- 如果 C2PA 存在但无法验证：
  - `PROVENANCE_PRESENT_BUT_UNVERIFIED`
- 如果只有普通 metadata 关键词：
  - `POSSIBLE_AI_BUT_UNVERIFIED`
- 如果没有任何来源信息：
  - `NO_PROVENANCE_FOUND`

#### 8. 报告解释必须包含

- 未发现 C2PA 或 AI 元数据不代表图片不是 AI 生成；
- C2PA 可能在平台上传、截图、格式转换、压缩过程中丢失；
- SynthID 需要官方检测能力，本工具默认不做本地 SynthID 判定；
- FFT / DCT / LSB 异常不能直接证明 SynthID 存在。

---

### fft_analysis.py

实现图片 FFT 频域分析模块。

输入：

- 图片路径；
- 输出目录。

处理流程：

1. 读取图片并转为灰度；
2. resize 到合理大小，例如最大边 1024，避免计算过大；
3. 做 2D FFT；
4. 使用 `fftshift` 将低频移动到中心；
5. 计算 log magnitude spectrum；
6. 保存频谱图 `spectrum.png`；
7. 对 R / G / B 三个通道分别做 FFT；
8. 保存：
   - `r_spectrum.png`
   - `g_spectrum.png`
   - `b_spectrum.png`
9. 对频谱图进行异常峰值检测：
   - 忽略中心低频区域；
   - 计算均值、标准差；
   - 找出超过 `mean + k * std` 的峰值；
   - 合并邻近峰值；
   - 检查峰值是否成对称分布；
10. 输出：
   - peak_count；
   - symmetric_peak_pairs；
   - peak_strength_mean；
   - spectrum_anomaly_score；
   - channel_frequency_anomaly_score；
   - evidence_items。

要求：

- 代码必须清晰；
- 评分必须说明是 heuristic；
- 不要把自然纹理误判为水印；
- 对周期纹理、网格纹理、压缩伪影要降低置信度；
- 输出 JSON 可被上层 UI 消费。

---

### dct_analysis.py

实现 DCT / JPEG 频域异常分析模块。

目标：

检测图片中频 DCT 系数是否存在异常分布、周期扰动或疑似水印痕迹。

输入：

- 图片路径；
- 输出目录。

处理流程：

1. 读取图片，转为 YCbCr 或灰度；
2. 将亮度通道按 8x8 block 切分；
3. 对每个 block 做 DCT；
4. 统计每个 DCT 坐标位置的：
   - mean；
   - std；
   - abs_mean；
   - zero_ratio；
5. 生成 8x8 DCT mean heatmap；
6. 生成中频系数直方图；
7. 分析：
   - 中频系数是否异常集中；
   - 中频系数是否存在周期性偏移；
   - 高频系数是否被异常抹平；
   - 低频是否正常；
8. 输出：
   - dct_anomaly_score；
   - dct_risk_level；
   - evidence_items。

要求：

- 明确区分 JPEG 压缩伪影和疑似水印扰动；
- 不要给出绝对判断；
- 给出 LOW / MEDIUM / HIGH / UNKNOWN 风险；
- 支持非 JPEG 图片，但要说明 DCT 分析只是基于像素重新计算，不等价于原始 JPEG 编码系数。

---

### lsb_analysis.py

实现 LSB 隐写可疑性分析模块。

输入：

- 图片路径；
- 输出目录。

处理流程：

1. 读取图片为 RGB；
2. 提取 R / G / B 三个通道的最低有效位 bit-plane；
3. 保存：
   - `lsb_r.png`
   - `lsb_g.png`
   - `lsb_b.png`
4. 计算每个通道 LSB 的：
   - 0/1 比例；
   - Shannon entropy；
   - 邻域相关性；
   - 随机性指标；
5. 对比三个通道之间的 LSB 统计差异；
6. 检查是否存在：
   - 异常接近随机；
   - 异常规则图案；
   - 局部区域突变；
7. 输出：
   - lsb_entropy_r/g/b；
   - lsb_balance_r/g/b；
   - lsb_randomness_score；
   - lsb_anomaly_score；
   - evidence_items。

要求：

- 对自然图片、截图、压缩图片分别给出解释；
- 不要简单把高熵当作隐写；
- PNG / BMP 的 LSB 检测置信度高于 JPEG；
- JPEG 图像的 LSB 分析要降低权重。

---

### noise_analysis.py

实现噪声残差分析模块。

输入：

- 图片路径；
- 输出目录。

处理流程：

1. 读取图片；
2. 转为 RGB 或灰度；
3. 使用 Gaussian blur 后相减获取 residual；
4. 使用 Laplacian 获取边缘 / 噪声残差；
5. 保存：
   - `residual.png`
   - `laplacian.png`
6. 计算局部噪声强度分布；
7. 检查是否存在局部噪声不一致；
8. 输出：
   - noise_inconsistency_score；
   - residual_stats；
   - evidence_items。

---

### scoring.py

实现统一评分逻辑。

模块评分：

- metadata_score；
- ai_provenance_score；
- fft_score；
- dct_score；
- lsb_score；
- noise_score。

最终风险：

```text
LOW
MEDIUM
HIGH
UNKNOWN
```

规则：

1. 如果 AI Provenance 有可验证 C2PA，优先在来源凭证层面给明确状态；
2. 如果没有来源凭证，不代表不是 AI 图；
3. 如果多个图像统计模块都异常，可以提高可疑性；
4. 如果只有单个模块异常，保持谨慎；
5. 如果图片是 JPEG，降低 LSB 分析权重；
6. 如果图片经过社交平台重编码，降低元数据缺失的解释强度；
7. 所有最终结论必须带 limitations。

---

## report.json Schema

请按照以下结构输出稳定 JSON，方便 Flutter 解析：

```json
{
  "schema_version": "0.1.0",
  "tool_name": "Image Forensics Inspector",
  "analysis_id": "uuid",
  "created_at": "2026-01-01T00:00:00Z",
  "input": {
    "file_name": "test.jpg",
    "file_path": "./test.jpg",
    "file_size_bytes": 123456,
    "mime_type": "image/jpeg",
    "format": "JPEG",
    "width": 1024,
    "height": 768,
    "mode": "RGB",
    "channels": 3,
    "has_alpha": false,
    "sha256": "...",
    "perceptual_hash": "..."
  },
  "overall": {
    "risk_level": "UNKNOWN",
    "confidence": 0.42,
    "summary": "No verified provenance metadata was found. Some frequency-domain anomalies were detected, but they are not sufficient to prove watermarking.",
    "limitations": [
      "This tool cannot prove that an image has no watermark.",
      "Unknown private watermarking schemes may not be detectable.",
      "C2PA metadata may be stripped by screenshots, recompression, or format conversion.",
      "SynthID requires official verification support."
    ]
  },
  "metadata": {
    "has_exif": false,
    "has_xmp": false,
    "has_iptc": false,
    "has_png_text": false,
    "has_jpeg_comment": false,
    "raw": {},
    "suspicious_fields": [],
    "metadata_ai_keywords": []
  },
  "ai_provenance": {
    "status": "NO_PROVENANCE_FOUND",
    "risk_level": "UNKNOWN",
    "c2pa_present": false,
    "c2pa_verified": null,
    "c2pa_tool_available": false,
    "detected_providers": [],
    "detected_models_or_tools": [],
    "claim_generator": null,
    "producer": null,
    "issuer": null,
    "actions": [],
    "ingredients": [],
    "metadata_ai_keywords": [],
    "raw_c2pa": null,
    "synthid": {
      "local_detection_supported": false,
      "possible_provider": null,
      "external_verification_required": true,
      "note": "SynthID is not a normal EXIF/XMP metadata field. Reliable detection requires official verification support."
    },
    "external_verification": {
      "content_credentials_verify_recommended": true,
      "openai_verification_recommended": true,
      "gemini_synthid_check_recommended": true
    },
    "limitations": [
      "No provenance metadata found does not prove the image is not AI-generated.",
      "C2PA metadata may be stripped by screenshots, format conversion, social platforms, or image recompression.",
      "Local FFT/DCT/LSB analysis cannot reliably determine whether a SynthID watermark is present."
    ]
  },
  "frequency_analysis": {
    "spectrum_image": "visualizations/spectrum.png",
    "r_spectrum_image": "visualizations/r_spectrum.png",
    "g_spectrum_image": "visualizations/g_spectrum.png",
    "b_spectrum_image": "visualizations/b_spectrum.png",
    "peak_count": 0,
    "symmetric_peak_pairs": [],
    "peak_strength_mean": 0.0,
    "spectrum_anomaly_score": 0.0,
    "channel_frequency_anomaly_score": 0.0,
    "risk_level": "LOW",
    "evidence_items": []
  },
  "dct_analysis": {
    "dct_mean_heatmap": "visualizations/dct_mean_heatmap.png",
    "dct_histogram": "visualizations/dct_histogram.png",
    "low_frequency_stats": {},
    "mid_frequency_stats": {},
    "high_frequency_stats": {},
    "dct_anomaly_score": 0.0,
    "risk_level": "LOW",
    "evidence_items": []
  },
  "lsb_analysis": {
    "lsb_r_image": "visualizations/lsb_r.png",
    "lsb_g_image": "visualizations/lsb_g.png",
    "lsb_b_image": "visualizations/lsb_b.png",
    "lsb_entropy": {
      "r": 0.0,
      "g": 0.0,
      "b": 0.0
    },
    "lsb_balance": {
      "r": 0.0,
      "g": 0.0,
      "b": 0.0
    },
    "lsb_randomness_score": 0.0,
    "lsb_anomaly_score": 0.0,
    "risk_level": "LOW",
    "evidence_items": []
  },
  "noise_analysis": {
    "residual_image": "visualizations/residual.png",
    "laplacian_image": "visualizations/laplacian.png",
    "noise_inconsistency_score": 0.0,
    "risk_level": "LOW",
    "evidence_items": []
  },
  "evidence_items": [
    {
      "module": "ai_provenance",
      "severity": "info",
      "title": "No C2PA manifest found",
      "description": "No C2PA provenance metadata was detected. This does not prove the image is not AI-generated.",
      "confidence": 0.5
    }
  ]
}
```

---

## Markdown 报告模板

请生成 `report.md`，结构如下：

```markdown
# Image Forensics Report

## 1. Summary

- File name: {{file_name}}
- SHA256: {{sha256}}
- Format: {{format}}
- Size: {{width}} x {{height}}
- Final risk level: {{risk_level}}
- Confidence: {{confidence}}

{{summary}}

## 2. Important Disclaimer

This tool provides forensic signals and heuristic analysis. It cannot prove that an image definitely contains a watermark, and it cannot prove that an image is definitely free of watermarking or AI generation.

No provenance metadata found does not prove the image is not AI-generated. C2PA metadata may be stripped by screenshots, uploads, downloads, resizing, recompression, social platforms, or format conversion. SynthID is not a normal EXIF/XMP field and cannot be reliably detected by ordinary metadata parsing or FFT visualization.

## 3. AI Provenance

Status: {{ai_provenance.status}}

C2PA present: {{ai_provenance.c2pa_present}}

C2PA verified: {{ai_provenance.c2pa_verified}}

Detected providers: {{ai_provenance.detected_providers}}

Detected tools or models: {{ai_provenance.detected_models_or_tools}}

Claim generator: {{ai_provenance.claim_generator}}

Producer: {{ai_provenance.producer}}

Issuer: {{ai_provenance.issuer}}

Actions: {{ai_provenance.actions}}

Ingredients: {{ai_provenance.ingredients}}

### SynthID Notes

Local SynthID detection supported: {{ai_provenance.synthid.local_detection_supported}}

External verification required: {{ai_provenance.synthid.external_verification_required}}

{{ai_provenance.synthid.note}}

## 4. Metadata

{{metadata_summary}}

## 5. Frequency Analysis

Spectrum anomaly score: {{frequency_analysis.spectrum_anomaly_score}}

Channel frequency anomaly score: {{frequency_analysis.channel_frequency_anomaly_score}}

Peak count: {{frequency_analysis.peak_count}}

Symmetric peak pairs: {{frequency_analysis.symmetric_peak_pairs}}

Visualization:

- {{frequency_analysis.spectrum_image}}
- {{frequency_analysis.r_spectrum_image}}
- {{frequency_analysis.g_spectrum_image}}
- {{frequency_analysis.b_spectrum_image}}

## 6. DCT Analysis

DCT anomaly score: {{dct_analysis.dct_anomaly_score}}

Risk level: {{dct_analysis.risk_level}}

Visualizations:

- {{dct_analysis.dct_mean_heatmap}}
- {{dct_analysis.dct_histogram}}

## 7. LSB Analysis

LSB anomaly score: {{lsb_analysis.lsb_anomaly_score}}

LSB randomness score: {{lsb_analysis.lsb_randomness_score}}

Visualizations:

- {{lsb_analysis.lsb_r_image}}
- {{lsb_analysis.lsb_g_image}}
- {{lsb_analysis.lsb_b_image}}

## 8. Noise Residual Analysis

Noise inconsistency score: {{noise_analysis.noise_inconsistency_score}}

Visualizations:

- {{noise_analysis.residual_image}}
- {{noise_analysis.laplacian_image}}

## 9. Evidence Items

{{evidence_items}}

## 10. Limitations

- This tool cannot prove that an image has no watermark.
- Unknown private watermarking schemes may not be detectable.
- C2PA metadata may be stripped by screenshots, recompression, social platforms, or format conversion.
- SynthID requires official verification support.
- FFT / DCT / LSB analysis cannot reliably identify provider-specific private watermarks.
- JPEG recompression may destroy or create misleading statistical traces.
```

---

## Python CLI 主流程

请实现 `analyze_image.py`：

流程：

1. 解析命令行参数；
2. 创建输出目录；
3. 创建 `visualizations/`；
4. 调用 basic_info；
5. 调用 metadata_analysis；
6. 调用 ai_provenance_analysis；
7. 调用 fft_analysis；
8. 调用 dct_analysis；
9. 调用 lsb_analysis；
10. 调用 noise_analysis；
11. 调用 scoring；
12. 写 `report.json`；
13. 写 `ai_provenance.json`；
14. 写 `report.md`；
15. 写 `report.html`；
16. stdout 输出 report.json 路径；
17. 任何错误都要写入 report 的 errors 字段，并返回非零退出码或可读错误。

---

## Flutter 调用 Python CLI

Flutter `AnalysisService` 需要实现：

```dart
Future<AnalysisReport> analyzeImage({
  required String imagePath,
  required String outputDir,
});
```

内部：

1. 找到 Python 路径；
2. 找到 `analyze_image.py`；
3. 使用 `Process.start` 调用；
4. 监听 stdout；
5. 监听 stderr；
6. 支持取消；
7. 读取 `report.json`；
8. 解析成 Dart model；
9. 返回 `AnalysisReport`；
10. 出错时展示可读错误。

不要使用同步阻塞调用。

---

## Dart Model 要求

请生成以下 Dart model：

- `RiskLevel`
- `AnalysisStatus`
- `EvidenceItem`
- `VisualizationAsset`
- `ImageBasicInfo`
- `MetadataResult`
- `AiProvenanceResult`
- `SynthIdInfo`
- `ExternalVerificationInfo`
- `FrequencyAnalysisResult`
- `DctAnalysisResult`
- `LsbAnalysisResult`
- `NoiseAnalysisResult`
- `AnalysisReport`

所有 model 都需要：

- `fromJson`
- `toJson`
- null-safe
- 对未知字段保持兼容
- 对缺字段给默认值

---

## 外部验证按钮

AI Provenance Tab 中提供外部验证按钮，但不要硬编码不可维护逻辑。

按钮包括：

1. Content Credentials Verify；
2. OpenAI provenance / verification guide；
3. Gemini / SynthID verification guide。

如果没有配置 URL，则按钮置灰或显示说明。

注意：

- 工具不能伪装成 OpenAI / Google 官方验证器；
- 外部验证入口只能作为建议；
- 报告里要写清楚“external verification recommended”。

---

## README 要求

生成 README，包含：

1. 项目介绍；
2. 工具能力；
3. 工具不能做什么；
4. 安装 Flutter；
5. 安装 Python 依赖；
6. 可选安装 c2patool；
7. 运行 Flutter；
8. 单独运行 Python CLI；
9. 输出目录说明；
10. report.json schema 简介；
11. AI Provenance 说明；
12. C2PA 说明；
13. SynthID 限制说明；
14. 免责声明。

README 中要明确写：

```text
This tool does not prove that an image is or is not AI-generated.
This tool does not provide official SynthID detection.
This tool does not remove, bypass, or crack watermarks.
```

---

## 安全与合规边界

这个工具只做取证分析和来源凭证检查，不做以下事情：

- 不移除水印；
- 不破解水印；
- 不绕过平台检测；
- 不伪造 C2PA；
- 不伪造 provenance metadata；
- 不生成规避检测的图片；
- 不提供反取证建议。

如果用户要求扩展上述能力，应该拒绝，并建议只做合法取证、内容来源验证和透明度分析。

---

## 后续 Rust 迁移路线

MVP 稳定后，可以设计 Rust core：

```text
image_forensics_core/
  crates/
    image_forensics_core/
    image_forensics_cli/
    image_forensics_ffi/
```

核心模块：

- metadata；
- image_loader；
- ai_provenance；
- fft_analysis；
- dct_analysis；
- lsb_analysis；
- noise_analysis；
- scoring；
- report；
- visualization。

推荐依赖：

```text
image
rustfft
ndarray
serde
serde_json
clap
anyhow
thiserror
```

FFI 接口：

```c
char* analyze_image(const char* input_path, const char* output_dir);
void free_string(char* ptr);
```

Rust 迁移目标：

- 减少 Python sidecar 依赖；
- 提高跨平台打包体验；
- 提升 FFT / DCT 性能；
- 方便发布单二进制 CLI；
- Flutter 通过 FFI 或本地进程调用 Rust core。

---

## 最终交付要求

请你基于上面的完整需求，生成一个可运行 MVP 项目。

生成顺序：

1. 完整目录结构；
2. Flutter `pubspec.yaml`；
3. Python `requirements.txt`；
4. Dart model；
5. Flutter service；
6. Flutter UI；
7. Python CLI 主入口；
8. Python 各分析模块；
9. scoring；
10. report writer；
11. README；
12. 运行说明；
13. 测试用例；
14. 后续优化建议。

每个文件都要给完整代码，不要只给片段。

要求：

- 代码可运行；
- 结构清晰；
- 错误可读；
- UI 不阻塞；
- JSON schema 稳定；
- 所有结论都谨慎；
- 所有水印和 AI 来源判断都必须带限制说明；
- 不要把没有元数据解释成“不是 AI 图”；
- 不要把 FFT / DCT 异常解释成 SynthID 证据；
- 不要实现水印移除、破解或规避检测能力。
