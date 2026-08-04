#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""
检查是否买入了炸板股
"""

import pandas as pd

# 读取决策日志
decision_df = pd.read_csv('data/decision_log.csv')

# 读取交易记录
trade_df = pd.read_csv('data/trade_records.csv')

# 读取涨停数据（包含炸板信息）
import os
zt_file = 'data/store/limit_up_baostock_20250724_20260724.csv'
if os.path.exists(zt_file):
    zt_df = pd.read_csv(zt_file, encoding='utf-8-sig', dtype={'code': str})
    zt_df['date'] = zt_df['date'].astype(str)

    # 筛选炸板股
    break_board_df = zt_df[zt_df['board_type'] == '炸板']

    print('='*80)
    print('炸板股数据检查')
    print('='*80)
    print()
    print(f'总涨停记录: {len(zt_df)}条')
    print(f'炸板记录: {len(break_board_df)}条 ({len(break_board_df)/len(zt_df)*100:.1f}%)')
    print()

    # 检查买入记录中是否包含炸板股
    buy_trades = trade_df[trade_df['action'] == 'buy']

    if len(buy_trades) > 0:
        # 检查每个买入日期的涨停股中是否有炸板股
        print('检查买入日是否有炸板股:')
        print()

        buy_dates = buy_trades['date'].unique()
        break_board_buy_count = 0

        for date in sorted(buy_dates):
            date_str = str(date)
            day_zt = zt_df[zt_df['date'] == date_str]
            day_break_board = day_zt[day_zt['board_type'] == '炸板']

            if len(day_break_board) > 0:
                day_buy = buy_trades[buy_trades['date'] == date]
                if len(day_buy) > 0:
                    print(f'{date_str}: 涨停{len(day_zt)}只，炸板{len(day_break_board)}只')
                    print(f'  炸板股: {", ".join(day_break_board["code"].values)}')
                    print(f'  买入股: {", ".join(day_buy["code"].values)}')

                    # 检查是否买入了炸板股
                    bought_codes = set(day_buy['code'].values)
                    break_board_codes = set(day_break_board['code'].values)
                    intersection = bought_codes & break_board_codes

                    if len(intersection) > 0:
                        print(f'  ⚠️  买入了炸板股: {", ".join(intersection)}')
                        break_board_buy_count += len(intersection)
                    print()

        if break_board_buy_count > 0:
            print(f'❌ 发现问题：买入了{break_board_buy_count}只炸板股！')
            print('   这是一个前视偏差问题：当天收盘后才知道炸板，但无法在当天买入！')
        else:
            print('✅ 未发现买入炸板股的情况')

    print()
    print('='*80)
    print('炸板股筛选逻辑分析')
    print('='*80)
    print()

    # 分析筛选逻辑
    print('当前筛选逻辑（strategy.py第298-299行）:')
    print('  if "board_type" in df.columns:')
    print('      df = df[~df["board_type"].str.contains("一字", na=False)]')
    print()
    print('问题：只过滤了一字板，没有过滤炸板股！')
    print()
    print('建议修改：')
    print('  if "board_type" in df.columns:')
    print('      df = df[~df["board_type"].str.contains("一字|炸板", na=False)]')

else:
    print(f'未找到涨停数据文件: {zt_file}')