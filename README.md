# DragonTrading - 龙抬头超短量化策略

基于情绪周期理论的A股超短线量化交易系统，围绕龙头股展开市场阶段判定与交易决策。

## 策略核心

- **情绪周期**：低位试错期 → 主升期(龙头确认) → 高位震荡期(龙头断板) → 退潮期
- **龙头锚定**：3板+板块效应(≥3只涨停)确认龙头，龙头回撤≥15%触发退潮
- **交易规则**：试错期做一进二(30%仓位)，主升期买龙头(80%仓位)，退潮期清仓

## 项目结构

```
DragonTrading/
├── src/
│   ├── engine.py      # 回测引擎（主循环 + 结果输出）
│   ├── strategy.py    # 策略层（龙头追踪 + 市场阶段 + 筛选）
│   ├── broker.py      # 交易层（买卖执行 + 税费 + 熔断）
│   └── data.py        # 数据层（akshare/Baostock）
├── config/
│   └── strategy.yaml  # 策略参数
├── scripts/
│   └── run_backtest.py
├── data/
│   └── store/         # 历史数据CSV
└── tests/
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 运行回测
python scripts/run_backtest.py --start 20260301 --end 20260723 --capital 100000
```

## 分层设计

| 层 | 文件 | 职责 |
|---|------|------|
| 数据层 | `data.py` | 行情获取、K线查询、板块统计 |
| 策略层 | `strategy.py` | 龙头追踪、市场阶段判定、股票筛选 |
| 交易层 | `broker.py` | 买卖执行、税费计算、仓位管理、熔断 |
| 引擎层 | `engine.py` | 日线循环编排、结果汇总、输出 |