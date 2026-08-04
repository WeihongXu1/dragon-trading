#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""
数据获取层 - 支持akshare在线API和CSV离线模式

功能：
1. 获取涨停股数据（包含封板时间、炸板次数等）
2. 获取大盘指数数据
3. 获取股票K线数据
4. 统计板块涨停情况
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import os
from typing import List, Dict, Optional


class DataFetcher:
    """数据获取器（支持CSV离线模式）"""

    def __init__(self, cache_dir: str = './cache', store_dir: str = None, use_csv: bool = True):
        self.cache_dir = cache_dir
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

        # CSV数据目录：src/data.py -> ../data/store
        self.store_dir = store_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'store')
        self.use_csv = use_csv

        self._limit_up_df = None
        self._limit_down_df = None
        self._index_df = None
        self._kline_df = None
        self._break_board_df = None
        self._data_source = None

        if self.use_csv and os.path.exists(self.store_dir):
            self._load_csv_data()

    def _load_csv_data(self):
        """从CSV文件加载数据"""
        try:
            bs_files = [f for f in os.listdir(self.store_dir) if f.startswith('limit_up_baostock_') and f.endswith('.csv')]
            if bs_files:
                bs_files.sort(reverse=True)
                bs_file = os.path.join(self.store_dir, bs_files[0])
                self._limit_up_df = pd.read_csv(bs_file, encoding='utf-8-sig', dtype={'code': str})
                self._data_source = 'baostock'
                print(f"[OK] 从CSV加载Baostock涨停数据: {bs_file} ({len(self._limit_up_df)}条)")

            if self._limit_up_df is None:
                zt_files = [f for f in os.listdir(self.store_dir) if f.startswith('limit_up_') and not f.startswith('limit_up_baostock_') and f.endswith('.csv')]
                if zt_files:
                    zt_file = os.path.join(self.store_dir, zt_files[0])
                    self._limit_up_df = pd.read_csv(zt_file, encoding='utf-8-sig', dtype={'code': str})
                    self._data_source = 'akshare'
                    print(f"[OK] 从CSV加载akshare涨停数据: {zt_file} ({len(self._limit_up_df)}条)")

            if self._limit_up_df is None:
                self._data_source = None
                print("[WARN] 未找到涨停数据CSV，将使用在线API")

            dt_files = [f for f in os.listdir(self.store_dir) if f.startswith('limit_down_baostock_') and f.endswith('.csv')]
            if not dt_files:
                dt_files = [f for f in os.listdir(self.store_dir) if f.startswith('limit_down_') and not f.startswith('limit_down_baostock_') and f.endswith('.csv')]
            if dt_files:
                dt_file = os.path.join(self.store_dir, dt_files[0])
                self._limit_down_df = pd.read_csv(dt_file, encoding='utf-8-sig')
                print(f"[OK] 从CSV加载跌停股数据: {dt_file}")

            index_file = os.path.join(self.store_dir, 'index_current.csv')
            if os.path.exists(index_file):
                self._index_df = pd.read_csv(index_file, encoding='utf-8-sig')
                print(f"[OK] 从CSV加载指数数据: {index_file}")

            kline_files = [f for f in os.listdir(self.store_dir) if f.startswith('all_kline_') and f.endswith('.csv')]
            if kline_files:
                kline_files.sort(reverse=True)
                kline_file = os.path.join(self.store_dir, kline_files[0])
                self._kline_df = pd.read_csv(kline_file, encoding='utf-8-sig', dtype={'code': str})
                print(f"[OK] 从CSV加载K线数据: {kline_file} ({len(self._kline_df)}条)")

            bb_files = [f for f in os.listdir(self.store_dir) if f.startswith('break_board_baostock_') and f.endswith('.csv')]
            if bb_files:
                bb_files.sort(reverse=True)
                bb_file = os.path.join(self.store_dir, bb_files[0])
                self._break_board_df = pd.read_csv(bb_file, encoding='utf-8-sig', dtype={'code': str})
                print(f"[OK] 从CSV加载炸板数据: {bb_file} ({len(self._break_board_df)}条)")

        except Exception as e:
            print(f"[WARN] 加载CSV数据失败: {e}")

    def get_limit_up_stocks(self, date: str) -> pd.DataFrame:
        """获取涨停股数据"""
        date_compact = date.replace('-', '')
        if self.use_csv and self._limit_up_df is not None:
            csv_dates = self._limit_up_df['date'].astype(str).str.replace('-', '')
            zt_df = self._limit_up_df[csv_dates == date_compact].copy()
            if not zt_df.empty:
                return zt_df

        try:
            df = ak.stock_zt_pool_em(date=date_compact)
            if df.empty:
                return pd.DataFrame()
            return self._clean_limit_up_data(df)
        except Exception as e:
            print(f"获取涨停股数据失败：{e}")
            return pd.DataFrame()

    def get_break_board_stocks(self, date: str) -> pd.DataFrame:
        """获取炸板股数据"""
        if self._break_board_df is None:
            return pd.DataFrame()
        date_compact = date.replace('-', '')
        csv_dates = self._break_board_df['date'].astype(str).str.replace('-', '')
        return self._break_board_df[csv_dates == date_compact].copy()

    def _clean_limit_up_data(self, df: pd.DataFrame) -> pd.DataFrame:
        column_mapping = {
            '代码': 'code', '名称': 'name', '最新价': 'price', '涨跌幅': 'change_pct',
            '涨停统计': 'streak', '首次封板时间': 'first_board_time', '最后封板时间': 'last_board_time',
            '炸板次数': 'break_count', '涨停类型': 'board_type', '连板数': 'streak',
            '封板资金': 'seal_amount', '成交额': 'amount', '换手率': 'turnover_rate',
            '总市值': 'market_cap', '所属行业': 'sector'
        }
        required_columns = ['代码', '名称', '最新价', '涨跌幅', '连板数',
                           '首次封板时间', '最后封板时间', '炸板次数',
                           '成交额', '换手率', '总市值', '所属行业']
        available_columns = [col for col in required_columns if col in df.columns]
        df = df[available_columns]
        df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})

        if 'first_board_time' in df.columns:
            df['first_board_time_int'] = df['first_board_time'].apply(self._parse_board_time)
        if 'last_board_time' in df.columns:
            df['last_board_time_int'] = df['last_board_time'].apply(self._parse_board_time)

        for col in ['streak', 'break_count']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
        for col in ['price', 'market_cap', 'turnover_rate', 'amount']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        if 'code' in df.columns:
            df = df[df['code'].str.startswith(('60', '00'))]
        return df

    def _parse_board_time(self, time_str) -> int:
        if pd.isna(time_str):
            return 0
        try:
            time_str = str(time_str)
            if '1900-01-01' in time_str:
                time_str = time_str.replace('1900-01-01 ', '').strip()
            parts = time_str.split(':')
            if len(parts) == 3:
                return int(parts[0]) * 10000 + int(parts[1]) * 100 + int(parts[2])
            return 0
        except Exception:
            return 0

    def get_index_data(self, date: str) -> Dict:
        if self.use_csv and self._index_df is not None:
            sh_row = self._index_df[self._index_df['代码'] == '000001']
            sz_row = self._index_df[self._index_df['代码'] == '399001']
            sh_change = float(sh_row['涨跌幅'].iloc[0]) if len(sh_row) > 0 else 0.0
            sz_change = float(sz_row['涨跌幅'].iloc[0]) if len(sz_row) > 0 else 0.0
            return {'date': date, 'sh_change': sh_change, 'sz_change': sz_change,
                    'market_stable': sh_change > -2.0 and sz_change > -2.0}

        try:
            date_compact = date.replace('-', '')
            sh_df = ak.stock_zh_index_daily(symbol="sh000001")
            if not sh_df.empty:
                sh_df['prev_close'] = sh_df['close'].shift(1)
                sh_df['date_str'] = sh_df['date'].astype(str).str.replace('-', '')
                sh_row = sh_df[sh_df['date_str'] == date_compact]
                if len(sh_row) > 0 and sh_row['prev_close'].iloc[0] > 0:
                    sh_change = (float(sh_row['close'].iloc[0]) / float(sh_row['prev_close'].iloc[0]) - 1) * 100
                else:
                    sh_change = 0.0
            else:
                sh_change = 0.0
            sz_df = ak.stock_zh_index_daily(symbol="sz399001")
            if not sz_df.empty:
                sz_df['prev_close'] = sz_df['close'].shift(1)
                sz_df['date_str'] = sz_df['date'].astype(str).str.replace('-', '')
                sz_row = sz_df[sz_df['date_str'] == date_compact]
                if len(sz_row) > 0 and sz_row['prev_close'].iloc[0] > 0:
                    sz_change = (float(sz_row['close'].iloc[0]) / float(sz_row['prev_close'].iloc[0]) - 1) * 100
                else:
                    sz_change = 0.0
            else:
                sz_change = 0.0
            return {'date': date, 'sh_change': sh_change, 'sz_change': sz_change,
                    'market_stable': sh_change > -2.0 and sz_change > -2.0}
        except Exception as e:
            print(f"获取大盘指数数据失败：{e}")
            return {'date': date, 'sh_change': 0.0, 'sz_change': 0.0, 'market_stable': True}

    def get_limit_down_count(self, date: str) -> int:
        date_compact = date.replace('-', '')
        if self.use_csv and self._limit_down_df is not None:
            csv_dates = self._limit_down_df['date'].astype(str).str.replace('-', '')
            row = self._limit_down_df[csv_dates == date_compact]
            if not row.empty:
                return int(row['limit_down_count'].iloc[0])
        try:
            df = ak.stock_zt_pool_dtgc_em(date=date_compact)
            if df.empty:
                return 0
            if '代码' in df.columns:
                df = df[df['代码'].str.startswith(('60', '00'))]
            return len(df)
        except Exception as e:
            print(f"获取跌停股数据失败：{e}")
            return 0

    def get_stock_kline(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        code_clean = code.replace('sh.', '').replace('sz.', '').replace('SH', '').replace('SZ', '')
        if self.use_csv and self._kline_df is not None:
            kline = self._kline_df[self._kline_df['code'] == code_clean].copy()
            if not kline.empty:
                kline['date_str'] = kline['date'].astype(str).str.replace('-', '')
                start_clean = start_date.replace('-', '')
                end_clean = end_date.replace('-', '')
                kline = kline[(kline['date_str'] >= start_clean) & (kline['date_str'] <= end_clean)]
                if not kline.empty:
                    return kline[['date', 'open', 'close', 'high', 'low', 'volume', 'amount']]
        try:
            df = ak.stock_zh_a_hist(symbol=code_clean, period='daily',
                                    start_date=start_date, end_date=end_date, adjust='qfq')
            if df.empty:
                return pd.DataFrame()
            return df.rename(columns={'日期': 'date', '开盘': 'open', '收盘': 'close',
                                      '最高': 'high', '最低': 'low', '成交量': 'volume', '成交额': 'amount'})
        except Exception as e:
            print(f"获取股票K线数据失败：{e}")
            return pd.DataFrame()

    def analyze_sector_limit_up(self, df: pd.DataFrame) -> Dict:
        if df.empty or 'sector' not in df.columns:
            return {}
        sector_count = df['sector'].value_counts().to_dict()
        sector_max_streak = {}
        for sector in df['sector'].unique():
            sector_df = df[df['sector'] == sector]
            sector_max_streak[sector] = sector_df['streak'].max() if 'streak' in sector_df.columns else 0
        top_sector = max(sector_count.items(), key=lambda x: x[1]) if sector_count else ('', 0)
        return {
            'sector_count': sector_count,
            'sector_max_streak': sector_max_streak,
            'top_sector': top_sector[0],
            'top_sector_count': top_sector[1],
            'total_limit_up': len(df)
        }

    def get_market_stats(self, date: str) -> Dict:
        zt_df = self.get_limit_up_stocks(date)
        index_data = self.get_index_data(date)
        limit_down_count = self.get_limit_down_count(date)
        sector_analysis = self.analyze_sector_limit_up(zt_df)
        total_limit_up = len(zt_df)
        first_board_count = len(zt_df[zt_df['streak'] == 1]) if 'streak' in zt_df.columns else 0
        second_board_count = len(zt_df[zt_df['streak'] == 2]) if 'streak' in zt_df.columns else 0
        third_board_count = len(zt_df[zt_df['streak'] >= 3]) if 'streak' in zt_df.columns else 0
        max_streak = zt_df['streak'].max() if 'streak' in zt_df.columns and len(zt_df) > 0 else 0

        bb_df = self.get_break_board_stocks(date)
        if not bb_df.empty:
            zt_df = pd.concat([zt_df, bb_df], ignore_index=True)

        return {
            'date': date, 'total_limit_up': total_limit_up, 'limit_down_count': limit_down_count,
            'first_board_count': first_board_count, 'second_board_count': second_board_count,
            'third_board_count': third_board_count, 'max_streak': max_streak,
            'market_stable': index_data['market_stable'],
            'sh_change': index_data['sh_change'], 'sz_change': index_data['sz_change'],
            'sector_analysis': sector_analysis, 'zt_df': zt_df
        }