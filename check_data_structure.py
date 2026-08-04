#!/usr/bin/env python
# -*- coding:utf-8 -*-

import pandas as pd
import os

# 检查涨停数据文件
zt_file = 'data/store/limit_up_baostock_20250724_20260724.csv'
if os.path.exists(zt_file):
    zt_df = pd.read_csv(zt_file, encoding='utf-8-sig', dtype={'code': str}, nrows=10)
    print('涨停数据文件列名:')
    print(zt_df.columns.tolist())
    print()
    print('board_type值分布:')
    zt_full = pd.read_csv(zt_file, encoding='utf-8-sig', dtype={'code': str})
    print(zt_full['board_type'].value_counts())
    print()
else:
    print(f'未找到文件: {zt_file}')

# 检查炸板数据文件
bb_file = 'data/store/break_board_baostock_20250724_20260724.csv'
if os.path.exists(bb_file):
    bb_df = pd.read_csv(bb_file, encoding='utf-8-sig', dtype={'code': str})
    print(f'炸板数据文件存在: {bb_file}')
    print(f'炸板记录数: {len(bb_df)}条')
    print()
    print('炸板数据文件列名:')
    print(bb_df.columns.tolist())
    print()
    print('前5条炸板记录:')
    print(bb_df.head())
else:
    print(f'未找到文件: {bb_file}')