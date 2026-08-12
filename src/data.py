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
import requests
from bs4 import BeautifulSoup
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
        self._top_concept_cache = {}  # {date: (top_sectors, sector_stocks)}
        self._concept_cache = {}  # {code: [sector1, sector2, ...]} 内存持久化，避免重复加载CSV

        # 预索引加速
        self._limit_up_by_date = {}   # {YYYYMMDD: DataFrame}
        self._break_board_by_date = {}  # {YYYYMMDD: DataFrame}
        self._limit_down_by_date = {}  # {YYYYMMDD: int}
        self._kline_by_code = {}      # {code: DataFrame}

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

        # 构建日期索引
        self._build_date_index()

    def _build_date_index(self):
        """构建日期/代码索引，加速回测数据访问"""
        if self._limit_up_df is not None:
            dates = self._limit_up_df['date'].astype(str).str.replace('-', '')
            for date_compact, grp in self._limit_up_df.groupby(dates):
                self._limit_up_by_date[date_compact] = grp.copy()

        if self._break_board_df is not None:
            dates = self._break_board_df['date'].astype(str).str.replace('-', '')
            for date_compact, grp in self._break_board_df.groupby(dates):
                self._break_board_by_date[date_compact] = grp.copy()

        if self._limit_down_df is not None:
            dates = self._limit_down_df['date'].astype(str).str.replace('-', '')
            for date_compact, grp in self._limit_down_df.groupby(dates):
                self._limit_down_by_date[date_compact] = int(grp['limit_down_count'].iloc[0])

        if self._kline_df is not None:
            for code, grp in self._kline_df.groupby('code'):
                grp = grp.copy()
                grp['date_str'] = grp['date'].astype(str).str.replace('-', '')
                self._kline_by_code[code] = grp

        if self._limit_up_by_date:
            print(f"  [加速] 涨停数据索引: {len(self._limit_up_by_date)} 个交易日")
        if self._kline_by_code:
            print(f"  [加速] K线数据索引: {len(self._kline_by_code)} 只股票")

    def get_limit_up_stocks(self, date: str) -> pd.DataFrame:
        """获取涨停股数据"""
        date_compact = date.replace('-', '')
        if self.use_csv and date_compact in self._limit_up_by_date:
            zt_df = self._limit_up_by_date[date_compact].copy()
            if not zt_df.empty:
                return self._apply_concept_cache(zt_df, date)

        try:
            df = ak.stock_zt_pool_em(date=date_compact)
            if df.empty:
                return pd.DataFrame()
            self._data_source = 'akshare'
            return self._apply_concept_cache(self._clean_limit_up_data(df), date)
        except Exception as e:
            print(f"获取涨停股数据失败：{e}")
            return pd.DataFrame()

    def get_break_board_stocks(self, date: str) -> pd.DataFrame:
        """获取炸板股数据"""
        date_compact = date.replace('-', '')
        if date_compact in self._break_board_by_date:
            return self._apply_concept_cache(self._break_board_by_date[date_compact].copy(), date)
        return pd.DataFrame()

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

    def _apply_concept_cache(self, df: pd.DataFrame, date: str = '') -> pd.DataFrame:
        """用概念板块覆盖sector列

        获取涨停最多的概念板块，将涨停股归类到对应概念板块。
        如果无法获取概念板块数据，保留原始行业分类作为fallback。
        """
        if df.empty or 'code' not in df.columns:
            return df

        # 获取涨停最多的概念板块
        top_sectors, sector_stocks = self._get_top_concept_sectors(date, df)

        if not top_sectors:
            return df  # fallback: 保留原始行业分类

        df = df.copy()
        # 清空原始sector，用概念板块覆盖
        df['sector'] = ''
        # 从板块数量少的到多的逐一赋值，确保数量多的板块覆盖数量少的
        sorted_sectors = sorted(sector_stocks.items(), key=lambda x: len(x[1]))
        for sector_name, stock_codes in sorted_sectors:
            df.loc[df['code'].astype(str).isin(stock_codes), 'sector'] = sector_name

        return df

    def _get_top_concept_sectors(self, date: str, zt_df: pd.DataFrame, top_n: int = 5) -> tuple:
        """获取涨停最多的概念板块

        1. 先尝试东方财富API
        2. 失败则逐个查询涨停股的概念板块（从同花顺个股页面）

        Args:
            date: 日期，用于缓存
            zt_df: 涨停股DataFrame
            top_n: 返回前N个板块

        Returns:
            (top_sectors, sector_stocks)
            top_sectors: [(sector_name, limit_up_count), ...]
            sector_stocks: {sector_name: [code1, code2, ...]}
        """
        if zt_df.empty or 'code' not in zt_df.columns:
            return [], {}

        # 缓存检查
        cache_key = f"top_concept_{date}"
        if cache_key in self._top_concept_cache:
            return self._top_concept_cache[cache_key]

        zt_codes = list(zt_df['code'].astype(str).unique())

        # 跳过东方财富API（已失效），直接使用同花顺概念板块缓存
        try:
            result = self._stock_concept_lookup(zt_codes, top_n)
            if result[0]:
                self._top_concept_cache[cache_key] = result
                return result
        except Exception as e:
            print(f"  [WARN] 概念板块查询失败: {e}")

        return [], {}

    def _eastmoney_top_sectors(self, zt_codes: set, top_n: int = 5) -> tuple:
        """东方财富API获取涨停最多的概念板块"""
        concept_df = ak.stock_board_concept_name_em()
        hot_sectors = concept_df.sort_values('上涨家数', ascending=False).head(30)

        sector_stocks = {}
        for _, row in hot_sectors.iterrows():
            sector_name = row['板块名称']
            try:
                cons_df = ak.stock_board_concept_cons_em(symbol=sector_name)
                cons_codes = set(cons_df['代码'].astype(str).tolist())
                overlap = zt_codes & cons_codes
                if len(overlap) >= 3:
                    sector_stocks[sector_name] = list(overlap)
            except Exception:
                continue

        sorted_sectors = sorted(sector_stocks.items(), key=lambda x: len(x[1]), reverse=True)
        top_sectors = sorted_sectors[:top_n]
        result_stocks = {name: codes for name, codes in top_sectors}

        if top_sectors:
            print(f"  [概念板块] 涨停最多: {', '.join([f'{s}({len(c)}只)' for s, c in top_sectors])}")

        return top_sectors, result_stocks

    def _stock_concept_lookup(self, stock_codes: list, top_n: int = 5) -> tuple:
        """逐个查询股票的概念板块（从同花顺个股页面）

        对每只股票，访问同花顺个股页面，解析其所属概念板块。
        结果缓存到CSV避免重复请求。
        """
        # 过滤掉非概念板块（沪深港通、融资融券等）
        BLACKLIST = {'深股通', '沪股通', '融资融券', '标普道琼斯A股', 'MSCI概念',
                     '同花顺漂亮100', '同花顺中证800', '富时罗素概念', 'MSCI中国',
                     '沪深300', '中证500', '上证50', '科创50', '创业板综',
                     '同花顺出海50', '人民币贬值受益', '同花顺特色小镇'}
        cache_file = os.path.join(self.store_dir, 'stock_concept_cache.csv')
        # 加载已有缓存（仅首次加载，后续复用内存）
        if not self._concept_cache:
            if os.path.exists(cache_file):
                try:
                    df = pd.read_csv(cache_file, encoding='utf-8-sig', dtype={'code': str})
                    for _, row in df.iterrows():
                        code = str(row['code'])
                        sectors = str(row.get('concepts', ''))
                        if sectors:
                            self._concept_cache[code] = sectors.split('|')
                    print(f"    [OK] 加载概念缓存: {len(self._concept_cache)}只股票")
                except Exception:
                    pass

        concept_cache = self._concept_cache

        # 找出需要查询的股票
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        to_fetch = [c for c in stock_codes if c not in concept_cache]
        new_cache = {}

        if to_fetch:
            print(f"    [INFO] 需查询 {len(to_fetch)} 只股票的概念板块...")
            # 逐个查询（只查主板股）
            for i, code in enumerate(to_fetch):
                if not code.startswith(('60', '00')):
                    continue
                try:
                    url = f'http://basic.10jqka.com.cn/{code}/'
                    r = requests.get(url, headers=headers, timeout=10)
                    r.encoding = 'gbk'
                    soup = BeautifulSoup(r.text, 'lxml')
                    div = soup.find('div', class_='newconcept')
                    if div:
                        concepts = [a.get_text(strip=True) for a in div.find_all('a')
                                   if a.get_text(strip=True) != '详情>>'
                                   and a.get_text(strip=True) not in BLACKLIST]
                        if concepts:
                            concept_cache[code] = concepts
                            new_cache[code] = concepts
                except Exception:
                    pass
                if (i + 1) % 20 == 0:
                    print(f"    进度: {i+1}/{len(to_fetch)} 已查询 {len(new_cache)} 只")

            # 保存新查询的缓存
            if new_cache:
                new_rows = []
                for code, sectors in new_cache.items():
                    new_rows.append({'code': code, 'concepts': '|'.join(sectors)})
                new_df = pd.DataFrame(new_rows)
                if os.path.exists(cache_file):
                    old_df = pd.read_csv(cache_file, encoding='utf-8-sig', dtype={'code': str})
                    combined = pd.concat([old_df, new_df], ignore_index=True)
                    combined = combined.drop_duplicates(subset='code', keep='last')
                else:
                    combined = new_df
                combined.to_csv(cache_file, index=False, encoding='utf-8-sig')
                print(f"    [OK] 缓存已更新: {len(new_cache)} 只新股票")

        # 统计每个概念板块的涨停股数量
        sector_stocks = {}
        for code, sectors in concept_cache.items():
            if code in stock_codes:
                for sector in sectors:
                    if sector not in sector_stocks:
                        sector_stocks[sector] = []
                    sector_stocks[sector].append(code)

        # 过滤并排序
        sector_stocks = {s: list(set(c)) for s, c in sector_stocks.items() if len(set(c)) >= 3}
        sorted_sectors = sorted(sector_stocks.items(), key=lambda x: len(x[1]), reverse=True)
        top_sectors = sorted_sectors[:top_n]
        result_stocks = {name: codes for name, codes in top_sectors}

        if top_sectors:
            print(f"  [概念板块] 涨停最多: {', '.join([f'{s}({len(c)}只)' for s, c in top_sectors])}")

        return top_sectors, result_stocks

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
        if date_compact in self._limit_down_by_date:
            return self._limit_down_by_date[date_compact]
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
        if code_clean in self._kline_by_code:
            kline = self._kline_by_code[code_clean]
            start_clean = start_date.replace('-', '')
            end_clean = end_date.replace('-', '')
            kline = kline[(kline['date_str'] >= start_clean) & (kline['date_str'] <= end_clean)]
            if not kline.empty:
                return kline[['date', 'open', 'close', 'high', 'low', 'volume', 'amount']].copy()
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
        # 过滤掉空板块
        valid_df = df[df['sector'].notna() & (df['sector'] != '')].copy()
        if valid_df.empty:
            return {
                'sector_count': {},
                'sector_max_streak': {},
                'top_sector': '',
                'top_sector_count': 0,
                'total_limit_up': len(df)
            }
        sector_count = valid_df['sector'].value_counts().to_dict()
        sector_max_streak = {}
        for sector in valid_df['sector'].unique():
            sector_df = valid_df[valid_df['sector'] == sector]
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

    def precache_concept_sectors(self, stock_codes: list):
        """预缓存概念板块数据

        批量查询股票的概念板块并缓存，避免回测时逐日查询。
        Args:
            stock_codes: 股票代码列表
        """
        print(f"\n预缓存概念板块数据（共 {len(stock_codes)} 只股票）...")
        self._stock_concept_lookup(stock_codes, top_n=5)
        # 打印缓存统计
        cache_file = os.path.join(self.store_dir, 'stock_concept_cache.csv')
        if os.path.exists(cache_file):
            df = pd.read_csv(cache_file, encoding='utf-8-sig', dtype={'code': str})
            print(f"[OK] 概念板块缓存完成: {len(df)} 只股票已缓存")