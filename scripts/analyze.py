#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对标账号拆解分析器
基于"基础对标+综合对标"方法论，自动化拆解抖音博主的起号路径和爆款策略。
"""

import os
import sys
import json
import time
import re
import asyncio
import subprocess
from datetime import datetime
from collections import Counter
from pathlib import Path
from typing import Optional, List, Dict, Any

# ==================== 配置 ====================

BROWSER_CDP = "http://127.0.0.1:18800"
WHISPER_MODEL = "base"

def find_openclaw_root() -> Optional[Path]:
    current = Path(__file__).resolve().parent
    for _ in range(5):
        if (current / 'config.json').exists() and (current / 'skills').is_dir():
            return current
        if current.parent == current:
            break
        current = current.parent
    home = Path.home() / '.openclaw'
    return home if home.exists() else None

OPENCLAW_ROOT = find_openclaw_root() or Path.home() / '.openclaw'
CONFIG_PATH = OPENCLAW_ROOT / 'config.json'
DEFAULT_OUTPUT_DIR = OPENCLAW_ROOT / "workspace" / "data" / "account-analyzer"

# ==================== 浏览器数据抓取 ====================

async def extract_profile_videos(page, profile_url, max_scrolls=30):
    """通过 Playwright 抓取博主主页的所有视频数据"""
    import asyncio
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ 请先安装 Playwright: pip3 install playwright", file=sys.stderr)
        sys.exit(1)
    
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(BROWSER_CDP)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()
        
        print(f"🌐 正在打开博主主页...", file=sys.stderr)
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # 提取博主基本信息
        profile_info = await extract_profile_info(page)
        
        # 滚动加载更多视频
        print(f"📜 正在滚动加载视频列表...", file=sys.stderr)
        all_videos = await scroll_and_collect_videos(page, max_scrolls)
        
        await browser.close()
    
    return profile_info, all_videos


async def extract_profile_info(page):
    """提取博主基本信息"""
    info = {}
    try:
        # 博主名称
        info['name'] = await page.evaluate("""() => {
            const h1 = document.querySelector('h1');
            if (h1) return h1.textContent.trim();
            const heading = document.querySelector('[class*="user-info"] h1, [class*="nickname"]');
            return heading ? heading.textContent.trim() : '';
        }""")
        
        # 粉丝、获赞、关注
        info['stats'] = await page.evaluate("""() => {
            const text = document.body.textContent || '';
            const fansMatch = text.match(/粉丝\s*([\d.]+[万]?)/);
            const likesMatch = text.match(/获赞\s*([\d.]+[万]?)/);
            const followMatch = text.match(/关注\s*([\d.]+[万]?)/);
            const dyidMatch = text.match(/抖音号[：:]?\s*(\S+)/);
            const ipMatch = text.match(/IP属地[：:]?\s*(\S+)/);
            return {
                fans: fansMatch ? fansMatch[1] : '',
                likes: likesMatch ? likesMatch[1] : '',
                follow: followMatch ? followMatch[1] : '',
                dyid: dyidMatch ? dyidMatch[1] : '',
                ip: ipMatch ? ipMatch[1] : ''
            };
        }""")
        
        # 简介
        info['bio'] = await page.evaluate("""() => {
            const bioEl = document.querySelector('[class*="signature"], [class*="desc"]');
            return bioEl ? bioEl.textContent.trim().substring(0, 200) : '';
        }""")
    except Exception as e:
        print(f"  ⚠️ 提取博主信息失败: {e}", file=sys.stderr)
    
    return info


async def scroll_and_collect_videos(page, max_scrolls=30):
    """滚动页面并收集所有视频卡片数据"""
    seen_ids = set()
    videos = []
    last_count = 0
    
    for i in range(max_scrolls):
        # 等待页面加载
        await page.wait_for_timeout(1000)
        
        # 提取当前可见的视频卡片
        new_videos = await page.evaluate("""() => {
            const cards = Array.from(document.querySelectorAll('a[href*="/video/"], a[href*="/note/"]'));
            const videos = [];
            const seen = new Set();
            
            for (const card of cards) {
                const href = card.href || '';
                const match = href.match(/\/(video|note)\/(\d+)/);
                if (!match) continue;
                const id = match[2];
                const type = match[1];
                if (seen.has(id)) continue;
                
                const text = card.textContent || '';
                // 去掉开头的数字（点赞数），提取纯标题
                let cleanText = text.replace(/^\s*\d+\.?\d*[万wW]?\s*/, '').replace(/\s+/g, ' ').trim();
                // 去重（标题重复出现的情况）
                const parts = cleanText.split(/\s{2,}/);
                let title = parts[0] || cleanText;
                // 如果标题超过100字，截取
                if (title.length > 100) title = title.substring(0, 100);
                
                if (seen.has(id)) continue;
                seen.add(id);
                
                // 提取点赞数
                const parent = card.closest('li') || card.parentElement?.parentElement;
                let likes = 0;
                if (parent) {
                    const parentText = parent.textContent || '';
                    // 匹配开头的独立数字（点赞数通常在标题前）
                    const numMatch = parentText.match(/^\s*(\d+\.?\d*[万wW]?)\s/);
                    if (numMatch) {
                        let num = numMatch[1];
                        if (num.includes('万') || num.includes('w') || num.includes('W')) {
                            try { num = parseFloat(num) * 10000; } catch(e) {}
                        } else {
                            try { num = parseInt(num); } catch(e) {}
                        }
                        likes = num;
                    }
                }
                
                if (title && title.length > 3) {
                    videos.push({
                        id,
                        type,
                        title: title,
                        likes: typeof likes === 'number' ? likes : 0,
                        comments: 0,
                    });
                }
            }
            
            return videos;
        }""")
        
        # 去重
        for v in new_videos:
            if v['id'] not in seen_ids and v.get('id'):
                seen_ids.add(v['id'])
                videos.append(v)
        
        # 检查是否有新内容
        if len(seen_ids) <= last_count:
            # 尝试继续滚动
            await page.evaluate("window.scrollBy(0, 800)")
        else:
            last_count = len(seen_ids)
            print(f"  📊 已加载 {last_count} 条视频...", file=sys.stderr)
            await page.evaluate("window.scrollBy(0, 800)")
    
    return videos


async def extract_video_url_from_page(page, video_id):
    """从视频页面提取视频直链"""
    try:
        await page.goto(f"https://www.douyin.com/video/{video_id}", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        
        video_url = await page.evaluate("""() => {
            const v = document.querySelector('video');
            return v ? (v.src || v.currentSrc) : null;
        }""")
        return video_url
    except Exception as e:
        print(f"  ⚠️ 提取视频链接失败: {e}", file=sys.stderr)
        return None


async def get_browser_page():
    """获取 Playwright page 对象"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ 请先安装 Playwright: pip3 install playwright", file=sys.stderr)
        return None, None
    
    p = await async_playwright().start()
    browser = await p.chromium.connect_over_cdp(BROWSER_CDP)
    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = context.pages[0] if context.pages else await context.new_page()
    return p, page


