# RunPod Persistent Server Setup

## 1. SSH into your RunPod pod

```bash
ssh kibsqb7yznbj7c-64411df5@ssh.runpod.io -i ~/.ssh/id_ed25519
```

## 2. Clone the repository

```bash
cd /workspace
git clone https://github.com/TrentConley/serverless_worker.git
cd serverless_worker
```

## 3. Set environment variables

Create `/workspace/.env` file:

```bash
cat > /workspace/.env << 'EOF'
R2_ENDPOINT_URL=https://52df42bc9560097648dbd0cd885e08d5.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=a62246b01ea4f7082d92eb6ccfd41b40
R2_SECRET_ACCESS_KEY=f9c66ab00cbf08adbe30a14a97fb47a4219b02c5b485fce18f73696875bb039b
EOF
```

Load them:
```bash
export $(cat /workspace/.env | xargs)
```

## 4. Install dependencies

```bash
pip install -r requirements.txt
```

## 5. Download test dataset (one-time)

The server will auto-download on first run, but you can pre-download:

```bash
python3 -c "
import os
os.environ['R2_ENDPOINT_URL'] = 'https://52df42bc9560097648dbd0cd885e08d5.r2.cloudflarestorage.com'
os.environ['R2_ACCESS_KEY_ID'] = 'a62246b01ea4f7082d92eb6ccfd41b40'
os.environ['R2_SECRET_ACCESS_KEY'] = 'f9c66ab00cbf08adbe30a14a97fb47a4219b02c5b485fce18f73696875bb039b'

import boto3
s3 = boto3.client('s3', endpoint_url=os.environ['R2_ENDPOINT_URL'], 
                  aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
                  aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
                  region_name='auto')

print('Downloading test dataset...')
s3.download_file('chess', 'private/dataset_test.tar.gz', '/tmp/dataset_test.tar.gz')
print('Extracting...')
import subprocess
subprocess.run(['tar', '-xzf', '/tmp/dataset_test.tar.gz', '-C', '/workspace'])
print('Done!')
"
```

## 6. Start the API server

### Option A: Run in foreground (for testing)

```bash
python3 api_server.py
```

### Option B: Run in background (persistent)

```bash
nohup python3 api_server.py > /workspace/api_server.log 2>&1 &
echo $! > /workspace/api_server.pid
```

To stop:
```bash
kill $(cat /workspace/api_server.pid)
```

### Option C: Use screen (recommended)

```bash
screen -S chess-api
python3 api_server.py
# Press Ctrl+A then D to detach
```

To reattach:
```bash
screen -r chess-api
```

## 7. Test the server

```bash
curl http://localhost:8000/
```

Should return:
```json
{
  "service": "Chess Evaluation API",
  "status": "running",
  "version": "1.0",
  "active_jobs": 0
}
```

## 8. Get the public URL

In RunPod dashboard:
1. Go to your pod
2. Click "Connect" → "HTTP Service"
3. Note the public URL (format: `https://xyz-8000.proxy.runpod.net`)

## 9. Update Railway Environment Variable

Add to Railway:
```
RUNPOD_API_URL=https://xyz-8000.proxy.runpod.net
```

(Remove `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT_ID` - no longer needed)

## API Endpoints

### POST /evaluate
Submit a job
```json
{
  "submission_id": 123,
  "submission_s3_key": "submissions/User/timestamp/file.tar.gz",
  "full_name": "User Name",
  "quick_test": false
}
```

Returns:
```json
{
  "job_id": "uuid-here",
  "status": "queued",
  "message": "Evaluation job submitted successfully"
}
```

### GET /status/{job_id}
Check job status

Returns:
```json
{
  "job_id": "uuid",
  "status": "queued|processing|completed|failed",
  "submission_id": 123,
  "full_name": "User Name",
  "created_at": "2025-11-02T...",
  "started_at": "2025-11-02T...",
  "completed_at": "2025-11-02T...",
  "results": {...},  // Only when completed
  "error": "..."     // Only when failed
}
```

### DELETE /job/{job_id}
Delete job after Railway retrieves results

### GET /jobs
List all jobs (for debugging)

## Monitoring

### Watch logs:
```bash
tail -f /workspace/api_server.log
```

### Check active jobs:
```bash
curl http://localhost:8000/jobs
```

### Restart server:
```bash
kill $(cat /workspace/api_server.pid)
nohup python3 api_server.py > /workspace/api_server.log 2>&1 &
echo $! > /workspace/api_server.pid
```

## Auto-start on Pod Restart

Add to RunPod's startup script (if available) or use systemd/supervisor
