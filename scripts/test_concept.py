#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""测试akshare概念板块成分股API"""

# 方式1：用东方财富概念板块成分股API（直接传BK代码）
try:
    import akshare as ak
    cons = ak.stock_board_concept_cons_em(symbol='BK06551')
    print(f"BK06551成分股: {len(cons)}只")
    print(cons[['代码', '名称']].head(10))
except Exception as e:
    print(f"BK06551失败: {e}")

# 方式2：用THS概念板块名称
try:
    import akshare as ak
    cons2 = ak.stock_board_concept_cons_em(symbol='芯片概念')
    print(f"\n芯片概念成分股: {len(cons2)}只")
    print(cons2[['代码', '名称']].head(10))
except Exception as e:
    print(f"芯片概念失败: {e}")

# 方式3：获取所有东方财富概念板块列表
try:
    import akshare as ak
    names = ak.stock_board_concept_name_em()
    print(f"\n概念板块列表: {len(names)}个")
    print(names.head(10))
except Exception as e:
    print(f"概念板块列表失败: {e}")