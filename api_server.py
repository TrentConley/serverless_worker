#!/usr/bin/env python3
"""
RunPod Persistent API Server for Chess Evaluation

This is a FastAPI server that runs continuously on a RunPod pod.
Railway submits jobs via POST and polls for results.
"""
import os
import sys
import json
import time
import subprocess
import tempfile
import shutil
from pathlib import Path
import boto3
import logging
from typing import Dict, Optional
from datetime import datetime
import uuid
import threading

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/workspace/api_server.log')
    ]
)
logger = logging.getLogger(__name__)

logger.info("=" * 80)
logger.info("CHESS EVALUATION API SERVER STARTING UP")
logger.info("=" * 80)

# R2 Configuration
logger.info("Loading R2 configuration...")
try:
    R2_ENDPOINT = os.environ['R2_ENDPOINT_URL']
    R2_ACCESS_KEY = os.environ['R2_ACCESS_KEY_ID']
    R2_SECRET_KEY = os.environ['R2_SECRET_ACCESS_KEY']
    R2_BUCKET = 'chess'
    logger.info(f"✓ R2 configured: bucket={R2_BUCKET}")
except KeyError as e:
    logger.error(f"✗ Missing R2 environment variable: {e}")
    raise

# Test dataset location
TEST_DATASET_CACHE = '/workspace/dataset_test'

# Initialize S3 client
logger.info("Initializing S3 client...")
s3_client = boto3.client(
    's3',
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    region_name='auto'
)
logger.info("✓ S3 client initialized")

# In-memory job storage
jobs: Dict[str, dict] = {}
jobs_lock = threading.Lock()

# FastAPI app
app = FastAPI(title="Chess Evaluation API", version="1.0")


class EvaluationRequest(BaseModel):
    submission_id: int
    submission_s3_key: str
    full_name: str
    quick_test: bool = False


def download_from_r2(s3_key: str, local_path: str):
    """Download file from R2"""
    logger.info(f"Downloading s3://{R2_BUCKET}/{s3_key}")
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    s3_client.download_file(R2_BUCKET, s3_key, local_path)
    size_mb = Path(local_path).stat().st_size / (1024 * 1024)
    logger.info(f"✓ Downloaded {size_mb:.2f} MB")


def upload_to_r2(local_path: str, s3_key: str):
    """Upload file to R2"""
    logger.info(f"Uploading to s3://{R2_BUCKET}/{s3_key}")
    s3_client.upload_file(local_path, R2_BUCKET, s3_key)
    logger.info(f"✓ Upload complete")


def ensure_test_dataset():
    """Ensure test dataset is available"""
    if Path(TEST_DATASET_CACHE).exists():
        image_count = len(list(Path(TEST_DATASET_CACHE).glob('images/*.png')))
        if image_count > 0:
            logger.info(f"✓ Test dataset cached: {image_count} images")
            return TEST_DATASET_CACHE
    
    logger.info("Downloading test dataset from R2...")
    tarball_path = '/tmp/dataset_test.tar.gz'
    download_from_r2('private/dataset_test.tar.gz', tarball_path)
    
    logger.info("Extracting test dataset...")
    Path(TEST_DATASET_CACHE).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ['tar', '--no-same-owner', '-xzf', tarball_path, '-C', str(Path(TEST_DATASET_CACHE).parent)],
        check=True
    )
    
    image_count = len(list(Path(TEST_DATASET_CACHE).glob('images/*.png')))
    logger.info(f"✓ Test dataset ready: {image_count} images")
    os.remove(tarball_path)
    
    return TEST_DATASET_CACHE


def run_evaluation(submission_dir: Path, test_dataset_path: str, quick_test: bool = False) -> dict:
    """Run the evaluation script"""
    logger.info("Starting evaluation...")
    
    result_file = submission_dir / 'results.json'
    eval_script = Path(__file__).parent / 'evaluate.py'
    
    cmd = [
        'python3',
        str(eval_script),
        str(submission_dir),
        test_dataset_path,
        '-o', str(result_file)
    ]
    
    if quick_test:
        cmd.extend(['-n', '100'])
    
    start_time = time.time()
    
    try:
        process = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=900
        )
        
        eval_time = time.time() - start_time
        logger.info(f"✓ Evaluation complete in {eval_time:.1f}s")
        
        with open(result_file) as f:
            results = json.load(f)
        
        return {
            'status': 'success',
            'results': results,
            'eval_time': eval_time
        }
    
    except subprocess.TimeoutExpired:
        logger.error("✗ Evaluation timed out")
        return {
            'status': 'error',
            'error': 'Evaluation timed out after 15 minutes'
        }
    except Exception as e:
        logger.error(f"✗ Evaluation failed: {e}")
        return {
            'status': 'error',
            'error': str(e)
        }


