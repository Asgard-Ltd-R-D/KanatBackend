python3 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip pyinstaller
rm -rf build dist
pyinstaller --onefile --clean --name composer composer.py
