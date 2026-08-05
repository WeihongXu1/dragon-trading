#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""
2026年6-7月策略腰斩归因分析
"""

import pandas as pd
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = 'data'

# ============================================================
# 1. 读取数据
# ============================================================
trade_df = pd.read_csv(f'{DATA_DIR}/trade_records.csv', dtype={'code': str})
decision_df = pd.read_csv(f'{DATA_DIR}/decision_log.csv')
daily_pnl_df = pd.read_csv(f'{DATA_DIR}/daily_pnl.csv', dtype={'code': str})

# 涨停数据（用于连板高度、炸板判断）
zt_file = f'{DATA_DIR}/store/limit_up_baostock_20250724_20260724.csv'
zt_df = pd.read_csv(zt_file, encoding='utf-8-sig', dtype={'code': str})
# 统一日期格式：2025-10-13 -> 20251013
zt_df['date'] = pd.to_datetime(zt_df['date']).dt.strftime('%Y%m%d')

# 筛选6-7月
def in_range(d):
    s = str(d)
    return s.startswith('202606') or s.startswith('202607')

sell_df = trade_df[trade_df['action'] == 'sell'].copy()
sell_df['date'] = sell_df['date'].astype(str)
sell_df = sell_df[sell_df['date'].apply(in_range)].copy()

# 每日盈亏（日期粒度）
daily_pnl_df['date'] = daily_pnl_df['date'].astype(str)
daily_pnl_67 = daily_pnl_df[daily_pnl_df['date'].apply(in_range)].copy()
daily_total = daily_pnl_67.groupby('date')['profit'].sum().reset_index()
daily_total = daily_total.sort_values('date').reset_index(drop=True)
daily_total['cum_profit'] = daily_total['profit'].cumsum()

# ============================================================
# 2. 总体情况
# ============================================================
sep = '=' * 90
print(sep)
print('【2026年6-7月策略腰斩归因分析】')
print(sep)
print()

total_profit = sell_df['profit'].sum()
total_count = len(sell_df)
win_count = len(sell_df[sell_df['profit'] > 0])
lose_count = len(sell_df[sell_df['profit'] < 0])
win_rate = win_count / total_count * 100 if total_count > 0 else 0
avg_profit = sell_df['profit'].mean()
avg_win = sell_df[sell_df['profit'] > 0]['profit'].mean() if win_count > 0 else 0
avg_lose = sell_df[sell_df['profit'] < 0]['profit'].mean() if lose_count > 0 else 0

print(f'6-7月总交易笔数: {total_count}笔')
print(f'6-7月总盈亏:   {total_profit:,.2f}元')
print(f'胜率:          {win_rate:.1f}% ({win_count}盈 / {lose_count}亏)')
print(f'单笔平均盈亏:  {avg_profit:,.2f}元')
print(f'平均盈利:      {avg_win:,.2f}元')
print(f'平均亏损:      {avg_lose:,.2f}元')
if avg_lose != 0:
    print(f'盈亏比:        {abs(avg_win/avg_lose):.2f}')
print()

# ============================================================
# 3. 时间维度：每日盈亏Top10亏损日
# ============================================================
print(sep)
print('【时间维度】每日盈亏Top10亏损日')
print(sep)
print()
top10_loss = daily_total.sort_values('profit').head(10)
for _, row in top10_loss.iterrows():
    # 看当天是哪些股票亏的
    day_pnl = daily_pnl_67[daily_pnl_67['date'] == row['date']].sort_values('profit')
    loss_stocks = []
    for _, s in day_pnl.iterrows():
        if s['profit'] < 0:
            name_row = trade_df[(trade_df['code'] == s['code']) & (trade_df['action'] == 'sell') & (trade_df['date'].astype(str) == row['date'])]
            name = name_row['name'].values[0] if len(name_row) > 0 else s['code']
            loss_stocks.append(f"{name}({s['profit']:,.0f})")
    # 当日周期
    phase_row = decision_df[decision_df['日期'].astype(str) == row['date']]
    phase = phase_row['周期'].values[0] if len(phase_row) > 0 else '-'
    print(f"{row['date']}  {phase:<8}  当日盈亏: {row['profit']:>10,.2f}元  亏损个股: {', '.join(loss_stocks[:5])}")
print()

# ============================================================
# 4. 时间维度：每日盈亏表
# ============================================================
print(sep)
print('【时间维度】6-7月逐日盈亏（含累计）')
print(sep)
print()
print(f"{'日期':<10} {'周期':<8} {'当日盈亏':>12} {'累计盈亏':>12} {'当日个股明细'}")
print('-' * 90)
for _, row in daily_total.iterrows():
    day_pnl = daily_pnl_67[daily_pnl_67['date'] == row['date']].sort_values('profit')
    details = []
    for _, s in day_pnl.iterrows():
        name_row = trade_df[(trade_df['code'] == s['code']) & (trade_df['action'] == 'sell') & (trade_df['date'].astype(str) == row['date'])]
        name = name_row['name'].values[0] if len(name_row) > 0 else s['code']
        sign = '+' if s['profit'] >= 0 else ''
        details.append(f"{name}{sign}{s['profit']:,.0f}")
    phase_row = decision_df[decision_df['日期'].astype(str) == row['date']]
    phase = phase_row['周期'].values[0] if len(phase_row) > 0 else '-'
    detail_str = ', '.join(details)
    if len(detail_str) > 50:
        detail_str = detail_str[:47] + '...'
    print(f"{row['date']:<10} {phase:<8} {row['profit']:>12,.2f} {row['cum_profit']:>12,.2f}  {detail_str}")
print()

# ============================================================
# 5. 个股维度：亏损Top20
# ============================================================
print(sep)
print('【个股维度】亏损Top20个股')
print(sep)
print()

stock_pnl = sell_df.groupby(['code', 'name']).agg(
    total_profit=('profit', 'sum'),
    count=('profit', 'count'),
    win=('profit', lambda x: (x > 0).sum()),
    avg_profit=('profit', 'mean'),
    max_profit=('profit', 'max'),
    min_profit=('profit', 'min'),
).reset_index().sort_values('total_profit')

# 加上买入时的信息
def get_buy_info(row):
    code = row['code']
    name = row['name']
    sells = sell_df[(sell_df['code'] == code) & (sell_df['name'] == name)]
    buy_dates = []
    buy_phases = []
    buy_streaks = []
    for _, s in sells.iterrows():
        sd = str(s['date'])
        buy = trade_df[(trade_df['code'] == code) & (trade_df['action'] == 'buy') &
                       (trade_df['date'].astype(str) < sd)].tail(1)
        if len(buy) > 0:
            bd = str(buy['date'].values[0])
            phase = buy['phase'].values[0]
            buy_dates.append(bd)
            buy_phases.append(phase)
            # 查当日连板数
            zt_row = zt_df[(zt_df['code'] == code) & (zt_df['date'] == bd)]
            streak = zt_row['streak'].values[0] if len(zt_row) > 0 and 'streak' in zt_row.columns else '-'
            buy_streaks.append(str(streak))
    return pd.Series([','.join(buy_dates), ','.join(buy_phases), ','.join(buy_streaks)])

stock_pnl[['buy_dates', 'buy_phases', 'buy_streaks']] = stock_pnl.apply(get_buy_info, axis=1)

top20_loss = stock_pnl.head(20).reset_index(drop=True)
print(f"{'排名':<4} {'代码':<6} {'名称':<8} {'总盈亏':>10} {'笔数':>4} {'胜率':>6} {'连板':>6} {'阶段':<10}")
for i, row in top20_loss.iterrows():
    wr = f"{row['win']/row['count']*100:.0f}%" if row['count'] > 0 else '-'
    print(f"{i+1:<4} {row['code']:<6} {row['name']:<8} {row['total_profit']:>10,.2f} {row['count']:>4} {wr:>6} {row['buy_streaks']:>6} {row['buy_phases']:<10}")
print()

# ============================================================
# 6. 周期维度：不同阶段盈亏
# ============================================================
print(sep)
print('【周期维度】不同市场阶段盈亏')
print(sep)
print()

phase_pnl = sell_df.groupby('phase').agg(
    total_profit=('profit', 'sum'),
    count=('profit', 'count'),
    win=('profit', lambda x: (x > 0).sum()),
    avg_profit=('profit', 'mean'),
    avg_win=('profit', lambda x: x[x > 0].mean() if (x > 0).sum() > 0 else 0),
    avg_lose=('profit', lambda x: x[x < 0].mean() if (x < 0).sum() > 0 else 0),
).reset_index().sort_values('total_profit')

print(f"{'阶段':<14} {'总盈亏':>12} {'笔数':>6} {'胜率':>6} {'单笔平均':>10} {'平均盈利':>10} {'平均亏损':>10}")
for _, row in phase_pnl.iterrows():
    wr = f"{row['win']/row['count']*100:.1f}%" if row['count'] > 0 else '-'
    ratio = f"{abs(row['avg_win']/row['avg_lose']):.2f}" if row['avg_lose'] != 0 else '-'
    print(f"{row['phase']:<14} {row['total_profit']:>12,.2f} {row['count']:>6} {wr:>6} {row['avg_profit']:>10,.2f} {row['avg_win']:>10,.2f} {row['avg_lose']:>10,.2f}")
print()

# 6-7月各阶段分布
phase_days = decision_df[decision_df['日期'].astype(str).apply(in_range)]['周期'].value_counts().reset_index()
phase_days.columns = ['阶段', '天数']
phase_days['占比'] = (phase_days['天数'] / phase_days['天数'].sum() * 100).round(1).astype(str) + '%'
print('6-7月各阶段分布:')
print(phase_days.to_string(index=False))
print()

# ============================================================
# 7. 连板高度：买入时连板数 vs 盈亏
# ============================================================
print(sep)
print('【连板高度】买入时连板数 vs 盈亏')
print(sep)
print()

def get_buy_streak(sell_row):
    code = sell_row['code']
    sd = str(sell_row['date'])
    buy = trade_df[(trade_df['code'] == code) & (trade_df['action'] == 'buy') &
                   (trade_df['date'].astype(str) < sd)].tail(1)
    if len(buy) == 0:
        return None
    bd = str(buy['date'].values[0])
    zt_row = zt_df[(zt_df['code'] == code) & (zt_df['date'] == bd)]
    if len(zt_row) > 0 and 'streak' in zt_row.columns:
        return zt_row['streak'].values[0]
    return None

def is_buy_breakboard(sell_row):
    code = sell_row['code']
    sd = str(sell_row['date'])
    buy = trade_df[(trade_df['code'] == code) & (trade_df['action'] == 'buy') &
                   (trade_df['date'].astype(str) < sd)].tail(1)
    if len(buy) == 0:
        return False
    bd = str(buy['date'].values[0])
    zt_row = zt_df[(zt_df['code'] == code) & (zt_df['date'] == bd)]
    if len(zt_row) > 0 and 'board_type' in zt_row.columns:
        return zt_row['board_type'].values[0] == '炸板'
    return False

sell_df['buy_streak'] = sell_df.apply(get_buy_streak, axis=1)
sell_df['buy_break_board'] = sell_df.apply(is_buy_breakboard, axis=1)

streak_pnl = sell_df[~sell_df['buy_streak'].isna()].groupby('buy_streak').agg(
    total_profit=('profit', 'sum'),
    count=('profit', 'count'),
    win=('profit', lambda x: (x > 0).sum()),
    avg_profit=('profit', 'mean'),
).reset_index().sort_values('buy_streak')

print(f"{'买入连板数':<10} {'总盈亏':>12} {'笔数':>6} {'胜率':>6} {'单笔平均':>10}")
for _, row in streak_pnl.iterrows():
    wr = f"{row['win']/row['count']*100:.1f}%" if row['count'] > 0 else '-'
    print(f"{int(row['buy_streak']):<10} {row['total_profit']:>12,.2f} {row['count']:>6} {wr:>6} {row['avg_profit']:>10,.2f}")
print()

# ============================================================
# 8. 炸板vs封板盈亏对比
# ============================================================
print(sep)
print('【炸板分析】买入当天炸板 vs 封板 盈亏对比')
print(sep)
print()

bb_pnl = sell_df.groupby('buy_break_board').agg(
    total_profit=('profit', 'sum'),
    count=('profit', 'count'),
    win=('profit', lambda x: (x > 0).sum()),
    avg_profit=('profit', 'mean'),
).reset_index()

for _, row in bb_pnl.iterrows():
    label = '炸板买入' if row['buy_break_board'] else '封板买入'
    wr = f"{row['win']/row['count']*100:.1f}%" if row['count'] > 0 else '-'
    print(f"{label}: 总盈亏{row['total_profit']:>12,.2f}元  {row['count']:>4}笔  胜率{wr:>6}  单笔平均{row['avg_profit']:>10,.2f}元")
print()

# 列出炸板买入亏损个股
bb_loss = sell_df[sell_df['buy_break_board']].sort_values('profit')
if len(bb_loss) > 0:
    print('炸板买入个股明细:')
    for _, row in bb_loss.head(15).iterrows():
        bd = trade_df[(trade_df['code'] == row['code']) & (trade_df['action'] == 'buy') &
                      (trade_df['date'].astype(str) < str(row['date']))].tail(1)
        bdate = str(bd['date'].values[0]) if len(bd) > 0 else '-'
        print(f"  {row['date']} {row['code']} {row['name']:<8} 买入日{bdate} 连板{row['buy_streak']} 盈亏{row['profit']:,.2f}元 ({row['profit_pct']*100:.1f}%)")
print()

# ============================================================
# 9. 主升期龙头交易明细
# ============================================================
print(sep)
print('【主升期龙头】6-7月主升期买入明细')
print(sep)
print()

main_buy = sell_df[sell_df['phase'] == '主升期'].sort_values('date')
if len(main_buy) > 0:
    print(f"{'卖出日':<10} {'代码':<6} {'名称':<8} {'买入连板':>6} {'炸板':>4} {'盈亏':>12} {'收益率':>8}")
    for _, row in main_buy.iterrows():
        bb = '是' if row['buy_break_board'] else '否'
        sign = '+' if row['profit'] >= 0 else ''
        print(f"{row['date']:<10} {row['code']:<6} {row['name']:<8} {str(row['buy_streak']):>6} {bb:>4} {row['profit']:>12,.2f} {row['profit_pct']*100:>+7.1f}%")
else:
    print('6-7月无主升期交易')
print()

# ============================================================
# 10. 持仓天数 vs 盈亏
# ============================================================
print(sep)
print('【持仓天数】持仓天数 vs 盈亏')
print(sep)
print()

def get_hold_days(sell_row):
    code = sell_row['code']
    sd = str(sell_row['date'])
    buy = trade_df[(trade_df['code'] == code) & (trade_df['action'] == 'buy') &
                   (trade_df['date'].astype(str) < sd)].tail(1)
    if len(buy) == 0:
        return None
    bd = str(buy['date'].values[0])
    try:
        from datetime import datetime
        d1 = datetime.strptime(bd, '%Y%m%d')
        d2 = datetime.strptime(sd, '%Y%m%d')
        return (d2 - d1).days
    except:
        return None

sell_df['hold_days'] = sell_df.apply(get_hold_days, axis=1)
hold_pnl = sell_df[~sell_df['hold_days'].isna()].groupby('hold_days').agg(
    total_profit=('profit', 'sum'),
    count=('profit', 'count'),
    win=('profit', lambda x: (x > 0).sum()),
    avg_profit=('profit', 'mean'),
).reset_index().sort_values('hold_days')

print(f"{'持仓天数':<8} {'总盈亏':>12} {'笔数':>6} {'胜率':>6} {'单笔平均':>10}")
for _, row in hold_pnl.iterrows():
    wr = f"{row['win']/row['count']*100:.1f}%" if row['count'] > 0 else '-'
    print(f"{int(row['hold_days']):<8} {row['total_profit']:>12,.2f} {row['count']:>6} {wr:>6} {row['avg_profit']:>10,.2f}")
print()

# ============================================================
# 11. 总结与建议
# ============================================================
print(sep)
print('【总结】')
print(sep)
print()

# 自动生成结论
loss_phases = phase_pnl[phase_pnl['total_profit'] < 0]['phase'].tolist()
bb_total = sell_df[sell_df['buy_break_board']]['profit'].sum()
normal_total = sell_df[~sell_df['buy_break_board']]['profit'].sum()

print(f'1. 6-7月总盈亏: {total_profit:,.2f}元, 共{total_count}笔交易')
if loss_phases:
    print(f'2. 亏损阶段: {", ".join(loss_phases)}')
# 最大亏损日
worst_day = daily_total.sort_values('profit').iloc[0]
print(f'3. 最大单日亏损: {worst_day["date"]} 亏损{worst_day["profit"]:,.2f}元')
# 个股
worst_stock = stock_pnl.iloc[0]
print(f'4. 最大亏损个股: {worst_stock["name"]}({worst_stock["code"]}) 累计亏损{worst_stock["total_profit"]:,.2f}元')
# 炸板
print(f'5. 炸板买入总盈亏: {bb_total:,.2f}元 / {sell_df["buy_break_board"].sum()}笔, 封板买入: {normal_total:,.2f}元 / {(~sell_df["buy_break_board"]).sum()}笔')
if len(streak_pnl) > 0:
    worst_streak_row = streak_pnl.sort_values('avg_profit').iloc[0]
    print(f'6. 最差连板高度: {int(worst_streak_row["buy_streak"])}板 单笔平均{worst_streak_row["avg_profit"]:,.2f}元')

print()
print('脚本输出完成，请根据以上数据自行判断根因。')
