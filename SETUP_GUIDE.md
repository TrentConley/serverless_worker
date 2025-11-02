# RunPod Serverless Setup Guide

## Prerequisites
✅ GitHub repo pushed: https://github.com/TrentConley/serverless_worker
✅ R2 bucket exists: `chess`
✅ Test dataset uploaded to R2: `private/dataset_test.tar.gz`

---

## Step 1: Create RunPod Serverless Endpoint

Go to: **https://www.runpod.io/console/serverless**

Click **"+ New Endpoint"**

---

## Step 2: Template Configuration

### Name
```
SpaceX Chess Evaluation
```

### Container Configuration

**Build Method:** GitHub

**GitHub Repository:**
```
TrentConley/serverless_worker
```

**Branch:**
```
main
```

**Dockerfile Path:**
```
Dockerfile
```

**Build Context:**
```
.
```

**Docker Command:** (leave empty, uses default from Dockerfile)

---

## Step 3: GPU Selection

**Select GPU Types:**
- ✅ RTX A4000 (or better)
- ✅ A5000
- ✅ A6000

**Minimum VRAM:** 16 GB

**Active Workers:** 0 (scales to zero when idle)

---

## Step 4: Storage Configuration

⚠️ **CRITICAL:** Volume is required for dataset caching

**Container Disk:** 20 GB

**Volume (Network Storage):** 50 GB
- ✅ Enable this
- Used to cache the 665MB test dataset
- First run downloads it, subsequent runs use cache

---

## Step 5: Environment Variables

Add these **SECRET** environment variables:

```bash
R2_ENDPOINT_URL=https://52df42bc9560097648dbd0cd885e08d5.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=a62246b01ea4f7082d92eb6ccfd41b40
R2_SECRET_ACCESS_KEY=f9c66ab00cbf08adbe30a14a97fb47a4219b02c5b485fce18f73696875bb039b
```

**Note:** `R2_BUCKET_NAME` is NOT needed - it's hardcoded to `chess` in the code

---

## Step 6: Advanced Settings

**Scaling Configuration:**
- **Min Workers:** 0
- **Max Workers:** 3
- **Idle Timeout:** 30 seconds
- **Max Concurrent Requests:** 1

**Execution Settings:**
- **Execution Timeout:** 900 seconds (15 minutes)
- **Max Retries:** 0 ⚠️ **IMPORTANT** - prevents infinite loops on errors

**Webhook:** (leave empty for now)

---

## Step 7: Create & Get Credentials

Click **"Create Endpoint"**

Wait for build to complete (~5-10 minutes)

### Get Endpoint ID
From the endpoint page, copy the **Endpoint ID**
- Format: `xrv0vwtja4iryk` (yours)

### Get API Key
1. Go to **Settings** → **API Keys**
2. Click **"Create API Key"**
3. Copy the key
- Format: `rpa_BBGCVMTGBW24LYJSLQBSC7KOV4DSLIRPOFWI0JWY` (yours)

---

## Step 8: Add Credentials to Railway

Go to your Railway project → Variables

Add these two variables:

```bash
RUNPOD_API_KEY=rpa_BBGCVMTGBW24LYJSLQBSC7KOV4DSLIRPOFWI0JWY
RUNPOD_ENDPOINT_ID=xrv0vwtja4iryk
```

Railway will auto-redeploy.

---

## Step 9: Test the System

### Submit via Railway
1. Go to: https://chessexam-production.up.railway.app
2. Login with your access code
3. Upload `demo_submission.tar.gz`

### Watch the Flow

**Railway Logs:**
```
[YourName] Saved upload: 0.00 MB
[YourName] ✓ Uploaded to R2: submissions/...
[YourName] ✓ RunPod job created: job-xxx
```

**RunPod Dashboard:**
- Job appears in queue
- Worker spins up (if cold start: ~30s)
- Job status: IN_PROGRESS

**RunPod Logs (first run):**
```
Downloading test dataset from R2...
Extracting test dataset...
Test dataset ready: 6144 images
Downloading submission from R2...
Running evaluation...
Evaluation complete in X.Xs
Uploading results to R2...
✓ Success
```

**Future runs:** Dataset already cached, instant

**Railway Dashboard:**
- Results appear automatically
- Can view metrics

---

## Troubleshooting

### Workers Run Forever
**Cause:** Max Retries > 0 and errors occur
**Fix:** Set Max Retries to 0 in Advanced Settings

### 404 Error Downloading Submission
**Cause:** Railway didn't upload to R2 or wrong bucket name
**Check:**
1. Railway logs show "✓ Uploaded to R2"
2. File size > 0 MB
3. Bucket name is `chess` (now hardcoded)

### Test Dataset Download Fails
**Cause:** Missing R2 credentials or wrong endpoint
**Fix:**
1. Verify all 3 R2 env vars set in RunPod
2. Check `private/dataset_test.tar.gz` exists in R2

### Worker Timeout
**Cause:** Evaluation takes > 15 min
**Fix:** Increase Execution Timeout to 1800 (30 min)

---

## How It Works

```
┌─────────────────────────────────────────────────────┐
│ 1. User submits via Railway                        │
│    - File uploaded to R2: submissions/...          │
│    - Database record created                        │
└────────────────┬────────────────────────────────────┘
                 │
                 v
┌─────────────────────────────────────────────────────┐
│ 2. Railway triggers RunPod API                     │
│    POST /v2/xrv0vwtja4iryk/run                     │
│    {                                                │
│      "input": {                                     │
│        "submission_id": 123,                        │
│        "submission_s3_key": "submissions/...",     │
│        "full_name": "Candidate Name",              │
│        "quick_test": false                         │
│      }                                              │
│    }                                                │
└────────────────┬────────────────────────────────────┘
                 │
                 v
┌─────────────────────────────────────────────────────┐
│ 3. RunPod Worker (GPU)                             │
│    - Downloads test dataset (cached on volume)     │
│    - Downloads submission from R2                   │
│    - Extracts and runs evaluation                   │
│    - Uploads results JSON to R2                     │
│    - Returns success                                │
└────────────────┬────────────────────────────────────┘
                 │
                 v
┌─────────────────────────────────────────────────────┐
│ 4. Railway polls RunPod status                     │
│    OR receives webhook callback                     │
│    - Updates database with results                  │
│    - User sees results in dashboard                 │
└─────────────────────────────────────────────────────┘
```

---

## Cost Estimation

**First submission:**
- Cold start: ~30s (free)
- Download dataset: ~1 min
- Evaluation: ~2-5 min
- **Total:** ~3-6 minutes on GPU

**Subsequent submissions:**
- Warm worker: instant (if within 30s)
- Dataset cached: instant
- Evaluation: ~2-5 min
- **Total:** ~2-5 minutes on GPU

**Pricing (approximate):**
- RTX A4000: ~$0.30/hour
- 5 min job: ~$0.025 per evaluation

---

## Success Checklist

Before going live:

- [ ] RunPod endpoint created and built successfully
- [ ] All 3 R2 environment variables set
- [ ] Volume (50GB) enabled for dataset caching
- [ ] Max Retries = 0 (prevents infinite loops)
- [ ] Execution timeout = 900s (15 min)
- [ ] Railway has RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID
- [ ] Test submission completes successfully
- [ ] Results appear in Railway dashboard
- [ ] Second submission uses cached dataset (faster)

---

## Current Status

✅ Code pushed to GitHub
✅ Error handling prevents infinite loops
✅ Bucket name hardcoded (no config errors)
✅ Railway deployment ready
⏳ Waiting for RunPod configuration
