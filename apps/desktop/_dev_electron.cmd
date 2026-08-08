@echo off
cd /d D:\data\pyProject\dc_agent\dechnicAuditor-agent\apps\desktop
call npm run dev:electron > _electron_restart.log 2>&1
