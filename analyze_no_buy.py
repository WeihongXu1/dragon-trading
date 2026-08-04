#!/usr/bin/env python
# -*- coding:utf-8 -*-

import pandas as pd

# 读取CSV
df = pd.read_csv('data/decision_log.csv')

print('='*80)
print('空仓原因完整统计')
print('='*80)
print()

# 计算总数
total_days = len(df)
no_buy = df[df['是否买入'] == '否']
no_buy_days = len(no_buy)

print(f'总交易天数: {total_days}天')
print(f'空仓天数: {no_buy_days}天')
print(f'空仓占比: {no_buy_days/total_days*100:.1f}%')
print()

# 统计不买入原因
print('='*80)
print('空仓原因详细统计')
print('='*80)
print()

reasons = no_buy['不买入原因'].value_counts()

summary_data = []
for reason, count in reasons.items():
    pct = count / total_days * 100
    summary_data.append({
        '不买入原因': reason,
        '天数': count,
        '占比': f'{pct:.1f}%'
    })

summary_df = pd.DataFrame(summary_data)
print(summary_df.to_string(index=False))

print()
print('='*80)
print('买入情况分析')
print('='*80)
print()

buy = df[df['是否买入'] == '是']
print(f'总买入天数: {len(buy)}天 ({len(buy)/total_days*100:.1f}%)')

print()
print('按周期统计买入:')
for phase in df['周期'].unique():
    phase_buy = df[(df['周期'] == phase) & (df['是否买入'] == '是')]
    phase_total = df[df['周期'] == phase]
    print(f'  {phase}: {len(phase_buy)}天/{len(phase_total)}天 ({len(phase_buy)/len(phase_total)*100:.1f}%)')

print()
print('='*80)
print('持仓分布')
print('='*80)
print()

for pos in sorted(df['持仓数量'].unique()):
    pos_days = df[df['持仓数量'] == pos]
    print(f'持仓{pos}只: {len(pos_days)}天 ({len(pos_days)/total_days*100:.1f}%)')

print()
print('='*80)
print('周期分布统计')
print('='*80)
print()

phase_dist = df['周期'].value_counts()
for phase, count in phase_dist.items():
    print(f'{phase}: {count}天 ({count/total_days*100:.1f}%)')

print()
print('='*80)
print('特殊情况检查')
print('='*80)
print()

# 检查持有股票但不买入的情况
hold_no_buy = df[(df['持仓数量'] > 0) & (df['是否买入'] == '否')]
if len(hold_no_buy) > 0:
    print(f'持有股票但不买入: {len(hold_no_buy)}天')
    for idx, row in hold_no_buy.iterrows():
        print(f"  {row['日期']}: {row['周期']} - {row['不买入原因']}")
else:
    print('没有持有股票但不买入的情况')