# Chess Evaluation - RunPod Serverless Worker

This directory contains the serverless GPU worker for running chess position evaluations.

## Repository Structure

serverless_worker/
├── handler.py          # RunPod serverless handler
├── evaluate.py         # Evaluation script (copied from main repo)
├── Dockerfile          # Docker image for RunPod
├── requirements.txt    # Python dependencies
└── README.txt          # This file

## Setup Instructions

### 1. Upload Test Dataset to R2

From the main repository:

```bash
# Create tarball of test dataset
tar -czf dataset_test.tar.gz dataset_test/

# Upload to R2 (private location)
python upload_to_r2.py dataset_test.tar.gz private/dataset_test.tar.gz
```

### 2. Build and Push Docker Image

```bash
cd serverless_worker

# Build the image
docker build -t your-dockerhub-username/chess-eval:latest .

# Push to Docker Hub (RunPod pulls from here)
docker login
docker push your-dockerhub-username/chess-eval:latest
```

### 3. Create RunPod Serverless Endpoint

Go to RunPod Dashboard → Serverless → Create Endpoint

**Configuration:**
- **Image**: your-dockerhub-username/chess-eval:latest
- **GPU**: A4000 or better (16GB VRAM recommended)
- **Container Disk**: 20 GB
- **Volume Size**: 50 GB (for caching test dataset)
- **Environment Variables**:
  - R2_ENDPOINT_URL=https://...
  - R2_ACCESS_KEY_ID=...
  - R2_SECRET_ACCESS_KEY=...
  - R2_BUCKET_NAME=chess

**Advanced Settings:**
- Max Workers: 3
- Idle Timeout: 30 seconds
- Execution Timeout: 900 seconds (15 min)
- Handler: handler.runpod_handler

### 4. Get RunPod API Key

Go to RunPod → Settings → API Keys → Create new key

### 5. Update Main Server

Add to Railway environment variables:
```
RUNPOD_API_KEY=your_api_key_here
RUNPOD_ENDPOINT_ID=your_endpoint_id_here
```

## Job Input Format

The handler expects this JSON input:

```json
{
  "input": {
    "submission_id": 123,
    "submission_s3_key": "submissions/user/timestamp/file.tar.gz",
    "full_name": "John Doe",
    "quick_test": false
  }
}
```

## Job Output Format

Success:
```json
{
  "status": "success",
  "submission_id": 123,
  "results_s3_key": "results/John_Doe/timestamp/results.json",
  "metrics": {
    "accuracy": 0.95,
    "avg_piece_accuracy": 0.98,
    "total_images": 3072,
    ...
  },
  "eval_time": 234.5
}
```

Error:
```json
{
  "status": "error",
  "error": "Error message",
  "details": "Detailed error information"
}
```

## Testing Locally

```bash
# Set environment variables
export R2_ENDPOINT_URL=...
export R2_ACCESS_KEY_ID=...
export R2_SECRET_ACCESS_KEY=...
export R2_BUCKET_NAME=chess

# Run handler
python handler.py
```

## Cost Estimation

RunPod Serverless pricing (approximate):
- A4000 GPU: ~$0.40/hour when active
- 15 minute evaluation: ~$0.10 per submission
- Idle time: No charge
- Network: Free egress to Cloudflare R2

For 100 submissions/month: ~$10-15

## Architecture Flow

1. User uploads submission → Railway server
2. Railway uploads to R2 → Creates database record
3. Railway triggers RunPod job via API
4. RunPod worker:
   - Downloads submission from R2
   - Downloads test dataset (cached after first run)
   - Runs evaluation on GPU
   - Uploads results to R2
5. Railway webhook receives completion
6. Railway updates database with results
7. User sees results on frontend
