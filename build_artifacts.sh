#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check for clean argument
if [ "$1" = "clean" ]; then
    echo "Cleaning build artifacts..."
    
    # Remove composer executable
    if [ -f "./composer" ]; then
        echo "Removing composer executable..."
        rm -f ./composer
        echo "✓ Removed composer"
    fi
    
    # Remove installer.run
    if [ -f "./installer.run" ]; then
        echo "Removing installer.run..."
        rm -f ./installer.run
        echo "✓ Removed installer.run"
    fi
    
    # Remove artifacts directory
    if [ -d "./artifacts" ]; then
        echo "Removing artifacts directory..."
        rm -rf ./artifacts
        echo "✓ Removed artifacts directory"
    fi
    
    # Remove .venv directory
    if [ -d "./.venv" ]; then
        echo "Removing .venv directory..."
        rm -rf ./.venv
        echo "✓ Removed .venv directory"
    fi
    
    # Remove .pyi_spec directory
    if [ -d "./.pyi_spec" ]; then
        echo "Removing .pyi_spec directory..."
        rm -rf ./.pyi_spec
        echo "✓ Removed .pyi_spec directory"
    fi
    
    # Remove .pyi_build directory
    if [ -d "./.pyi_build" ]; then
        echo "Removing .pyi_build directory..."
        rm -rf ./.pyi_build
        echo "✓ Removed .pyi_build directory"
    fi
    
    echo ""
    echo "✓ Clean complete!"
    exit 0
fi

# Check for OS argument
if [ $# -eq 0 ]; then
    echo "Error: OS platform argument required"
    echo ""
    echo "Usage:"
    echo "  $0 <OS_PLATFORM>"
    echo "  $0 clean"
    echo ""
    echo "Available OS platforms:"
    echo "  win-x64        - Windows 64-bit"
    echo "  linux-x64      - Linux 64-bit"
    echo "  linux-musl-x64 - Linux 64-bit (musl)"
    echo "  osx-arm64      - macOS ARM64 (Apple Silicon)"
    echo ""
    echo "Examples:"
    echo "  $0 osx-arm64"
    echo "  $0 linux-x64"
    echo "  $0 win-x64"
    echo "  $0 clean        # Remove all build artifacts"
    echo ""
    exit 1
fi

OS_PLATFORM="$1"
VALID_PLATFORMS=("win-x64" "linux-x64" "linux-musl-x64" "osx-arm64")

# Validate OS platform
VALID=false
for platform in "${VALID_PLATFORMS[@]}"; do
    if [ "$platform" = "$OS_PLATFORM" ]; then
        VALID=true
        break
    fi
done

if [ "$VALID" = false ]; then
    echo "Error: Invalid OS platform: $OS_PLATFORM"
    echo ""
    echo "Available OS platforms:"
    echo "  win-x64        - Windows 64-bit"
    echo "  linux-x64      - Linux 64-bit"
    echo "  linux-musl-x64 - Linux 64-bit (musl)"
    echo "  osx-arm64      - macOS ARM64 (Apple Silicon)"
    echo ""
    exit 1
fi

echo -e "${BLUE}=== Building Artifacts for $OS_PLATFORM ===${NC}"

# Step 1: Build release using composer.py
echo -e "${YELLOW}Step 1: Building release with composer.py for $OS_PLATFORM...${NC}"
python3 composer.py release "$OS_PLATFORM"
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to build release${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Release built successfully${NC}"

# Step 2: Create composer executable (internal to this script)
echo -e "${YELLOW}Step 2: Creating composer executable...${NC}"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
echo "Installing PyInstaller..."
python -m pip install --upgrade pip pyinstaller --quiet

# Clean previous builds and PyInstaller cache
echo "Cleaning previous builds and cache..."
rm -rf build dist .pyi_build .pyi_spec composer
# Also clean PyInstaller's global cache
python -m PyInstaller --clean > /dev/null 2>&1 || true

# Build executable from scratch (no cache)
echo "Building composer executable from scratch (no cache)..."
pyinstaller --onefile \
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

# Step 3: Create installer.run file
echo -e "${YELLOW}Step 3: Creating installer.run...${NC}"

INSTALLER_FILE="installer.run"

# Remove existing installer.run if it exists (will be overwritten)
if [ -f "$INSTALLER_FILE" ]; then
    echo "Removing existing installer.run..."
    rm -f "$INSTALLER_FILE"
fi

TEMP_DIR=$(mktemp -d)
INSTALL_DIR="$TEMP_DIR/installer"

# Create installation directory structure
mkdir -p "$INSTALL_DIR"

# Copy files to install directory
echo "Copying files..."
# README.md and DEPLOY_README.md go to root (outside artifacts)
cp README.md "$INSTALL_DIR/"
cp DEPLOY_README.md "$INSTALL_DIR/"
# composer executable goes to root
cp composer "$INSTALL_DIR/"
# Copy artifacts directory (contains releases and packages from composer release)
cp -r artifacts "$INSTALL_DIR/"

# Copy docker-compose files and QuestDB Dockerfile into artifacts directory
echo "Copying Docker Compose files and QuestDB Dockerfile into artifacts..."
cp docker-compose.dev.yml "$INSTALL_DIR/artifacts/"
cp docker-compose.prod.yml "$INSTALL_DIR/artifacts/"
cp -r QuestDB "$INSTALL_DIR/artifacts/"

# Make composer executable
chmod +x "$INSTALL_DIR/composer"

# Create the self-extracting installer.run file
cat > "$INSTALLER_FILE" << 'INSTALLER_EOF'
#!/bin/bash
# Self-extracting installer for BackendApplication

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== BackendApplication Installer ===${NC}"

# Determine base extraction directory (current directory by default)
BASE_DIR="${1:-.}"

# Create BackendApplication directory
EXTRACT_DIR="$BASE_DIR/BackendApplication"

if [ -d "$EXTRACT_DIR" ]; then
    echo "Warning: Directory $EXTRACT_DIR already exists."
    echo "Please remove it or choose a different location."
    exit 1
fi

echo "Creating directory: $EXTRACT_DIR"
mkdir -p "$EXTRACT_DIR"

# Get the line number where the archive starts
ARCHIVE_START=$(awk '/^__ARCHIVE_BELOW__/ {print NR + 1; exit 0; }' "$0")

# Extract the archive directly to the BackendApplication directory
echo -e "${BLUE}Extracting files to $EXTRACT_DIR...${NC}"
tail -n +$ARCHIVE_START "$0" | tar -xz -C "$EXTRACT_DIR"

echo -e "${GREEN}✓ Installation complete!${NC}"
echo ""
echo "Files extracted to: $EXTRACT_DIR"
echo ""
echo "Contents:"
echo "  - README.md"
echo "  - DEPLOY_README.md"
echo "  - composer (executable)"
echo "  - artifacts/ (directory with releases, packages, docker-compose files, QuestDB)"
echo ""
echo "To use composer, run:"
echo "  cd $EXTRACT_DIR"
echo "  ./composer --help"
echo ""
echo "Installation directory: $EXTRACT_DIR"
echo ""

exit 0

__ARCHIVE_BELOW__
INSTALLER_EOF

# Create tar archive of the installer directory contents (not the directory itself)
cd "$INSTALL_DIR"
tar -czf "$TEMP_DIR/installer.tar.gz" .
cd - > /dev/null

# Append the archive to the installer script
cat "$TEMP_DIR/installer.tar.gz" >> "$INSTALLER_FILE"

# Make installer executable
chmod +x "$INSTALLER_FILE"

# Cleanup
rm -rf "$TEMP_DIR"

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

