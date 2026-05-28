const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const VIS = (filename) => `/jobs/${JOB_ID}/image/${encodeURIComponent(SLUG)}/vis/${encodeURIComponent(filename)}`;
const PREVIEW = `/jobs/${JOB_ID}/image/${encodeURIComponent(SLUG)}/preview`;

function fmtNum(v, digits=3) {
  if (v == null) return "-";
  if (typeof v !== "number") return v;
  return v.toFixed(digits);
}

function badge(level) {
  const lvl = level || "UNKNOWN";
  const cn = { HIGH: "高风险", MEDIUM: "中风险", LOW: "低风险", UNKNOWN: "未知", ERROR: "出错" }[lvl] || lvl;
  return `<span class="badge ${lvl}">${cn}</span>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function kvBlock(items) {
  return `<div class="kv">` + items.map(([k, v]) => `<div class="k">${k}</div><div class="v">${v == null ? "-" : v}</div>`).join("") + `</div>`;
}

function explain(html) {
  return `<div class="explain">${html}</div>`;
}

function notice(title, html) {
  return `<div class="notice"><div class="title">${title}</div>${html}</div>`;
}

function renderOverview(report) {
  const inp = report.input || {};
  const ov = report.overall || {};
  document.title = inp.file_name || "Image";
  $("#title").textContent = inp.file_name || "Image";
  $("#preview-img").src = PREVIEW;

  $("#overview-list").innerHTML = `
    <h3 style="margin-top:0">${badge(ov.risk_level)} 综合评估</h3>
    <p>${ov.summary || ""}</p>
    ${kvBlock([
      ["路径", inp.file_path],
      ["大小", inp.file_size_bytes ? (inp.file_size_bytes/1024).toFixed(1) + " KB" : "-"],
      ["格式", inp.format],
      ["尺寸", inp.width ? inp.width + " x " + inp.height : "-"],
      ["模式", inp.mode],
      ["通道", inp.channels],
      ["透明通道", inp.has_alpha],
      ["MIME", inp.mime_type],
      ["SHA256", inp.sha256],
      ["pHash 感知哈希", inp.perceptual_hash],
      ["综合置信度", fmtNum(ov.confidence, 3)],
    ])}
    <h4>各模块得分（0~1，越高越可疑）</h4>
    ${kvBlock(Object.entries(ov.module_scores || {}).map(([k, v]) => [k, fmtNum(v, 3)]))}
  `;
}

function renderExtraction(report) {
  const e = report.extraction || {};
  const t = e.trailing_data || {};
  const streams = e.lsb_streams_with_findings || [];
  const fileMagic = e.file_magic_hits || [];

  const trailingHtml = (t.trailing_bytes && t.trailing_bytes > 0) ? `
    <h3>在图像数据末尾发现了 ${t.trailing_bytes} 字节的额外内容 —— 可能是被附加上去的隐藏文件</h3>
    ${kvBlock([
      ["格式", t.format],
      ["图像结尾偏移", t.image_end_offset],
      ["文件总长", t.file_size],
      ["附加字节数", t.trailing_bytes],
      ["前 64 字节 (hex)", `<code>${t.preview_hex || ""}</code>`],
      ["前 120 字节 (文本)", `<pre class="json" style="max-height:120px">${escapeHtml(t.preview_text || "")}</pre>`],
    ])}
    ${(t.magic_in_trailing && t.magic_in_trailing.length) ? `
      <h4>识别到的文件类型</h4>
      <ul>${t.magic_in_trailing.map(m => `<li><strong>${m.format}</strong> @ 偏移 +${m.offset}</li>`).join("")}</ul>
    ` : ""}
    ${(t.strings_in_trailing && t.strings_in_trailing.length) ? `
      <h4>从附加内容里读出来的可读字符串（前 ${Math.min(20, t.strings_in_trailing.length)} 条）</h4>
      <pre class="json" style="max-height:240px">${escapeHtml(t.strings_in_trailing.slice(0,20).join("\n"))}</pre>
    ` : ""}
  ` : `<p class="muted">没有发现图像数据流之后的附加字节。</p>`;

  const streamsHtml = streams.length ? streams.map(s => `
    <div class="evidence-item warning">
      <div class="title">从 LSB 比特流解出可读内容 — 通道顺序 ${s.channel_order}, 第 ${s.bit_index} 位, ${s.bit_order}-端序</div>
      ${(s.magic_hits && s.magic_hits.length) ? `<div><strong>识别到的文件类型：</strong>${s.magic_hits.map(h => `${h.format}@+${h.offset}`).join(", ")}</div>` : ""}
      ${(s.strings_sample && s.strings_sample.length) ? `<div><strong>可读字符串样本：</strong><pre class="json" style="max-height:160px">${escapeHtml(s.strings_sample.join("\n"))}</pre></div>` : ""}
      <div class="meta">总共提取了 ${s.extracted_bytes} 字节</div>
    </div>
  `).join("") : `<p class="muted">在常见 LSB 比特流组合中没发现可读字符串或文件签名。</p>`;

  const fileMagicHtml = fileMagic.length > 1 ? `
    <h3>整文件中检测到的多个文件签名</h3>
    <ul>${fileMagic.map(m => `<li>${m.format} @ 偏移 ${m.offset}</li>`).join("")}</ul>
  ` : "";

  $("#tab-extraction").innerHTML = `
    <h2>隐藏内容提取 ${badge(e.risk_level)}</h2>
    ${explain(`
      <strong>这一步在做什么：</strong>把"可能藏在图片里的东西"提出来直接显示。<br>
      包括两种常见隐藏手法：<br>
      &nbsp;&nbsp;① <strong>文件尾部附加</strong>：把 ZIP / 文本拼在 PNG/JPEG 末尾（很多 CTF 题、binwalk 检测的对象）；<br>
      &nbsp;&nbsp;② <strong>LSB 隐写</strong>：把信息塞进每个像素的最低位（zsteg / steghide 风格）。本工具尝试 R/G/B/RGB/BGR 多种顺序、bit 0/1/2、大小端，逐一解码看能不能拼出可读字符串或文件头。
    `)}

    <h3>① 文件尾部附加数据</h3>
    ${trailingHtml}

    <h3>② LSB 比特流提取</h3>
    ${streamsHtml}

    ${fileMagicHtml}

    <h3>这一步的局限</h3>
    <ul class="muted small">${(e.limitations || []).map(l => `<li>${l}</li>`).join("")}</ul>
  `;
}

function renderSteg(report) {
  const s = report.steganalysis || {};
  const per = s.per_channel || {};
  const channelRows = ["r","g","b"].map(ch => {
    const c = per[ch] || {};
    const chi = c.chi_square || {};
    const slide = c.chi_square_sliding || {};
    const spa = c.sample_pair_analysis || {};
    return `<tr>
      <td>${ch.toUpperCase()}</td>
      <td>${fmtNum(chi.chi2, 1)}</td>
      <td>${chi.dof}</td>
      <td>${fmtNum(chi.p_embed, 3)}</td>
      <td>${fmtNum(slide.prefix_embed_ratio, 3)}</td>
      <td>${fmtNum(spa.embedding_rate, 3)}</td>
    </tr>`;
  }).join("");

  $("#tab-steg").innerHTML = `
    <h2>隐写检测（卡方 + SPA） ${badge(s.risk_level)}</h2>
    ${explain(`
      <strong>这一步在做什么：</strong>用统计方法判断"图片是否被改过最低位（LSB）来藏信息"。<br>
      &nbsp;&nbsp;• <strong>卡方检测</strong>（Westfeld &amp; Pfitzmann 1999）：正常照片的相邻颜色值出现频率不一样，被 LSB 嵌入后会变得几乎相等；P 值越接近 1 = 越可能藏了东西。<br>
      &nbsp;&nbsp;• <strong>SPA 嵌入率估计</strong>（Dumitrescu/Wu/Wang 2003）：直接给出"大约多少比例的像素被改过 LSB"，比如 0.50 表示约一半像素被替换。<br>
      ${ s.spa_max_embedding_rate > 0.4 || s.chi_square_max_p_embed > 0.9
        ? '<strong>本图结论：</strong>统计特征强烈指向 LSB 隐写。'
        : '<strong>本图结论：</strong>统计特征接近正常照片。' }
    `)}
    ${kvBlock([
      ["卡方 P(嵌入) 最大值", fmtNum(s.chi_square_max_p_embed, 3) + "（越接近 1 越可疑）"],
      ["卡方滑窗最大前缀比", fmtNum(s.chi_square_prefix_max, 3)],
      ["SPA 估计的最大嵌入率", fmtNum(s.spa_max_embedding_rate, 3) + "（≥0.1 已经可疑）"],
      ["综合分", fmtNum(s.steganalysis_score, 3)],
    ])}
    <h3>每通道详情</h3>
    <table class="results">
      <thead><tr><th>通道</th><th>χ²</th><th>自由度</th><th>P(嵌入)</th><th>顺序前缀比</th><th>SPA 嵌入率</th></tr></thead>
      <tbody>${channelRows}</tbody>
    </table>
    <h3>这一步的局限</h3>
    <ul class="muted small">${(s.limitations || []).map(l => `<li>${l}</li>`).join("")}</ul>
  `;
}

function renderMetadata(report) {
  const m = report.metadata || {};
  const flags = kvBlock([
    ["EXIF（拍摄信息）", m.has_exif],
    ["XMP（Adobe 扩展元数据）", m.has_xmp],
    ["IPTC（新闻图通用元数据）", m.has_iptc],
    ["PNG 文本块", m.has_png_text],
    ["JPEG 注释段", m.has_jpeg_comment],
    ["命中的 AI 关键词", (m.metadata_ai_keywords || []).join(", ") || "-"],
    ["可疑字段", (m.suspicious_fields || []).join(", ") || "-"],
  ]);
  const raw = m.raw || {};
  $("#tab-metadata").innerHTML = `
    <h2>元数据 ${badge(m.has_exif || m.has_xmp || m.has_iptc ? "LOW" : "UNKNOWN")}</h2>
    ${explain(`
      <strong>这一步在做什么：</strong>把图片里"附带的描述信息"全部读出来。这些字段通常存放：相机型号、拍摄时间、地理坐标、版权声明、修图软件、AI 生成参数（Stable Diffusion / ComfyUI 的 prompt 等）。<br>
      下面同时高亮了"AI 生成器关键词"和"图库版权关键词"。
    `)}
    ${flags}
    <h3>原始字段</h3>
    <pre class="json">${escapeHtml(JSON.stringify(raw, null, 2))}</pre>
  `;
}

function renderAi(report) {
  const a = report.ai_provenance || {};
  $("#tab-ai").innerHTML = `
    <h2>AI 来源凭证 ${badge(a.risk_level)}</h2>
    ${explain(`
      <strong>这一步在做什么：</strong>查这张图是不是 AI 生成的，依据是两类信号：<br>
      &nbsp;&nbsp;① <strong>C2PA 来源凭证</strong>（OpenAI / Adobe / 索尼相机用的官方"图片身份证"标准）；<br>
      &nbsp;&nbsp;② <strong>元数据关键词</strong>（如 Stable Diffusion / DALL-E / Midjourney / Firefly 等）。<br>
      <strong>注意：</strong>SynthID（Google 的隐式水印）无法在本地可靠检测，需要官方接口。
    `)}
    ${kvBlock([
      ["状态", `<strong>${a.status || "-"}</strong>`],
      ["风险等级", badge(a.risk_level)],
      ["有 C2PA", a.c2pa_present],
      ["C2PA 已验证", a.c2pa_verified],
      ["c2patool 是否可用", a.c2pa_tool_available],
      ["识别到的厂商 / 提供方", (a.detected_providers || []).join(", ") || "-"],
      ["识别到的工具 / 模型", (a.detected_models_or_tools || []).join(", ") || "-"],
      ["claim_generator", a.claim_generator],
      ["生产方 (producer)", a.producer],
      ["签发方 (issuer)", a.issuer],
      ["动作 (actions)", (a.actions || []).join(", ") || "-"],
    ])}
    <h3>SynthID</h3>
    ${kvBlock([
      ["是否支持本地检测", a.synthid?.local_detection_supported],
      ["是否需要外部验证", a.synthid?.external_verification_required],
      ["说明", a.synthid?.note],
    ])}
    <h3>这一步的局限</h3>
    <ul class="muted small">${(a.limitations || []).map(l => `<li>${l}</li>`).join("")}</ul>
    <h3>建议跑的外部验证渠道</h3>
    <ul>
      <li><a href="https://contentcredentials.org/verify" target="_blank">Content Credentials Verify（C2PA 官方）</a></li>
      <li><a href="https://help.openai.com/en/articles/8912793" target="_blank">OpenAI 来源验证说明</a></li>
      <li><a href="https://deepmind.google/technologies/synthid/" target="_blank">Google Gemini / SynthID 介绍</a></li>
    </ul>
  `;
}

function renderFft(report) {
  const f = report.frequency_analysis || {};
  $("#tab-fft").innerHTML = `
    <h2>频域 (FFT) 分析 ${badge(f.risk_level)}</h2>
    ${explain(`
      <strong>这一步在做什么：</strong>把图片做傅里叶变换变成频谱图。"周期性的水印 / GAN 生成图 / 扫描重采样痕迹"在频谱里常常表现为<strong>对称的亮点</strong>或<strong>规则网格</strong>。普通照片的频谱更像中心明亮、周围弥散的噪声团。
    `)}
    ${kvBlock([
      ["频谱异常分", fmtNum(f.spectrum_anomaly_score)],
      ["通道频率异常分", fmtNum(f.channel_frequency_anomaly_score)],
      ["峰值数量", f.peak_count],
      ["对称峰对数量", (f.symmetric_peak_pairs || []).length],
      ["峰强度均值", fmtNum(f.peak_strength_mean)],
    ])}
    <div class="vis-grid">
      <figure><img src="${VIS('spectrum.png')}" /><figcaption>灰度频谱</figcaption></figure>
      <figure><img src="${VIS('r_spectrum.png')}" /><figcaption>红通道</figcaption></figure>
      <figure><img src="${VIS('g_spectrum.png')}" /><figcaption>绿通道</figcaption></figure>
      <figure><img src="${VIS('b_spectrum.png')}" /><figcaption>蓝通道</figcaption></figure>
    </div>
    <h3>这一步的局限</h3>
    <ul class="muted small">${(f.limitations || []).map(l => `<li>${l}</li>`).join("")}</ul>
  `;
}

function renderDct(report) {
  const d = report.dct_analysis || {};
  const ks = d.dct_ks_statistic;
  $("#tab-dct").innerHTML = `
    <h2>DCT 频域分析 ${badge(d.risk_level)}</h2>
    ${explain(`
      <strong>这一步在做什么：</strong>JPEG 是把图像切成 8×8 块再做 DCT（离散余弦变换）压缩的。本工具看每个 8×8 块的中频系数：<br>
      &nbsp;&nbsp;• 中频"几乎全 0" → 可能是被强压缩或合成图；<br>
      &nbsp;&nbsp;• 中频系数偏离自然图典型的拉普拉斯分布（K-S 检验 D 值偏大）→ 可能存在 <strong>spread-spectrum / DCT 域水印</strong>（如 Imatag / 部分 Digimarc 实现）。
    `)}
    ${kvBlock([
      ["DCT 异常分", fmtNum(d.dct_anomaly_score)],
      ["低频 |系数| 均值", fmtNum(d.low_frequency_stats?.abs_mean)],
      ["中频 |系数| 均值", fmtNum(d.mid_frequency_stats?.abs_mean)],
      ["高频 |系数| 均值", fmtNum(d.high_frequency_stats?.abs_mean)],
      ["中频零比例", fmtNum(d.mid_frequency_stats?.zero_ratio)],
      ["K-S 统计量 D", fmtNum(ks)],
      ["K-S p 值", fmtNum(d.dct_ks_p_value)],
    ])}
    <div class="vis-grid">
      <figure><img src="${VIS('dct_mean_heatmap.png')}" /><figcaption>8×8 DCT 系数 |均值| 热力图</figcaption></figure>
      <figure><img src="${VIS('dct_histogram.png')}" /><figcaption>中频 DCT 系数直方图</figcaption></figure>
    </div>
    <h3>这一步的局限</h3>
    <ul class="muted small">${(d.limitations || []).map(l => `<li>${l}</li>`).join("")}</ul>
  `;
}

function renderLsb(report) {
  const l = report.lsb_analysis || {};
  $("#tab-lsb").innerHTML = `
    <h2>LSB 位平面分析 ${badge(l.risk_level)}</h2>
    ${explain(`
      <strong>这一步在做什么：</strong>把每个像素的最低位单独抽出来作为一张黑白图。<br>
      &nbsp;&nbsp;• 正常照片的位平面会有明显结构（边缘、纹理）；<br>
      &nbsp;&nbsp;• 如果整张位平面看起来像"白噪声雪花" → 强烈提示 LSB 已被随机数据替换（LSB 隐写或最大化嵌入）。
    `)}
    ${kvBlock([
      ["LSB 异常分", fmtNum(l.lsb_anomaly_score)],
      ["随机度评分", fmtNum(l.lsb_randomness_score) + "（越接近 1 越像噪声）"],
      ["位平面熵 R/G/B", `${fmtNum(l.lsb_entropy?.r)} / ${fmtNum(l.lsb_entropy?.g)} / ${fmtNum(l.lsb_entropy?.b)}`],
      ["0/1 平衡度 R/G/B", `${fmtNum(l.lsb_balance?.r)} / ${fmtNum(l.lsb_balance?.g)} / ${fmtNum(l.lsb_balance?.b)}`],
      ["邻域相关 R/G/B", `${fmtNum(l.lsb_neighborhood_correlation?.r)} / ${fmtNum(l.lsb_neighborhood_correlation?.g)} / ${fmtNum(l.lsb_neighborhood_correlation?.b)}`],
    ])}
    <div class="vis-grid">
      <figure><img src="${VIS('lsb_r.png')}" /><figcaption>红通道 LSB</figcaption></figure>
      <figure><img src="${VIS('lsb_g.png')}" /><figcaption>绿通道 LSB</figcaption></figure>
      <figure><img src="${VIS('lsb_b.png')}" /><figcaption>蓝通道 LSB</figcaption></figure>
    </div>
    <h3>这一步的局限</h3>
    <ul class="muted small">${(l.limitations || []).map(x => `<li>${x}</li>`).join("")}</ul>
  `;
}

function renderNoise(report) {
  const n = report.noise_analysis || {};
  $("#tab-noise").innerHTML = `
    <h2>噪声残差分析 ${badge(n.risk_level)}</h2>
    ${explain(`
      <strong>这一步在做什么：</strong>把图像与"被高斯模糊后的图像"相减，得到噪声残差。<br>
      &nbsp;&nbsp;• 正常照片各区域的噪声是均匀分布的；<br>
      &nbsp;&nbsp;• 如果某块区域的局部噪声明显更高/更低 → 可能是<strong>拼接 / 局部修图 / 复制粘贴篡改</strong>。
    `)}
    ${kvBlock([
      ["噪声不一致分", fmtNum(n.noise_inconsistency_score)],
      ["残差标准差", fmtNum(n.residual_stats?.std)],
      ["残差 |均值|", fmtNum(n.residual_stats?.abs_mean)],
      ["局部 std 均值", fmtNum(n.residual_stats?.local_std_mean)],
      ["局部 std 标准差", fmtNum(n.residual_stats?.local_std_std)],
    ])}
    <div class="vis-grid">
      <figure><img src="${VIS('residual.png')}" /><figcaption>噪声残差（灰度 - 模糊版）</figcaption></figure>
      <figure><img src="${VIS('laplacian.png')}" /><figcaption>|拉普拉斯| 边缘强度</figcaption></figure>
    </div>
    <h3>这一步的局限</h3>
    <ul class="muted small">${(n.limitations || []).map(l => `<li>${l}</li>`).join("")}</ul>
  `;
}

function renderEla(report) {
  const e = report.ela || {};
  $("#tab-ela").innerHTML = `
    <h2>误差等级分析 (ELA) ${badge(e.risk_level)}</h2>
    ${explain(`
      <strong>这一步在做什么：</strong>把图像以 quality=${e.ela_quality} 重新 JPEG 压缩，跟原图相减得到 "ELA 图"（FotoForensics 经典手法）。<br>
      &nbsp;&nbsp;• 没改过的区域：所有像素的误差水平接近；<br>
      &nbsp;&nbsp;• 被剪贴 / 局部 P 过的区域：经常出现明显更亮的"高误差色块"（因为来源压缩历史不同）。
    `)}
    ${kvBlock([
      ["ELA 不一致分", fmtNum(e.ela_inconsistency_score)],
      ["分块均值的平均", fmtNum(e.block_mean_mean)],
      ["分块均值的标准差", fmtNum(e.block_mean_std)],
    ])}
    <div class="vis-grid">
      <figure><img src="${VIS('ela.png')}" /><figcaption>ELA 图（已放大 ${e.ela_scale}×）</figcaption></figure>
    </div>
    <h3>这一步的局限</h3>
    <ul class="muted small">${(e.limitations || []).map(l => `<li>${l}</li>`).join("")}</ul>
  `;
}

function renderCopyright(report) {
  const m = report.metadata || {};
  const ocr = report.visible_watermark || {};
  const ph = report.phash_match || {};

  // ---- 1. 元数据图库黑名单 ----
  const stockHits = m.metadata_stock_hits || [];
  const metaRisk = (m.stock_image_match === "HIGH") ? "HIGH" : (stockHits.length ? "MEDIUM" : "LOW");
  const metaHtml = stockHits.length ? `
    <p>命中了 <strong>${stockHits.length}</strong> 条图库 / 版权关键词，强烈提示这张图来自 <strong>${[...new Set(stockHits.map(h => h.keyword))].join(", ")}</strong> 等付费图库。</p>
    <table class="results">
      <thead><tr><th>命中关键词</th><th>所在字段</th><th>原值预览</th></tr></thead>
      <tbody>${stockHits.map(h => `
        <tr><td><strong>${escapeHtml(h.keyword)}</strong></td>
            <td><code>${escapeHtml(h.field)}</code></td>
            <td>${escapeHtml(h.value_preview || "")}</td></tr>`).join("")}</tbody>
    </table>
  ` : `<p class="muted">元数据中没有匹配到任何已知图库 / 水印厂商关键词（如 Getty / Shutterstock / Adobe Stock 等）。</p>`;

  // ---- 2. 可见水印 OCR ----
  let ocrBlock;
  if (ocr.status === "OCR_UNAVAILABLE") {
    ocrBlock = notice("OCR 引擎尚未启用 — 这一项暂时跳过，<strong>不代表图里没有水印</strong>",
      `<p>这项检测需要本地装一个开源 OCR 引擎（<code>tesseract</code>），用来识别图片像素里"烧"上去的水印文字（如 "Getty Images"、"© 2024 Shutterstock"）。</p>
       <p><strong>怎么开启：</strong></p>
       <ol>
         <li>装 tesseract 二进制：
           <ul>
             <li>Windows：下载 <a href="https://github.com/UB-Mannheim/tesseract/wiki" target="_blank">UB-Mannheim 安装包</a>，安装时勾选"加入 PATH"</li>
             <li>macOS：终端执行 <code>brew install tesseract</code></li>
             <li>Linux：<code>sudo apt install tesseract-ocr</code></li>
           </ul>
         </li>
         <li>装 Python 包（如果还没装）：<code>pip install pytesseract</code></li>
         <li>重启本工具，再次运行扫描即可。</li>
       </ol>
       <p>装好之后，本模块会把图片切成 8 个区域（四角 / 上下条 / 中心 / 整图）逐个 OCR 扫描，并匹配 Getty / Shutterstock / iStock / Alamy 等 30+ 图库品牌关键词与 ©®™ 符号。</p>`);
  } else {
    const ocrSummary = kvBlock([
      ["状态", ocr.status || "-"],
      ["OCR 后端", ocr.backend || "-"],
      ["扫描的区域数", ocr.regions_scanned || "-"],
      ["OCR 可疑分", fmtNum(ocr.ocr_score)],
    ]);
    const ocrHits = (ocr.hits || []).length ? `
      <h4>命中的水印关键词</h4>
      <table class="results">
        <thead><tr><th>关键词</th><th>类型</th><th>区域</th><th>上下文</th></tr></thead>
        <tbody>${ocr.hits.map(h => `
          <tr><td><strong>${escapeHtml(h.keyword)}</strong></td>
              <td>${escapeHtml(h.match_type)}</td>
              <td>${escapeHtml(h.region)}</td>
              <td><code>${escapeHtml(h.context || "")}</code></td></tr>`).join("")}</tbody>
      </table>
      ${ocr.raw_text_excerpt ? `<details><summary>查看 OCR 原始文本（前 4KB）</summary><pre class="json" style="max-height:240px">${escapeHtml(ocr.raw_text_excerpt)}</pre></details>` : ""}
    ` : `<p class="muted">没有在图像四角 / 中心区域识别到版权图水印关键词。</p>`;
    ocrBlock = ocrSummary + ocrHits;
  }

  // ---- 3. pHash 反查 ----
  let phBlock;
  if (ph.status === "DISABLED" || !ph.status) {
    phBlock = notice("pHash 反查未启用 — 没设置参考图库",
      `<p>这项检测需要你提供"已知的版权原图目录"，工具会用感知哈希（pHash）和它一一比对，识别"被洗过的同源图"——它对 JPEG 重压缩、缩放、轻度调色都很鲁棒。</p>
       <p><strong>怎么开启：</strong></p>
       <ol>
         <li>把你已有的版权原图放进一个目录（举例：<code>D:\\copyright_refs\\</code>）。</li>
         <li>设置环境变量 <code>FORENSICS_PHASH_REFERENCE_DIR</code>：
           <ul>
             <li>Windows PowerShell：<code>$env:FORENSICS_PHASH_REFERENCE_DIR='D:\\copyright_refs'</code></li>
             <li>macOS / Linux：<code>export FORENSICS_PHASH_REFERENCE_DIR=/path/to/refs</code></li>
           </ul>
         </li>
         <li>重新启动本工具，扫描时即可在这里看到反查命中详情。</li>
       </ol>
       <p>本工具自带的 demo 默认指向 <code>tools/phash_reference/</code>，里面已经放了 4 张演示图。</p>`);
  } else if (ph.status === "PHASH_UNAVAILABLE") {
    phBlock = notice("imagehash 库未安装 — pHash 反查无法运行",
      `<p>请安装：<code>pip install imagehash</code>，然后重新启动本工具。</p>`);
  } else if (ph.status === "EMPTY_REFERENCE") {
    phBlock = notice("参考图库目录是空的",
      `<p>当前指向 <code>${escapeHtml(ph.reference_dir || "")}</code>，但里面没有可用图片。请放入至少 1 张你自己的版权原图。</p>`);
  } else {
    const phMatches = ph.matches || [];
    const phSummary = kvBlock([
      ["状态", ph.status],
      ["参考库", `<code>${escapeHtml(ph.reference_dir || "-")}</code>`],
      ["库内图片数", ph.reference_count],
      ["候选图 pHash", `<code>${ph.candidate_phash || "-"}</code>`],
      ["最近邻 Hamming 距离", `${ph.best_distance} （≤ ${ph.default_threshold ?? 8} 视为同源）`],
      ["pHash 可疑分", fmtNum(ph.phash_score)],
    ]);
    const phTable = phMatches.length ? `
      <h4>命中的相似图</h4>
      <table class="results">
        <thead><tr><th>参考路径</th><th>距离</th><th>pHash</th></tr></thead>
        <tbody>${phMatches.map(mm => `
          <tr><td><code>${escapeHtml(mm.reference)}</code></td>
              <td>${mm.distance}</td>
              <td><code>${escapeHtml(mm.phash)}</code></td></tr>`).join("")}</tbody>
      </table>
    ` : `<p class="muted">候选图与参考库内任何图都距离 &gt; ${ph.default_threshold || 8}，视为不同源（即：不是这批已知版权图洗出来的）。</p>`;
    phBlock = phSummary + phTable;
  }

  $("#tab-copyright").innerHTML = `
    <h2>版权 / 图库检测</h2>
    ${explain(`
      <strong>这一步在做什么：</strong>专门针对"被人拿付费图库的图洗一下当原创"的场景，从三个角度判定：<br>
      &nbsp;&nbsp;① <strong>元数据黑名单</strong>：图片 EXIF / XMP 里有没有残留 Getty / Shutterstock / Adobe Stock 等关键词；<br>
      &nbsp;&nbsp;② <strong>可见水印 OCR</strong>：识别像素里"烧"进去的水印文字（如 "Getty Images"、©）；<br>
      &nbsp;&nbsp;③ <strong>pHash 反查</strong>：把图与你本地的版权图库做感知哈希比对 —— <em>对重压缩 / 缩放 / 轻度调色鲁棒，是抓"洗图"最有效的一招</em>。
    `)}

    <h3>① 元数据图库黑名单 ${badge(metaRisk)}</h3>
    ${metaHtml}

    <h3>② 可见水印 OCR ${badge(ocr.risk_level)}</h3>
    ${ocrBlock}

    <h3>③ 感知哈希 (pHash) 反查 ${badge(ph.risk_level)}</h3>
    ${phBlock}
  `;
}

function renderEvidence(report) {
  const items = report.evidence_items || [];
  if (!items.length) {
    $("#tab-evidence").innerHTML = `<h2>证据汇总</h2><p class="muted">没有触发任何证据条目。</p>`;
    return;
  }
  $("#tab-evidence").innerHTML = `<h2>证据汇总（共 ${items.length} 条）</h2>` + items.map(it => `
    <div class="evidence-item ${it.severity || ''}">
      <div class="title">[${it.module || '-'}] ${it.title || ''}</div>
      <div>${it.description || ''}</div>
      <div class="meta">严重度=${it.severity} 置信度=${fmtNum(it.confidence, 2)}</div>
    </div>
  `).join("");
}

function renderRaw(report) {
  $("#tab-raw").innerHTML = `<h2>原始 report.json</h2><pre class="json">${escapeHtml(JSON.stringify(report, null, 2))}</pre>`;
}

/**
 * 根据 report 给每个 tab 按钮加上风险颜色。
 * 哪个模块有问题（HIGH/MEDIUM），对应 tab 就染色 + 加小圆点。
 */
function colorizeTabs(report) {
  const tabRisk = {
    extraction: report.extraction?.risk_level,
    copyright: (() => {
      const stock = report.metadata?.stock_image_match === "HIGH" ? "HIGH" : null;
      const ocrR = report.visible_watermark?.risk_level;
      const phR  = report.phash_match?.risk_level;
      const arr = [stock, ocrR, phR].filter(Boolean);
      if (arr.includes("HIGH")) return "HIGH";
      if (arr.includes("MEDIUM")) return "MEDIUM";
      if (arr.length) return "LOW";
      return null;
    })(),
    steg: report.steganalysis?.risk_level,
    metadata: (report.metadata?.metadata_ai_keywords || []).length ? "MEDIUM"
              : (report.metadata?.has_exif || report.metadata?.has_xmp ? "LOW" : null),
    ai: report.ai_provenance?.risk_level,
    fft: report.frequency_analysis?.risk_level,
    dct: report.dct_analysis?.risk_level,
    lsb: report.lsb_analysis?.risk_level,
    noise: report.noise_analysis?.risk_level,
    ela: report.ela?.risk_level,
    evidence: (() => {
      const ev = report.evidence_items || [];
      if (ev.some(x => x.severity === "error" || x.severity === "high")) return "HIGH";
      if (ev.some(x => x.severity === "warning" || x.severity === "medium")) return "MEDIUM";
      return ev.length ? "LOW" : null;
    })(),
  };
  $$(".tabs button").forEach(btn => {
    const key = btn.dataset.tab;
    const risk = tabRisk[key];
    btn.classList.remove("risk-HIGH", "risk-MEDIUM", "risk-LOW", "risk-UNKNOWN");
    if (risk) btn.classList.add("risk-" + risk);
    if (risk) btn.title = `本模块风险等级：${ {HIGH:"高风险",MEDIUM:"中风险",LOW:"低风险",UNKNOWN:"未知"}[risk] || risk }`;
  });
}

$$(".tabs button").forEach(btn => {
  btn.addEventListener("click", () => {
    $$(".tabs button").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    $$(".tab-pane").forEach(p => p.classList.add("hidden"));
    $("#tab-" + btn.dataset.tab).classList.remove("hidden");
  });
});

(async function main() {
  const resp = await fetch(`/api/jobs/${JOB_ID}/image/${encodeURIComponent(SLUG)}/report`);
  if (!resp.ok) {
    document.body.innerHTML = `<div style="padding:24px">无法加载 report.json</div>`;
    return;
  }
  const report = await resp.json();
  renderOverview(report);
  renderExtraction(report);
  renderCopyright(report);
  renderSteg(report);
  renderMetadata(report);
  renderAi(report);
  renderFft(report);
  renderDct(report);
  renderLsb(report);
  renderNoise(report);
  renderEla(report);
  renderEvidence(report);
  renderRaw(report);
  colorizeTabs(report);
})();
