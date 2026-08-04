#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""
回测入口脚本

用法：
    python scripts/run_backtest.py
    python scripts/run_backtest.py --start 20260301 --end 20260723 --capital 100000
"""

import sys
import os
import argparse

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine import BacktestEngine


def main():
    parser = argparse.ArgumentParser(description='龙抬头超短量化策略回测')
    parser.add_argument('--start', type=str, default='20250724', help='开始日期 YYYYMMDD')
    parser.add_argument('--end', type=str, default='20260724', help='结束日期 YYYYMMDD')
    parser.add_argument('--capital', type=float, default=100000, help='初始资金')
    args = parser.parse_args()

    engine = BacktestEngine(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital
    )
    engine.run()


if __name__ == '__main__':
    main()