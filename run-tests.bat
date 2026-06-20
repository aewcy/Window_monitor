@echo off
REM 后端 API 测试运行脚本
REM 用法: run-tests.bat

echo ============================================
echo   Monitor Server - API Tests
echo ============================================
echo.

D:\python\python.exe -m pytest server/tests/ -v --tb=short

echo.
if %ERRORLEVEL% EQU 0 (
    echo ✅ All tests passed
) else (
    echo ❌ Some tests failed
)
pause
