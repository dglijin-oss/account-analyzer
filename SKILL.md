# Account Analyzer - 对标账号拆解技能

## 描述

自动化拆解抖音对标账号，提取爆款因子、分析起号路径、识别变现模式。基于"基础对标+综合对标"方法论，帮你快速拆解对标账号的核心策略。

## ⚠️ 前置条件

1. **OpenClaw 浏览器已启动**（用于抓取视频数据）
2. **Playwright** 已安装（`pip3 install playwright`）
3. **Whisper** 已安装（用于视频转写，可选）
4. **ffmpeg** 已安装（用于音频提取）

## 使用方法

### 基础对标拆解（1K-10K 尾部博主）

```bash
python3 skills/account-analyzer/scripts/analyze.py \
  --profile-url "https://www.douyin.com/user/XXXXX" \
  --mode basic
```

### 综合对标拆解（1万粉以上博主）

```bash
python3 skills/account-analyzer/scripts/analyze.py \
  --profile-url "https://www.douyin.com/user/XXXXX" \
  --mode comprehensive
```

### 带视频转写的深度拆解

```bash
python3 skills/account-analyzer/scripts/analyze.py \
  --profile-url "https://www.douyin.com/user/XXXXX" \
  --mode basic \
  --transcribe-top 5
```

### 指定视频ID直接拆解

```bash
python3 skills/account-analyzer/scripts/analyze.py \
  --profile-url "https://www.douyin.com/user/XXXXX" \
  --mode basic \
  --video-ids "7594031728987498459,7594147461460516977,7621859829086493951"
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--profile-url` | 是 | 博主主页链接 |
| `--mode` | 否 | `basic`（基础对标）或 `comprehensive`（综合对标），默认 basic |
| `--transcribe-top` | 否 | 转写点赞最高的前 N 条视频文案（默认不转写） |
| `--output-file` | 否 | 自定义输出报告路径 |
| `--video-ids` | 否 | 直接指定视频 ID 列表（逗号分隔） |

## 输出报告包含

### 基础对标报告
- 博主基本信息（粉丝、获赞、IP属地）
- 视频数据概览（总数、平均点赞、中位数）
- **起号路径分析**（第一篇 → 第一篇破百赞 → 第一篇破千赞）
- 爆款视频 TOP10
- 标题关键词分析
- 发布时间规律
- 爆款因子总结

### 综合对标报告（在基础之上增加）
- 变现路径分析（广告、带货、私域引流等）
- 内容方向分析
- 受众人群分析
- 拍摄剪辑手法分析

## 文件结构

```
skills/account-analyzer/
├── SKILL.md
└── scripts/
    └── analyze.py          # 主脚本
```
