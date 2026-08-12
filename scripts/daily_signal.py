#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""
盘前交易信号灯 - 每天早上跑一次，告诉你今天能不能交易

用法：
    python scripts/daily_signal.py
    python scripts/daily_signal.py --html            # 同时生成手机网页
    python scripts/daily_signal.py --date 20260804   # 指定T日

依赖：
    - 需要T-1日的涨停/跌停/指数数据（CSV或在线API）
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta
import pandas as pd

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data import DataFetcher
from src.strategy import DragonTracker, DragonState
from src.broker import Broker


# 状态文件路径
STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'dragon_state.json'
)

# 网页输出目录
PUBLIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'public'
)


def load_tracker() -> DragonTracker:
    """从JSON文件恢复DragonTracker状态"""
    tracker = DragonTracker()
    if not os.path.exists(STATE_FILE):
        print("[INFO] 首次运行，无历史状态，初始化为默认状态")
        return tracker

    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)

        ds = state.get('dragon', {})
        tracker.dragon = DragonState(
            stock=ds.get('stock'),
            streak=ds.get('streak', 0),
            sector=ds.get('sector'),
            broken=ds.get('broken', False),
            break_days=ds.get('break_days', 0),
            peak_price=ds.get('peak_price', 0.0)
        )
        tracker.current_phase = state.get('current_phase', '低位试错期')
        tracker.dragon_candidates = state.get('dragon_candidates', [])
        print(f"[OK] 恢复历史状态：阶段={tracker.current_phase}  龙头={tracker.dragon.stock or '无'}")
    except Exception as e:
        print(f"[WARN] 读取状态文件失败 ({e})，使用默认状态")

    return tracker


def save_tracker(tracker: DragonTracker):
    """保存DragonTracker状态到JSON"""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        state = {
            'dragon': {
                'stock': tracker.dragon.stock,
                'streak': tracker.dragon.streak,
                'sector': tracker.dragon.sector,
                'broken': tracker.dragon.broken,
                'break_days': tracker.dragon.break_days,
                'peak_price': tracker.dragon.peak_price,
            },
            'current_phase': tracker.current_phase,
            'dragon_candidates': tracker.dragon_candidates,
            'last_update': datetime.now().strftime('%Y%m%d')
        }
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"[OK] 状态已保存")
    except Exception as e:
        print(f"[WARN] 保存状态失败: {e}")


def get_prev_trading_day(fetcher: DataFetcher, target_date: str, max_try: int = 5) -> str:
    """获取target_date前最近一个有数据的交易日"""
    dt = datetime.strptime(target_date, '%Y%m%d')
    for _ in range(max_try):
        dt -= timedelta(days=1)
        if dt.weekday() >= 5:
            continue
        date_str = dt.strftime('%Y%m%d')
        stats = fetcher.get_market_stats(date_str)
        if stats and stats.get('total_limit_up', 0) > 0:
            return date_str
    return ''


