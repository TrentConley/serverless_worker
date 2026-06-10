#!/bin/bash
# RunPod startup script for Chess API
# Add this to RunPod's Docker Command or run manually

cd /workspace/serverless_worker
source venv/bin/activate
pip install -r requirements.txt
# Load environment variables
if [ -f /workspace/.env ]; then
    export $(cat /workspace/.env | xargs)
fi

# Check if already running
if pgrep -f "python3.*api_server.py" > /dev/null; then
    echo "API server already running"
    exit 0
fi

# Start the API server in background
echo "Starting Chess API server..."
nohup python3 /workspace/serverless_worker/api_server.py > /workspace/api_server.log 2>&1 &
echo $! > /workspace/api_server.pid
echo "API server started with PID $(cat /workspace/api_server.pid)"
