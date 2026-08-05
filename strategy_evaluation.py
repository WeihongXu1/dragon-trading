#!/usr/bin/env python
# -*- coding:utf-8 -*-

"""
量化策略测评脚本

计算量化策略的常用测评指标：
1. 收益率指标：总收益率、年化收益率、累计收益曲线
2. 风险指标：最大回撤、最大回撤持续时间、波动率、下行波动率
3. 风险调整收益指标：夏普比率、索提诺比率、卡玛比率
4. 交易统计指标：胜率、盈亏比、平均盈利/亏损、最大连续盈利/亏损
5. 其他指标：日均收益、月均收益、正收益月份占比
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.font_manager import FontProperties
from datetime import datetime, timedelta
import os
from typing import Dict, List, Tuple


# ========================
# 中文字体配置（Windows兼容）
# ========================
def _setup_chinese_font():
    """设置 matplotlib 中文字体，解决 Windows 下中文乱码"""
    # 按优先级尝试常用中文字体
    chinese_fonts = ['SimHei', 'Microsoft YaHei', 'Microsoft YaHei UI', 'SimSun', 'FangSong']
    for font_name in chinese_fonts:
        try:
            FontProperties(family=font_name)
            plt.rcParams['font.sans-serif'] = [font_name] + plt.rcParams['font.sans-serif']
            plt.rcParams['axes.unicode_minus'] = False
            return
        except Exception:
            continue
    # 兜底：尝试通过 font_manager 查找
    import matplotlib.font_manager as fm
    for f in fm.fontManager.ttflist:
        if any(kw in f.name.lower() for kw in ['yahei', 'simhei', 'simsun', 'songti', 'heiti']):
            plt.rcParams['font.sans-serif'] = [f.name] + plt.rcParams['font.sans-serif']
            plt.rcParams['axes.unicode_minus'] = False
            return


# 在导入时自动执行
_setup_chinese_font()


class StrategyEvaluator:
    """策略测评器"""

    # 无风险利率（年化）
    RISK_FREE_RATE = 0.03

    # 交易日数（一年约250个交易日）
    TRADING_DAYS_PER_YEAR = 250

    def __init__(self, data_dir: str = './data'):
        self.data_dir = data_dir
        self.trade_records = None
        self.daily_pnl = None
        self.summary = None
        self.cumulative_returns = None
        self.monthly_returns = None

    def load_data(self):
        """加载回测数据"""
        print("加载回测数据...")

        # 加载交易记录
        trade_file = os.path.join(self.data_dir, 'trade_records.csv')
        if os.path.exists(trade_file):
            self.trade_records = pd.read_csv(trade_file, encoding='utf-8-sig')
            print(f"  [OK] 交易记录: {len(self.trade_records)}条")
        else:
            print(f"  [WARN] 未找到交易记录文件: {trade_file}")
            self.trade_records = pd.DataFrame()

        # 加载每日盈亏
        pnl_file = os.path.join(self.data_dir, 'daily_pnl.csv')
        if os.path.exists(pnl_file):
            self.daily_pnl = pd.read_csv(pnl_file, encoding='utf-8-sig')
            print(f"  [OK] 每日盈亏: {len(self.daily_pnl)}条")
        else:
            print(f"  [WARN] 未找到每日盈亏文件: {pnl_file}")
            self.daily_pnl = pd.DataFrame()

        # 加载汇总结果
        summary_file = os.path.join(self.data_dir, 'backtest_summary.csv')
        if os.path.exists(summary_file):
            self.summary = pd.read_csv(summary_file, encoding='utf-8-sig')
            print(f"  [OK] 汇总结果: {len(self.summary)}条")
        else:
            print(f"  [WARN] 未找到汇总结果文件: {summary_file}")
            self.summary = pd.DataFrame()

        # 计算累计收益和月度收益
        if not self.daily_pnl.empty:
            self._calculate_cumulative_returns()
            self._calculate_monthly_returns()

    def _calculate_cumulative_returns(self):
        """计算累计收益曲线"""
        if self.daily_pnl.empty:
            return

        # 按日期分组，计算每日总盈亏
        daily_total = self.daily_pnl.groupby('date')['profit'].sum().reset_index()
        daily_total.columns = ['date', 'daily_profit']

        # 初始资金
        initial_capital = 100000
        if not self.summary.empty:
            initial_capital = self.summary['initial_capital'].iloc[0]

        # 计算累计收益
        daily_total['cumulative_profit'] = daily_total['daily_profit'].cumsum()
        daily_total['cumulative_capital'] = initial_capital + daily_total['cumulative_profit']
        daily_total['cumulative_return'] = daily_total['cumulative_profit'] / initial_capital

        self.cumulative_returns = daily_total

    def _calculate_monthly_returns(self):
        """计算月度收益"""
        if self.daily_pnl.empty:
            return

        # 转换日期格式
        df = self.daily_pnl.copy()
        df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        df['month'] = df['date'].dt.to_period('M')

        # 按月分组
        monthly = df.groupby('month')['profit'].sum().reset_index()
        monthly.columns = ['month', 'monthly_profit']

        # 初始资金
        initial_capital = 100000
        if not self.summary.empty:
            initial_capital = self.summary['initial_capital'].iloc[0]

        # 计算月度收益率
        monthly['monthly_return'] = monthly['monthly_profit'] / initial_capital

        self.monthly_returns = monthly

    # ========================
    # 收益率指标
    # ========================

    def calculate_return_metrics(self) -> Dict:
        """计算收益率指标"""
        metrics = {}

        if self.summary.empty:
            return metrics

        # 总收益率
        total_return = self.summary['total_return_pct'].iloc[0]
        metrics['总收益率(%)'] = total_return

        # 回测天数
        start_date = datetime.strptime(str(self.summary['start_date'].iloc[0]), '%Y%m%d')
        end_date = datetime.strptime(str(self.summary['end_date'].iloc[0]), '%Y%m%d')
        days = (end_date - start_date).days
        trading_days = days * 5 / 7  # 估算交易日
        metrics['回测天数'] = days
        metrics['估算交易日'] = int(trading_days)

        # 年化收益率
        years = trading_days / self.TRADING_DAYS_PER_YEAR
        if years > 0:
            annual_return = ((1 + total_return / 100) ** (1 / years) - 1) * 100
            metrics['年化收益率(%)'] = annual_return
        else:
            metrics['年化收益率(%)'] = 0

        # 初始资金
        metrics['初始资金'] = self.summary['initial_capital'].iloc[0]
        metrics['最终资金'] = self.summary['final_capital'].iloc[0]
        metrics['总盈亏'] = self.summary['total_profit'].iloc[0]

        return metrics

    # ========================
    # 风险指标
    # ========================

    def calculate_risk_metrics(self) -> Dict:
        """计算风险指标"""
        metrics = {}

        if self.cumulative_returns is None or self.cumulative_returns.empty:
            return metrics

        # 最大回撤
        cumulative = self.cumulative_returns['cumulative_capital']
        peak = cumulative.expanding(min_periods=1).max()
        drawdown = (cumulative - peak) / peak

        max_drawdown = drawdown.min()
        metrics['最大回撤(%)'] = max_drawdown * 100

        # 最大回撤持续时间
        # 找到最大回撤的位置
        max_dd_idx = drawdown.idxmin()
        if max_dd_idx > 0:
            # 找到最大回撤前的峰值
            peak_idx = cumulative[:max_dd_idx].idxmax()
            # 找到回撤恢复的日期
            recovery_idx = cumulative[max_dd_idx:].idxmax() if max_dd_idx < len(cumulative) - 1 else len(cumulative) - 1

            # 持续时间（天数）
            if peak_idx < recovery_idx:
                dd_duration = recovery_idx - peak_idx
                metrics['最大回撤持续天数'] = dd_duration
            else:
                metrics['最大回撤持续天数'] = 0
        else:
            metrics['最大回撤持续天数'] = 0

        # 日收益率波动率
        if len(self.daily_pnl) > 0:
            daily_total = self.daily_pnl.groupby('date')['profit_pct'].sum().reset_index()
            if len(daily_total) > 1:
                daily_volatility = daily_total['profit_pct'].std()
                metrics['日波动率(%)'] = daily_volatility * 100

                # 年化波动率
                annual_volatility = daily_volatility * np.sqrt(self.TRADING_DAYS_PER_YEAR)
                metrics['年化波动率(%)'] = annual_volatility * 100

                # 下行波动率（只计算负收益）
                negative_returns = daily_total[daily_total['profit_pct'] < 0]['profit_pct']
                if len(negative_returns) > 1:
                    downside_volatility = negative_returns.std()
                    metrics['下行波动率(%)'] = downside_volatility * 100

        return metrics

    # ========================
    # 风险调整收益指标
    # ========================

    def calculate_risk_adjusted_metrics(self) -> Dict:
        """计算风险调整收益指标"""
        metrics = {}

        if self.cumulative_returns is None or self.cumulative_returns.empty:
            return metrics

        # 夏普比率
        if '年化收益率(%)' in self.calculate_return_metrics() and '年化波动率(%)' in self.calculate_risk_metrics():
            annual_return = self.calculate_return_metrics()['年化收益率(%)'] / 100
            annual_volatility = self.calculate_risk_metrics()['年化波动率(%)'] / 100

            if annual_volatility > 0:
                sharpe_ratio = (annual_return - self.RISK_FREE_RATE) / annual_volatility
                metrics['夏普比率'] = sharpe_ratio

        # 索提诺比率
        if '年化收益率(%)' in self.calculate_return_metrics() and '下行波动率(%)' in self.calculate_risk_metrics():
            annual_return = self.calculate_return_metrics()['年化收益率(%)'] / 100
            downside_volatility = self.calculate_risk_metrics()['下行波动率(%)'] / 100

            if downside_volatility > 0:
                sortino_ratio = (annual_return - self.RISK_FREE_RATE) / downside_volatility
                metrics['索提诺比率'] = sortino_ratio

        # 卡玛比率（年化收益率 / 最大回撤绝对值）
        if '年化收益率(%)' in self.calculate_return_metrics() and '最大回撤(%)' in self.calculate_risk_metrics():
            annual_return = self.calculate_return_metrics()['年化收益率(%)']
            max_drawdown = abs(self.calculate_risk_metrics()['最大回撤(%)'])

            if max_drawdown > 0:
                calmar_ratio = annual_return / max_drawdown
                metrics['卡玛比率'] = calmar_ratio

        return metrics

    # ========================
    # 交易统计指标
    # ========================

    def calculate_trading_metrics(self) -> Dict:
        """计算交易统计指标"""
        metrics = {}

        if self.trade_records.empty:
            return metrics

        # 分离买入和卖出记录
        buy_records = self.trade_records[self.trade_records['action'] == 'buy']
        sell_records = self.trade_records[self.trade_records['action'] == 'sell']

        # 交易次数
        metrics['买入次数'] = len(buy_records)
        metrics['卖出次数'] = len(sell_records)

        if sell_records.empty:
            return metrics

        # 胜率
        profitable_trades = sell_records[sell_records['profit'] > 0]
        loss_trades = sell_records[sell_records['profit'] <= 0]

        metrics['盈利次数'] = len(profitable_trades)
        metrics['亏损次数'] = len(loss_trades)
        metrics['胜率(%)'] = len(profitable_trades) / len(sell_records) * 100 if len(sell_records) > 0 else 0

        # 平均盈利/亏损
        if len(profitable_trades) > 0:
            metrics['平均盈利(元)'] = profitable_trades['profit'].mean()
            metrics['平均盈利比例(%)'] = profitable_trades['profit_pct'].mean() * 100
        else:
            metrics['平均盈利(元)'] = 0
            metrics['平均盈利比例(%)'] = 0

        if len(loss_trades) > 0:
            metrics['平均亏损(元)'] = loss_trades['profit'].mean()
            metrics['平均亏损比例(%)'] = loss_trades['profit_pct'].mean() * 100
        else:
            metrics['平均亏损(元)'] = 0
            metrics['平均亏损比例(%)'] = 0

        # 盈亏比
        if metrics['平均亏损(元)'] != 0:
            profit_loss_ratio = abs(metrics['平均盈利(元)'] / metrics['平均亏损(元)'])
            metrics['盈亏比'] = profit_loss_ratio
        else:
            metrics['盈亏比'] = 0

        # 最大单笔盈利/亏损
        if len(profitable_trades) > 0:
            metrics['最大单笔盈利(元)'] = profitable_trades['profit'].max()
            metrics['最大单笔盈利比例(%)'] = profitable_trades['profit_pct'].max() * 100
        else:
            metrics['最大单笔盈利(元)'] = 0
            metrics['最大单笔盈利比例(%)'] = 0

        if len(loss_trades) > 0:
            metrics['最大单笔亏损(元)'] = loss_trades['profit'].min()
            metrics['最大单笔亏损比例(%)'] = loss_trades['profit_pct'].min() * 100
        else:
            metrics['最大单笔亏损(元)'] = 0
            metrics['最大单笔亏损比例(%)'] = 0

        # 最大连续盈利/亏损次数
        if len(sell_records) > 0:
            # 按日期排序
            sell_sorted = sell_records.sort_values('date')

            # 计算连续盈利
            max_win_streak = 0
            current_streak = 0
            for profit in sell_sorted['profit']:
                if profit > 0:
                    current_streak += 1
                    max_win_streak = max(max_win_streak, current_streak)
                else:
                    current_streak = 0
            metrics['最大连续盈利次数'] = max_win_streak

            # 计算连续亏损
            max_loss_streak = 0
            current_streak = 0
            for profit in sell_sorted['profit']:
                if profit <= 0:
                    current_streak += 1
                    max_loss_streak = max(max_loss_streak, current_streak)
                else:
                    current_streak = 0
            metrics['最大连续亏损次数'] = max_loss_streak

        # 平均持仓周期
        if len(sell_records) > 0 and 'buy_date' in sell_records.columns:
            sell_records_copy = sell_records.copy()
            sell_records_copy['buy_date'] = pd.to_datetime(sell_records_copy['buy_date'], format='%Y%m%d', errors='coerce')
            sell_records_copy['sell_date'] = pd.to_datetime(sell_records_copy['date'], format='%Y%m%d', errors='coerce')

            if not sell_records_copy['buy_date'].isna().all():
                sell_records_copy['holding_days'] = (sell_records_copy['sell_date'] - sell_records_copy['buy_date']).dt.days
                metrics['平均持仓天数'] = sell_records_copy['holding_days'].mean()

        return metrics

    # ========================
    # 其他指标
    # ========================

    def calculate_other_metrics(self) -> Dict:
        """计算其他指标"""
        metrics = {}

        if self.daily_pnl.empty or self.summary.empty:
            return metrics

        # 回测天数
        start_date = datetime.strptime(str(self.summary['start_date'].iloc[0]), '%Y%m%d')
        end_date = datetime.strptime(str(self.summary['end_date'].iloc[0]), '%Y%m%d')
        days = (end_date - start_date).days

        # 日均收益
        total_profit = self.summary['total_profit'].iloc[0]
        if days > 0:
            metrics['日均收益(元)'] = total_profit / days
            metrics['日均收益率(%)'] = (total_profit / self.summary['initial_capital'].iloc[0] / days) * 100

        # 月均收益
        months = days / 30
        if months > 0:
            metrics['月均收益(元)'] = total_profit / months
            metrics['月均收益率(%)'] = (total_profit / self.summary['initial_capital'].iloc[0] / months) * 100

        # 正收益月份占比
        if self.monthly_returns is not None and not self.monthly_returns.empty:
            positive_months = len(self.monthly_returns[self.monthly_returns['monthly_profit'] > 0])
            total_months = len(self.monthly_returns)
            metrics['正收益月份占比(%)'] = positive_months / total_months * 100 if total_months > 0 else 0

        return metrics

    # ========================
    # 综合评估
    # ========================

    def evaluate(self) -> Dict:
        """综合评估策略"""
        print("\n" + "=" * 80)
        print("量化策略测评报告")
        print("=" * 80)

        # 加载数据
        self.load_data()

        if self.daily_pnl.empty and self.trade_records.empty:
            print("[ERROR] 未找到回测数据，请先运行回测")
            return {}

        # 计算各项指标
        all_metrics = {}

        print("\n【收益率指标】")
        print("-" * 80)
        return_metrics = self.calculate_return_metrics()
        for key, value in return_metrics.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")
        all_metrics.update(return_metrics)

        print("\n【风险指标】")
        print("-" * 80)
        risk_metrics = self.calculate_risk_metrics()
        for key, value in risk_metrics.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")
        all_metrics.update(risk_metrics)

        print("\n【风险调整收益指标】")
        print("-" * 80)
        risk_adjusted_metrics = self.calculate_risk_adjusted_metrics()
        for key, value in risk_adjusted_metrics.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.4f}")
            else:
                print(f"  {key}: {value}")
        all_metrics.update(risk_adjusted_metrics)

        print("\n【交易统计指标】")
        print("-" * 80)
        trading_metrics = self.calculate_trading_metrics()
        for key, value in trading_metrics.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")
        all_metrics.update(trading_metrics)

        print("\n【其他指标】")
        print("-" * 80)
        other_metrics = self.calculate_other_metrics()
        for key, value in other_metrics.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")
        all_metrics.update(other_metrics)

        return all_metrics

    # ========================
    # 可视化
    # ========================

    def plot_results(self):
        """绘制可视化图表"""
        if self.cumulative_returns is None or self.cumulative_returns.empty:
            print("[WARN] 无累计收益数据，无法绘图")
            return

        # 创建图表
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('量化策略测评可视化报告', fontsize=16, fontweight='bold')

        # 1. 累计收益曲线
        ax1 = axes[0, 0]
        dates = pd.to_datetime(self.cumulative_returns['date'], format='%Y%m%d')
        ax1.plot(dates, self.cumulative_returns['cumulative_return'] * 100, 'b-', linewidth=2)
        ax1.set_title('累计收益率曲线', fontsize=12, fontweight='bold')
        ax1.set_xlabel('日期')
        ax1.set_ylabel('累计收益率(%)')
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

        # 2. 回撤曲线
        ax2 = axes[0, 1]
        cumulative = self.cumulative_returns['cumulative_capital']
        peak = cumulative.expanding(min_periods=1).max()
        drawdown = (cumulative - peak) / peak * 100
        ax2.fill_between(dates, drawdown, 0, alpha=0.3, color='red')
        ax2.plot(dates, drawdown, 'r-', linewidth=2)
        ax2.set_title('回撤曲线', fontsize=12, fontweight='bold')
        ax2.set_xlabel('日期')
        ax2.set_ylabel('回撤(%)')
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

        # 3. 月度收益柱状图
        ax3 = axes[1, 0]
        if self.monthly_returns is not None and not self.monthly_returns.empty:
            months = [str(m) for m in self.monthly_returns['month']]
            profits = self.monthly_returns['monthly_profit']
            colors = ['green' if p > 0 else 'red' for p in profits]
            ax3.bar(range(len(months)), profits, color=colors, alpha=0.7)
            ax3.set_title('月度收益分布', fontsize=12, fontweight='bold')
            ax3.set_xlabel('月份')
            ax3.set_ylabel('盈亏(元)')
            ax3.grid(True, alpha=0.3, axis='y')
            ax3.set_xticks(range(0, len(months), max(1, len(months)//10)))
            ax3.set_xticklabels([months[i] for i in range(0, len(months), max(1, len(months)//10))], rotation=45)

        # 4. 盈亏分布
        ax4 = axes[1, 1]
        if not self.trade_records.empty:
            sell_records = self.trade_records[self.trade_records['action'] == 'sell']
            if not sell_records.empty:
                profits = sell_records['profit_pct'] * 100
                ax4.hist(profits, bins=50, alpha=0.7, color='blue', edgecolor='black')
                ax4.axvline(x=0, color='red', linestyle='--', linewidth=2, label='盈亏平衡线')
                ax4.set_title('单笔交易盈亏分布', fontsize=12, fontweight='bold')
                ax4.set_xlabel('收益率(%)')
                ax4.set_ylabel('频次')
                ax4.grid(True, alpha=0.3)
                ax4.legend()

        plt.tight_layout()

        # 保存图表
        plot_file = os.path.join(self.data_dir, 'strategy_evaluation.png')
        plt.savefig(plot_file, dpi=300, bbox_inches='tight')
        print(f"\n[OK] 可视化图表已保存: {plot_file}")

        plt.show()

    # ========================
    # 保存报告
    # ========================

    def save_report(self, metrics: Dict):
        """保存测评报告"""
        if not metrics:
            return

        # 转换为DataFrame
        df = pd.DataFrame([metrics])

        # 保存CSV
        report_file = os.path.join(self.data_dir, 'strategy_evaluation_report.csv')
        df.to_csv(report_file, index=False, encoding='utf-8-sig')
        print(f"[OK] 测评报告已保存: {report_file}")


def main():
    """主函数"""
    # 项目根目录
    project_root = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(project_root, 'data')

    # 创建测评器
    evaluator = StrategyEvaluator(data_dir)

    # 执行测评
    metrics = evaluator.evaluate()

    if metrics:
        # 绘制可视化图表
        print("\n" + "=" * 80)
        print("生成可视化图表...")
        print("=" * 80)
        evaluator.plot_results()

        # 保存报告
        evaluator.save_report(metrics)

        print("\n" + "=" * 80)
        print("测评完成！")
        print("=" * 80)


if __name__ == '__main__':
    main()