def print_signal(tracker: DragonTracker, market_stats: dict, today: str, prev_date: str, fetcher: DataFetcher = None):
    """打印交易信号"""
    phase = tracker.current_phase
    dragon = tracker.dragon
    limit_down = market_stats.get('limit_down_count', 0)
    total_limit_up = market_stats.get('total_limit_up', 0)
    max_streak = market_stats.get('max_streak', 0)
    market_stable = market_stats.get('market_stable', True)
    first_board = market_stats.get('first_board_count', 0)
    second_board = market_stats.get('second_board_count', 0)
    third_board = market_stats.get('third_board_count', 0)
    sector = market_stats.get('sector_analysis', {})

    print("\n" + "=" * 60)
    print("  龙抬头 - 每日交易信号灯")
    print("=" * 60)
    print(f"  T日：{today}")
    print(f"  数据基准：{prev_date}（T-1）")
    print()

    # ── 市场概况 ──
    print("  📊 昨日市场概况")
    print(f"    涨停：{total_limit_up}只  跌停：{limit_down}只"
          f"  首板：{first_board}  二板：{second_board}  三板+：{third_board}")
    print(f"    最高连板：{max_streak}板  "
          f"大盘：{'稳定' if market_stable else '⚠️不稳'}")
    if sector and 'top_sector' in sector:
        print(f"    最强板块：{sector['top_sector']}（{sector.get('top_sector_count', 0)}只涨停）")
    print()

    # ── 龙头追踪 ──
    print("  🐉 龙头追踪")
    if dragon.stock:
        name = ''
        zt_df = market_stats.get('zt_df', None)
        if zt_df is not None and not zt_df.empty and 'code' in zt_df.columns:
            match = zt_df[zt_df['code'] == dragon.stock]
            if not match.empty and 'name' in match.columns:
                name = match.iloc[0]['name']
        print(f"    龙头：{dragon.stock}  {name}  {'（已断板）' if dragon.broken else ''}")
        print(f"    连板：{dragon.streak}板  板块：{dragon.sector or '未知'}")
        if dragon.broken:
            print(f"    断板天数：第{dragon.break_days}天")
        if dragon.peak_price > 0:
            print(f"    最高价：{dragon.peak_price:.2f}")
    else:
        print(f"    无龙头确认")
    print()

    # ── 预选龙头候选 ──
    print("  🎯 预选龙头候选（今日观察）")
    candidates = tracker.dragon_candidates
    if candidates:
        zt_df = market_stats.get('zt_df', pd.DataFrame())
        for i, c in enumerate(candidates, 1):
            name = c.get('name', '')
            sec = c.get('sector', '未知')
            streak = c.get('streak', 2)
            # 检查是否已涨停
            is_zt = False
            if not zt_df.empty and 'code' in zt_df.columns:
                stock = zt_df[zt_df['code'] == c['code']]
                if not stock.empty:
                    is_zt = True
                    name = stock.iloc[0].get('name', name)
            zt_mark = ' ✅' if is_zt else ''
            print(f"    {i}. {c['code']} {name} {streak}板 板块={sec}{zt_mark}")
        print(f"    （共{len(candidates)}只候选，观察今日是否三板晋级）")
    else:
        print(f"    无预选候选（等待二板股出现）")
    print()

    # ── 交易信号 ──
    # 判断是否可交易
    if phase == '退潮期':
        signal = '🔴  不可交易'
        reason = f'退潮期（跌停{limit_down}只 > 15只阈值）'
        advice = '关软件，今天不看盘！'
        can_trade = False
    elif phase == '高位震荡期' and dragon.break_days == 1:
        signal = '🔴  不可交易'
        reason = '龙头断板第一天（铁律2：断板当天不买）'
        advice = '管住手，今天不买！'
        can_trade = False
    elif phase == '主升期':
        signal = '🟢  可交易'
        reason = '主升期，持有龙头'
        advice = '持有龙头不动，不新开仓'
        can_trade = True
    elif phase == '高位震荡期':
        signal = '🟡  谨慎交易'
        reason = f'高位震荡期（断板第{dragon.break_days}天）'
        advice = '可做一进二，仓位50%，最多2只'
        can_trade = True
    else:  # 低位试错期
        signal = '🟡  谨慎交易'
        reason = '低位试错期'
        advice = '可试错二板股，仓位50%，最多2只'
        can_trade = True

    print(f"  {'=' * 50}")
    print(f"  {signal}")
    print(f"  {'=' * 50}")
    print(f"  当前阶段：{phase}")
    print(f"  判定原因：{reason}")
    print(f"  操作建议：{advice}")
    print()

    # ── 规则检查清单 ──
    print("  📋 规则检查清单")
    checks = [
        ('退潮期（跌停≤15只）', limit_down <= 15, f'跌停{limit_down}只'),
        ('大盘稳定（跌幅<2%）', market_stable, ''),
        ('断板当天不买', not (phase == '高位震荡期' and dragon.break_days == 1), ''),
        ('熔断中', True, '（未实现，待扩展）'),
    ]
    for label, passed, detail in checks:
        mark = '✅' if passed else '❌'
        detail_str = f'（{detail}）' if detail else ''
        print(f"    {mark} {label}{detail_str}")
    print()

    # ── 违规预警 ──
    print("  ⚠️  违规预警")
    print(f"    今天如果出手，你是在「{phase}」阶段出手")
    if can_trade:
        print(f"    系统允许交易，但只做系统内的事：")
        if phase == '主升期':
            print(f"      只买龙头 {dragon.stock}，不碰其他股")
        elif phase == '低位试错期':
            print(f"      只买符合条件的二板股，仓位≤50%，最多2只")
        elif phase == '高位震荡期':
            print(f"      只买一进二，仓位≤50%，最多2只")
    else:
        print(f"    系统禁止交易！任何买入都是违规操作！")
    print()

    # ── 今日仓位计划 ──
    print("  📝 今日仓位计划")
    print(f"    试错期单只仓位：{Broker.TRIAL_PCT*100:.0f}%  最多持有：2只")
    print(f"    主升期仓位：{Broker.MAIN_PCT*100:.0f}%  最多持有：1只")
    print()

    # ── 数据来源提示 ──
    if fetcher:
        data_source = getattr(fetcher, '_data_source', '未知')
        print(f"  🔗 数据来源：{data_source}")
    print()


