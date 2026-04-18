@echo off
setlocal

set PROJECT_ROOT=%~dp0
set REPORT_DIR=%PROJECT_ROOT%benchmark_reports

echo [benchmark] project: %PROJECT_ROOT%
echo [benchmark] report_dir: %REPORT_DIR%

python "%PROJECT_ROOT%scripts\fixed_scenario_benchmark.py" --project-path "%PROJECT_ROOT%" --report-dir "%REPORT_DIR%"

echo [benchmark] done
endlocal
