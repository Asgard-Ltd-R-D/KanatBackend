python3 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip pyinstaller
rm -rf build dist
pyinstaller --onefile --clean --name composer \
  --distpath . \
  --workpath .pyi_build \
  --specpath .pyi_spec \
  composer.py

# now the binary is ./composer
./composer --help