# ==================== 数据分析 ====================

def parse_likes(likes_str):
    """解析点赞数字符串"""
    if not likes_str:
        return 0
    s = str(likes_str).strip()
    if '万' in s or 'w' in s.lower():
        try:
            return int(float(s.replace('万', '').replace('w', '').replace('W', '')) * 10000)
        except:
            return 0
    try:
        return int(float(s))
    except:
        return 0


def analyze_videos(videos: List[Dict], mode: str = 'basic'):
    """分析视频数据，生成拆解报告"""
    
    # 按点赞排序
    videos_by_likes = sorted(videos, key=lambda v: v.get('likes', 0), reverse=True)
    
    report = {
        'total_videos': len(videos),
        'videos': videos_by_likes,
    }
    
    if not videos:
        return report
    
    # 基础统计
    all_likes = [v.get('likes', 0) for v in videos]
    report['total_likes'] = sum(all_likes)
    report['avg_likes'] = int(sum(all_likes) / len(all_likes)) if all_likes else 0
    report['median_likes'] = sorted(all_likes)[len(all_likes) // 2] if all_likes else 0
    report['max_likes'] = max(all_likes) if all_likes else 0
    
    # 数据分布
    report['over_100'] = len([l for l in all_likes if l >= 100])
    report['over_1000'] = len([l for l in all_likes if l >= 1000])
    report['over_10000'] = len([l for l in all_likes if l >= 10000])
    
    # 标题关键词分析
    all_titles = ' '.join([v.get('title', '') for v in videos])
    # 提取话题标签
    hashtags = re.findall(r'#([^#\s]+)', all_titles)
    report['top_hashtags'] = Counter(hashtags).most_common(15)
    
    # 标题长度分析
    title_lengths = [len(v.get('title', '')) for v in videos]
    report['avg_title_length'] = int(sum(title_lengths) / len(title_lengths)) if title_lengths else 0
    
    # 爆款视频分类
    report['top_10'] = videos_by_likes[:10]
    
    # 起号路径分析
    if len(videos_by_likes) > 0:
        # 找到第一个破百赞和破千赞的视频（按数据排名，不是时间）
        first_over_100 = None
        first_over_1000 = None
        for v in videos_by_likes:
            if v.get('likes', 0) >= 100 and not first_over_100:
                first_over_100 = v
            if v.get('likes', 0) >= 1000 and not first_over_1000:
                first_over_1000 = v
        
        report['milestones'] = {
            'top_video': videos_by_likes[0],
            'first_over_100': first_over_100,
            'first_over_1000': first_over_1000,
        }
    
    # 综合对标额外分析
    if mode == 'comprehensive':
        report['content_directions'] = analyze_content_directions(videos)
        report['engagement_ratio'] = analyze_engagement(videos)
    
    return report


def analyze_content_directions(videos):
    """分析内容方向"""
    directions = []
    for v in videos:
        title = v.get('title', '')
        hashtags = re.findall(r'#([^#\s]+)', title)
        if hashtags:
            directions.extend(hashtags)
    return Counter(directions).most_common(10)


def analyze_engagement(videos):
    """分析互动情况"""
    total_likes = sum(v.get('likes', 0) for v in videos)
    total_comments = sum(v.get('comments', 0) for v in videos)
    return {
        'total_likes': total_likes,
        'total_comments': total_comments,
        'avg_likes_per_video': int(total_likes / len(videos)) if videos else 0,
    }


# ==================== 报告生成 ====================

def generate_report(report: Dict, profile_info: Dict, mode: str, output_file: Path):
    """生成 Markdown 格式的分析报告"""
    
    lines = []
    lines.append(f"# 对标账号拆解报告")
    lines.append("")
    lines.append(f"**生成时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**拆解模式:** {'综合对标' if mode == 'comprehensive' else '基础对标'}")
    lines.append("")
    
    # 博主信息
    if profile_info:
        lines.append(f"## 👤 博主信息")
        lines.append("")
        if profile_info.get('name'):
            lines.append(f"**昵称:** {profile_info['name']}")
        if profile_info.get('bio'):
            lines.append(f"**简介:** {profile_info['bio']}")
        stats = profile_info.get('stats', {})
        if stats.get('fans'):
            lines.append(f"**粉丝:** {stats['fans']}")
        if stats.get('likes'):
            lines.append(f"**获赞:** {stats['likes']}")
        if stats.get('follow'):
            lines.append(f"**关注:** {stats['follow']}")
        if stats.get('dyid'):
            lines.append(f"**抖音号:** {stats['dyid']}")
        if stats.get('ip'):
            lines.append(f"**IP属地:** {stats['ip']}")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # 数据概览
    lines.append(f"## 📊 数据概览")
    lines.append("")
    lines.append(f"- **视频总数:** {report.get('total_videos', 0)}")
    lines.append(f"- **总获赞:** {report.get('total_likes', 0):,}")
    lines.append(f"- **平均点赞:** {report.get('avg_likes', 0):,}")
    lines.append(f"- **中位点赞:** {report.get('median_likes', 0):,}")
    lines.append(f"- **最高点赞:** {report.get('max_likes', 0):,}")
    lines.append(f"- **破百赞视频:** {report.get('over_100', 0)} 条")
    lines.append(f"- **破千赞视频:** {report.get('over_1000', 0)} 条")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 起号路径分析
    milestones = report.get('milestones', {})
    if milestones:
        lines.append(f"## 🚀 起号路径分析")
        lines.append("")
        
        if milestones.get('top_video'):
            v = milestones['top_video']
            lines.append(f"### 🏆 最高赞视频")
            lines.append(f"- **标题:** {v.get('title', '')}")
            lines.append(f"- **点赞:** {v.get('likes', 0):,}")
            lines.append(f"- **视频ID:** {v.get('id', '')}")
            lines.append(f"- **链接:** https://www.douyin.com/video/{v.get('id', '')}")
            lines.append("")
        
        if milestones.get('first_over_100'):
            v = milestones['first_over_100']
            lines.append(f"### 💯 破百赞视频")
            lines.append(f"- **标题:** {v.get('title', '')}")
            lines.append(f"- **点赞:** {v.get('likes', 0):,}")
            lines.append(f"- **视频ID:** {v.get('id', '')}")
            lines.append(f"- **链接:** https://www.douyin.com/video/{v.get('id', '')}")
            lines.append("")
        
        if milestones.get('first_over_1000'):
            v = milestones['first_over_1000']
            lines.append(f"### 🔥 破千赞视频")
            lines.append(f"- **标题:** {v.get('title', '')}")
            lines.append(f"- **点赞:** {v.get('likes', 0):,}")
            lines.append(f"- **视频ID:** {v.get('id', '')}")
            lines.append(f"- **链接:** https://www.douyin.com/video/{v.get('id', '')}")
            lines.append("")
        
        lines.append("---")
        lines.append("")
    
    # 爆款视频 TOP 10
    top_10 = report.get('top_10', [])
    if top_10:
        lines.append(f"## 📈 爆款视频 TOP 10")
        lines.append("")
        for i, v in enumerate(top_10, 1):
            lines.append(f"### {i}. {v.get('title', '无标题')}")
            lines.append(f"- 点赞: {v.get('likes', 0):,}")
            lines.append(f"- 视频ID: {v.get('id', '')}")
            lines.append(f"- 链接: https://www.douyin.com/video/{v.get('id', '')}")
            lines.append("")
        lines.append("---")
        lines.append("")
    
    # 热门话题标签
    top_hashtags = report.get('top_hashtags', [])
    if top_hashtags:
        lines.append(f"## 🏷️ 热门话题标签")
        lines.append("")
        for tag, count in top_hashtags:
            lines.append(f"- #{tag} ({count} 次)")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # 综合对标额外内容
    if mode == 'comprehensive':
        lines.append(f"## 💰 变现路径分析")
        lines.append("")
        lines.append("> ⚠️ 需要人工进一步分析以下内容：")
        lines.append("1. 是否接广告/商单？（查看视频描述中的品牌标签）")
        lines.append("2. 是否带货？（查看是否挂载商品链接）")
        lines.append("3. 是否引流私域？（查看主页是否留联系方式）")
        lines.append("4. 是否开店？（查看是否有店铺入口）")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # 爆款因子分析
    lines.append(f"## 🔍 爆款因子分析")
    lines.append("")
    lines.append("> ⚠️ 以下为自动分析，建议结合人工判断：")
    lines.append("")
    
    # 标题模式分析
    if top_10:
        lines.append(f"### 标题特征")
        # 检查是否有问句
        question_count = sum(1 for v in top_10 if '？' in v.get('title', '') or '?' in v.get('title', ''))
        if question_count > len(top_10) * 0.3:
            lines.append(f"- ✅ **疑问式标题**: {question_count}/{len(top_10)} 使用问号，引发好奇心")
        
        # 检查是否有感叹号
        exclaim_count = sum(1 for v in top_10 if '！' in v.get('title', '') or '!' in v.get('title', ''))
        if exclaim_count > len(top_10) * 0.3:
            lines.append(f"- ✅ **感叹式标题**: {exclaim_count}/{len(top_10)} 使用感叹号，增强情绪")
        
        # 检查是否有数字
        num_count = sum(1 for v in top_10 if re.search(r'\d+', v.get('title', '')))
        if num_count > len(top_10) * 0.3:
            lines.append(f"- ✅ **数字型标题**: {num_count}/{len(top_10)} 包含具体数字，增强可信度")
        
        lines.append("")
    
    lines.append(f"### 内容方向")
    if top_hashtags:
        for tag, count in top_hashtags[:5]:
            lines.append(f"- **#{tag}**: 出现 {count} 次")
    lines.append("")
    
    lines.append("---")
    lines.append("")
    lines.append(f"*报告由 Account Analyzer 自动生成*")
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    return output_file


# ==================== 视频转写 ====================

def download_video(url, path):
    import requests
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.douyin.com/"}
    with requests.get(url, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    size = os.path.getsize(path)
    if size < 1000:
        raise ValueError(f"文件太小({size}B)")
    return path


def extract_audio(video_path, audio_path):
    cmd = ['ffmpeg', '-i', str(video_path), '-vn', '-acodec', 'libmp3lame', '-y', str(audio_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return os.path.exists(audio_path) and os.path.getsize(audio_path) > 0, result.stderr[:300] if result.returncode != 0 else ""


def transcribe_audio(audio_path):
    import whisper
    model = whisper.load_model(WHISPER_MODEL)
    result = model.transcribe(audio=str(audio_path), language='zh', initial_prompt="以下是普通话的句子。")
    return result['text'].strip()


async def transcribe_top_videos(page, videos, top_n, report_file):
    """转写点赞最高的前 N 条视频"""
    import tempfile
    
    if top_n <= 0:
        return
    
    print(f"\n🎤 开始转写 Top {top_n} 视频文案...", file=sys.stderr)
    
    # 添加转写内容到报告
    lines = ["\n---\n", "\n## 🎙️ 视频文案转写 (Top {0})\n".format(top_n), ""]
    
    success = 0
    for i, video in enumerate(videos[:top_n]):
        print(f"\n  [{i+1}/{top_n}] 👍{video.get('likes', 0)} {video.get('title', '')[:40]}...", file=sys.stderr)
        
        try:
            # 跳过图文笔记
            if video.get('type') == 'note':
                print(f"  ⏭️  跳过图文笔记", file=sys.stderr)
                continue
            
            # 获取视频直链
            video_url = await extract_video_url_from_page(page, video['id'])
            if not video_url or 'douyinvod.com' not in video_url:
                print(f"  ✗ 无法获取有效视频链接 (可能是图文笔记)", file=sys.stderr)
                continue
            
            # 下载
            import tempfile
            video_path = Path(tempfile.gettempdir()) / f"dy_{video['id']}.mp4"
            audio_path = Path(tempfile.gettempdir()) / f"dy_{video['id']}.mp3"
            
            print(f"  [1/3] 下载视频...", file=sys.stderr)
            download_video(video_url, video_path)
            
            print(f"  [2/3] 提取音频...", file=sys.stderr)
            ok, err = extract_audio(video_path, audio_path)
            if not ok:
                raise Exception(f"音频提取失败: {err}")
            
            print(f"  [3/3] Whisper 转写...", file=sys.stderr)
            transcription = transcribe_audio(audio_path)
            
            # 清理
            for p in [video_path, audio_path]:
                if p.exists():
                    p.unlink()
            
            lines.append(f"### {i+1}. {video.get('title', '')}")
            lines.append(f"- 点赞: {video.get('likes', 0):,}")
            lines.append(f"- 链接: https://www.douyin.com/video/{video['id']}")
            lines.append("")
            lines.append(f"**文案:**")
            lines.append("")
            lines.append(transcription)
            lines.append("")
            lines.append("---")
            lines.append("")
            
            print(f"  ✅ 完成 ({len(transcription)} 字)", file=sys.stderr)
            success += 1
            
        except Exception as e:
            print(f"  ❌ 失败: {e}", file=sys.stderr)
    
    # 追加到报告
    with open(report_file, 'a', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"\n🎉 转写完成: {success}/{top_n}", file=sys.stderr)


# ==================== 主流程 ====================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="对标账号拆解分析器")
    parser.add_argument("--profile-url", required=True, help="博主主页URL")
    parser.add_argument("--mode", choices=['basic', 'comprehensive'], default='basic', help="拆解模式")
    parser.add_argument("--transcribe-top", type=int, default=0, help="转写点赞最高的前N条视频")
    parser.add_argument("--output-file", help="输出报告路径")
    parser.add_argument("--video-ids", help="直接指定视频ID列表（逗号分隔）")
    args = parser.parse_args()
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = Path(args.output_file) if args.output_file else DEFAULT_OUTPUT_DIR / f"{timestamp}_analysis.md"
    
    print(f"🔍 对标账号拆解分析器")
    print(f"📋 模式: {'综合对标' if args.mode == 'comprehensive' else '基础对标'}")
    print(f"🔗 目标: {args.profile_url}")
    print()
    
    # 如果指定了 video-ids，跳过浏览器抓取
    if args.video_ids:
        video_ids = [vid.strip() for vid in args.video_ids.split(',') if vid.strip()]
        print(f"📋 指定视频ID: {len(video_ids)} 条", file=sys.stderr)
        videos = [{"id": vid, "title": f"视频 {vid}", "likes": 0, "type": "video"} for vid in video_ids]
        profile_info = {}
    else:
        # 浏览器抓取
        print("[1/3] 正在抓取博主主页数据...", file=sys.stderr)
        
        async def run_extraction():
            return await extract_profile_videos(None, args.profile_url)
        
        # 使用 asyncio.run
        profile_info, videos = asyncio.run(extract_profile_videos(None, args.profile_url))
    
    if not videos:
        print("❌ 未能抓取到视频数据", file=sys.stderr)
        sys.exit(1)
    
    print(f"  ✅ 抓取到 {len(videos)} 条视频", file=sys.stderr)
    
    # 分析
    print(f"\n[2/3] 正在分析数据...", file=sys.stderr)
    report = analyze_videos(videos, args.mode)
    
    # 生成报告
    print(f"[3/3] 正在生成报告...", file=sys.stderr)
    output_file = generate_report(report, profile_info, args.mode, output_file)
    print(f"  ✅ 报告已保存: {output_file}", file=sys.stderr)
    
    # 如果需要转写
    if args.transcribe_top > 0:
        print(f"\n[4/4] 正在转写 Top {args.transcribe_top} 视频...", file=sys.stderr)
        async def run_transcribe():
            p, page = await get_browser_page()
            await transcribe_top_videos(page, report.get('videos', []), args.transcribe_top, output_file)
            await p.stop()
        
        asyncio.run(run_transcribe())
    
    print(f"\n🎉 分析完成!")
    print(f"📁 报告: {output_file}")
    print(f"ANALYSIS_PATH:{output_file}")


if __name__ == "__main__":
    main()