def process_evaluation(job_id: str, request_data: EvaluationRequest):
    """Background task to process an evaluation"""
    logger.info("=" * 80)
    logger.info(f"PROCESSING JOB: {job_id}")
    logger.info(f"Submission ID: {request_data.submission_id}")
    logger.info(f"Candidate: {request_data.full_name}")
    logger.info("=" * 80)
    
    try:
        # Update job status
        with jobs_lock:
            jobs[job_id]['status'] = 'processing'
            jobs[job_id]['started_at'] = datetime.utcnow().isoformat()
        
        # Ensure test dataset
        test_dataset_path = ensure_test_dataset()
        
        # Create temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Download submission
            logger.info(f"Downloading submission: {request_data.submission_s3_key}")
            tarball_path = temp_path / 'submission.tar.gz'
            download_from_r2(request_data.submission_s3_key, str(tarball_path))
            logger.info(f"✓ Downloaded: {tarball_path.stat().st_size / 1024:.2f} KB")
            
            # Extract
            submission_dir = temp_path / 'submission'
            submission_dir.mkdir()
            logger.info("Extracting submission...")
            subprocess.run(
                ['tar', '--no-same-owner', '-xzf', str(tarball_path), '-C', str(submission_dir)],
                check=True,
                capture_output=True
            )
            logger.info("✓ Extraction complete")
            
            # Verify predict.py
            if not (submission_dir / 'predict.py').exists():
                raise FileNotFoundError("predict.py not found in submission")
            
            # Install dependencies
            requirements_txt = submission_dir / 'requirements.txt'
            if requirements_txt.exists():
                logger.info("Installing dependencies...")
                subprocess.run(
                    ['pip', 'install', '-q', '-r', str(requirements_txt)],
                    check=True,
                    timeout=300
                )
                logger.info("✓ Dependencies installed")
            
            # Run evaluation
            eval_result = run_evaluation(submission_dir, test_dataset_path, request_data.quick_test)
            
            if eval_result['status'] != 'success':
                # Evaluation failed
                with jobs_lock:
                    jobs[job_id]['status'] = 'failed'
                    jobs[job_id]['error'] = eval_result.get('error', 'Unknown error')
                    jobs[job_id]['completed_at'] = datetime.utcnow().isoformat()
                logger.error(f"✗ Job {job_id} failed: {eval_result.get('error')}")
                return
            
            # Success - store results
            results = eval_result['results']
            metrics = results['metrics']
            
            logger.info(f"✓ Results: {metrics['accuracy']*100:.2f}% accuracy")
            
            # Upload results to R2
            results_s3_key = f"results/{request_data.full_name.replace(' ', '_')}/{int(time.time())}/results.json"
            results_json = json.dumps(results, indent=2)
            
            logger.info(f"Uploading results to R2: {results_s3_key}")
            s3_client.put_object(
                Bucket=R2_BUCKET,
                Key=results_s3_key,
                Body=results_json.encode('utf-8'),
                ContentType='application/json'
            )
            logger.info("✓ Results uploaded to R2")
            
            # Update job with results
            with jobs_lock:
                jobs[job_id]['status'] = 'completed'
                jobs[job_id]['results'] = {
                    'submission_id': request_data.submission_id,
                    'metrics': metrics,
                    'results_s3_key': results_s3_key,
                    'eval_time': eval_result['eval_time']
                }
                jobs[job_id]['completed_at'] = datetime.utcnow().isoformat()
            
            logger.info(f"✓✓✓ Job {job_id} completed successfully!")
            logger.info("=" * 80)
    
    except Exception as e:
        logger.error(f"✗ Job {job_id} failed with exception: {e}")
        import traceback
        traceback.print_exc()
        
        with jobs_lock:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = str(e)
            jobs[job_id]['completed_at'] = datetime.utcnow().isoformat()


@app.get("/")
def root():
    """Health check"""
    return {
        "service": "Chess Evaluation API",
        "status": "running",
        "version": "1.0",
        "active_jobs": len([j for j in jobs.values() if j['status'] in ['queued', 'processing']])
    }


@app.post("/evaluate")
def submit_evaluation(request: EvaluationRequest, background_tasks: BackgroundTasks):
    """Submit an evaluation job"""
    job_id = str(uuid.uuid4())
    
    logger.info(f"NEW EVALUATION REQUEST: {job_id}")
    logger.info(f"  Submission ID: {request.submission_id}")
    logger.info(f"  S3 Key: {request.submission_s3_key}")
    logger.info(f"  Candidate: {request.full_name}")
    
    # Create job record
    with jobs_lock:
        jobs[job_id] = {
            'job_id': job_id,
            'status': 'queued',
            'submission_id': request.submission_id,
            'full_name': request.full_name,
            'created_at': datetime.utcnow().isoformat(),
            'started_at': None,
            'completed_at': None,
            'results': None,
            'error': None
        }
    
    # Start background processing
    background_tasks.add_task(process_evaluation, job_id, request)
    
    logger.info(f"✓ Job {job_id} queued")
    
    return {
        'job_id': job_id,
        'status': 'queued',
        'message': 'Evaluation job submitted successfully'
    }


@app.get("/status/{job_id}")
def get_job_status(job_id: str):
    """Get status of a job"""
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job = jobs[job_id].copy()
    
    return job


@app.delete("/job/{job_id}")
def delete_job(job_id: str):
    """Delete job results (called by Railway after retrieving)"""
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        
        del jobs[job_id]
    
    logger.info(f"✓ Job {job_id} deleted")
    return {'status': 'deleted'}


@app.get("/jobs")
def list_jobs():
    """List all jobs (for debugging)"""
    with jobs_lock:
        return {
            'total': len(jobs),
            'jobs': list(jobs.values())
        }


if __name__ == "__main__":
    import uvicorn
    
    # Ensure test dataset on startup
    logger.info("Initializing test dataset...")
    ensure_test_dataset()
    
    logger.info("=" * 80)
    logger.info("SERVER READY - Listening on port 8000")
    logger.info("=" * 80)
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