def generate_html(tracker: DragonTracker, market_stats: dict, today: str, prev_date: str, fetcher: DataFetcher = None):
    """生成手机端HTML网页"""
    phase = tracker.current_phase
    dragon = tracker.dragon
    limit_down = market_stats.get('limit_down_count', 0)
    total_limit_up = market_stats.get('total_limit_up', 0)
    max_streak = market_stats.get('max_streak', 0)
    market_stable = market_stats.get('market_stable', True)
    first_board = market_stats.get('first_board_count', 0)
    second_board = market_stats.get('second_board_count', 0)
    third_board = market_stats.get('third_board_count', 0)
    sector = market_stats.get('sector_analysis', {})

    # 判断信号
    if phase == '退潮期':
        signal_text = '不可交易'
        signal_css = 'red'
        reason = f'退潮期（跌停{limit_down}只 > 15只阈值）'
        advice = '关软件，今天不看盘！'
        can_trade = False
    elif phase == '高位震荡期' and dragon.break_days == 1:
        signal_text = '不可交易'
        signal_css = 'red'
        reason = '龙头断板第一天（铁律2：断板当天不买）'
        advice = '管住手，今天不买！'
        can_trade = False
    elif phase == '主升期':
        signal_text = '可交易'
        signal_css = 'green'
        reason = '主升期，持有龙头'
        advice = '持有龙头不动，不新开仓'
        can_trade = True
    elif phase == '高位震荡期':
        signal_text = '谨慎交易'
        signal_css = 'yellow'
        reason = f'高位震荡期（断板第{dragon.break_days}天）'
        advice = '可做一进二，仓位50%，最多2只'
        can_trade = True
    else:
        signal_text = '谨慎交易'
        signal_css = 'yellow'
        reason = '低位试错期'
        advice = '可试错二板股，仓位50%，最多2只'
        can_trade = True

    # 龙头名称
    dragon_name = ''
    if dragon.stock:
        zt_df = market_stats.get('zt_df', None)
        if zt_df is not None and not zt_df.empty and 'code' in zt_df.columns:
            match = zt_df[zt_df['code'] == dragon.stock]
            if not match.empty and 'name' in match.columns:
                dragon_name = match.iloc[0]['name']

    # 规则检查
    checks = [
        ('退潮期（跌停≤15只）', limit_down <= 15, f'跌停{limit_down}只'),
        ('大盘稳定（跌幅<2%）', market_stable, ''),
        ('断板当天不买', not (phase == '高位震荡期' and dragon.break_days == 1), ''),
    ]

    # 板块信息
    top_sector = sector.get('top_sector', '') if sector else ''
    top_sector_count = sector.get('top_sector_count', 0) if sector else 0

    # 数据来源
    data_source = ''
    if fetcher:
        data_source = getattr(fetcher, '_data_source', '未知')

    # 生成HTML
    market_stable_text = '稳定' if market_stable else '⚠️不稳'
    checks_html = ''
    for label, passed, detail in checks:
        mark = '✅' if passed else '❌'
        cls = 'pass' if passed else 'fail'
        detail_str = f'<span class="detail">{detail}</span>' if detail else ''
        checks_html += f'<div class="check {cls}">{mark} {label} {detail_str}</div>'

    dragon_html = ''
    if dragon.stock:
        broken_tag = '<span class="tag tag-warn">已断板</span>' if dragon.broken else ''
        dragon_html = f'''
        <div class="card">
            <div class="section-title">🐉 龙头追踪</div>
            <div class="info-row">
                <span class="info-label">龙头</span>
                <span class="info-value">{dragon.stock} {dragon_name} {broken_tag}</span>
            </div>
            <div class="info-row">
                <span class="info-label">连板</span>
                <span class="info-value">{dragon.streak}板</span>
            </div>
            <div class="info-row">
                <span class="info-label">板块</span>
                <span class="info-value">{dragon.sector or '未知'}</span>
            </div>'''
        if dragon.broken:
            dragon_html += f'''
            <div class="info-row">
                <span class="info-label">断板天数</span>
                <span class="info-value">第{dragon.break_days}天</span>
            </div>'''
        if dragon.peak_price > 0:
            dragon_html += f'''
            <div class="info-row">
                <span class="info-label">最高价</span>
                <span class="info-value">{dragon.peak_price:.2f}</span>
            </div>'''
        dragon_html += '</div>'
    else:
        dragon_html = '''
        <div class="card">
            <div class="section-title">🐉 龙头追踪</div>
            <div class="no-data">暂无龙头确认</div>
        </div>'''

    # ── 预选龙头候选 HTML ──
    candidates_html = ''
    candidates = tracker.dragon_candidates
    if candidates:
        items_html = ''
        zt_df = market_stats.get('zt_df', pd.DataFrame())
        for c in candidates:
            name = c.get('name', '')
            sec = c.get('sector', '未知')
            streak = c.get('streak', 2)
            is_zt = False
            if not zt_df.empty and 'code' in zt_df.columns:
                stock = zt_df[zt_df['code'] == c['code']]
                if not stock.empty:
                    is_zt = True
                    name = stock.iloc[0].get('name', name)
            zt_tag = ' <span class="tag" style="background:#e8f5e9;color:#2e7d32;">已涨停</span>' if is_zt else ' <span class="tag" style="background:#fff3e0;color:#e65100;">未涨停</span>'
            items_html += f'''
            <div class="info-row">
                <span class="info-label">{c["code"]} {name}</span>
                <span class="info-value">{streak}板 板块={sec}{zt_tag}</span>
            </div>'''
        candidates_html = f'''
        <div class="card">
            <div class="section-title">🎯 预选龙头候选（今日观察）</div>
            {items_html}
            <div class="no-data" style="padding-top:6px;font-size:12px;color:#888;">共{len(candidates)}只候选，观察今日是否三板晋级</div>
        </div>'''
    else:
        candidates_html = '''
        <div class="card">
            <div class="section-title">🎯 预选龙头候选（今日观察）</div>
            <div class="no-data">暂无预选候选（等待二板股出现）</div>
        </div>'''

    # 违规预警
    warning_html = ''
    if can_trade:
        if phase == '主升期':
            warning_html = f'只买龙头 {dragon.stock}，不碰其他股'
        elif phase == '低位试错期':
            warning_html = '只买符合条件的二板股，仓位≤50%，最多2只'
        elif phase == '高位震荡期':
            warning_html = '只买一进二，仓位≤50%，最多2只'
    else:
        warning_html = '系统禁止交易！任何买入都是违规操作！'

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>龙抬头 - 交易信号 {today}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
    background: #f0f2f5; color: #333; padding: 12px; max-width: 480px; margin: 0 auto;
}}
.header {{ text-align: center; padding: 16px 0 8px; }}
.header h1 {{ font-size: 20px; font-weight: 700; color: #1a1a2e; }}
.header .date {{ font-size: 13px; color: #888; margin-top: 4px; }}
.signal-banner {{
    text-align: center; padding: 28px 16px; border-radius: 14px;
    font-size: 30px; font-weight: 700; color: #fff; margin: 12px 0;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}}
.green {{ background: linear-gradient(135deg, #43a047, #2e7d32); }}
.red {{ background: linear-gradient(135deg, #e53935, #b71c1c); }}
.yellow {{ background: linear-gradient(135deg, #fb8c00, #ef6c00); }}
.card {{
    background: #fff; border-radius: 12px; padding: 16px;
    margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}}
.section-title {{ font-size: 15px; font-weight: 600; color: #1a1a2e; margin-bottom: 10px; }}
.info-row {{ display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px solid #f0f0f0; font-size: 14px; }}
.info-row:last-child {{ border-bottom: none; }}
.info-label {{ color: #888; }}
.info-value {{ font-weight: 500; color: #333; }}
.tag {{ display: inline-block; font-size: 11px; padding: 1px 6px; border-radius: 4px; margin-left: 4px; }}
.tag-warn {{ background: #fff3e0; color: #e65100; }}
.phase-info {{ text-align: center; padding: 12px 0; }}
.phase-info .phase {{ font-size: 18px; font-weight: 600; margin-bottom: 4px; }}
.phase-info .reason {{ font-size: 13px; color: #666; }}
.advice {{ text-align: center; font-size: 16px; font-weight: 600; padding: 8px 0; }}
.check {{ padding: 8px 0; font-size: 14px; border-bottom: 1px solid #f0f0f0; }}
.check:last-child {{ border-bottom: none; }}
.check.pass {{ color: #2e7d32; }}
.check.fail {{ color: #c62828; }}
.check .detail {{ color: #888; font-size: 12px; margin-left: 4px; }}
.warning {{ text-align: center; padding: 12px; font-size: 14px; color: #c62828; }}
.warning.safe {{ color: #2e7d32; }}
.footer {{ text-align: center; color: #aaa; font-size: 11px; padding: 16px 0; }}
.data-source {{ text-align: center; color: #aaa; font-size: 11px; margin-top: 4px; }}
.no-data {{ text-align: center; color: #999; font-size: 14px; padding: 8px 0; }}
</style>
</head>
<body>

<div class="header">
    <h1>🐉 龙抬头 · 交易信号</h1>
    <div class="date">T日 {today} ｜ 基于 {prev_date} 数据</div>
</div>

<div class="signal-banner {signal_css}">{signal_text}</div>

<div class="card">
    <div class="section-title">📊 昨日市场概况</div>
    <div class="info-row">
        <span class="info-label">涨停</span>
        <span class="info-value">{total_limit_up}只</span>
    </div>
    <div class="info-row">
        <span class="info-label">跌停</span>
        <span class="info-value">{limit_down}只</span>
    </div>
    <div class="info-row">
        <span class="info-label">首板/二板/三板+</span>
        <span class="info-value">{first_board}/{second_board}/{third_board}</span>
    </div>
    <div class="info-row">
        <span class="info-label">最高连板</span>
        <span class="info-value">{max_streak}板</span>
    </div>
    <div class="info-row">
        <span class="info-label">大盘</span>
        <span class="info-value">{market_stable_text}</span>
    </div>'''

    if top_sector:
        html += f'''
    <div class="info-row">
        <span class="info-label">最强板块</span>
        <span class="info-value">{top_sector}（{top_sector_count}只涨停）</span>
    </div>'''

    html += f'''
</div>

{dragon_html}

{candidates_html}

<div class="card">
    <div class="section-title">🚦 交易信号</div>
    <div class="phase-info">
        <div class="phase">{phase}</div>
        <div class="reason">{reason}</div>
    </div>
    <div class="advice">{advice}</div>
</div>

<div class="card">
    <div class="section-title">📋 规则检查</div>
    {checks_html}
</div>

<div class="card">
    <div class="section-title">⚠️ 违规预警</div>
    <div class="warning {'safe' if can_trade else ''}">
        今天如果出手，你是在「{phase}」阶段出手<br>
        {warning_html}
    </div>
</div>

<div class="card">
    <div class="section-title">📝 仓位计划</div>
    <div class="info-row">
        <span class="info-label">试错期</span>
        <span class="info-value">{Broker.TRIAL_PCT*100:.0f}%仓位，最多2只</span>
    </div>
    <div class="info-row">
        <span class="info-label">主升期</span>
        <span class="info-value">{Broker.MAIN_PCT*100:.0f}%仓位，最多1只</span>
    </div>
</div>

<div class="footer">
    自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}
    <div class="data-source">数据来源：{data_source}</div>
</div>

</body>
</html>'''

    # 写入文件
    try:
        os.makedirs(PUBLIC_DIR, exist_ok=True)
        html_path = os.path.join(PUBLIC_DIR, 'index.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"[OK] 网页已生成：{html_path}")
    except Exception as e:
        print(f"[WARN] 生成网页失败: {e}")


def pushplus_notify(token: str, signal_text: str, phase: str, advice: str, url: str = ''):
    """通过 PushPlus 推送消息到微信"""
    pass  # 已废弃，不再使用


def generate_fallback_html(today: str, error_msg: str = ''):
    """生成降级网页（数据获取失败时使用）"""
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>龙抬头 - 信号待更新 {today}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f0f2f5; color: #333; padding: 12px; max-width: 480px; margin: 0 auto; }}
.header {{ text-align: center; padding: 16px 0 8px; }}
.header h1 {{ font-size: 20px; font-weight: 700; color: #1a1a2e; }}
.header .date {{ font-size: 13px; color: #888; margin-top: 4px; }}
.card {{ background: #fff; border-radius: 12px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
.signal {{ text-align: center; padding: 28px 16px; border-radius: 14px; font-size: 24px; font-weight: 700; color: #fff; margin: 12px 0; background: linear-gradient(135deg, #fb8c00, #ef6c00); }}
.warn {{ color: #c62828; text-align: center; font-size: 14px; padding: 12px; }}
.footer {{ text-align: center; color: #aaa; font-size: 11px; padding: 16px 0; }}
</style>
</head>
<body>
<div class="header">
    <h1>🐉 龙抬头 · 交易信号</h1>
    <div class="date">{today}</div>
</div>
<div class="signal">⏳ 信号待更新</div>
<div class="card">
    <div class="warn">数据获取失败，无法生成今日信号</div>
    <div style="text-align:center;color:#666;font-size:13px;padding:8px 0;">
        {error_msg}
    </div>
    <div style="text-align:center;color:#888;font-size:12px;padding:8px 0;">
        请稍后再试，或检查数据源是否正常
    </div>
</div>
<div class="footer">
    自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}
</div>
</body>
</html>'''
    try:
        os.makedirs(PUBLIC_DIR, exist_ok=True)
        html_path = os.path.join(PUBLIC_DIR, 'index.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"[OK] 降级网页已生成：{html_path}")
    except Exception as e:
        print(f"[WARN] 生成降级网页失败: {e}")


def main():
    parser = argparse.ArgumentParser(description='龙抬头每日交易信号灯')
    parser.add_argument('--date', type=str, default='',
                        help='T日日期 YYYYMMDD（默认今天）')
    parser.add_argument('--html', action='store_true',
                        help='同时生成手机端网页')
    parser.add_argument('--review', action='store_true',
                        help='在网页下方追加T-1日交易回顾')
    args = parser.parse_args()

    today = args.date or datetime.now().strftime('%Y%m%d')

    # ── 初始化 ──
    fetcher = DataFetcher()

    tracker = load_tracker()

    # ── 获取T-1日数据 ──
    print(f"\n[INFO] 获取{today}之前最近交易日数据...")
    prev_date = get_prev_trading_day(fetcher, today)
    if not prev_date:
        print(f"[ERROR] 未找到 {today} 之前的有效数据")
        print("[HINT] 检查 data/store/ 目录下是否有数据文件，或网络是否正常")
        if args.html:
            generate_fallback_html(today, '未找到前一日有效数据，网络或数据源异常')
        return

    print(f"[OK] 使用 {prev_date} 的数据判断 {today} 的阶段")

    market_stats = fetcher.get_market_stats(prev_date)
    if not market_stats or market_stats.get('total_limit_up', 0) == 0:
        print(f"[ERROR] {prev_date} 无涨停数据")
        if args.html:
            generate_fallback_html(today, f'{prev_date} 无涨停数据，数据源可能为空')
        return

    # ── 统一策略处理（process_day = 阶段判定 + 预选确认 + 预选新候选） ──
    try:
        phase = tracker.process_day(
            prev_market_stats=market_stats,
            today_zt_df=market_stats['zt_df'],
            fetcher=fetcher,
            prev_date=prev_date,
            sector_analysis=market_stats.get('sector_analysis', {})
        )
    except Exception as e:
        print(f"[ERROR] 策略处理失败: {e}")
        if args.html:
            generate_fallback_html(today, f'策略处理异常: {e}')
        return

    # ── 保存状态 ──
    save_tracker(tracker)

    # ── 输出信号 ──
    print_signal(tracker, market_stats, today, prev_date, fetcher)

    # ── 生成网页（如果指定了 --html） ──
    if args.html:
        generate_html(tracker, market_stats, today, prev_date, fetcher)

    # ── 网页追加T-1日回顾（如果指定了 --review） ──
    if args.review and args.html:
        # 获取T-1日市场数据，追加回顾到网页
        review_date = prev_date
        review_stats = fetcher.get_market_stats(review_date)
        if review_stats and review_stats.get('total_limit_up', 0) > 0:
            from scripts.daily_review import generate_review_html
            review_html = generate_review_html(tracker, review_stats, review_date, fetcher, today)
            html_path = os.path.join(PUBLIC_DIR, 'index.html')
            if os.path.exists(html_path):
                with open(html_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                content = content.replace('</body>', review_html + '\n</body>')
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"[OK] 交易回顾已追加到网页")
        else:
            print(f"[WARN] 无 {review_date} 数据，跳过回顾")


if __name__ == '__main__':
    main()