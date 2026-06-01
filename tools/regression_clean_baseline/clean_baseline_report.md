# 干净基线回归报告 (clean baseline regression)

- 日期: 2026-06-01
- 工具: `image_forensics.analyzer.analyze_image`
- 用例数: 4
- 整体结果: **PASS ✅**

## 验收清单（每张图均要求 overall ∈ {LOW,UNKNOWN}、extraction=LOW、user_payload_strings=[]、无 magic_in_trailing 高分误报）

| # | 文件 | 描述 | 格式 | 字节 | overall | overall.score | extraction | ext.score | payload | magic_in_trailing | 通过 |
|---|------|------|------|------|---------|---------------|------------|-----------|---------|-------------------|------|
| 1 | `phone_raw_5712x4284_q85.jpg` | 5712x4284 RGB 噪声 JPEG q=85 (phone original) | JPEG | 3262115 | UNKNOWN | None | LOW | 0.000 | 0 | no | ✅ |
| 2 | `foliage_1500x1000_q92.jpg` | 1500x1000 高纹理 JPEG q=92 (dense foliage) | JPEG | 2454165 | LOW | None | LOW | 0.000 | 0 | no | ✅ |
| 3 | `dual_soi_mpo.mpo` | 双 SOI 拼接合成 MPO | JPEG | 1269295 | LOW | None | LOW | 0.000 | 0 | no | ✅ |
| 4 | `clean_1024_no_meta.png` | 1024x1024 干净 PNG 无元数据 | PNG | 1092114 | LOW | None | LOW | 0.000 | 0 | no | ✅ |

## 单项检查矩阵

| 文件 | overall ∈ {LOW,UNKNOWN} | extraction == LOW | user_payload_strings == [] | 无 magic_in_trailing 误报 |
|------|------------------------|-------------------|----------------------------|---------------------------|
| `phone_raw_5712x4284_q85.jpg` | ✅ | ✅ | ✅ | ✅ |
| `foliage_1500x1000_q92.jpg` | ✅ | ✅ | ✅ | ✅ |
| `dual_soi_mpo.mpo` | ✅ | ✅ | ✅ | ✅ |
| `clean_1024_no_meta.png` | ✅ | ✅ | ✅ | ✅ |

## 子模块诊断（chi/SPA/LSB/FFT 风险位）

| 文件 | steg.risk | chi_p_max | chi_prefix_max | spa_max | lsb.risk | lsb.score | fft.risk |
|------|-----------|-----------|----------------|---------|----------|-----------|----------|
| `phone_raw_5712x4284_q85.jpg` | LOW | 0.300 | 0.300 | 0.000 | LOW | 0.180 | MEDIUM |
| `foliage_1500x1000_q92.jpg` | LOW | 0.300 | 0.300 | 0.017 | LOW | 0.105 | LOW |
| `dual_soi_mpo.mpo` | LOW | 0.300 | 0.300 | 0.032 | LOW | 0.105 | LOW |
| `clean_1024_no_meta.png` | LOW | 1.000 | 1.000 | 0.002 | LOW | 0.350 | LOW |
