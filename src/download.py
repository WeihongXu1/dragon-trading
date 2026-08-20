#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""
数据预下载脚本

功能：
1. 批量下载指定时间段的涨停股数据
2. 下载大盘指数数据
3. 下载跌停股数据
4. 保存为CSV文件供回测使用

使用方法：
python download_data.py --start_date 20260701 --end_date 20260723
python download_data.py --mode baostock --start_date 20250701 --end_date 20260701
python download_data.py --precache                                    # 仅预缓存概念板块

author: assistant
version: 20260723
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import argparse
import time
import baostock as bs

# 导入DataFetcher用于概念板块预缓存
from data import DataFetcher

# pandas 2.0+ 移除了 DataFrame.append()，Baostock 内部仍在使用，需要兼容
if not hasattr(pd.DataFrame, 'append'):
    pd.DataFrame.append = lambda self, other, ignore_index=False, sort=False, **kwargs: \
        pd.concat([self, other], ignore_index=ignore_index, sort=sort)


class DataDownloader:
    """数据下载器"""

    def __init__(self, store_dir: str):
        """
        初始化

        Args:
            store_dir: 数据存储目录
        """
        self.store_dir = store_dir
        if not os.path.exists(store_dir):
            os.makedirs(store_dir)

    def download_limit_up_data(self, date: str) -> pd.DataFrame:
        """
        下载涨停股数据

        Args:
            date: 日期，格式YYYYMMDD

        Returns:
            DataFrame: 涨停股数据
        """
        try:
            import akshare as ak
            print(f"  下载涨停股数据: {date}")
            df = ak.stock_zt_pool_em(date=date)

            if df.empty:
                print(f"  [WARN] 日期 {date} 无涨停股数据")
                return pd.DataFrame()

            # 数据清洗
            df = self._clean_limit_up_data(df)

            return df

        except Exception as e:
            print(f"  [ERR] 下载涨停股数据失败: {e}")
            return pd.DataFrame()

    def _clean_limit_up_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        清洗涨停股数据

        Args:
            df: 原始数据

        Returns:
            DataFrame: 清洗后的数据
        """
        # 重命名列
        column_mapping = {
            '代码': 'code',
            '名称': 'name',
            '最新价': 'price',
            '涨跌幅': 'change_pct',
            '连板数': 'streak',
            '首次封板时间': 'first_board_time',
            '最后封板时间': 'last_board_time',
            '炸板次数': 'break_count',
            '涨停类型': 'board_type',
            '成交额': 'amount',
            '换手率': 'turnover_rate',
            '总市值': 'market_cap',
            '所属行业': 'sector'
        }

        # 选择需要的列
        required_columns = ['代码', '名称', '最新价', '连板数',
                           '首次封板时间', '炸板次数', '成交额',
                           '换手率', '总市值', '所属行业']

        # 检查列是否存在
        available_columns = [col for col in required_columns if col in df.columns]
        df = df[available_columns]

        # 重命名
        df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})

        # 处理封板时间
        if 'first_board_time' in df.columns:
            df['first_board_time_int'] = df['first_board_time'].apply(self._parse_board_time)

        # 数据类型转换
        if 'streak' in df.columns:
            df['streak'] = pd.to_numeric(df['streak'], errors='coerce').fillna(0).astype(int)

        if 'break_count' in df.columns:
            df['break_count'] = pd.to_numeric(df['break_count'], errors='coerce').fillna(0).astype(int)

        if 'price' in df.columns:
            df['price'] = pd.to_numeric(df['price'], errors='coerce')

        if 'market_cap' in df.columns:
            df['market_cap'] = pd.to_numeric(df['market_cap'], errors='coerce')

        if 'turnover_rate' in df.columns:
            df['turnover_rate'] = pd.to_numeric(df['turnover_rate'], errors='coerce')

        if 'amount' in df.columns:
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')

        # 筛选主板股票（60、00开头）
        if 'code' in df.columns:
            df = df[df['code'].str.startswith(('60', '00'))]

        return df

    def _parse_board_time(self, time_str) -> int:
        """
        解析封板时间

        Args:
            time_str: 时间字符串

        Returns:
            int: 时间整数，如92503
        """
        if pd.isna(time_str):
            return 0

        try:
            time_str = str(time_str)

            # 处理带日期前缀的情况
            if '1900-01-01' in time_str:
                time_str = time_str.replace('1900-01-01 ', '').strip()

            # 解析时间
            parts = time_str.split(':')
            if len(parts) == 3:
                hour = int(parts[0])
                minute = int(parts[1])
                second = int(parts[2])
                return hour * 10000 + minute * 100 + second
            else:
                return 0
        except Exception:
            return 0

    def download_index_data(self) -> pd.DataFrame:
        """
        下载大盘指数数据

        Returns:
            DataFrame: 指数数据
        """
        try:
            import akshare as ak
            print("  下载大盘指数数据...")
            index_df = ak.stock_zh_index_spot()

            # 只保留上证指数和深成指
            index_df = index_df[index_df['代码'].isin(['000001', '399001'])]

            return index_df

        except Exception as e:
            print(f"  [ERR] 下载指数数据失败: {e}")
            return pd.DataFrame()

    def download_limit_down_data(self, date: str) -> int:
        """
        下载跌停股数量

        Args:
            date: 日期

        Returns:
            int: 跌停股数量
        """
        try:
            import akshare as ak
            print(f"  下载跌停股数据: {date}")
            df = ak.stock_zt_pool_dtgc_em(date=date)

            if df.empty:
                return 0

            # 筛选主板股票
            if '代码' in df.columns:
                df = df[df['代码'].str.startswith(('60', '00'))]

            return len(df)

        except Exception as e:
            print(f"  [WARN] 下载跌停股数据失败: {e}")
            return 0

    def download_all_dates(self, start_date: str, end_date: str):
        """
        批量下载指定时间段的数据

        Args:
            start_date: 开始日期
            end_date: 结束日期
        """
        print(f"\n开始下载数据: {start_date} - {end_date}")
        print("=" * 80)

        # 生成日期列表
        start = datetime.strptime(start_date, '%Y%m%d')
        end = datetime.strptime(end_date, '%Y%m%d')

        dates = []
        current = start
        while current <= end:
            if current.weekday() < 5:  # 排除周末
                dates.append(current.strftime('%Y%m%d'))
            current += timedelta(days=1)

        print(f"共需下载 {len(dates)} 个交易日的数据\n")

        # 下载每一天的数据
        all_limit_up_data = []
        all_limit_down_counts = []

        for i, date in enumerate(dates):
            print(f"[{i+1}/{len(dates)}] 处理日期: {date}")

            # 下载涨停股数据
            zt_df = self.download_limit_up_data(date)

            if not zt_df.empty:
                zt_df['date'] = date
                all_limit_up_data.append(zt_df)

            # 下载跌停股数量
            limit_down_count = self.download_limit_down_data(date)
            all_limit_down_counts.append({
                'date': date,
                'limit_down_count': limit_down_count
            })

            # 添加延时，避免请求过快
            time.sleep(0.5)

        # 保存涨停股数据
        if all_limit_up_data:
            print("\n保存涨停股数据...")
            all_zt_df = pd.concat(all_limit_up_data, ignore_index=True)
            zt_file = os.path.join(self.store_dir, f'limit_up_{start_date}_{end_date}.csv')
            all_zt_df.to_csv(zt_file, index=False, encoding='utf-8-sig')
            print(f"[OK] 涨停股数据已保存: {zt_file}")
            print(f"  共 {len(all_zt_df)} 条记录")

        # 保存跌停股数据
        if all_limit_down_counts:
            print("\n保存跌停股数据...")
            limit_down_df = pd.DataFrame(all_limit_down_counts)
            limit_down_file = os.path.join(self.store_dir, f'limit_down_{start_date}_{end_date}.csv')
            limit_down_df.to_csv(limit_down_file, index=False, encoding='utf-8-sig')
            print(f"[OK] 跌停股数据已保存: {limit_down_file}")

        # 下载并保存指数数据（只需要最后一次）
        print("\n下载指数数据...")
        index_df = self.download_index_data()
        if not index_df.empty:
            index_file = os.path.join(self.store_dir, 'index_current.csv')
            index_df.to_csv(index_file, index=False, encoding='utf-8-sig')
            print(f"[OK] 指数数据已保存: {index_file}")

        print("\n" + "=" * 80)
        print("数据下载完成！")

    def download_kline_baostock(self, start_date: str, end_date: str):
        """
        使用Baostock下载全市场K线数据（一年）

        Args:
            start_date: 开始日期，格式YYYYMMDD（如20250701）
            end_date: 结束日期，格式YYYYMMDD
        """
        print(f"\n使用Baostock下载全市场K线数据: {start_date} - {end_date}")
        print("=" * 80)

        # Baostock 需要 YYYY-MM-DD 格式
        start_fmt = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        end_fmt = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"

        bs.login()

        # 获取所有股票代码（不传day参数，返回所有股票）
        rs = bs.query_all_stock()
        all_stocks = rs.get_data()
        
        if all_stocks.empty:
            # 备选方案：使用 query_stock_basic
            print("query_all_stock 返回空，尝试 query_stock_basic...")
            rs = bs.query_stock_basic()
            all_stocks = rs.get_data()
        
        if all_stocks.empty:
            print("[ERR] 无法获取股票列表，请检查 Baostock 版本")
            bs.logout()
            return pd.DataFrame()
        
        print(f"Baostock返回列名: {list(all_stocks.columns)}")
        print(f"Baostock返回记录数: {len(all_stocks)}")
        
        # 兼容不同版本的Baostock列名
        col_map = {col.lower(): col for col in all_stocks.columns}
        code_col = col_map.get('code', all_stocks.columns[0])
        name_col = col_map.get('code_name', all_stocks.columns[1] if len(all_stocks.columns) > 1 else all_stocks.columns[0])
        
        # 筛选主板股票（sh.60xxxx, sz.00xxxx）
        codes = all_stocks[code_col].astype(str)
        main_board = all_stocks[codes.str.match(r'(sh\.60|sz\.00)')].copy()
        main_board = main_board.reset_index(drop=True)
        main_board.rename(columns={code_col: 'code', name_col: 'code_name'}, inplace=True)
        print(f"共 {len(main_board)} 只主板股票，预计需要 30-60 分钟\n")

        all_kline = []
        error_count = 0
        total = len(main_board)

        for i, (_, stock) in enumerate(main_board.iterrows()):
            code = stock['code']
            code_name = stock['code_name']
            short_code = code.replace('sh.', '').replace('sz.', '')

            try:
                rs = bs.query_history_k_data_plus(
                    code,
                    "date,open,high,low,close,preclose,volume,amount,turn,tradestatus,isST",
                    start_date=start_fmt, end_date=end_fmt,
                    frequency="d", adjustflag="3"
                )
                data = rs.get_data()
                if not data.empty:
                    data['code'] = short_code
                    data['name'] = code_name
                    all_kline.append(data)
            except Exception:
                error_count += 1

            if (i + 1) % 200 == 0:
                print(f"  进度: {i+1}/{total} ({100*(i+1)//total}%)  "
                      f"已收集 {len(all_kline)} 只有效股票")

        bs.logout()

        if all_kline:
            combined = pd.concat(all_kline, ignore_index=True)
            kline_file = os.path.join(self.store_dir, f'all_kline_{start_date}_{end_date}.csv')
            combined.to_csv(kline_file, index=False, encoding='utf-8-sig')
            print(f"\n[OK] K线数据已保存: {kline_file}")
            print(f"  共 {len(combined)} 条记录, {error_count} 只股票下载失败")
            return combined
        else:
            print("\n[ERR] 未下载到任何K线数据")
            return pd.DataFrame()

    def download_stock_info(self, kline_df=None):
        """
        下载股票基本信息（概念板块、市值）
        使用同花顺获取概念板块，缓存到CSV

        Returns:
            tuple: (sector_map: dict, cap_map: dict)
        """
        info_file = os.path.join(self.store_dir, 'stock_sector_cap.csv')
        if os.path.exists(info_file):
            # 检查文件是否有效（非空）
            try:
                df = pd.read_csv(info_file, encoding='utf-8-sig', dtype={'code': str})
                if df.empty:
                    print(f"[WARN] 缓存文件为空，重新下载")
                    os.remove(info_file)
                else:
                    print(f"[OK] 股票信息已缓存: {info_file}")
                    sector_map = {}
                    cap_map = {}
                    for _, row in df.iterrows():
                        code = str(row['code'])
                        sector_map[code] = str(row.get('sector', ''))
                        cap_map[code] = float(row.get('market_cap', 0))
                    print(f"  已加载 {len(sector_map)} 只股票的行业/市值信息")
                    return sector_map, cap_map
            except pd.errors.EmptyDataError:
                print(f"[WARN] 缓存文件无效，重新下载")
                if os.path.exists(info_file):
                    os.remove(info_file)

        print("\n下载股票行业和市值信息...")
        print("=" * 80)

        sector_map = {}
        cap_map = {}

        # 1. 获取行业分类（Baostock行业分类）
        print("  获取行业分类（Baostock）...")
        try:
            lg = bs.login()
            print(f'    Baostock登录: error_code="{lg.error_code}" error_msg="{lg.error_msg}"')

            # 查询股票行业分类
            rs = bs.query_stock_industry()
            print(f'    查询行业分类: error_code="{rs.error_code}" error_msg="{rs.error_msg}"')

            industry_list = []
            while (rs.error_code == '0') & rs.next():
                industry_list.append(rs.get_row_data())

            industry_df = pd.DataFrame(industry_list)
            if not industry_df.empty:
                print(f'    Baostock行业分类列名: {list(industry_df.columns)}')
                print(f'    共 {len(industry_df)} 条记录')

                # 兼容不同版本的列名
                code_col = 'code' if 'code' in industry_df.columns else industry_df.columns[0]
                industry_col = 'industry' if 'industry' in industry_df.columns else industry_df.columns[1]

                for _, row in industry_df.iterrows():
                    code = str(row[code_col]).replace('sh.', '').replace('sz.', '')
                    industry = str(row[industry_col])
                    if code.startswith(('60', '00')):
                        sector_map[code] = industry
                print(f"    已提取 {len(sector_map)} 只主板股票的行业信息")
            else:
                print(f"    [WARN] Baostock行业分类数据为空")
        except Exception as e:
            print(f"    [WARN] 获取行业分类失败: {e}")
        finally:
            bs.logout()

        # 2. 获取市值（从K线数据推算）
        print("  计算市值信息（从K线数据）...")
        try:
            # 从K线数据中推算市值
            # 市值 ≈ 成交额 / 换手率
            # 注意：kline_df 的 code 已是纯数字格式（如 000725），无 sh./sz. 前缀
            latest_kline = kline_df.sort_values('date').groupby('code').last().reset_index()
            for _, row in latest_kline.iterrows():
                code = str(row['code'])
                # 只处理主板股票（60/00开头）
                if code.startswith('60') or code.startswith('00'):
                    turn = float(row.get('turn', 0))
                    amount = float(row.get('amount', 0))
                    if turn > 0:
                        # 市值 ≈ 成交额 / 换手率
                        market_cap = amount / turn * 100  # 单位：亿元
                        cap_map[code] = market_cap
            print(f"  市值信息: {len(cap_map)} 只股票")
        except Exception as e:
            print(f"  [WARN] 计算市值失败: {e}")

        # 合并保存
        all_codes = set(list(sector_map.keys()) + list(cap_map.keys()))
        records = []
        for code in all_codes:
            records.append({
                'code': code,
                'sector': sector_map.get(code, ''),
                'market_cap': cap_map.get(code, 0)
            })
        info_df = pd.DataFrame(records)
        info_df.to_csv(info_file, index=False, encoding='utf-8-sig')
        print(f"[OK] 股票信息已保存: {info_file} ({len(records)} 条)")
        return sector_map, cap_map

    def build_limit_up_from_kline(self, start_date: str, end_date: str):
        """
        从Baostock K线数据计算涨停股，生成与akshare格式一致的涨停CSV

        Args:
            start_date: 开始日期
            end_date: 结束日期
        """
        kline_file = os.path.join(self.store_dir, f'all_kline_{start_date}_{end_date}.csv')

        if not os.path.exists(kline_file):
            print(f"[ERR] K线文件不存在: {kline_file}")
            print("   请先运行 download_kline_baostock")
            return

        print(f"\n从K线数据计算涨停股...")
        print(f"加载K线数据: {kline_file}")
        kline_df = pd.read_csv(kline_file, encoding='utf-8-sig', dtype={'code': str})
        print(f"  共 {len(kline_df)} 条K线记录")

        # 数据类型转换
        for col in ['open', 'high', 'low', 'close', 'preclose', 'turn']:
            if col in kline_df.columns:
                kline_df[col] = pd.to_numeric(kline_df[col], errors='coerce')

        # 计算涨跌幅
        kline_df['pct_chg'] = (kline_df['close'] / kline_df['preclose'] - 1) * 100

        # 判断涨停：非ST≈9.9%以上，ST≈4.9%以上
        kline_df['isST'] = kline_df.get('isST', '0')
        kline_df['is_limit_up'] = kline_df.apply(
            lambda r: r['pct_chg'] >= 4.9 if r['isST'] == '1' else r['pct_chg'] >= 9.9,
            axis=1
        )

        # 只保留涨停记录
        zt_all = kline_df[kline_df['is_limit_up']].copy()
        print(f"  涨停记录: {len(zt_all)} 条")

        if zt_all.empty:
            print("[WARN] 未找到任何涨停记录")
            return

        # 提取交易日历（从所有K线数据中）
        all_dates = sorted(kline_df['date'].unique())
        trading_dates = set(all_dates)
        print(f"  交易日历: {len(trading_dates)} 个交易日")

        # 计算连板数（streak）
        zt_all = zt_all.sort_values(['code', 'date']).reset_index(drop=True)
        zt_all['streak'] = 1
        for code in zt_all['code'].unique():
            code_mask = zt_all['code'] == code
            code_idx = zt_all[code_mask].index
            if len(code_idx) > 1:
                prev_date = None
                streak = 1
                for idx in code_idx:
                    curr_date = zt_all.loc[idx, 'date']
                    if prev_date is not None:
                        # 检查中间是否有交易日（未涨停的交易日）
                        prev_dt = datetime.strptime(prev_date, '%Y-%m-%d')
                        curr_dt = datetime.strptime(curr_date, '%Y-%m-%d')
                        # 找出两个涨停日期之间的所有日期
                        check_date = prev_dt + timedelta(days=1)
                        has_trading_day_between = False
                        while check_date < curr_dt:
                            check_str = check_date.strftime('%Y-%m-%d')
                            if check_str in trading_dates:
                                # 中间有交易日，但股票没有涨停，连板中断
                                has_trading_day_between = True
                                break
                            check_date += timedelta(days=1)
                        
                        if has_trading_day_between:
                            streak = 1  # 重置为1板
                        else:
                            streak += 1  # 继续连板
                    zt_all.loc[idx, 'streak'] = streak
                    prev_date = curr_date

        # 判断涨停类型（一字板 vs 换手板）
        zt_all['board_type'] = zt_all.apply(
            lambda r: '一字板' if (r['open'] == r['high'] == r['low'] == r['close'] and r['turn'] < 1)
            else '换手板',
            axis=1
        )

        # 获取概念板块和市值信息
        sector_map, cap_map = self.download_stock_info(kline_df)

        print(f"  概念板块映射: {len(sector_map)} 只股票")
        print(f"  市值数据: {len(cap_map)} 只股票")

        # 构建输出DataFrame（与akshare涨停池格式对齐）
        records = []
        for _, row in zt_all.iterrows():
            code = row['code']
            records.append({
                'code': code,
                'name': row.get('name', ''),
                'price': row['close'],
                'change_pct': round(row['pct_chg'], 2),
                'streak': int(row['streak']),
                'first_board_time': '09:30:00',  # K线无法获取精确封板时间
                'first_board_time_int': 93000,
                'last_board_time': '15:00:00',
                'last_board_time_int': 150000,
                'break_count': 0,  # K线无法获取炸板次数
                'board_type': row['board_type'],
                'amount': row.get('amount', 0),
                'turnover_rate': float(row.get('turn', 0)),
                'market_cap': cap_map.get(code, 0),
                'sector': sector_map.get(code, ''),
                'date': row['date'],
            })

        result_df = pd.DataFrame(records)

        # 保存
        output_file = os.path.join(self.store_dir, f'limit_up_baostock_{start_date}_{end_date}.csv')
        result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\n[OK] 涨停数据已生成: {output_file}")
        print(f"  共 {len(result_df)} 条记录")

        # 统计
        date_counts = result_df.groupby('date').size()
        print(f"  覆盖 {len(date_counts)} 个交易日")
        print(f"  日均涨停 {date_counts.mean():.0f} 只")

        # 同时生成跌停数据
        self._build_limit_down_from_kline(kline_df, start_date, end_date)

        # 生成炸板数据（触及涨停但未封住）
        self._build_break_board_from_kline(kline_df, start_date, end_date)

        return result_df

    def _build_limit_down_from_kline(self, kline_df: pd.DataFrame, start_date: str, end_date: str):
        """从K线数据计算跌停股数量"""
        print("\n从K线数据计算跌停股...")

        kline_df = kline_df.copy()
        for col in ['open', 'high', 'low', 'close', 'preclose']:
            if col in kline_df.columns:
                kline_df[col] = pd.to_numeric(kline_df[col], errors='coerce')

        kline_df['pct_chg'] = (kline_df['close'] / kline_df['preclose'] - 1) * 100
        kline_df['isST'] = kline_df.get('isST', '0')
        kline_df['is_limit_down'] = kline_df.apply(
            lambda r: r['pct_chg'] <= -4.9 if r['isST'] == '1' else r['pct_chg'] <= -9.9,
            axis=1
        )

        dt_all = kline_df[kline_df['is_limit_down']]
        dt_counts = dt_all.groupby('date').size().reset_index(name='limit_down_count')

        dt_file = os.path.join(self.store_dir, f'limit_down_baostock_{start_date}_{end_date}.csv')
        dt_counts.to_csv(dt_file, index=False, encoding='utf-8-sig')
        print(f"[OK] 跌停数据已生成: {dt_file}")
        print(f"  共 {len(dt_counts)} 个交易日，总跌停 {dt_counts['limit_down_count'].sum()} 次")

    def _build_break_board_from_kline(self, kline_df: pd.DataFrame, start_date: str, end_date: str):
        """从K线数据计算炸板股（触及涨停价但收盘未封住）"""
        print("\n从K线数据计算炸板股...")

        kline_df = kline_df.copy()
        for col in ['open', 'high', 'low', 'close', 'preclose', 'turn']:
            if col in kline_df.columns:
                kline_df[col] = pd.to_numeric(kline_df[col], errors='coerce')

        # 计算涨停价
        kline_df['isST'] = kline_df.get('isST', '0')
        kline_df['limit_up_price'] = kline_df.apply(
            lambda r: round(r['preclose'] * 1.05, 2) if r['isST'] == '1' else round(r['preclose'] * 1.10, 2),
            axis=1
        )

        # 炸板条件：当日最高价触及涨停价，但收盘价低于涨停价
        kline_df['is_break_board'] = (
            (kline_df['high'] >= kline_df['limit_up_price']) &
            (kline_df['close'] < kline_df['limit_up_price'])
        )

        bb_all = kline_df[kline_df['is_break_board']].copy()
        print(f"  炸板记录: {len(bb_all)} 条")

        if bb_all.empty:
            print("[WARN] 未找到任何炸板记录")
            return

        # 获取概念板块和市值信息
        sector_map, cap_map = self.download_stock_info(kline_df)

        # 计算连板数（基于涨停数据，炸板当天也算连板延续）
        # 先加载已生成的涨停数据来计算streak
        zt_file = os.path.join(self.store_dir, f'limit_up_baostock_{start_date}_{end_date}.csv')
        zt_all = pd.DataFrame()
        if os.path.exists(zt_file):
            zt_all = pd.read_csv(zt_file, encoding='utf-8-sig', dtype={'code': str})
            if 'date' in zt_all.columns:
                zt_all['date'] = zt_all['date'].astype(str)

        # 构建输出
        records = []
        for _, row in bb_all.iterrows():
            code = row['code']
            date_str = str(row['date'])

            # 计算连板：从涨停数据中查找该股票前一天的streak
            streak = 1
            if not zt_all.empty and 'code' in zt_all.columns and 'date' in zt_all.columns:
                prev_date = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
                prev_zt = zt_all[(zt_all['code'] == code) & (zt_all['date'] == prev_date)]
                if not prev_zt.empty and 'streak' in prev_zt.columns:
                    streak = int(prev_zt['streak'].values[0]) + 1

            records.append({
                'code': code,
                'name': row.get('name', ''),
                'price': row['limit_up_price'],  # 买入价按涨停价
                'close_price': row['close'],      # 实际收盘价
                'change_pct': round((row['close'] / row['preclose'] - 1) * 100, 2),
                'streak': streak,
                'first_board_time': '09:30:00',
                'first_board_time_int': 93000,
                'last_board_time': '15:00:00',
                'last_board_time_int': 150000,
                'break_count': 1,
                'board_type': '炸板',
                'amount': row.get('amount', 0),
                'turnover_rate': float(row.get('turn', 0)),
                'market_cap': cap_map.get(code, 0),
                'sector': sector_map.get(code, ''),
                'date': date_str,
            })

        result_df = pd.DataFrame(records)

        # 保存
        output_file = os.path.join(self.store_dir, f'break_board_baostock_{start_date}_{end_date}.csv')
        result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\n[OK] 炸板数据已生成: {output_file}")
        print(f"  共 {len(result_df)} 条记录")

    def precache_concept_sectors(self):
        """预缓存概念板块数据

        扫描所有涨停CSV文件，提取唯一股票代码，
        批量查询概念板块并缓存，避免回测时逐日查询。
        """
        print("\n预缓存概念板块数据...")
        print("=" * 80)

        # 扫描所有涨停CSV
        all_codes = set()
        csv_files = [f for f in os.listdir(self.store_dir)
                     if f.startswith('limit_up_') and f.endswith('.csv')]
        for fname in csv_files:
            fpath = os.path.join(self.store_dir, fname)
            try:
                df = pd.read_csv(fpath, encoding='utf-8-sig', dtype={'code': str})
                codes = df['code'].dropna().unique()
                all_codes.update(codes)
            except Exception as e:
                print(f"  [WARN] 读取 {fname} 失败: {e}")

        # 只保留主板股票
        all_codes = [c for c in all_codes if str(c).startswith(('60', '00'))]
        print(f"  从 {len(csv_files)} 个CSV提取 {len(all_codes)} 只主板股票")

        if not all_codes:
            print("[WARN] 未找到任何股票代码")
            return

        # 用DataFetcher查询概念板块
        fetcher = DataFetcher(store_dir=self.store_dir, use_csv=False)
        fetcher.precache_concept_sectors(all_codes)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='下载超短策略所需数据')
    parser.add_argument('--start_date', type=str, default='20250724', help='开始日期，格式YYYYMMDD')
    parser.add_argument('--end_date', type=str, default='20260724', help='结束日期，格式YYYYMMDD')
    parser.add_argument('--store_dir', type=str,
                       default='e:\\Quantitative_trading\\DragonTrading\\data\\store',
                       help='数据存储目录')
    parser.add_argument('--mode', type=str, default=None,
                       choices=['akshare', 'baostock', 'both'],
                       help='数据源模式: akshare(近1月涨停池), baostock(K线计算涨停), both(全部下载)')
    parser.add_argument('--precache', action='store_true',
                       help='预缓存概念板块数据（可单独使用，也可搭配下载）')

    args = parser.parse_args()

    downloader = DataDownloader(args.store_dir)

    # 预缓存概念板块（单独使用）
    if args.precache and not args.mode:
        downloader.precache_concept_sectors()
        return

    # 下载数据
    if args.mode == 'baostock':
        # Baostock模式：下载K线 → 计算涨停
        downloader.download_kline_baostock(args.start_date, args.end_date)
        downloader.build_limit_up_from_kline(args.start_date, args.end_date)
    elif args.mode == 'both':
        # 两种都下载
        downloader.download_all_dates(args.start_date, args.end_date)
        downloader.download_kline_baostock(args.start_date, args.end_date)
        downloader.build_limit_up_from_kline(args.start_date, args.end_date)
    else:
        # akshare模式（原有逻辑）
        downloader.download_all_dates(args.start_date, args.end_date)

    # 预缓存概念板块
    if args.precache:
        downloader.precache_concept_sectors()


if __name__ == '__main__':
    main()