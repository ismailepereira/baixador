@echo off
chcp 65001 >nul
title Baixador - servidor local
setlocal
set "ROOT=%~dp0"
set "FFMPEG_DIR=%ROOT%bin\ffmpeg"
set "FFMPEG_EXE=%FFMPEG_DIR%\bin\ffmpeg.exe"

REM ---- ffmpeg: baixa local na primeira execucao ----
if not exist "%FFMPEG_EXE%" (
  echo.
  echo [setup] ffmpeg nao encontrado. Baixando ^(~100 MB^)...
  if not exist "%ROOT%bin" mkdir "%ROOT%bin"
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop'; $url='https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'; $zip='%ROOT%bin\ffmpeg.zip'; Write-Host 'Baixando...'; Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing; Write-Host 'Extraindo...'; Expand-Archive -Path $zip -DestinationPath '%ROOT%bin' -Force; $extracted = Get-ChildItem '%ROOT%bin' -Directory ^| Where-Object { $_.Name -like 'ffmpeg-*' } ^| Select-Object -First 1; if (Test-Path '%FFMPEG_DIR%') { Remove-Item '%FFMPEG_DIR%' -Recurse -Force }; Rename-Item $extracted.FullName '%FFMPEG_DIR%'; Remove-Item $zip -Force; Write-Host 'ffmpeg OK.'"
  if errorlevel 1 (
    echo [erro] Falha ao baixar/extrair ffmpeg. Tente manualmente.
    pause
    exit /b 1
  )
)

set "BAIXADOR_FFMPEG=%FFMPEG_EXE%"
set "PATH=%FFMPEG_DIR%\bin;%PATH%"

REM ---- venv + dependencias Python ----
cd /d "%ROOT%server"
if not exist ".venv" (
  echo.
  echo [setup] Criando ambiente virtual...
  python -m venv .venv
  call .venv\Scripts\activate.bat
  echo [setup] Instalando yt-dlp, spotdl, flask...
  python -m pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)

echo.
echo ====================================================
echo  Baixador rodando em http://127.0.0.1:5005
echo  ffmpeg: %FFMPEG_EXE%
echo  Mantenha esta janela aberta. Ctrl+C para parar.
echo ====================================================
echo.
python server.py
pause
