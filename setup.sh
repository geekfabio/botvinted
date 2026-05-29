#!/bin/bash
set -e

echo "=========================================="
echo "🤖 Vinted Alert Bot Setup"
echo "=========================================="

# Update and install dependencies
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip git

# Set up project directories
echo "Creating project directories..."
mkdir -p data logs

# Create and activate virtual environment
echo "Setting up Python virtual environment..."
python3.11 -m venv venv
source venv/bin/activate

# Install Python requirements
echo "Installing Python requirements..."
pip install --upgrade pip
pip install -r requirements.txt

# Copy example configuration files
echo "Copying configuration files..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from example."
else
    echo ".env already exists, skipping."
fi

if [ ! -f config.yaml ]; then
    cp config.example.yaml config.yaml
    echo "Created config.yaml from example."
else
    echo "config.yaml already exists, skipping."
fi

echo "=========================================="
echo "✅ Setup complete!"
echo "Please edit .env and config.yaml with your details."
echo "To run the bot:"
echo "source venv/bin/activate && python bot.py"
echo "=========================================="
