@echo off
REM Activate virtual environment and install package
call .venv\Scripts\activate.bat
pip install -e ".[dev]"
echo.
echo Installation complete! You can now run:
echo   - pytest           (run tests)
echo   - varta-mqtt       (run service)
echo   - pytest --cov     (tests with coverage)
