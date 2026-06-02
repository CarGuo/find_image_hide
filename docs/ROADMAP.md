# 项目路线图（Roadmap）

> 最后更新：2026-06-02（P1 三件套完成）
>
> 本文件用于沉淀**能力规划 + 决策记录**，避免历次 conversation context 丢失。  
> 每次推进一个阶段就回到这里勾掉对应项，并记下当时的决策依据。

---

## 一、当前能力盘点

### 已落地的检测模块（[image_forensics/](file:///d:/workspace/project/find_image_hide/image_forensics)）

| 模块 | 文件 | 算法/能力 |
|---|---|---|
| LSB 隐写 | [lsb_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/lsb_analysis.py) | LSB 8 位面 × 3 通道 / cross-channel diff / hierarchy violation |
| 通用隐写 | [steganalysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/steganalysis.py) | 通用统计 + 差分 |
| 频域 | [fft_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/fft_analysis.py)、[dct_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/dct_analysis.py) | FFT/DCT 频谱异常 |
| 篡改 | [ela.py](file:///d:/workspace/project/find_image_hide/image_forensics/ela.py)、[noise_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/noise_analysis.py) | ELA + 噪声 |
| Copy-Move | [copy_move_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/copy_move_analysis.py) | 8×8 块 DCT + zig-zag 签名 + shift-vector histogram + SNR |
| AI 启发式 | [ai_heuristics.py](file:///d:/workspace/project/find_image_hide/image_forensics/ai_heuristics.py) | 通道相关 + HF 残差 + 36-bin 色相直方图（永远 ≤ MEDIUM） |
| 元数据 | [metadata_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/metadata_analysis.py)、[psd_metadata.py](file:///d:/workspace/project/find_image_hide/image_forensics/psd_metadata.py) | EXIF / IPTC / XMP / PNG-text / PSD |
| 附加文件 | [extraction.py](file:///d:/workspace/project/find_image_hide/image_forensics/extraction.py) | EOF 后追加 ZIP/TXT/Polyglot |
| 水印 | [invisible_watermark_detect.py](file:///d:/workspace/project/find_image_hide/image_forensics/invisible_watermark_detect.py)、[visible_watermark_ocr.py](file:///d:/workspace/project/find_image_hide/image_forensics/visible_watermark_ocr.py) | DwtDct + OCR |
| pHash 同源 | [phash_match.py](file:///d:/workspace/project/find_image_hide/image_forensics/phash_match.py) | 感知哈希查重 |
| AI 来源 | [ai_provenance_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/ai_provenance_analysis.py) | reverse-SynthID（已通） |

### 关键能力盲点

- ✅ ~~没有 zsteg 风格的 PNG 多通道·多位面 LSB 扫描~~ → P1.1 已扩展 8 位面 × 3 通道
- ✅ ~~没有 Copy-Move（复制粘贴）篡改定位~~ → P1.3 已落地（8×8 块 DCT + shift-vector histogram）
- ✅ ~~AI 检测仅靠 metadata 关键词 + reverse-SynthID~~ → P1.4 已加颜色 / HF 启发式（仅辅助 ≤ MEDIUM）
- ❌ 没有 steghide / F5 / OutGuess / JSteg 等 JPEG DCT 域隐写检测
- ❌ 没有 Splicing（拼接）篡改定位 / 噪声残差网络
- ❌ 没有 GAN/扩散指纹（CNNDetection / DIRE 等深度模型）
- ❌ 没有 C2PA / Content Credentials 凭据校验
- ❌ 没有 Camera Ballistics / PRNU 设备指纹
- ❌ 没有反向图像搜索 / 主张比对
- ❌ 没有 Deepfake 人脸检测
- ❌ 格式兼容：HEIC / HEIF / AVIF / WebP / TIFF / RAW 支持薄弱

---

## 二、行业基线（已调研）

### 商业竞品

- **Amped Authenticate** — 司法级取证黄金标准，40+ filter，可重现报告
- **InVID-WeVerify** — 记者验证插件，反向搜索多引擎
- **FotoForensics / Forensically** — 浏览器 triage（ELA / Noise / Clone）
- **Reality Defender / Truepic / TrueMedia** — 商用 AI / Deepfake SaaS
- **DeepFake-O-Meter v2.0**（开源平台）— 18 个 docker 化检测器

### 强相关开源

| 项目 | 用途 | 接入难度 |
|---|---|---|
| stegoveritas（pip 包） | LSB / 位面 / metadata triage | 低 |
| zsteg（Ruby gem） | PNG/BMP 多通道 LSB | 中 |
| stegseek | steghide cracker | 低 |
| binwalk | 嵌入文件签名扫描 | 低 |
| Aletheia | LSB / J-UNIWARD / SPA / SteganoGAN | 高 |
| CNNDetection | GAN 生成图检测 | 高 |
| AIDE / UniversalFakeDetect / NPR / DIRE | AI 检测 backbone | 高 |
| IMDLBenCo | 篡改定位统一基准 | 高 |
| c2pa-python SDK | Content Credentials 校验 | 中 |

### 学术 / 工业级数据集

**隐写**：BOSSBase 1.01 / BOWS2 / ALASKA2 / LSSD / StegoAppDB  
**AI 生成**：GenImage / AI-Face / Chameleon / DiffusionDB  
**篡改**：CASIA v1/v2 / CoMoFoD / Columbia / NIST16 / DEFACTO / IMD2020 / COVERAGE  
**真实分布对照**：picsum.photos / Unsplash / Wikimedia / RAISE / Dresden / Kodak Lossless

---

## 三、阶段规划

### 🎯 P0 — 数据集扩展（进行中）

**P0.1** 扩充 [download_test_images.py](file:///d:/workspace/project/find_image_hide/tools/download_test_images.py)：在现有 9 条基础上新增 `clean_real / ai_generated / c2pa_signed` 等子集的免费公有领域 URL，总量 ~25 张，**重在展示，不堆量**

**P0.2** 新建 [tools/launder_image.py](file:///d:/workspace/project/find_image_hide/tools/launder_image.py)：生成 Telegram / 微信 / Twitter 三档压缩的 laundered 变体，驱动 pHash 鲁棒性测试

**P0.3** 新建 [tools/datasets/](file:///d:/workspace/project/find_image_hide/tools/datasets) 下的 `fetch_genimage_mini.py / fetch_chameleon_mini.py / fetch_casia_v2_mini.py / fetch_comofod_mini.py`，每数据集 5-10 张，懒加载到 `.cache/datasets/`

**P0.4** 新建 [tools/build_dataset_index.py](file:///d:/workspace/project/find_image_hide/tools/build_dataset_index.py)：扫描 `test_images + .cache/datasets` 生成 `dataset_index.json`（label / source / license / expected_findings）

**P0.5** 新建 [docs/DATASETS.md](file:///d:/workspace/project/find_image_hide/docs/DATASETS.md)：记录所有样本与数据集的来源、license、下载方式、引用要求

### 🎯 P1 — 检测能力补强（按 ROI 排序）

**P1.1** ⭐⭐⭐ ✅ **2026-06-02 完成** — 在 [lsb_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/lsb_analysis.py) 扩展 8 位面 × 3 通道全扫描 + cross-channel diff + plane-progression 单调性检验。新增字段 `lsb_plane_stats / lsb_white_noise_planes / lsb_common_white_noise_planes / lsb_hierarchy_violation_score / lsb_plane0_cross_channel_spread`，向后兼容 legacy plane-0 字段。

**P1.2** 新增 [steganalysis_external.py](file:///d:/workspace/project/find_image_hide/image_forensics/steganalysis_external.py)：subprocess 集成 stegoveritas / binwalk / stegseek，软依赖、有则用、无则跳

**P1.3** ⭐⭐⭐ ✅ **2026-06-02 完成** — 新建 [copy_move_analysis.py](file:///d:/workspace/project/find_image_hide/image_forensics/copy_move_analysis.py)：经典 Fridrich-Goljan-Du 2003（8×8 块 DCT-II + zig-zag 前 16 系数 + lexicographic sort + shift-vector histogram + SNR 评分），纯 NumPy einsum 一次性计算所有块 DCT。analyzer 已串联，scoring 加权 0.06，可直接进入 direct_high。新增**块多样性门控**（diversity<0.30 或 ac_energy<0.5 时跳过），消除合成图 / 平滑梯度上的假阳性。

**P1.4** ⭐⭐ ✅ **2026-06-02 完成** — 新建 [ai_heuristics.py](file:///d:/workspace/project/find_image_hide/image_forensics/ai_heuristics.py)：CVPR'25 *Secret Lies in Color* 启发的三特征加权（通道相关 45% + 高频残差平整度 35% + 36-bin 色相直方图峰值 30%）。**永远只升到 MEDIUM，不进 direct_high**。新增 `downscale_ratio` 信号失效保护：原图被强缩放（>1.5×）时屏蔽 HF 信号、（>2×）时屏蔽色相信号，避免 LANCZOS 摧毁高频后误判。

**P1.5** 新增 [c2pa_check.py](file:///d:/workspace/project/find_image_hide/image_forensics/c2pa_check.py)：用 `c2pa-python` 读 manifest，UI 显示"内容凭证：✓ Adobe Photoshop / ⚠ 未签 / ✗ 失效"

**P1.6** UI 增加反向图像搜索按钮：上传图 → 一键打开 Google Images / TinEye / Yandex / Bing 多 tab

### 🎯 P2 — 长尾 / 加分项

- HEIC / AVIF / WebP / RAW 解码兼容
- Deepfake 人脸检测（DeepFake-O-Meter 风格软依赖）
- PRNU 相机指纹
- 报告导出 PDF / 司法级"可重现报告"

---

## 四、决策记录

### 2026-06-02

- **起步阶段**：先 P0 补样本
- **样本范围**：免费公有领域 + 学术数据集 mini + Laundered/HEIC/AVIF/WebP/RAW，**每类 5-10 张，重在展示不堆量**
- **P1 优先项**：LSB 全位面 + Copy-Move + 颜色/频域 AI 启发式
- **外部工具策略**：软依赖 subprocess + 一键安装（沿用 reverse-SynthID 那套，不污染用户环境）
- **是否落 ROADMAP 文档**：是 → 本文件
- **跨平台要求**：所有 fetcher / 命令 / 路径处理按 `platform.system()` 分支，Win + macOS 通吃

### 2026-06-02（P1 三件套收官）

- **顺序**：按 ROADMAP 顺序 LSB → Copy-Move → AI 启发式（不并行，方便逐项回归）
- **依赖**：纯 NumPy / Pillow，**零新依赖**（不引入 scikit-image / scipy.fft / OpenCV-SIFT，保持安装无依赖冲突）
- **Copy-Move 算法选择**：放弃 SIFT/ORB（OpenCV-contrib 协议复杂、SIFT 专利争议），改用 Fridrich-Goljan-Du 2003 经典块 DCT 自相似 — 数学严谨、纯 NumPy einsum、跑得过 stride=4 密集采样
- **AI 启发式 risk 上限**：永久 MEDIUM，**不允许 direct_high**。理由：颜色 / 高频统计在缩放、JPEG、相机 AI 降噪面前都太脆弱，独签 HIGH 会污染 overall 判定
- **缩放陷阱护栏**：AI 启发式入口 probe 原图尺寸，downscale_ratio>1.5× 屏蔽 HF 信号、>2× 屏蔽色相信号（已修复 phone_raw_5712x4284_q85.jpg 假阳性）
- **Copy-Move 自相似护栏**：块多样性<30% 或 AC 能量<0.5 时整图跳过（已修复 normal_png.png 平滑梯度假阳性）
- **回归覆盖**：[regression_clean_baseline.py](file:///d:/workspace/project/find_image_hide/tools/regression_clean_baseline.py) 4/4 通过；[run_regression.py](file:///d:/workspace/project/find_image_hide/tools/run_regression.py) 14/14 通过；mini AI 数据集 12 张 0 假阳性、1 命中 MEDIUM
- **scoring 权重调整**：extraction 0.28→0.26、steganalysis 0.18→0.16、visible_wm/invisible_wm/phash 0.10→0.08；新增 copy_move=0.06、ai_heuristics=0.04（合计仍 1.0）

---

## 五、推进规则

每个 P 阶段都按以下顺序：

1. 先扩**测试图**（保证有真伪样本能验回归）
2. 再加**检测模块**（新模块上线即跑回归）
3. UI 在 [webapp.py](file:///d:/workspace/project/find_image_hide/webapp.py) / [app.js](file:///d:/workspace/project/find_image_hide/webui/static/app.js) 增量加 tab，不动既有结构
4. 每个 P 阶段独立 commit + push，方便 review

每完成一个 P 任务，回到本文件勾掉相应项，并在 §四 追加新决策。
