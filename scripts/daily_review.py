#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""
T-1日交易回顾 - 收盘后看模型当天做了什么决策

用法：
    python scripts/daily_review.py
    python scripts/daily_review.py --date 20260803   # 指定回顾日期

输出：
    - 当天市场数据
    - 模型当前阶段和龙头状态
    - 买入/卖出/持有决策
    - 持仓变动
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data import DataFetcher
from src.strategy import DragonTracker, DragonState
from src.broker import Broker


STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'dragon_state.json'
)


def load_tracker() -> DragonTracker:
    """从JSON文件恢复DragonTracker状态"""
    tracker = DragonTracker()
    if not os.path.exists(STATE_FILE):
        print("[INFO] 无历史状态，初始化为默认状态")
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
        return tracker
    except Exception as e:
        print(f"[WARN] 读取状态文件失败 ({e})，使用默认状态")
        return tracker


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


def main():
    parser = argparse.ArgumentParser(description='龙抬头每日交易回顾')
    parser.add_argument('--date', type=str, default='',
                        help='回顾日期 YYYYMMDD（默认T-1）')
    args = parser.parse_args()

    # 默认回顾T-1日
    fetcher = DataFetcher()
    today = datetime.now().strftime('%Y%m%d')
    review_date = args.date or get_prev_trading_day(fetcher, today)
    if not review_date:
        print("[ERROR] 无法确定回顾日期")
        return

    # 获取T-1市场数据
    market_stats = fetcher.get_market_stats(review_date)
    if not market_stats or market_stats.get('total_limit_up', 0) == 0:
        print(f"[ERROR] {review_date} 无有效数据")
        return

    zt_df = market_stats.get('zt_df', pd.DataFrame())
    total_limit_up = market_stats.get('total_limit_up', 0)
    limit_down = market_stats.get('limit_down_count', 0)
    max_streak = market_stats.get('max_streak', 0)
    first_board = market_stats.get('first_board_count', 0)
    second_board = market_stats.get('second_board_count', 0)
    third_board = market_stats.get('third_board_count', 0)
    market_stable = market_stats.get('market_stable', True)
    sector = market_stats.get('sector_analysis', {})
    data_source = getattr(fetcher, '_data_source', '未知')

    # 加载当前状态
    tracker = load_tracker()
    phase = tracker.current_phase

    # ── 输出 ──
    print(f"\n{'='*60}")
    print(f"  龙抬头 - 交易回顾  {review_date}")
    print(f"{'='*60}")
    print(f"  数据来源：{data_source}")

    # 1. 市场数据
    print(f"\n  📊 当日市场数据")
    print(f"    涨停：{total_limit_up}只  跌停：{limit_down}只")
    print(f"    首板：{first_board}  二板：{second_board}  三板+：{third_board}")
    print(f"    最高连板：{max_streak}板  "
          f"大盘：{'稳定' if market_stable else '⚠️不稳'}")
    if sector and 'top_sector' in sector:
        print(f"    最强板块：{sector['top_sector']}（{sector.get('top_sector_count', 0)}只涨停）")

    # 2. 当前阶段
    print(f"\n  🚦 当前阶段：{phase}")
    if phase == '退潮期':
        print(f"    判定：退潮期（跌停{limit_down}只 > 15只阈值）")
        print(f"    决策：强制空仓，卖出非涨停持仓")
    elif phase == '高位震荡期' and tracker.dragon.break_days == 1:
        print(f"    判定：龙头断板第一天")
        print(f"    决策：断板当天不买")
    elif phase == '主升期':
        print(f"    决策：持有龙头，不新开仓")
    elif phase == '高位震荡期':
        print(f"    判定：高位震荡期（断板第{tracker.dragon.break_days}天）")
        print(f"    决策：可做一进二，仓位50%，最多2只")
    else:
        print(f"    决策：可试错二板股，仓位50%，最多2只")

    # 3. 龙头状态
    print(f"\n  🐉 龙头状态")
    if tracker.dragon.stock:
        print(f"    龙头：{tracker.dragon.stock}（{tracker.dragon.streak}板）"
              f"{' 已断板' if tracker.dragon.broken else ''}")
        print(f"    板块：{tracker.dragon.sector or '未知'}")
        if tracker.dragon.broken:
            print(f"    断板天数：第{tracker.dragon.break_days}天")
        if tracker.dragon.peak_price > 0:
            print(f"    最高价：{tracker.dragon.peak_price:.2f}")

        # 检查龙头是否涨停
        if not zt_df.empty and 'code' in zt_df.columns:
            dragon_zt = zt_df[(zt_df['code'] == tracker.dragon.stock) & (zt_df['board_type'] != '炸板')]
            print(f"    今日表现：{'✅ 涨停' if not dragon_zt.empty else '❌ 未涨停'}")
    else:
        print(f"    无龙头确认")

    # 4. 预选龙头检查
    if tracker.dragon_candidates:
        print(f"\n  🎯 预选龙头检查")
        for c in tracker.dragon_candidates:
            if not zt_df.empty and 'code' in zt_df.columns:
                c_zt = zt_df[(zt_df['code'] == c['code']) & (zt_df['streak'] >= 3)]
                mark = '✅ 已三板' if not c_zt.empty else '❌ 未三板'
            else:
                mark = '❓ 无数据'
            print(f"    {mark}  {c['code']} {c.get('name', '')}（{c.get('sector', '')}）")

    # 5. 买入决策
    print(f"\n  💰 买入筛选结果")
    is_baostock = data_source == 'baostock'
    if phase == '退潮期':
        print(f"    退潮期 → 不买入")
    elif phase == '高位震荡期' and tracker.dragon.break_days == 1:
        print(f"    断板当天 → 不买入")
    else:
        buy_df = tracker.filter_buy_stocks(zt_df, phase, is_baostock, fetcher, review_date)
        if buy_df.empty:
            print(f"    无符合条件股票")
        else:
            print(f"    筛选出 {len(buy_df)} 只可买股票：")
            for _, row in buy_df.iterrows():
                bt = row.get('board_type', '')
                mark = '⚠️炸板' if bt == '炸板' else '✅封板'
                print(f"      {row['code']} {row.get('name','')}  "
                      f"价{row.get('price',0):.2f} {mark}  "
                      f"换手{row.get('turnover_rate',0):.1f}%  连板{row.get('streak',1)}")

    # 6. 卖出决策
    print(f"\n  📤 卖出信号")
    if phase == '退潮期':
        print(f"    退潮期 → 强制卖出所有非涨停持仓")
    elif not zt_df.empty and 'code' in zt_df.columns:
        zt_codes = set(zt_df[zt_df['board_type'] != '炸板']['code'].values)
        print(f"    今日封板涨停：{len(zt_codes)}只")
        print(f"    规则：持仓中未涨停的 → 卖出；涨停的 → 持有")
    else:
        print(f"    无涨停数据，无法判断")

    # 7. 决策总结
    print(f"\n  📋 决策总结")
    if phase == '退潮期':
        print(f"    🔴 空仓观望")
    elif phase == '主升期':
        print(f"    🟢 持有龙头 {tracker.dragon.stock}")
    elif phase == '高位震荡期' and tracker.dragon.break_days == 1:
        print(f"    🔴 断板当天，不操作")
    else:
        buy_df = tracker.filter_buy_stocks(zt_df, phase, is_baostock, fetcher, review_date) if phase != '退潮期' and not (phase == '高位震荡期' and tracker.dragon.break_days == 1) else pd.DataFrame()
        if buy_df.empty:
            print(f"    🟡 无符合条件股票，空仓等待")
        else:
            print(f"    🟡 可交易，仓位≤50%，最多2只")

    # 8. 仓位计划参考
    print(f"\n  📝 仓位参考")
    print(f"    试错期单只仓位：{Broker.TRIAL_PCT*100:.0f}%  最多持有：2只")
    print(f"    主升期仓位：{Broker.MAIN_PCT*100:.0f}%  最多持有：1只")
    print()


if __name__ == '__main__':
    main()