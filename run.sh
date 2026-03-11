#!/bin/bash

case "$1" in
    start)
        echo "Killing any process on port 5000..."
        fuser -k 5000/tcp 2>/dev/null || true
        sleep 1
        echo "Starting Flask app..."
        python app.py
        ;;
    test)
        echo "Running tests..."
        python -m pytest test_app.py -v --tb=short
        ;;
    lint)
        echo "Running ruff linter..."
        ruff check .
        ;;
    *)
        echo "Usage: ./run.sh {start|test|lint}"
        exit 1
        ;;
esac
