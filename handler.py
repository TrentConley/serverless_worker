"""
RunPod Serverless Handler for Chess Evaluation

This handler:
1. Downloads submission from R2
2. Downloads test dataset (cached)
3. Runs evaluation
4. Uploads results to R2
5. Updates database
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# R2 Configuration
R2_ENDPOINT = os.environ['R2_ENDPOINT_URL']
R2_ACCESS_KEY = os.environ['R2_ACCESS_KEY_ID']
R2_SECRET_KEY = os.environ['R2_SECRET_ACCESS_KEY']
R2_BUCKET = os.environ.get('R2_BUCKET_NAME', 'chess')

# Test dataset location
TEST_DATASET_PATH = '/workspace/dataset_test'
TEST_DATASET_CACHE = '/runpod-volume/dataset_test' if os.path.exists('/runpod-volume') else '/tmp/dataset_test'

# Initialize S3 client
s3_client = boto3.client(
    's3',
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    region_name='auto'
)


def download_from_r2(s3_key: str, local_path: str):
    """Download file from R2"""
    logger.info(f"Downloading s3://{R2_BUCKET}/{s3_key} to {local_path}")
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    s3_client.download_file(R2_BUCKET, s3_key, local_path)
    size_mb = Path(local_path).stat().st_size / (1024 * 1024)
    logger.info(f"Downloaded {size_mb:.2f} MB")


def upload_to_r2(local_path: str, s3_key: str):
    """Upload file to R2"""
    logger.info(f"Uploading {local_path} to s3://{R2_BUCKET}/{s3_key}")
    s3_client.upload_file(local_path, R2_BUCKET, s3_key)
    logger.info(f"Upload complete")


def upload_string_to_r2(content: str, s3_key: str):
    """Upload string content to R2"""
    logger.info(f"Uploading content to s3://{R2_BUCKET}/{s3_key}")
    s3_client.put_object(
        Bucket=R2_BUCKET,
        Key=s3_key,
        Body=content.encode('utf-8'),
        ContentType='application/json'
    )
    logger.info(f"Upload complete")


def ensure_test_dataset():
    """Download and cache test dataset if not present"""
    if Path(TEST_DATASET_CACHE).exists():
        # Count images to verify
        image_count = len(list(Path(TEST_DATASET_CACHE).glob('images/*.png')))
        if image_count > 0:
            logger.info(f"Test dataset cached: {image_count} images")
            return TEST_DATASET_CACHE
    
    logger.info("Downloading test dataset from R2...")
    tarball_path = '/tmp/dataset_test.tar.gz'
    download_from_r2('private/dataset_test.tar.gz', tarball_path)
    
    logger.info("Extracting test dataset...")
    Path(TEST_DATASET_CACHE).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ['tar', '-xzf', tarball_path, '-C', str(Path(TEST_DATASET_CACHE).parent)],
        check=True
    )
    
    # Verify extraction
    image_count = len(list(Path(TEST_DATASET_CACHE).glob('images/*.png')))
    logger.info(f"Test dataset ready: {image_count} images")
    
    # Cleanup tarball
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
            timeout=900  # 15 min timeout
        )
        
        eval_time = time.time() - start_time
        logger.info(f"Evaluation complete in {eval_time:.1f}s")
        
        # Read results
        with open(result_file) as f:
            results = json.load(f)
        
        return {
            'status': 'success',
            'results': results,
            'eval_time': eval_time
        }
    
    except subprocess.TimeoutExpired:
        logger.error("Evaluation timed out")
        return {
            'status': 'error',
            'error': 'Evaluation timed out (>15 minutes)'
        }
    except subprocess.CalledProcessError as e:
        logger.error(f"Evaluation failed: {e.stderr}")
        return {
            'status': 'error',
            'error': 'Evaluation failed',
            'details': e.stderr
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            'status': 'error',
            'error': str(e)
        }


def handler(job):
    """
    RunPod handler function
    
    Expected job input:
    {
        "submission_id": 123,
        "submission_s3_key": "submissions/user/timestamp/file.tar.gz",
        "full_name": "John Doe",
        "quick_test": false
    }
    """
    job_input = job.get('input', {})
    
    submission_id = job_input.get('submission_id')
    submission_s3_key = job_input.get('submission_s3_key')
    full_name = job_input.get('full_name', 'Unknown')
    quick_test = job_input.get('quick_test', False)
    
    logger.info("="*60)
    logger.info(f"Processing submission ID: {submission_id}")
    logger.info(f"Candidate: {full_name}")
    logger.info(f"Quick test: {quick_test}")
    logger.info("="*60)
    
    if not submission_s3_key:
        return {
            'error': 'Missing submission_s3_key in job input'
        }
    
    try:
        # Ensure test dataset is available
        test_dataset_path = ensure_test_dataset()
        
        # Create temporary directory for submission
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Download submission
            tarball_path = temp_path / 'submission.tar.gz'
            download_from_r2(submission_s3_key, str(tarball_path))
            
            # Extract submission
            submission_dir = temp_path / 'submission'
            submission_dir.mkdir()
            
            logger.info("Extracting submission...")
            subprocess.run(
                ['tar', '-xzf', str(tarball_path), '-C', str(submission_dir)],
                check=True,
                capture_output=True
            )
            
            # Verify predict.py exists
            if not (submission_dir / 'predict.py').exists():
                return {
                    'error': 'predict.py not found in submission'
                }
            
            # Install dependencies
            requirements_txt = submission_dir / 'requirements.txt'
            if requirements_txt.exists():
                logger.info("Installing dependencies...")
                subprocess.run(
                    ['pip', 'install', '-q', '-r', str(requirements_txt)],
                    check=True,
                    timeout=300
                )
            
            # Run evaluation
            eval_result = run_evaluation(submission_dir, test_dataset_path, quick_test)
            
            if eval_result['status'] != 'success':
                return eval_result
            
            results = eval_result['results']
            metrics = results['metrics']
            
            logger.info(f"Results: {metrics['accuracy']*100:.2f}% accuracy")
            
            # Upload results to R2
            results_s3_key = f"results/{full_name}/{int(time.time())}/results.json"
            upload_string_to_r2(json.dumps(results, indent=2), results_s3_key)
            
            logger.info("="*60)
            logger.info("Evaluation complete!")
            logger.info("="*60)
            
            return {
                'status': 'success',
                'submission_id': submission_id,
                'results_s3_key': results_s3_key,
                'metrics': metrics,
                'eval_time': eval_result['eval_time']
            }
    
    except Exception as e:
        logger.error(f"Handler error: {e}", exc_info=True)
        return {
            'error': str(e)
        }


# For RunPod serverless
def runpod_handler(event):
    """Wrapper for RunPod"""
    return handler(event)


# For testing locally
if __name__ == '__main__':
    # Test with mock job
    test_job = {
        'input': {
            'submission_id': 1,
            'submission_s3_key': 'submissions/test/123456/submission.tar.gz',
            'full_name': 'Test User',
            'quick_test': True
        }
    }
    
    result = handler(test_job)
    print(json.dumps(result, indent=2))
