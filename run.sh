#!/bin/bash

case "$1" in
    start)
        echo "Killing any process on port 5000..."
        fuser -k 5000/tcp 2>/dev/null || true
        sleep 1
        echo "Starting Flask app..."
        python app.py
        ;;
    *)
        echo "Usage: ./run.sh start"
        exit 1
        ;;
esac
