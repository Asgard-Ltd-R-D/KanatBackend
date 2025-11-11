#!/bin/bash
set -e

export COPYFILE_DISABLE=1

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

copy_with_progress() {
    local src="$1"
    local dest="$2"
    local label="$3"

    if [ -z "$label" ]; then
        label="Copying ${src}"
    fi

    if [ -f "$src" ]; then
        mkdir -p "$(dirname "$dest")"
        printf "%s: 0%%" "$label"
        cp "$src" "$dest"
        printf "\r%s: 100%%\n" "$label"
        return
    fi

    if [ -d "$src" ]; then
        mkdir -p "$dest"

        # Ensure directory structure exists first
        while IFS= read -r -d '' dir; do
            local rel="${dir#$src/}"
            mkdir -p "$dest/$rel"
        done < <(find "$src" -type d -print0)

        local total
        total=$(find "$src" -type f | wc -l | tr -d ' ')
        if [ "${total}" -eq 0 ]; then
            printf "%s: 100%%\n" "$label"
            return
        fi

        local count=0
        while IFS= read -r -d '' file; do
            local rel="${file#$src/}"
            local target="$dest/$rel"
            mkdir -p "$(dirname "$target")"
            cp "$file" "$target"
            count=$((count + 1))
            local percent=$((count * 100 / total))
            printf "\r%s: %d%% (%d/%d)" "$label" "$percent" "$count" "$total"
        done < <(find "$src" -type f -print0)
        printf "\n"
        return
    fi

    cp "$src" "$dest"
}

PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi

# ----------------- CLEAN MODE -----------------
if [ "$1" = "clean" ]; then
    echo -e "${BLUE}=== Cleaning build artifacts ===${NC}"

    if [ -f "./composer" ]; then
        echo "Removing composer executable..."
        rm -f ./composer
        echo -e "${GREEN}✓ Removed composer${NC}"
    fi

    if [ -f "./installer.run" ]; then
        echo "Removing installer.run..."
        rm -f ./installer.run
        echo -e "${GREEN}✓ Removed installer.run${NC}"
    fi

    if [ -d "./artifacts" ]; then
        echo "Removing artifacts directory..."
        rm -rf ./artifacts
        echo -e "${GREEN}✓ Removed artifacts directory${NC}"
    fi

    if [ -d "./.venv" ]; then
        echo "Removing .venv directory..."
        rm -rf ./.venv
        echo -e "${GREEN}✓ Removed .venv directory${NC}"
    fi

    if [ -d "./.pyi_spec" ]; then
        echo "Removing .pyi_spec directory..."
        rm -rf ./.pyi_spec
        echo -e "${GREEN}✓ Removed .pyi_spec directory${NC}"
    fi

    if [ -d "./.pyi_build" ]; then
        echo "Removing .pyi_build directory..."
        rm -rf ./.pyi_build
        echo -e "${GREEN}✓ Removed .pyi_build directory${NC}"
    fi

    echo ""
    echo -e "${GREEN}✓ Clean complete!${NC}"
    exit 0
fi

# ----------------- ARG VALIDATION -----------------
if [ $# -eq 0 ]; then
    echo -e "${RED}Error: OS platform argument required${NC}"
    echo ""
    echo "Usage:"
    echo "  $0 <OS_PLATFORM>"
    echo "  $0 clean"
    echo ""
    echo "Available OS platforms:"
    echo "  1  win-x64         - Windows 64-bit"
    echo "  2  linux-x64       - Linux 64-bit"
    echo "  3  linux-musl-x64  - Linux 64-bit (musl)"
    echo "  4  osx-arm64       - macOS ARM64 (Apple Silicon)"
    echo "  5  linux-arm64     - Linux ARM64"
    echo "  6  win-arm64       - Windows ARM64"
    echo "  7  osx-x64         - macOS x64 (Intel)"
    echo ""
    echo "Examples:"
    echo "  $0 4"
    echo "  $0 osx-arm64"
    echo "  $0 linux-x64"
    echo "  $0 win-x64"
    echo "  $0 clean        # Remove all build artifacts"
    echo ""
    exit 1
fi

OS_PLATFORM="$1"

case "$OS_PLATFORM" in
    1) OS_PLATFORM="win-x64" ;;
    2) OS_PLATFORM="linux-x64" ;;
    3) OS_PLATFORM="linux-musl-x64" ;;
    4) OS_PLATFORM="osx-arm64" ;;
    5) OS_PLATFORM="linux-arm64" ;;
    6) OS_PLATFORM="win-arm64" ;;
    7) OS_PLATFORM="osx-x64" ;;
