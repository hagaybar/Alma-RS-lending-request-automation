@echo off
REM ========================================
REM Resource Sharing Forms Processor
REM Single-Run Mode (SANDBOX)
REM Run by the task "RS SB Lending-Borrowing (on demand)", which has no
REM schedule since 2026-11-25: start it by hand when testing
REM Lock file prevents overlapping executions
REM ========================================

cd /d D:\Scripts\DevSandbox\Alma-RS-lending-request-automation

poetry run python resource_sharing_forms_processor.py --config config\tests-config.json --live
exit /b %ERRORLEVEL%
