@echo off
:: LockMaker — Windows 10/11 launcher (doble clic)
setlocal
cd /d "%~dp0"
title LockMaker

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo Python 3 no esta instalado.
  echo Descargalo de https://www.python.org/downloads/ y marca "Add python.exe to PATH".
  pause & exit /b 1
)

%PY% -c "import PIL" >nul 2>&1 || (
  echo Instalando Pillow (unica dependencia)...
  %PY% -m pip install --user --quiet pillow
)

echo.
echo  Se abrira el panel de LockMaker. Deja esta ventana abierta mientras lo usas.
echo  (Ctrl+C o cerrar la ventana para salir)
echo.
%PY% lockmaker.py %*
endlocal
