@echo off
TITLE Resource Sharing Forms Processor - SANDBOX WATCH MODE

echo ========================================
echo RESOURCE SHARING FORMS PROCESSOR
echo SANDBOX - WATCH MODE
echo ========================================
echo.
echo Monitoring input folder for new TSV files...
echo Checking every 60 seconds (configurable in config)
echo Press Ctrl+C to stop monitoring
echo.

REM Change to the standalone repository directory
cd /d D:\Scripts\DevSandbox\Alma-RS-lending-request-automation

REM Verify we're in the right place
echo Working directory: %CD%
echo.

REM Run using Poetry (no PYTHONPATH needed)
poetry run python resource_sharing_forms_processor.py --config config\rs_forms_config.json --watch --live

pause