esac
VALID_PLATFORMS=("win-x64" "linux-x64" "linux-musl-x64" "osx-arm64" "linux-arm64" "win-arm64" "osx-x64")

VALID=false
for platform in "${VALID_PLATFORMS[@]}"; do
    if [ "$platform" = "$OS_PLATFORM" ]; then
        VALID=true
        break
    fi
done

if [ "$VALID" = false ]; then
    echo -e "${RED}Error: Invalid OS platform: $OS_PLATFORM${NC}"
    echo ""
    echo "Available OS platforms:"
    echo "  1  win-x64         - Windows 64-bit"
    echo "  2  linux-x64       - Linux 64-bit"
    echo "  3  linux-musl-x64  - Linux 64-bit (musl)"
    echo "  4  osx-arm64       - macOS ARM64 (Apple Silicon)"
    echo "  5  linux-arm64     - Linux ARM64"
    echo "  6  win-arm64       - Windows ARM64"
    echo "  7  osx-x64         - macOS x64 (Intel)"
    echo ""
    exit 1
fi

RID_OVERRIDE="$OS_PLATFORM"
export KANAT_TARGET_RID="$RID_OVERRIDE"
export KANAT_BUILD_PLATFORM="$OS_PLATFORM"
if [[ "$OS_PLATFORM" == "linux-x64" || "$OS_PLATFORM" == "linux-arm64" ]]; then
    export KANAT_DOCKER_PLATFORMS="${KANAT_DOCKER_PLATFORMS:-linux/amd64,linux/arm64}"
fi

echo -e "${BLUE}=== Building Artifacts for $OS_PLATFORM ===${NC}"
echo ""

