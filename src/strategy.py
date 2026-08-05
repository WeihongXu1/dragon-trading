#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""
策略层 - 龙头追踪 + 市场阶段判定 + 股票筛选

核心逻辑：
- 情绪周期围绕龙头展开：试错期 → 主升期(龙头确认) → 高位震荡期(龙头断板) → 退潮期
- 龙头确认需要3板 + 板块效应(≥3只涨停)
- 龙头回撤≥15% 触发退潮期
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import pandas as pd


@dataclass
class DragonState:
    """龙头追踪状态"""
    stock: Optional[str] = None         # 龙头股代码
    streak: int = 0                     # 连板数
    sector: Optional[str] = None        # 龙头所在板块
    broken: bool = False                # 是否已断板
    break_days: int = 0                 # 断板天数
    peak_price: float = 0.0             # 龙头最高价
    


class DragonTracker:
    """龙头追踪器 + 市场阶段判定 + 股票筛选"""

    # ---------- 参数 ----------
    # 退潮判定
    LIMIT_DOWN_THRESHOLD = 15
    DRAGON_RETREAT_PCT = 0.15
    # 情绪冰点
    EMOTION_FREEZE_LIMIT_UP = 20
    # 板块效应
    SECTOR_EFFECT_MIN = 3
    # 筛选
    TRIAL_MAX_PRICE = 20
    MAIN_MAX_PRICE = 30
    MAX_MARKET_CAP = 30_000_000_000
    MIN_MARKET_CAP = 3_000_000_000   # 最小市值30亿（低于此不买）
    MIN_BOARD_TIME = 93500   # 封板时间下限（9:35）
    MAX_BOARD_TIME = 103000  # 封板时间上限（10:30）
    MAX_OPEN_CHANGE = 7.0    # 最低价涨幅上限（最低价涨幅>7%不买）
    AKSHARE_MIN_TURNOVER = 1.0   # akshare数据最小换手率
    BAOSTOCK_MIN_TURNOVER = 3.0  # Baostock数据最小换手率（提高门槛）
    MIN_TURNOVER_RATE = 5.0  # 最小换手率（低于5%不买，不管涨停还是炸板）

    def __init__(self):
        self.dragon = DragonState()
        self.current_phase = '低位试错期'
        self.dragon_candidates: List[Dict] = []  # 龙头预选池（前一日的二板股）

    # ========================
    # 龙头状态管理
    # ========================

    def clear_dragon(self):
        """清空龙头（退潮期使用）"""
        self.dragon = DragonState()

    def break_dragon(self):
        """标记龙头断板（高位震荡期使用）"""
        self.dragon.broken = True
        self.dragon.break_days = 1

    def is_dragon_limit_down(self, market_stats: Dict) -> bool:
        """检查龙头是否跌停"""
        if not self.dragon.stock:
            return False
        dt_df = market_stats.get('dt_df', pd.DataFrame())
        if dt_df.empty or 'code' not in dt_df.columns:
            return False
        return self.dragon.stock in dt_df['code'].values

    def get_dragon_price(self, fetcher, date: str) -> float:
        """获取龙头当前中间价（用于判断回撤）"""
        if not self.dragon.stock:
            return 0.0
        try:
            kline = fetcher.get_stock_kline(self.dragon.stock, date, date)
            if not kline.empty:
                return (kline.iloc[-1]['high'] + kline.iloc[-1]['low']) / 2
        except Exception:
            pass
        return 0.0

    # ========================
    # 情绪周期判定
    # ========================

    def determine_phase(self, market_stats: Dict, fetcher, date: str = '') -> str:
        """判断市场阶段（龙头锚定版）

        状态流转：
        低位试错期 → 预选龙头 → 主升期（龙头确认）→ 高位震荡期（龙头断板）→ 退潮期（龙头跌停）

        龙头预选逻辑：
        - T-1：预选二板股（有板块效应）
        - T：检查预选股是否三板 → 打板买入，确认龙头
        """
        total_limit_up = market_stats.get('total_limit_up', 0)
        limit_down_count = market_stats.get('limit_down_count', 0)
        first_board_count = market_stats.get('first_board_count', 0)
        second_board_count = market_stats.get('second_board_count', 0)
        third_board_count = market_stats.get('third_board_count', 0)
        max_streak = market_stats.get('max_streak', 0)
        market_stable = market_stats.get('market_stable', True)
        sector_analysis = market_stats.get('sector_analysis', {})
        zt_df = market_stats.get('zt_df', pd.DataFrame())

        # 优先级1：退潮期（大盘崩盘或跌停潮）
        if limit_down_count > self.LIMIT_DOWN_THRESHOLD or not market_stable:
            self.clear_dragon()
            self.dragon_candidates = []  # 清空预选池
            return '退潮期'

        # 优先级2：龙头追踪（已确认龙头的情况下）
        if self.dragon.stock:
            # 龙头跌停 → 退潮期
            if self.is_dragon_limit_down(market_stats):
                print(f"    龙头 {self.dragon.stock} 跌停 → 退潮期")
                self.clear_dragon()
                return '退潮期'

            # 检查龙头今日是否涨停
            dragon_today = zt_df[(zt_df['code'] == self.dragon.stock) & (zt_df['board_type'] != '炸板')] \
                if not zt_df.empty and 'code' in zt_df.columns else pd.DataFrame()

            if len(dragon_today) == 0:
                # 龙头不在涨停列表 → 断板
                # 如果龙头连板数<5，直接判断跌停数量决定进入退潮期或低位试错期
                if self.dragon.streak < 5:
                    if limit_down_count > self.LIMIT_DOWN_THRESHOLD:
                        print(f"    龙头 {self.dragon.stock} 仅{self.dragon.streak}板断板，跌停{limit_down_count}只 → 退潮期")
                        self.clear_dragon()
                        return '退潮期'
                    else:
                        print(f"    龙头 {self.dragon.stock} 仅{self.dragon.streak}板断板，跌停{limit_down_count}只 → 低位试错期")
                        self.clear_dragon()
                        return '低位试错期'

                # 龙头连板数>=5，进入高位震荡期
                if not self.dragon.broken:
                    print(f"    龙头 {self.dragon.stock} 断板 → 高位震荡期（断板第1天）")
                    self.break_dragon()
                else:
                    self.dragon.break_days += 1
                    print(f"    龙头 {self.dragon.stock} 断板第{self.dragon.break_days}天 → 高位震荡期")

                # 检查龙头回撤是否≥15%
                current_price = self.get_dragon_price(fetcher, date)
                if self.dragon.peak_price > 0 and current_price > 0:
                    drop_pct = (self.dragon.peak_price - current_price) / self.dragon.peak_price
                    if drop_pct >= self.DRAGON_RETREAT_PCT:
                        print(f"    龙头 {self.dragon.stock} 从高点{self.dragon.peak_price:.2f}回撤{drop_pct*100:.1f}% → 退潮期")
                        self.clear_dragon()
                        return '退潮期'

                return '高位震荡期'
            else:
                # 龙头还在涨停
                if self.dragon.broken:
                    # 龙头断板后即使反包也不买回，继续高位震荡期
                    print(f"    龙头 {self.dragon.stock} 断板后反包，不买回，继续高位震荡期")
                    return '高位震荡期'
                else:
                    # 主升期正常追踪，更新最高价
                    dragon_price = float(dragon_today.iloc[0].get('price', 0))
                    if dragon_price > self.dragon.peak_price:
                        self.dragon.peak_price = dragon_price
                    self.dragon.streak = int(dragon_today.iloc[0].get('streak', self.dragon.streak))
                    return '主升期'

        # 优先级3：打板情绪冰点 → 强制低位试错期
        is_emotion_freeze = (
            total_limit_up < self.EMOTION_FREEZE_LIMIT_UP or
            (max_streak <= 2 and limit_down_count > total_limit_up * 0.5)
        )
        if is_emotion_freeze and market_stable:
            print(f"    打板情绪冰点（涨停{total_limit_up}只，最高连板{max_streak}，跌停{limit_down_count}只）→ 强制低位试错期")
            self.dragon_candidates = []  # 清空预选池
            return '低位试错期'

        # 优先级4：默认低位试错期
        return '低位试错期'

    def preselect_dragons(self, zt_df: pd.DataFrame, sector_analysis: Dict) -> List[Dict]:
        """预选龙头候选

        包括两部分：
        1. 二板股（有板块效应）→ 跟踪龙头诞生
        2. 高板股（≥3板，有板块效应）→ 发现已有龙头
        """
        if zt_df.empty or 'streak' not in zt_df.columns:
            return []

        candidates = []

        # 1. 找高板股（≥3板，有板块效应）
        high_board_df = zt_df[zt_df['streak'] >= 3].copy()
        if not high_board_df.empty and 'board_type' in high_board_df.columns:
            # 过滤一字板（盘中买不到），炸板也算候选
            high_board_df = high_board_df[~high_board_df['board_type'].str.contains('一字', na=False)]
            # 过滤换手率
            if 'turnover_rate' in high_board_df.columns:
                high_board_df = high_board_df[high_board_df['turnover_rate'] >= self.MIN_TURNOVER_RATE]

            if not high_board_df.empty and 'sector' in high_board_df.columns and sector_analysis:
                sector_counts = sector_analysis.get('sector_count', {})
                # 找有板块效应的板块
                valid_sectors = [s for s, c in sector_counts.items() if c >= self.SECTOR_EFFECT_MIN]

                for sector in valid_sectors:
                    sector_high = high_board_df[high_board_df['sector'] == sector]
                    for _, row in sector_high.iterrows():
                        if 'price' in row and row['price'] >= self.MAIN_MAX_PRICE:
                            continue
                        candidates.append({
                            'code': row['code'],
                            'name': row.get('name', ''),
                            'sector': sector,
                            'price': row.get('price', 0),
                            'streak': row['streak'],
                            'is_high_board': True  # 标记为高板股
                        })

        # 2. 找二板股（有板块效应）
        s2_df = zt_df[zt_df['streak'] == 2].copy()
        if not s2_df.empty:
            # 过滤一字板（盘中买不到），炸板也算候选
            if 'board_type' in s2_df.columns:
                s2_df = s2_df[~s2_df['board_type'].str.contains('一字', na=False)]
            # 过滤换手率
            if 'turnover_rate' in s2_df.columns:
                s2_df = s2_df[s2_df['turnover_rate'] >= self.MIN_TURNOVER_RATE]

            if not s2_df.empty and 'sector' in s2_df.columns and sector_analysis:
                sector_counts = sector_analysis.get('sector_count', {})
                # 找有板块效应的板块
                valid_sectors = [s for s, c in sector_counts.items() if c >= self.SECTOR_EFFECT_MIN]

                for sector in valid_sectors:
                    sector_s2 = s2_df[s2_df['sector'] == sector]
                    for _, row in sector_s2.iterrows():
                        if 'price' in row and row['price'] >= self.MAIN_MAX_PRICE:
                            continue
                        candidates.append({
                            'code': row['code'],
                            'name': row.get('name', ''),
                            'sector': sector,
                            'price': row.get('price', 0),
                            'streak': 2,
                            'is_high_board': False  # 标记为二板股
                        })

        # 按连板数排序（高板股优先）
        candidates.sort(key=lambda x: x.get('streak', 0), reverse=True)

        return candidates

    def check_candidates_confirm(self, zt_df: pd.DataFrame) -> Optional[Dict]:
        """检查预选股是否成功三板"""
        if zt_df.empty or 'code' not in zt_df.columns:
            return None

        for candidate in self.dragon_candidates:
            code = candidate['code']
            # 检查是否三板（涨停且非炸板）
            stock = zt_df[(zt_df['code'] == code) & (zt_df['board_type'] != '炸板')]
            if not stock.empty and 'streak' in stock.columns:
                streak = stock.iloc[0]['streak']
                if streak >= 3:
                    # 成功三板，返回确认信息
                    result = candidate.copy()
                    result['price'] = float(stock.iloc[0].get('price', candidate.get('price', 0)))
                    return result
        return None

    # ========================
    # 股票筛选
    # ========================

    def filter_buy_stocks(self, zt_df: pd.DataFrame, phase: str, is_baostock: bool = False,
                          fetcher=None, date: str = '', sector_analysis: Dict = None) -> pd.DataFrame:
        """筛选买入股票（所有阶段统一过滤）

        Args:
            zt_df: 涨停股数据
            phase: 市场阶段
            is_baostock: 是否Baostock数据
            fetcher: 数据获取器（用于检查开盘涨幅）
            date: 日期（用于检查开盘涨幅）
        """
        if zt_df.empty:
            return pd.DataFrame()

        df = zt_df.copy()

        # 通用过滤
        if 'name' in df.columns:
            df = df[~df['name'].str.contains('ST|退', na=False, case=False)]
        if 'board_type' in df.columns:
            df = df[~df['board_type'].str.contains('一字', na=False)]
        # 换手率过滤：低于MIN_TURNOVER_RATE的不买
        if 'turnover_rate' in df.columns:
            df = df[df['turnover_rate'] >= self.MIN_TURNOVER_RATE]

        # 开盘涨幅过滤（最低价涨幅>7%不买，风险大）
        # 但主升期买龙头时不限制，龙头可能高开很多
        if fetcher and date and 'price' in df.columns and phase != '主升期':
            filtered_codes = []
            for idx, row in df.iterrows():
                code = row['code']
                limit_price = row['price']  # 涨停价
                try:
                    kline = fetcher.get_stock_kline(code, date, date)
                    if not kline.empty and 'low' in kline.columns:
                        low_price = float(kline.iloc[-1]['low'])
                        # 昨收价 ≈ 涨停价 / 1.1
                        preclose = limit_price / 1.1
                        low_change = (low_price - preclose) / preclose * 100
                        if low_change <= self.MAX_OPEN_CHANGE:
                            filtered_codes.append(code)
                except Exception:
                    filtered_codes.append(code)  # 获取失败则保留
            df = df[df['code'].isin(filtered_codes)]

        # 阶段特定过滤
        if phase == '主升期':
            if self.dragon.stock and 'code' in df.columns:
                df = df[df['code'] == self.dragon.stock]
                if 'price' in df.columns:
                    df = df[df['price'] < self.MAIN_MAX_PRICE]
                if 'market_cap' in df.columns:
                    df = df[(df['market_cap'] >= self.MIN_MARKET_CAP) & (df['market_cap'] < self.MAX_MARKET_CAP)]
                return df
            return pd.DataFrame()

        if 'price' in df.columns:
            df = df[df['price'] < self.TRIAL_MAX_PRICE]
        if 'market_cap' in df.columns:
            df = df[(df['market_cap'] >= self.MIN_MARKET_CAP) & (df['market_cap'] < self.MAX_MARKET_CAP)]
        if 'first_board_time_int' in df.columns and not is_baostock:
            df = df[df['first_board_time_int'] >= self.MIN_BOARD_TIME]
            df = df[df['first_board_time_int'] <= self.MAX_BOARD_TIME]

        if phase in ('低位试错期', '高位震荡期'):
            if 'streak' in df.columns:
                df = df[df['streak'] == 2]
        
        # 高位震荡期：断板当天不能买一进二
        if phase == '高位震荡期' and self.dragon.break_days == 1:
            print(f"    龙头断板第1天，禁止买入")
            return pd.DataFrame()  # 返回空DataFrame

        # 一进二优先买有板块效应的
        if phase in ('低位试错期', '高位震荡期') and sector_analysis and 'sector' in df.columns:
            sector_counts = sector_analysis.get('sector_count', {})
            if sector_counts:
                has_effect = df['sector'].map(lambda s: sector_counts.get(s, 0) >= self.SECTOR_EFFECT_MIN)
                sector_df = df[has_effect].sample(frac=1.0, random_state=None)
                no_sector_df = df[~has_effect].sample(frac=1.0, random_state=None)
                df = pd.concat([sector_df, no_sector_df], ignore_index=True)
                print(f"    一进二候选：有板块效应{len(sector_df)}只，无板块效应{len(no_sector_df)}只")
            else:
                df = df.sample(frac=1.0, random_state=None).reset_index(drop=True)
        else:
            # 模拟实盘随机买入（无法预知哪只股会炸板）
            df = df.sample(frac=1.0, random_state=None).reset_index(drop=True)

        return df

    def filter_dragon_candidate(self, zt_df: pd.DataFrame, candidate: Dict) -> pd.DataFrame:
        """筛选预选股是否可买（三板时打板买入）

        Args:
            zt_df: 当天的涨停数据
            candidate: 预选的龙头候选

        Returns:
            如果可买，返回包含该股票的DataFrame；否则返回空DataFrame
        """
        if zt_df.empty or 'code' not in zt_df.columns:
            return pd.DataFrame()

        # 检查预选股是否在涨停列表中（炸板也算，盘中不知道会炸板）
        code = candidate['code']
        stock = zt_df[zt_df['code'] == code]

        if stock.empty:
            return pd.DataFrame()

        # 检查是否三板
        if 'streak' in stock.columns and stock.iloc[0]['streak'] >= 3:
            # 过滤ST/退
            if 'name' in stock.columns:
                name = stock.iloc[0]['name']
                if 'ST' in name or '退' in name:
                    return pd.DataFrame()

            # 过滤一字板
            if 'board_type' in stock.columns:
                if '一字' in stock.iloc[0]['board_type']:
                    return pd.DataFrame()

            # 过滤换手率（低于MIN_TURNOVER_RATE不买）
            if 'turnover_rate' in stock.columns:
                if stock.iloc[0]['turnover_rate'] < self.MIN_TURNOVER_RATE:
                    return pd.DataFrame()

            # 过滤股价
            if 'price' in stock.columns:
                if stock.iloc[0]['price'] >= self.MAIN_MAX_PRICE:
                    return pd.DataFrame()

            # 过滤市值（低于30亿不买，高于300亿不买；市值缺失/为0也不买）
            if 'market_cap' in stock.columns:
                market_cap = stock.iloc[0]['market_cap']
                if market_cap == 0 or market_cap < self.MIN_MARKET_CAP or market_cap >= self.MAX_MARKET_CAP:
                    return pd.DataFrame()

            # 可买
            return stock

        return pd.DataFrame()