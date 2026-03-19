@echo off
REM ========================================
REM Resource Sharing Forms Processor
REM Scheduled Task - Single-Run Mode (SANDBOX)
REM For testing Task Scheduler setup before production
REM ========================================

cd /d D:\Scripts\DevSandbox\Alma-RS-lending-request-automation

poetry run python resource_sharing_forms_processor.py --config config\rs_forms_config.json --live

exit /b %ERRORLEVEL%