# ----------------- STEP 1: composer.py release -----------------
echo -e "${BLUE}Step 1/3: Building release with composer.py${NC}"
echo -e "${YELLOW}Running: ${PYTHON_BIN} composer.py release \"$OS_PLATFORM\"${NC}"
"$PYTHON_BIN" composer.py release "$OS_PLATFORM"
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to build release${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Release built successfully${NC}"
echo ""

# ----------------- STEP 2: PyInstaller composer binary -----------------
echo -e "${BLUE}Step 2/3: Creating composer executable${NC}"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    "$PYTHON_BIN" -m venv .venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo "Using existing virtual environment .venv"
fi

# Activate virtual environment
# shellcheck disable=SC1091
VENV_ACTIVATE=".venv/bin/activate"
if [ ! -f "$VENV_ACTIVATE" ]; then
    VENV_ACTIVATE=".venv/Scripts/activate"
fi
if [ ! -f "$VENV_ACTIVATE" ]; then
    echo -e "${RED}Failed to locate virtual environment activate script${NC}"
    exit 1
fi
# shellcheck disable=SC1090
source "$VENV_ACTIVATE"

echo "Installing PyInstaller (and upgrading pip)..."
"$PYTHON_BIN" -m pip install --upgrade pip pyinstaller --quiet
echo -e "${GREEN}✓ Dependencies installed${NC}"

echo "Cleaning previous builds and PyInstaller cache..."
rm -rf build dist .pyi_build .pyi_spec composer
"$PYTHON_BIN" -m PyInstaller --clean > /dev/null 2>&1 || true

echo "Building composer executable from scratch (no cache)..."
"$PYTHON_BIN" -m PyInstaller --onefile \
  --clean \
  --noconfirm \
  --name composer \
  --distpath . \
  --workpath .pyi_build \
  --specpath .pyi_spec \
  --log-level=WARN \
  composer.py

if [ ! -f "./composer" ]; then
    echo -e "${RED}Failed to create composer executable${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Composer executable created${NC}"
echo ""

# ----------------- STEP 3: Build installer.run -----------------
echo -e "${BLUE}Step 3/3: Creating installer.run${NC}"

INSTALLER_FILE="installer.run"

if [ -f "$INSTALLER_FILE" ]; then
    echo "Removing existing installer.run..."
    rm -f "$INSTALLER_FILE"
fi

TEMP_DIR=$(mktemp -d)
INSTALL_DIR="$TEMP_DIR/installer"

mkdir -p "$INSTALL_DIR"

echo "Copying files into installer image..."
copy_with_progress Composer_cli/INSTALL_README.md "$INSTALL_DIR/README.md" "Copying Composer README"
copy_with_progress composer "$INSTALL_DIR/composer" "Copying composer binary"
copy_with_progress artifacts "$INSTALL_DIR/artifacts" "Copying artifacts directory"

echo "Copying Docker Compose files and QuestDB Dockerfile..."
copy_with_progress docker-compose.dev.yml "$INSTALL_DIR/docker-compose.dev.yml" "Copying docker-compose.dev.yml"
copy_with_progress docker-compose.prod.yml "$INSTALL_DIR/docker-compose.prod.yml" "Copying docker-compose.prod.yml"
copy_with_progress QuestDB "$INSTALL_DIR/QuestDB" "Copying QuestDB directory"

# Clear releases directory to keep composer build-on-demand
rm -rf "$INSTALL_DIR/artifacts/releases"
mkdir -p "$INSTALL_DIR/artifacts/releases"

# Clean up nested empty artifacts/QuestDB dirs inside the payload
# (but keep the top-level ones we just created)
echo "Cleaning nested empty artifacts/QuestDB directories inside installer image..."
find "$INSTALL_DIR" \
  -type d \( -name artifacts -o -name QuestDB \) \
  ! -path "$INSTALL_DIR/artifacts" \
  ! -path "$INSTALL_DIR/QuestDB" \
  -empty -print -delete

chmod +x "$INSTALL_DIR/composer"

echo "Embedding installer logic into installer.run..."

# --------- Self-extracting installer body with UX sugar ---------
cat > "$INSTALLER_FILE" << 'INSTALLER_EOF'
#!/bin/bash
# Self-extracting installer for BackendApplication

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

check_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        error "Required command '$cmd' is not installed or not in PATH."
        echo "Please install it and run the installer again."
        exit 1
    fi
}

echo -e "${BLUE}=== BackendApplication Installer ===${NC}"
echo

# Step 1: Pre-flight checks
echo -e "${BLUE}Step 1/3: Pre-flight checks${NC}"
check_cmd python3
check_cmd tar
ok "All required tools found (python3, tar)"
echo

# Determine base extraction directory (current directory by default)
BASE_DIR="${1:-.}"
info "Base directory: $BASE_DIR"

# Step 2: Prepare installation directory
echo -e "${BLUE}Step 2/3: Preparing installation directory${NC}"

EXTRACT_DIR="$BASE_DIR/BackendApplication"

if [ -d "$EXTRACT_DIR" ]; then
    warn "Directory $EXTRACT_DIR already exists."
    echo "To avoid overwriting existing files, please:"
    echo "  - Remove the directory: rm -rf \"$EXTRACT_DIR\""
    echo "  - Or choose a different base directory when running the installer."
    echo
    echo "Example:"
    echo "  ./installer.run /opt"
    exit 1
fi

info "Creating directory: $EXTRACT_DIR"
mkdir -p "$EXTRACT_DIR"
ok "Installation directory prepared"
echo

# Get the line number where the archive starts
ARCHIVE_START=$(awk '/^__ARCHIVE_BELOW__/ {print NR + 1; exit 0; }' "$0")

