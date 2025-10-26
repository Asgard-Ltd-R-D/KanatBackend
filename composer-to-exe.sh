python3 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip pyinstaller
pyinstaller --onefile --name composer composer.py
