@echo off
setlocal
cd /d %~dp0
py -3.11 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
where tesseract >nul 2>nul
if errorlevel 1 (
  echo Tesseract-OCR wurde nicht gefunden. Bitte Tesseract fuer Windows mit deu und eng Sprachdaten installieren.
  echo https://github.com/UB-Mannheim/tesseract/wiki
  pause
  exit /b 1
)
set TESS=%ProgramFiles%\Tesseract-OCR
if not exist "%TESS%\tesseract.exe" for %%I in (tesseract.exe) do set TESS=%%~$PATH:I
pyinstaller --noconfirm --clean --onefile --windowed --name AtlasMonsterImporter ^
  --add-binary "%TESS%\tesseract.exe;." ^
  --add-data "%ProgramFiles%\Tesseract-OCR\tessdata;tessdata" ^
  atlas_importer.py
 echo.
echo Fertig: dist\AtlasMonsterImporter.exe
pause
