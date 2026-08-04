@echo off
REM 数据下载一键运行脚本
REM 支持 Baostock（K线计算涨停，可覆盖数年）和 akshare（涨停池，近1月）

echo ========================================
echo 超短量化策略 - 数据下载
echo ========================================
echo.
echo 模式选择:
echo   1. Baostock模式（推荐）- 从K线计算涨停，可覆盖任意时间段
echo   2. akshare模式 - 使用涨停池API，仅支持近1个月
echo.

set PYTHON_EXE=D:\anaconda\envs\ultra_short_310\python.exe
set PROJECT_DIR=e:\Quantitative_trading\DragonTrading

if not exist "%PYTHON_EXE%" (
    echo [错误] Python环境不存在: %PYTHON_EXE%
    pause
    exit /b 1
)

echo [1/3] 安装依赖...
"%PYTHON_EXE%" -m pip install baostock -q
echo.

echo [2/3] 设置参数（默认下载一年数据）...
echo ========================================
echo   开始日期: 20250723
echo   结束日期: 20260723
echo   模式: baostock
echo ========================================

cd /d "%PROJECT_DIR%"
echo.
echo [3/3] 开始下载数据（首次下载约30-60分钟，请耐心等待）...
echo.
"%PYTHON_EXE%" src/download.py --start_date 20250723 --end_date 20260723 --mode baostock
echo.

echo ========================================
echo 数据下载完成！
echo 数据已保存到: %PROJECT_DIR%\data\store\
echo ========================================

pause