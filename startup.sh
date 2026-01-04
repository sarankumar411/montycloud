#!/bin/bash
# Startup script for Image Upload Service

set -e

echo "=========================================="
echo "Image Upload Service - Startup Script"
echo "=========================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed"
    exit 1
fi

echo "✓ Python 3 found: $(python3 --version)"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "⚠️  Docker is not installed. LocalStack won't start."
    echo "Please install Docker to use LocalStack"
else
    echo "✓ Docker found: $(docker --version)"
    
    # Check if Docker daemon is running
    if ! docker info > /dev/null 2>&1; then
        echo "⚠️  Docker daemon is not running"
        echo "Please start Docker daemon"
    else
        echo "✓ Docker daemon is running"
    fi
fi

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env file from .env.example..."
    cp .env.example .env
    echo "✓ Created .env file"
fi

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip install -r requirements.txt
echo "✓ Dependencies installed"

# Start LocalStack
if command -v docker &> /dev/null; then
    echo ""
    echo "Starting LocalStack..."
    docker-compose up -d
    
    # Wait for LocalStack to be ready
    echo "Waiting for LocalStack to be ready..."
    sleep 5
    
    if curl -s http://localhost:4566/_localstack/health > /dev/null 2>&1; then
        echo "✓ LocalStack is ready"
    else
        echo "⚠️  LocalStack may still be starting, continuing anyway..."
    fi
else
    echo ""
    echo "⚠️  Docker not available, skipping LocalStack startup"
fi

# Run tests (optional)
echo ""
read -p "Run unit tests? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    pytest test_app.py -v
fi

# Start the application
echo ""
echo "=========================================="
echo "Starting Image Upload Service API"
echo "=========================================="
echo "API will be available at: http://localhost:5000"
echo "Health check: http://localhost:5000/health"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

python app.py
