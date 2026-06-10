#!/usr/bin/env python3
"""
Fetch and run a past submission from R2

Usage:
    python fetch_and_run_submission.py --list                    # List all submissions
    python fetch_and_run_submission.py --name Clara              # Find and run Clara's latest submission
    python fetch_and_run_submission.py --key submissions/...     # Run specific submission by S3 key
"""
import os
import sys
import json
import subprocess
import tempfile
import argparse
from pathlib import Path

import boto3

# R2 Configuration - load from environment
R2_ENDPOINT = os.environ.get('R2_ENDPOINT_URL')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_BUCKET = 'chess'

# Test dataset location
TEST_DATASET_PATH = '/workspace/dataset_test'

def get_s3_client():
    """Initialize S3 client for R2"""
    if not all([R2_ENDPOINT, R2_ACCESS_KEY, R2_SECRET_KEY]):
        print("ERROR: Missing R2 environment variables")
        print("Required: R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY")
        sys.exit(1)
    
    return boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name='auto'
    )


def list_submissions(s3_client, name_filter=None):
    """List all submissions in R2, optionally filtered by name"""
    print(f"Listing submissions in s3://{R2_BUCKET}/submissions/...")
    
    paginator = s3_client.get_paginator('list_objects_v2')
    submissions = []
    
    for page in paginator.paginate(Bucket=R2_BUCKET, Prefix='submissions/'):
        for obj in page.get('Contents', []):
            key = obj['Key']
            size = obj['Size']
            last_modified = obj['LastModified']
            
            # Parse the key: submissions/{name}/{timestamp}/file.tar.gz
            parts = key.split('/')
            if len(parts) >= 3:
                name = parts[1].replace('_', ' ')
                timestamp = parts[2] if len(parts) > 2 else ''
                
                if name_filter and name_filter.lower() not in name.lower():
                    continue
                
                submissions.append({
                    'key': key,
                    'name': name,
                    'timestamp': timestamp,
                    'size': size,
                    'last_modified': last_modified
                })
    
    return submissions


def download_submission(s3_client, s3_key, local_dir):
    """Download and extract submission"""
    tarball_path = local_dir / 'submission.tar.gz'
    
    print(f"Downloading {s3_key}...")
    s3_client.download_file(R2_BUCKET, s3_key, str(tarball_path))
    print(f"Downloaded: {tarball_path.stat().st_size / 1024:.2f} KB")
    
    # Extract
    submission_dir = local_dir / 'submission'
    submission_dir.mkdir()
    
    print("Extracting...")
    subprocess.run(
        ['tar', '--no-same-owner', '-xzf', str(tarball_path), '-C', str(submission_dir)],
        check=True
    )
    
    # List contents
    print(f"\nSubmission contents:")
    for f in submission_dir.rglob('*'):
        if f.is_file():
            rel_path = f.relative_to(submission_dir)
            print(f"  {rel_path} ({f.stat().st_size / 1024:.2f} KB)")
    
    return submission_dir


def run_evaluation(submission_dir, test_dataset_path, max_samples=100):
    """Run evaluation on the submission"""
    eval_script = Path(__file__).parent / 'evaluate.py'
    result_file = submission_dir / 'results.json'
    
    cmd = [
        'python3',
        str(eval_script),
        str(submission_dir),
        test_dataset_path,
        '-o', str(result_file),
        '-n', str(max_samples)
    ]
    
    print(f"\nRunning evaluation with {max_samples} samples...")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 60)
    
    try:
        subprocess.run(cmd, check=True)
        
        # Read and display results
        with open(result_file) as f:
            results = json.load(f)
        
        return results
    except subprocess.CalledProcessError as e:
        print(f"Evaluation failed: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Fetch and run a past submission from R2")
    parser.add_argument('--list', action='store_true', help="List all submissions")
    parser.add_argument('--name', type=str, help="Filter by candidate name (partial match)")
    parser.add_argument('--key', type=str, help="Specific S3 key to run")
    parser.add_argument('--samples', type=int, default=100, help="Number of samples for evaluation (default: 100)")
    parser.add_argument('--full', action='store_true', help="Run full evaluation (all samples)")
    
    args = parser.parse_args()
    
    s3_client = get_s3_client()
    
    if args.list or (args.name and not args.key):
        # List submissions
        submissions = list_submissions(s3_client, args.name)
        
        if not submissions:
            print("No submissions found")
            return
        
        print(f"\nFound {len(submissions)} submission(s):\n")
        for i, sub in enumerate(submissions, 1):
            print(f"{i}. {sub['name']}")
            print(f"   Key: {sub['key']}")
            print(f"   Size: {sub['size'] / 1024:.2f} KB")
            print(f"   Modified: {sub['last_modified']}")
            print()
        
        if not args.name:
            return
        
        # If filtering by name, use the most recent one
        if submissions:
            # Sort by timestamp (newest first)
            submissions.sort(key=lambda x: x['timestamp'], reverse=True)
            selected = submissions[0]
            print(f"Selected most recent submission for '{args.name}': {selected['key']}")
            args.key = selected['key']
    
    if args.key:
        # Download and run
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            submission_dir = download_submission(s3_client, args.key, temp_path)
            
            # Check for predict.py
            if not (submission_dir / 'predict.py').exists():
                print("ERROR: predict.py not found in submission")
                return
            
            # Install requirements if present
            requirements_txt = submission_dir / 'requirements.txt'
            if requirements_txt.exists():
                print("\nInstalling dependencies...")
                subprocess.run(
                    ['pip', 'install', '-q', '-r', str(requirements_txt)],
                    check=True
                )
            
            # Check test dataset
            if not Path(TEST_DATASET_PATH).exists():
                print(f"ERROR: Test dataset not found at {TEST_DATASET_PATH}")
                print("Please ensure the test dataset is available")
                return
            
            # Run evaluation
            max_samples = None if args.full else args.samples
            results = run_evaluation(submission_dir, TEST_DATASET_PATH, max_samples or 100)
            
            if results:
                print("\n" + "=" * 60)
                print("EVALUATION COMPLETE")
                print("=" * 60)
                metrics = results['metrics']
                print(f"Accuracy:           {metrics['accuracy']:.2%}")
                print(f"Avg Piece Accuracy: {metrics['avg_piece_accuracy']:.2%}")
                print(f"Total Images:       {metrics['total_images']}")
                print(f"Correct:            {metrics['correct_predictions']}")
                print(f"Avg Time/Image:     {metrics['avg_inference_time']:.4f}s")
                print("=" * 60)


if __name__ == '__main__':
    main()
