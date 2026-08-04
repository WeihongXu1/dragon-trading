@echo off
REM 安装依赖包脚本

echo ========================================
echo 安装akshare、baostock和依赖包
echo ========================================
echo.

set PYTHON_EXE=D:\anaconda\envs\ultra_short_310\python.exe

if not exist "%PYTHON_EXE%" (
    echo [错误] Python环境不存在: %PYTHON_EXE%
    pause
    exit /b 1
)

echo [1/3] 升级pip...
"%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel
echo.

echo [2/3] 安装akshare、baostock、pandas、numpy、openpyxl...
"%PYTHON_EXE%" -m pip install akshare baostock pandas numpy openpyxl -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.

echo [3/3] 验证安装...
"%PYTHON_EXE%" -c "import akshare; import baostock; import pandas; import numpy; print(''); print('========================================'); print('所有依赖包安装成功！'); print('========================================'); print('akshare版本:', akshare.__version__); print('pandas版本:', pandas.__version__); print('numpy版本:', numpy.__version__)"
echo.

pause