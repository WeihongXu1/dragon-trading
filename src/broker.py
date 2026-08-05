#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""
交易执行层 - 买卖操作 + 税费计算 + 仓位管理

税费模型：
- 佣金：万分之2.5（双向）
- 印花税：千分之一（仅卖出）
- 过户费：十万分之一（双向）
- 滑点：0.2%（打板成本）
"""

from typing import List, Dict
import pandas as pd


class Broker:
    """交易执行器"""

    # 费率参数
    COMMISSION_RATE = 0.00025      # 佣金率
    STAMP_TAX_RATE = 0.001         # 印花税率（仅卖出）
    TRANSFER_FEE_RATE = 0.00001    # 过户费率
    SLIPPAGE_RATE = 0.002          # 滑点率

    # 仓位参数
    TRIAL_PCT = 0.50               # 试错期单只仓位
    MAIN_PCT = 1.00                # 主升期仓位（全仓）

    def __init__(self, initial_capital: float):
        self.capital = initial_capital
        self.initial_capital = initial_capital
        self.positions: Dict[str, Dict] = {}
        self.trade_records: List[Dict] = []
        self.daily_pnl: List[Dict] = []  # 新增：每日盈亏记录

    # ========================
    # 买入
    # ========================

    def get_position_pct(self, phase: str) -> float:
        """根据阶段返回仓位比例"""
        return self.MAIN_PCT if phase == '主升期' else self.TRIAL_PCT

    def execute_buy(self, date: str, stock_info: Dict, phase: str) -> bool:
        """执行买入，返回是否成功"""
        stock_code = stock_info['code']
        stock_name = stock_info.get('name', '')
        price = stock_info.get('price', 0)

        if price <= 0:
            return False

        position_pct = self.get_position_pct(phase)
        buy_amount = self.capital * position_pct

        # 仓位限制：试错期最多2只，主升期只能1只
        current_holdings = len(self.positions)
        if phase in ('低位试错期', '高位震荡期') and current_holdings >= 2:
            return False
        if phase == '主升期' and current_holdings >= 1:
            return False

        buy_shares = int(buy_amount / price / 100) * 100

        if buy_shares == 0:
            return False

        # 计算买入成本（超限就少买几手，逐手回退到 total_buy_cost <= self.capital）
        total_buy_cost = 0.0
        while buy_shares > 0:
            actual_buy_amount = buy_shares * price
            commission = actual_buy_amount * self.COMMISSION_RATE
            transfer_fee = actual_buy_amount * self.TRANSFER_FEE_RATE
            slippage = actual_buy_amount * self.SLIPPAGE_RATE
            total_buy_cost = actual_buy_amount + commission + transfer_fee + slippage
            if total_buy_cost <= self.capital:
                break
            buy_shares -= 100

        if buy_shares == 0 or total_buy_cost > self.capital:
            return False

        # 记录交易
        self.trade_records.append({
            'date': date, 'code': stock_code, 'name': stock_name,
            'action': 'buy', 'price': price, 'shares': buy_shares,
            'amount': actual_buy_amount, 'commission': commission,
            'transfer_fee': transfer_fee, 'slippage': slippage,
            'total_cost': total_buy_cost, 'position_pct': position_pct,
            'phase': phase
        })

        # 更新持仓
        close_price = stock_info.get('close_price', price)  # 炸板股有close_price字段
        self.positions[stock_code] = {
            'buy_date': date, 'buy_price': price, 'shares': buy_shares,
            'amount': actual_buy_amount, 'total_cost': total_buy_cost,
            'name': stock_name, 'streak': stock_info.get('streak', 1),
            'close_price': close_price,  # 记录买入当天收盘价（炸板股会低于买入价）
            'board_type': stock_info.get('board_type', '')  # 记录板类型
        }

        self.capital -= total_buy_cost
        return True

    # ========================
    # 卖出
    # ========================

    def check_sell(self, zt_df: pd.DataFrame) -> List[Dict]:
        """检查卖出条件（涨停持有，不涨停/炸板卖出）"""
        sell_list = []

        for stock_code, pos in self.positions.items():
            # 封板涨停 → 继续持有（炸板不算，第二天必须卖）
            if not zt_df.empty and 'code' in zt_df.columns:
                stock_today = zt_df[(zt_df['code'] == stock_code) & (zt_df['board_type'] != '炸板')]
                if len(stock_today) > 0:
                    continue

            # 未涨停 → 卖出
            sell_list.append({
                'code': stock_code, 'name': pos['name'], 'shares': pos['shares'],
                'buy_price': pos['buy_price'], 'buy_date': pos['buy_date']
            })
        return sell_list

    def execute_sell(self, date: str, sell_list: List[Dict], sell_prices: Dict[str, float],
                     phase: str):
        for sell_info in sell_list:
            stock_code = sell_info['code']
            sell_price = sell_prices.get(stock_code, sell_info['buy_price'])

            sell_amount = sell_info['shares'] * sell_price
            buy_amount = sell_info['shares'] * sell_info['buy_price']

            # 计算卖出成本
            commission = sell_amount * self.COMMISSION_RATE
            stamp_tax = sell_amount * self.STAMP_TAX_RATE
            transfer_fee = sell_amount * self.TRANSFER_FEE_RATE
            slippage = sell_amount * self.SLIPPAGE_RATE
            total_sell_cost = commission + stamp_tax + transfer_fee + slippage

            actual_sell_amount = sell_amount - total_sell_cost
            actual_profit = actual_sell_amount - buy_amount
            actual_profit_pct = actual_profit / buy_amount if buy_amount > 0 else 0

            # 记录卖出
            self.trade_records.append({
                'date': date, 'code': stock_code, 'name': sell_info['name'],
                'action': 'sell', 'buy_price': sell_info['buy_price'],
                'sell_price': sell_price, 'shares': sell_info['shares'],
                'amount': sell_amount, 'commission': commission,
                'stamp_tax': stamp_tax, 'transfer_fee': transfer_fee,
                'slippage': slippage, 'total_cost': total_sell_cost,
                'actual_amount': actual_sell_amount, 'profit': actual_profit,
                'profit_pct': actual_profit_pct, 'phase': phase
            })

            self.capital += actual_sell_amount

            # 记录每日盈亏
            self.daily_pnl.append({
                'date': date,
                'code': stock_code,
                'profit': actual_profit,
                'profit_pct': actual_profit_pct
            })

            if stock_code in self.positions:
                del self.positions[stock_code]

    def get_sell_prices(self, sell_list: List[Dict], fetcher, date: str) -> Dict[str, float]:
        """获取卖出中间价"""
        prices = {}
        for sell_info in sell_list:
            code = sell_info['code']
            try:
                kline = fetcher.get_stock_kline(code, date, date)
                if not kline.empty:
                    prices[code] = (kline.iloc[-1]['high'] + kline.iloc[-1]['low']) / 2
                else:
                    prices[code] = sell_info['buy_price']
            except Exception:
                prices[code] = sell_info['buy_price']
        return prices

    def get_position_value(self, fetcher, date: str) -> float:
        """计算持仓市值"""
        total = 0.0
        for code, pos in self.positions.items():
            try:
                kline = fetcher.get_stock_kline(code, date, date)
                if not kline.empty:
                    price = (kline.iloc[-1]['high'] + kline.iloc[-1]['low']) / 2
                else:
                    price = pos['buy_price']
            except Exception:
                price = pos['buy_price']
            total += pos['shares'] * price
        return total

    def get_position_codes(self) -> List[str]:
        """获取持仓股票代码列表"""
        return list(self.positions.keys())