# Step 3: Extract files
echo -e "${BLUE}Step 3/3: Extracting files${NC}"
info "Extracting files to: $EXTRACT_DIR"

ARCHIVE_TEMP=$(mktemp -d)
tail -n +$ARCHIVE_START "$0" > "$ARCHIVE_TEMP/archive.tar.gz"

python3 - "$ARCHIVE_TEMP/archive.tar.gz" "$EXTRACT_DIR" <<'PY'
import sys
import tarfile

archive_path, target_dir = sys.argv[1:3]

with tarfile.open(archive_path, "r:gz") as archive:
    members = archive.getmembers()
    total = len(members) or 1
    bar_len = 40

    for idx, member in enumerate(members, 1):
        archive.extract(member, path=target_dir)
        percent = int(idx * 100 / total)
        done = int(bar_len * percent / 100)
        bar = "#" * done + "-" * (bar_len - done)
        sys.stdout.write(f"\r[{bar}] {percent:3d}% ({idx}/{total})")
        sys.stdout.flush()

print()
PY

rm -rf "$ARCHIVE_TEMP"
ok "Files extracted successfully"
echo

echo -e "${GREEN}✓ Installation complete!${NC}"
echo
echo "Installed to: $EXTRACT_DIR"
echo
echo "Contents:"
echo "  - README.md (Composer usage guide)"
echo "  - composer (executable)"
echo "  - artifacts/ (directory with releases, packages, docker-compose files, QuestDB)"
echo
echo "Quick start:"
echo "  cd \"$EXTRACT_DIR\""
echo "  ./composer --help"
echo
echo "Tip: You can re-run the installer to a different location by passing a base directory, e.g.:"
echo "  ./installer.run /opt"
echo
echo "Thank you for installing BackendApplication!"
echo

exit 0

__ARCHIVE_BELOW__
INSTALLER_EOF

# Create tar archive of the installer directory contents (not the directory itself)
cd "$INSTALL_DIR"
tar -czf "$TEMP_DIR/installer.tar.gz" .
cd - > /dev/null

# Append the archive to the installer script
cat "$TEMP_DIR/installer.tar.gz" >> "$INSTALLER_FILE"

chmod +x "$INSTALLER_FILE"

# Cleanup build-time bits
deactivate || true
rm -rf "$TEMP_DIR" .pyi_build .pyi_spec build dist composer .venv

echo ""
echo -e "${GREEN}✓ installer.run created successfully${NC}"
echo ""
echo -e "${BLUE}Installation file: ${GREEN}$INSTALLER_FILE${NC}"
echo -e "${BLUE}Platform: ${GREEN}$OS_PLATFORM${NC}"
echo ""
echo "The installer contains:"
echo "  - README.md (root)"
echo "  - DEPLOY_README.md (root)"
echo "  - composer (executable, root)"
echo "  - artifacts/ (directory with:)"
echo "    - releases/ (DLL builds)"
echo "    - packages/ (release tars)"
echo "    - docker-compose.dev.yml"
echo "    - docker-compose.prod.yml"
echo "    - QuestDB/ (Dockerfile)"
echo ""
echo "To install, run:"
echo "  ./installer.run [base_directory]"
echo ""
echo "Files will be extracted to: <base_directory>/BackendApplication/"
echo "If no base directory is specified, files will be extracted to: ./BackendApplication/"
echo ""

FINAL_INSTALLER_DIR="artifacts/installers/${OS_PLATFORM}"
FINAL_INSTALLER_NAME="installer-${OS_PLATFORM}.run"
mkdir -p "$FINAL_INSTALLER_DIR"
cp "$INSTALLER_FILE" "$FINAL_INSTALLER_DIR/$FINAL_INSTALLER_NAME"

echo -e "${BLUE}Installer copied to artifacts: ${GREEN}${FINAL_INSTALLER_DIR}/${FINAL_INSTALLER_NAME}${NC}"
echo ""
