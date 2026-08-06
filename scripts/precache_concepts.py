#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
概念板块预缓存脚本

直接运行即可，无需参数。
会自动扫描现有涨停数据，缓存所有股票的概念板块。
"""

import os
import sys
import pandas as pd

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data import DataFetcher

store_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'store')

fetcher = DataFetcher(store_dir=store_dir, use_csv=False)

# 扫描所有涨停CSV
all_codes = set()
csv_files = [f for f in os.listdir(store_dir)
             if f.startswith('limit_up_') and f.endswith('.csv')]
for fname in csv_files:
    fpath = os.path.join(store_dir, fname)
    df = pd.read_csv(fpath, encoding='utf-8-sig', dtype={'code': str})
    codes = df['code'].dropna().unique()
    all_codes.update(codes)

all_codes = [c for c in all_codes if str(c).startswith(('60', '00'))]
print(f"从 {len(csv_files)} 个CSV提取 {len(all_codes)} 只主板股票")

fetcher.precache_concept_sectors(all_codes)

print("\n完成！可以关闭窗口了。")
input("按回车键退出...")