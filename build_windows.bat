@echo off
setlocal
cd /d %~dp0
py -3.11 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
where choco >nul 2>nul
if errorlevel 1 (
  echo Chocolatey fehlt. Bitte Tesseract-OCR fuer Windows installieren oder den GitHub-Build verwenden.
  pause
  exit /b 1
)
choco install tesseract --yes --no-progress
if not exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
  echo Tesseract wurde nicht am erwarteten Ort gefunden.
  pause
  exit /b 1
)
pyinstaller --noconfirm --clean --onefile --windowed --name AtlasMonsterImporter ^
  --add-binary "C:\Program Files\Tesseract-OCR\tesseract.exe;." ^
  --add-data "C:\Program Files\Tesseract-OCR\tessdata;tessdata" ^
  atlas_importer.py
 echo.
echo Fertig: dist\AtlasMonsterImporter.exe
pause
