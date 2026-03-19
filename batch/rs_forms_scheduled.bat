@echo off
REM ========================================
REM Resource Sharing Forms Processor
REM Scheduled Task - Single-Run Mode (PRODUCTION)
REM Called by Windows Task Scheduler every 1 minute
REM Lock file prevents overlapping executions
REM ========================================

cd /d D:\Scripts\Alma-RS-lending-request-automation

poetry run python resource_sharing_forms_processor.py --config config\rs_forms_config_prod.json --live

exit /b %ERRORLEVEL%
