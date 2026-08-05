#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""
引擎层 - 回测主循环 + 结果计算 + 输出

组装策略、交易、数据三层，执行日线级别的回测循环。
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict
from collections import Counter

import pandas as pd
import numpy as np

from src.data import DataFetcher
from src.strategy import DragonTracker
from src.broker import Broker


class BacktestEngine:
    """回测引擎"""

    def __init__(self, start_date: str, end_date: str, initial_capital: float = 100000):
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital

        # 三层组件
        self.fetcher = DataFetcher()
        self.tracker = DragonTracker()
        self.broker = Broker(initial_capital)

        # 结果记录
        self.summary: Dict = {}

        # 决策日志（新增）
        self.decision_log: List[Dict] = []

        # 前一日数据
        self.prev_market_stats = None
        self.prev_date = None

    def log_decision(self, date: str, phase: str, bought: bool, reason: str = '', holdings: int = 0, buy_stock: str = ''):
        """记录决策日志（每个交易日都记录）"""
        if bought:
            # 买入情况
            self.decision_log.append({
                '日期': date,
                '周期': phase,
                '是否买入': '是',
                '买入股票': buy_stock,
                '持仓数量': holdings,
                '资金余额': round(self.broker.capital, 2),
                '不买入原因': ''
            })
        else:
            # 不买入情况
            self.decision_log.append({
                '日期': date,
                '周期': phase,
                '是否买入': '否',
                '买入股票': '',
                '持仓数量': holdings,
                '资金余额': round(self.broker.capital, 2),
                '不买入原因': reason
            })

    def get_trading_dates(self) -> List[str]:
        """获取交易日列表"""
        start = datetime.strptime(self.start_date, '%Y%m%d')
        end = datetime.strptime(self.end_date, '%Y%m%d')
        dates = []
        current = start
        while current <= end:
            if current.weekday() < 5:
                dates.append(current.strftime('%Y%m%d'))
            current += timedelta(days=1)
        return dates

    def run(self):
        """运行回测"""
        print(f"开始回测：{self.start_date} - {self.end_date}")
        print(f"初始资金：{self.initial_capital:,.2f}元")
        data_source = getattr(self.fetcher, '_data_source', 'akshare')
        is_baostock = (data_source == 'baostock')
        if is_baostock:
            print(f"数据源：Baostock（封板时间/炸板数据不可用，换手率门槛提高至3%）")
        elif data_source == 'akshare':
            print(f"数据源：akshare涨停池（含封板时间/炸板数据）")
        else:
            print(f"数据源：在线API")
        print("-" * 80)

        trading_dates = self.get_trading_dates()

        for date in trading_dates:
            try:
                print(f"\n处理日期：{date}")

                # 获取市场数据
                market_stats = self.fetcher.get_market_stats(date)

                if not market_stats or market_stats.get('total_limit_up', 0) == 0:
                    print(f"  无涨停股数据，跳过")
                    self.prev_market_stats = None
                    continue

                # ========== 判断市场阶段（用T-1的数据，避免未来函数）==========
                if self.prev_market_stats:
                    phase = self.tracker.determine_phase(self.prev_market_stats, self.fetcher, self.prev_date)
                else:
                    # 第一天没有前一天数据，用当天数据
                    phase = self.tracker.determine_phase(market_stats, self.fetcher, date)
                self.tracker.current_phase = phase

                # ========== 预选确认（用T的zt_df检查预选股是否三板）==========
                # 这是正确的时间线：T-1预选，T日盘中观察是否三板
                bought_dragon_today = False  # 标记今天是否已买入龙头
                if self.tracker.dragon_candidates:
                    # 遍历预选候选，找第一个可买的
                    for candidate in self.tracker.dragon_candidates:
                        stock_df = self.tracker.filter_dragon_candidate(market_stats['zt_df'], candidate)
                        if not stock_df.empty:
                            # 找到可买的预选股，执行买入
                            stock_info = stock_df.iloc[0].to_dict()
                            success = self.broker.execute_buy(date, stock_info, '主升期')
                            if success:
                                # 买入成功，确认龙头，进入主升期
                                self.tracker.dragon.stock = candidate['code']
                                self.tracker.dragon.streak = 3
                                self.tracker.dragon.sector = candidate.get('sector', '')
                                self.tracker.dragon.broken = False
                                self.tracker.dragon.break_days = 0
                                self.tracker.dragon.peak_price = float(stock_info.get('price', 0))
                                self.tracker.dragon_candidates = []
                                phase = '主升期'
                                self.tracker.current_phase = phase
                                bought_dragon_today = True  # 标记今天已买入
                                print(f"    龙头确认：{candidate['code']} {candidate.get('name','')} 3板 板块={self.tracker.dragon.sector or '未知'}（预选成功，已买入）")
                                print(f"  买入：{candidate['code']} {candidate.get('name', '')} 仓位100%")
                                break

                    if not bought_dragon_today:
                        # 预选股没有三板或不可买，清空预选池
                        print(f"    预选股未三板或不可买，清空预选池（原有{len(self.tracker.dragon_candidates)}只）")
                        self.tracker.dragon_candidates = []

                # 如果今天已经买入龙头（预选确认），跳过后续流程
                if bought_dragon_today:
                    self.log_decision(date, phase, True, '预选股三板买入成功', 1)
                    self.prev_market_stats = market_stats
                    self.prev_date = date
                    continue

                # ========== 预选龙头候选 ==========
                # 优先级：高板股（≥3板）> 二板股
                # bought_dragon_today已在前面定义，这里不需要重新定义
                if not self.tracker.dragon_candidates and phase in ('低位试错期', '高位震荡期'):
                    candidates = self.tracker.preselect_dragons(market_stats['zt_df'], market_stats.get('sector_analysis', {}))
                    if candidates:
                        # 分离高板股和二板股
                        high_board_candidates = [c for c in candidates if c.get('is_high_board', False)]
                        s2_candidates = [c for c in candidates if not c.get('is_high_board', False)]

                        # 优先处理高板股：直接买入作为龙头
                        if high_board_candidates:
                            # 找连板数最高的
                            best_high = max(high_board_candidates, key=lambda x: x.get('streak', 0))
                            stock_df = self.tracker.filter_dragon_candidate(market_stats['zt_df'], best_high)
                            if not stock_df.empty:
                                stock_info = stock_df.iloc[0].to_dict()
                                success = self.broker.execute_buy(date, stock_info, '主升期')
                                if success:
                                    # 买入成功，确认龙头，进入主升期
                                    self.tracker.dragon.stock = best_high['code']
                                    self.tracker.dragon.streak = best_high['streak']
                                    self.tracker.dragon.sector = best_high.get('sector', '')
                                    self.tracker.dragon.broken = False
                                    self.tracker.dragon.break_days = 0
                                    self.tracker.dragon.peak_price = float(stock_info.get('price', 0))
                                    phase = '主升期'
                                    self.tracker.current_phase = phase
                                    bought_dragon_today = True  # 标记今天已买入
                                    print(f"    龙头确认：{best_high['code']} {best_high.get('name','')} {best_high['streak']}板 板块={self.tracker.dragon.sector or '未知'}（高板股直接买入）")
                                    print(f"  买入：{best_high['code']} {best_high.get('name', '')} 仓位100%")
                                else:
                                    # 买入失败，检查下一个高板股
                                    print(f"    高板股 {best_high['code']} 买入失败")
                            # 如果高板股买入失败或不可买，继续尝试其他高板股
                            # 如果所有高板股都不可买，才预选二板股
                            if not bought_dragon_today:
                                # 尝试其他高板股
                                for candidate in high_board_candidates[1:]:
                                    stock_df = self.tracker.filter_dragon_candidate(market_stats['zt_df'], candidate)
                                    if not stock_df.empty:
                                        stock_info = stock_df.iloc[0].to_dict()
                                        success = self.broker.execute_buy(date, stock_info, '主升期')
                                        if success:
                                            self.tracker.dragon.stock = candidate['code']
                                            self.tracker.dragon.streak = candidate['streak']
                                            self.tracker.dragon.sector = candidate.get('sector', '')
                                            self.tracker.dragon.broken = False
                                            self.tracker.dragon.break_days = 0
                                            self.tracker.dragon.peak_price = float(stock_info.get('price', 0))
                                            phase = '主升期'
                                            self.tracker.current_phase = phase
                                            bought_dragon_today = True  # 标记今天已买入
                                            print(f"    龙头确认：{candidate['code']} {candidate.get('name','')} {candidate['streak']}板 板块={self.tracker.dragon.sector or '未知'}（高板股直接买入）")
                                            print(f"  买入：{candidate['code']} {candidate.get('name', '')} 仓位100%")
                                            break

                                # 如果所有高板股都不可买，预选二板股
                                if not bought_dragon_today and s2_candidates:
                                    self.tracker.dragon_candidates = s2_candidates
                                    codes = [c['code'] for c in s2_candidates]
                                    print(f"    高板股不可买，预选二板股候选：{', '.join(codes)}（共{len(s2_candidates)}只）")

                        # 没有高板股，预选二板股
                        elif s2_candidates:
                            self.tracker.dragon_candidates = s2_candidates
                            codes = [c['code'] for c in s2_candidates]
                            print(f"    预选龙头候选（二板股）：{', '.join(codes)}（共{len(s2_candidates)}只）")

                # 如果今天已经买入龙头，跳过后续买入筛选
                if bought_dragon_today:
                    self.log_decision(date, phase, True, '高板股买入成功', 1)
                    self.prev_market_stats = market_stats
                    self.prev_date = date
                    continue

                # 打印市场信息（用前一天的数据）
                prev_stats = self.prev_market_stats or market_stats
                data_source = "当日" if not self.prev_market_stats else "前一日"
                print(f"  市场阶段：{phase}（基于{data_source}数据）")
                print(f"    涨停{prev_stats.get('total_limit_up',0)}只 "
                      f"跌停{prev_stats.get('limit_down_count',0)}只 "
                      f"首板{prev_stats.get('first_board_count',0)} "
                      f"二板{prev_stats.get('second_board_count',0)} "
                      f"三板{prev_stats.get('third_board_count',0)} "
                      f"最高连板{prev_stats.get('max_streak',0)} "
                      f"大盘{'稳定' if prev_stats.get('market_stable') else '不稳'}")

                # 打印二板股和龙头候选
                zt_df_temp = market_stats['zt_df']
                if not zt_df_temp.empty and 'streak' in zt_df_temp.columns:
                    s2 = len(zt_df_temp[zt_df_temp['streak'] == 2])
                    print(f"    原始二板股: {s2}只")
                if phase == '主升期' and self.tracker.dragon.stock:
                    zt_df = market_stats['zt_df']
                    if not zt_df.empty and 'streak' in zt_df.columns:
                        dragons = zt_df[zt_df['streak'] >= 3][['code', 'name', 'streak', 'sector']]
                        if not dragons.empty:
                            print(f"    龙头候选：")
                            for _, d in dragons.iterrows():
                                print(f"      {d['code']} {d['name']} {d['streak']}板 板块={d.get('sector','未知')}")

                zt_df = market_stats['zt_df']

                # ========== 退潮期处理 ==========
                if phase == '退潮期':
                    self._handle_retreat(date, zt_df)
                    if not self.broker.positions:
                        self.log_decision(date, phase, False, '退潮期强制空仓', 0)
                        self.prev_market_stats = market_stats
                        self.prev_date = date
                        continue
                    self.prev_market_stats = market_stats
                    self.prev_date = date

                # ========== 常规卖出检查 ==========
                if self.broker.positions:
                    sell_list = self.broker.check_sell(zt_df)
                    if sell_list:
                        sell_prices = self.broker.get_sell_prices(sell_list, self.fetcher, date)
                        self.broker.execute_sell(date, sell_list, sell_prices, phase)
                        print(f"  卖出{len(sell_list)}只股票")

                if self.broker.positions:
                    codes = self.broker.get_position_codes()
                    print(f"  持有中（涨停）：{', '.join(codes)}，继续持有")

                # ========== 高位震荡期 ==========
                if phase == '高位震荡期':
                    if self.tracker.dragon.break_days == 1:
                        # 断板当天，不买入
                        print(f"  高位震荡期（断板当天），不买入")
                        self.log_decision(date, phase, False, '高位震荡期断板当天', len(self.broker.positions))
                        self.prev_market_stats = market_stats
                        self.prev_date = date
                        continue
                    else:
                        # 断板第二天及以后，允许买一进二
                        print(f"  高位震荡期（断板第{self.tracker.dragon.break_days}天），尝试做一进二")

                # 退潮期不买入
                if phase == '退潮期':
                    self.log_decision(date, phase, False, '退潮期强制空仓', len(self.broker.positions))
                    self.prev_market_stats = market_stats
                    self.prev_date = date
                    continue

                # ========== 筛选买入 ==========
                buy_df = self.tracker.filter_buy_stocks(zt_df, phase, is_baostock, self.fetcher, date)
                if buy_df.empty:
                    print(f"  无符合条件股票（筛选后）")
                    self.log_decision(date, phase, False, '无符合条件股票', len(self.broker.positions))
                    self.prev_market_stats = market_stats
                    self.prev_date = date
                    continue

                print(f"  筛选后可买股票: {len(buy_df)}只")

                # ========== 执行买入 ==========
                bought_stocks = []
                if phase == '低位试错期':
                    for idx, row in buy_df.head(3).iterrows():
                        success = self.broker.execute_buy(date, row.to_dict(), phase)
                        if success:
                            board_type = row.get('board_type', '')
                            is_break = board_type == '炸板'
                            msg = f"  买入：{row['code']} {row.get('name', '')} 仓位{self.broker.TRIAL_PCT*100:.0f}%"
                            if is_break:
                                loss_pct = (row.get('close_price', row['price']) - row['price']) / row['price'] * 100
                                msg += f" [炸板! 浮亏{loss_pct:.1f}%]"
                            print(msg)
                            bought_stocks.append(f"{row['code']} {row.get('name', '')}")
                        else:
                            print(f"  买入失败：{row['code']} {row.get('name', '')}")

                elif phase == '主升期':
                    if 'streak' in buy_df.columns and not buy_df.empty:
                        dragon = buy_df.loc[buy_df['streak'].idxmax()]
                        dragon_code = dragon['code']
                        is_continues = False
                        if self.prev_market_stats:
                            prev_zt = self.prev_market_stats.get('zt_df', pd.DataFrame())
                            if not prev_zt.empty and 'code' in prev_zt.columns:
                                is_continues = dragon_code in prev_zt['code'].values

                        if is_continues:
                            success = self.broker.execute_buy(date, dragon.to_dict(), phase)
                            if success:
                                print(f"  买入龙头：{dragon['code']} {dragon.get('name', '')} 仓位{self.broker.MAIN_PCT*100:.0f}%")
                                bought_stocks.append(f"{dragon['code']} {dragon.get('name', '')}")
                            else:
                                print(f"  买入龙头失败：{dragon['code']} {dragon.get('name', '')}")
                        else:
                            print(f"  龙头 {dragon_code} 昨日未涨停，不买入（防止高位反包）")

                elif phase == '高位震荡期':
                    for idx, row in buy_df.head(2).iterrows():
                        success = self.broker.execute_buy(date, row.to_dict(), phase)
                        if success:
                            board_type = row.get('board_type', '')
                            is_break = board_type == '炸板'
                            msg = f"  买入：{row['code']} {row.get('name', '')} 仓位{self.broker.TRIAL_PCT*100:.0f}%"
                            if is_break:
                                loss_pct = (row.get('close_price', row['price']) - row['price']) / row['price'] * 100
                                msg += f" [炸板! 浮亏{loss_pct:.1f}%]"
                            print(msg)
                            bought_stocks.append(f"{row['code']} {row.get('name', '')}")
                        else:
                            print(f"  买入失败：{row['code']} {row.get('name', '')}")

                # 记录当日决策
                if bought_stocks:
                    self.log_decision(date, phase, True, '', len(self.broker.positions), ', '.join(bought_stocks))
                else:
                    # 持仓已满/资金不足属于"想卖卖不出"，不是策略判断，不记日志
                    if buy_df.head(1).empty or not self.broker.execute_buy(date, buy_df.iloc[0].to_dict(), phase):
                        pass
                    else:
                        self.log_decision(date, phase, False, '其他原因', len(self.broker.positions))

                self.prev_market_stats = market_stats
                self.prev_date = date

            except Exception as e:
                print(f"  处理失败：{e}")
                continue

        self._print_results()

    def _handle_retreat(self, date: str, zt_df: pd.DataFrame):
        """退潮期处理：卖出非涨停股"""
        if not self.broker.positions:
            return

        force_sell = []
        hold_list = []
        for code, pos in list(self.broker.positions.items()):
            stock_zt = zt_df[(zt_df['code'] == code) & (zt_df['board_type'] != '炸板')] \
                if not zt_df.empty and 'code' in zt_df.columns else pd.DataFrame()
            if len(stock_zt) > 0:
                hold_list.append(code)
            else:
                mid_price = self._get_last_price(code, date)
                if mid_price <= 0:
                    mid_price = pos['buy_price']
                force_sell.append({
                    'code': code, 'name': pos['name'], 'shares': pos['shares'],
                    'buy_price': pos['buy_price'], 'buy_date': pos['buy_date']
                })

        if force_sell:
            sell_prices = {s['code']: s.get('sell_price', s['buy_price']) for s in force_sell}
            for s in force_sell:
                if s['code'] not in sell_prices or sell_prices[s['code']] == s['buy_price']:
                    sell_prices[s['code']] = self._get_last_price(s['code'], date) or s['buy_price']
            self.broker.execute_sell(date, force_sell, sell_prices, '退潮期')
            print(f"  退潮期卖出{len(force_sell)}只股票")
        if hold_list:
            print(f"  退潮期保留涨停股：{', '.join(hold_list)}")

        self.tracker.clear_dragon()

    def _get_last_price(self, code: str, date: str) -> float:
        """获取股票中间价"""
        try:
            kline = self.fetcher.get_stock_kline(code, date, date)
            if not kline.empty:
                return (kline.iloc[-1]['high'] + kline.iloc[-1]['low']) / 2
        except Exception:
            pass
        return 0.0

    def _print_results(self):
        """打印回测结果"""
        print("\n" + "=" * 80)
        print("回测结果")
        print("=" * 80)

        final_capital = self.broker.capital
        total_position_value = 0.0

        if self.broker.positions:
            print(f"\n剩余持仓（按{self.end_date}中间价结算）：")
            for code, pos in self.broker.positions.items():
                last_price = self._get_last_price(code, self.end_date)
                if last_price <= 0:
                    last_price = pos['buy_price']
                pos_value = pos['shares'] * last_price
                total_position_value += pos_value
                print(f"  {code} {pos['name']}: "
                      f"买入价={pos['buy_price']:.2f}, "
                      f"结算价={last_price:.2f}, "
                      f"股数={pos['shares']}, "
                      f"市值={pos_value:,.2f}元")
            final_capital += total_position_value
            print(f"  持仓总市值：{total_position_value:,.2f}元")

        total_profit = final_capital - self.initial_capital
        total_return = total_profit / self.initial_capital * 100

        print(f"\n初始资金：{self.initial_capital:,.2f}元")
        print(f"现金余额：{self.broker.capital:,.2f}元")
        print(f"最终资金（含持仓）：{final_capital:,.2f}元")
        print(f"总收益：{total_profit:,.2f}元")
        print(f"总收益率：{total_return:.2f}%")

        buy_trades = [t for t in self.broker.trade_records if t['action'] == 'buy']
        sell_trades = [t for t in self.broker.trade_records if t['action'] == 'sell']

        print(f"\n交易统计：")
        print(f"买入次数：{len(buy_trades)}")
        print(f"卖出次数：{len(sell_trades)}")

        if sell_trades:
            profits = [t['profit'] for t in sell_trades]
            profit_pcts = [t['profit_pct'] for t in sell_trades]
            win_trades = [t for t in sell_trades if t['profit'] > 0]
            loss_trades = [t for t in sell_trades if t['profit'] <= 0]
            win_rate = len(win_trades) / len(sell_trades) * 100 if sell_trades else 0
            avg_profit = np.mean(profits) if profits else 0
            avg_profit_pct = np.mean(profit_pcts) * 100 if profit_pcts else 0

            print(f"\n盈亏分布：")
            print(f"盈利次数：{len(win_trades)}")
            print(f"亏损次数：{len(loss_trades)}")
            print(f"胜率：{win_rate:.2f}%")
            print(f"平均盈亏：{avg_profit:,.2f}元")
            print(f"平均收益率：{avg_profit_pct:.2f}%")

        # ========== 交易日统计表 ==========
        if self.decision_log:
            print(f"\n交易日统计：")
            print(f"{'='*80}")
            total_days = len(self.decision_log)
            buy_days = [d for d in self.decision_log if d['是否买入'] == '是']
            no_buy_days = [d for d in self.decision_log if d['是否买入'] == '否']
            buy_count = len(buy_days)
            no_buy_count = len(no_buy_days)

            print(f"  总交易日：{total_days}天")
            print(f"  出手天数：{buy_count}天 ({buy_count/total_days*100:.1f}%)")
            print(f"  空仓天数：{no_buy_count}天 ({no_buy_count/total_days*100:.1f}%)")

            # 空仓原因统计
            if no_buy_days:
                reason_counter = Counter(d['不买入原因'] for d in no_buy_days)
                print(f"\n  空仓原因分布：")
                print(f"  {'原因':<20} {'天数':>5} {'占比':>8}")
                print(f"  {'-'*35}")
                for reason, count in reason_counter.most_common():
                    print(f"  {reason:<20} {count:>5}天 {count/no_buy_count*100:>7.1f}%")

        # 保存汇总结果
        self.summary = {
            'start_date': self.start_date,
            'end_date': self.end_date,
            'initial_capital': self.initial_capital,
            'cash_balance': self.broker.capital,
            'position_value': total_position_value,
            'final_capital': final_capital,
            'total_profit': total_profit,
            'total_return_pct': total_return,
            'buy_count': len(buy_trades),
            'sell_count': len(sell_trades),
            'win_count': len(win_trades) if sell_trades else 0,
            'loss_count': len(loss_trades) if sell_trades else 0,
            'win_rate_pct': win_rate if sell_trades else 0,
            'avg_profit': avg_profit if sell_trades else 0,
            'avg_return_pct': avg_profit_pct if sell_trades else 0
        }

        # 保存决策日志
        if self.decision_log:
            decision_df = pd.DataFrame(self.decision_log)
            decision_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'decision_log.csv')
            os.makedirs(os.path.dirname(decision_file), exist_ok=True)
            decision_df.to_csv(decision_file, index=False, encoding='utf-8-sig')
            print(f"\n决策日志已保存：{decision_file}")

        self._save_results()

    def _save_results(self):
        """保存回测结果（3个CSV + 1个Excel）"""
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')

        trade_df = pd.DataFrame(self.broker.trade_records)
        pnl_df = pd.DataFrame(self.broker.daily_pnl)
        summary_df = pd.DataFrame([self.summary]) if self.summary else pd.DataFrame()

        # Excel（多Sheet）
        excel_path = os.path.join(data_dir, 'backtest_results.xlsx')
        try:
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                trade_df.to_excel(writer, sheet_name='交易记录', index=False)
                pnl_df.to_excel(writer, sheet_name='每日盈亏', index=False)
                if not summary_df.empty:
                    summary_df.to_excel(writer, sheet_name='汇总结果', index=False)
            print(f"\n回测结果（Excel）：{excel_path}")
        except Exception as e:
            print(f"[WARN] 写入Excel失败: {e}")

        # CSV备份（3个文件）
        try:
            trade_path = os.path.join(data_dir, 'trade_records.csv')
            trade_df.to_csv(trade_path, index=False, encoding='utf-8-sig')
            print(f"  交易记录：{trade_path}")
        except PermissionError:
            pass

        try:
            pnl_path = os.path.join(data_dir, 'daily_pnl.csv')
            pnl_df.to_csv(pnl_path, index=False, encoding='utf-8-sig')
            print(f"  每日盈亏：{pnl_path}")
        except PermissionError:
            pass

        if not summary_df.empty:
            try:
                summary_path = os.path.join(data_dir, 'backtest_summary.csv')
                summary_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
                print(f"  汇总结果：{summary_path}")
            except PermissionError:
                pass