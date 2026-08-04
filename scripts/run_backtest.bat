@echo off
REM 超短策略回测一键运行脚本

echo ========================================
echo 超短量化策略回测系统
echo ========================================
echo.

set PYTHON_EXE=D:\anaconda\envs\ultra_short_310\python.exe
set PROJECT_DIR=e:\Quantitative_trading\DragonTrading

if not exist "%PYTHON_EXE%" (
    echo [错误] Python环境不存在: %PYTHON_EXE%
    pause
    exit /b 1
)

echo [1/3] 检查Python版本...
"%PYTHON_EXE%" --version
echo.

echo [2/3] 检查CSV数据是否存在...
cd /d "%PROJECT_DIR%"
set HAS_DATA=0
for %%f in (data\store\limit_up_baostock_*.csv) do set HAS_DATA=1
if %HAS_DATA%==0 (
    for %%f in (data\store\limit_up_*.csv) do set HAS_DATA=1
)
if %HAS_DATA%==1 (
    echo [OK] CSV数据已存在
    dir data\store\*.csv 2>nul
) else (
    echo [警告] CSV数据不存在，请先运行"下载数据.bat"
)
echo.

echo [3/3] 开始运行回测...
echo ========================================
"%PYTHON_EXE%" scripts/run_backtest.py --start 20260301 --end 20260723 --capital 100000
echo.

echo ========================================
echo 回测完成！
echo 结果已保存到 data\ 目录
echo ========================================

pause