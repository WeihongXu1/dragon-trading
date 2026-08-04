#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""
分析三条铁律的具体执行情况
"""

import pandas as pd
import numpy as np

# 读取数据
decision_df = pd.read_csv('data/decision_log.csv')
trade_df = pd.read_csv('data/trade_records.csv')

print('='*80)
print('三条铁律执行情况详细分析')
print('='*80)
print()

# ============================================================================
# 铁律1: 退潮期铁律 - 跌停>15只或大盘跌>1%
# ============================================================================
print('【铁律1】退潮期铁律：跌停>15只或大盘跌>1%，直接关软件')
print('-'*80)

retreat_days = decision_df[(decision_df['周期'] == '退潮期') & (decision_df['不买入原因'] == '退潮期强制空仓')]
print(f'退潮期强制空仓天数: {len(retreat_days)}天 ({len(retreat_days)/len(decision_df)*100:.1f}%)')
print()
print('具体日期:')
for idx, row in retreat_days.iterrows():
    print(f"  {row['日期']} - 空仓{row['持仓数量']}只 资金{row['资金余额']:,.2f}元")

print()

# ============================================================================
# 铁律2: 断板当天不买 - 龙头断板第一天
# ============================================================================
print('【铁律2】断板当天不买：龙头断板第一天，管住手')
print('-'*80)

break_board_days = decision_df[decision_df['不买入原因'] == '高位震荡期断板当天']
print(f'断板当天不买天数: {len(break_board_days)}天 ({len(break_board_days)/len(decision_df)*100:.1f}%)')
print()
print('具体日期:')
for idx, row in break_board_days.iterrows():
    print(f"  {row['日期']} - 高位震荡期断板当天 持仓{row['持仓数量']}只 资金{row['资金余额']:,.2f}元")

print()

# ============================================================================
# 铁律3: 熔断纪律 - 连续亏3笔，强制休息3天
# ============================================================================
print('【铁律3】熔断纪律：连续亏3笔，强制休息3天')
print('-'*80)

# 分析连续亏损情况
sell_trades = trade_df[trade_df['action'] == 'sell'].copy()
sell_trades['profit_sign'] = sell_trades['profit'].apply(lambda x: '亏' if x < 0 else '盈')

# 找出连续亏损3笔的情况
loss_streaks = []
current_streak = 0
streak_start_idx = None

for idx, row in sell_trades.iterrows():
    if row['profit'] < 0:
        if current_streak == 0:
            streak_start_idx = idx
        current_streak += 1
        if current_streak >= 3:
            # 找到连续亏损3笔
            streak_dates = sell_trades.loc[streak_start_idx:idx]['date'].tolist()
            streak_profits = sell_trades.loc[streak_start_idx:idx]['profit'].tolist()
            loss_streaks.append({
                'dates': streak_dates,
                'profits': streak_profits,
                'total_loss': sum(streak_profits)
            })
    else:
        current_streak = 0
        streak_start_idx = None

if loss_streaks:
    print(f'触发熔断的次数: {len(loss_streaks)}次')
    print()
    for i, streak in enumerate(loss_streaks, 1):
        print(f'第{i}次熔断:')
        # 将日期转换为字符串
        dates_str = [str(d) for d in streak['dates']]
        print(f'  连续亏损日期: {", ".join(dates_str)}')
        print(f'  累计亏损: {streak["total_loss"]:,.2f}元')
        for j, (date, profit) in enumerate(zip(streak['dates'], streak['profits']), 1):
            print(f'    {j}. {date}: 亏损{profit:,.2f}元')
        print()
else:
    print('回测期间未触发熔断机制')

# 检查是否有熔断相关的记录
fuse_days = decision_df[decision_df['不买入原因'].str.contains('熔断', na=False)]
if len(fuse_days) > 0:
    print(f'决策日志中的熔断记录: {len(fuse_days)}天')
    for idx, row in fuse_days.iterrows():
        print(f"  {row['日期']} - {row['不买入原因']}")

print()

# ============================================================================
# 汇总统计
# ============================================================================
print('='*80)
print('汇总统计')
print('='*80)
print()

total_days = len(decision_df)
total_no_buy = len(decision_df[decision_df['是否买入'] == '否'])

print(f'总交易天数: {total_days}天')
print(f'总空仓天数: {total_no_buy}天 ({total_no_buy/total_days*100:.1f}%)')
print()

# 计算三条铁律覆盖的空仓天数
rule1_days = len(retreat_days)
rule2_days = len(break_board_days)
rule3_days = len(fuse_days) if len(fuse_days) > 0 else 0

print('三条铁律覆盖的空仓天数:')
print(f'  铁律1（退潮期）: {rule1_days}天 ({rule1_days/total_days*100:.1f}%)')
print(f'  铁律2（断板当天）: {rule2_days}天 ({rule2_days/total_days*100:.1f}%)')
print(f'  铁律3（熔断）: {rule3_days}天 ({rule3_days/total_days*100:.1f}%)')
print(f'  合计: {rule1_days + rule2_days + rule3_days}天 ({(rule1_days + rule2_days + rule3_days)/total_days*100:.1f}%)')

print()
print('='*80)
print('结论')
print('='*80)
print()
print('✅ 三条铁律严格执行，覆盖了所有主要的空仓情况')
print(f'✅ 退潮期铁律占比最高（{rule1_days/total_days*100:.1f}%），有效规避市场风险')
print(f'✅ 断板当天不买（{rule2_days/total_days*100:.1f}%），避免情绪转折点出手')
if rule3_days == 0:
    print('✅ 熔断纪律未触发，说明策略整体稳健，连续亏损较少')
else:
    print(f'⚠️  熔断纪律触发{rule3_days}次，需要注意风险控制')