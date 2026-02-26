#!/bin/bash
# Install kitten-say globally.
# Usage: sudo bash install.sh [/path/to/venv/python3]
#
# If no Python path is given, uses the first python3 found with kittentts installed.

set -e

INSTALL_DIR="/usr/local/bin"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Find Python with kittentts
if [ -n "$1" ]; then
    PYTHON="$1"
elif command -v python3 &>/dev/null && python3 -c "import kittentts" 2>/dev/null; then
    PYTHON="$(command -v python3)"
else
    echo "Error: kittentts not found. Install it first:"
    echo "  pip install kittentts"
    echo ""
    echo "Or specify the Python path explicitly:"
    echo "  sudo bash install.sh /path/to/venv/bin/python3"
    exit 1
fi

echo "Installing kitten-say to ${INSTALL_DIR}..."
echo "Using Python: ${PYTHON}"

# Install the Python scripts
cp "${SCRIPT_DIR}/kitten-say.py" "${INSTALL_DIR}/kitten-say.py"
cp "${SCRIPT_DIR}/kitten-tts-daemon" "${INSTALL_DIR}/kitten-tts-daemon"
chmod 755 "${INSTALL_DIR}/kitten-say.py" "${INSTALL_DIR}/kitten-tts-daemon"

# Install the shell wrapper
cat > "${INSTALL_DIR}/kitten-say" << WRAPPER
#!/bin/bash
exec ${PYTHON} ${INSTALL_DIR}/kitten-say.py "\$@"
WRAPPER
chmod 755 "${INSTALL_DIR}/kitten-say"

echo ""
echo "Installed. Usage:"
echo "  kitten-say \"Hello world\""
echo "  kitten-say -v Luna \"Hello world\""
echo "  kitten-say -f report.txt"
echo "  kitten-say --voices"
echo "  kitten-say --stop"
