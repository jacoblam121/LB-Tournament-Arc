#!/bin/bash
# Tournament Bot Manual Test Runner

echo "🧪 Starting Tournament Bot Manual Test Suite..."
echo "📁 Working directory: $(pwd)"
echo "🐍 Python version: $(python3 --version)"
echo ""

# Activate virtual environment
if [ -d "venv" ]; then
    echo "🔧 Activating virtual environment..."
    source venv/bin/activate
    echo "✅ Virtual environment activated"
else
    echo "❌ Virtual environment not found! Please run setup first."
    exit 1
fi

# Check if required dependencies are installed
echo "🔍 Checking dependencies..."
python3 -c "import discord, sqlalchemy, aiosqlite" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ Dependencies verified"
else
    echo "❌ Missing dependencies! Installing..."
    pip install -r requirements.txt
fi

echo ""
echo "🚀 Launching manual test suite..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Run the manual test suite
python3 manual_test.py

echo ""
echo "🏁 Manual test suite completed."