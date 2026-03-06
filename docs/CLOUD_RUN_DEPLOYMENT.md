# Google Cloud Run Deployment — NeuralGTO Backend

**Status:** Always Free tier — $0/month when idle, scales to zero automatically.

## Quick Start (5 minutes)

### 1. Install gcloud CLI

Download from: https://cloud.google.com/sdk/docs/install

```powershell
# Verify installation
gcloud --version
```

### 2. Create a Google Cloud Project

```bash
gcloud projects create neuralgto-backend
gcloud config set project neuralgto-backend
```

Or use the Cloud Console: https://console.cloud.google.com/projectcreate

### 3. Enable Required APIs

```bash
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

### 4. Authenticate Docker

```bash
gcloud auth configure-docker
```

### 5. Build & Push Docker Image

```bash
cd /path/to/NeuralGTO

# Build image
docker build -t gcr.io/neuralgto-backend/neuralgto-api:latest -f backend/Dockerfile .

# Push to Google Container Registry
docker push gcr.io/neuralgto-backend/neuralgto-api:latest
```

### 6. Deploy to Cloud Run

```bash
gcloud run deploy neuralgto-api \
  --image gcr.io/neuralgto-backend/neuralgto-api:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --timeout 120
```

**Parameters explained:**
- `--allow-unauthenticated` — public API (required)
- `--memory 512Mi` — enough for FastAPI + LLM (free tier allows up to 2 GB)
- `--cpu 1` — 1 CPU (free tier allows up to 2)
- `--timeout 120` — 2 minute timeout (Gemini requests + processing)

### 7. Get Your Service URL

After deployment succeeds, the output shows:
```
Service URL: https://neuralgto-api-abc123def.a.run.app
```

Save this URL — it's your backend!

### 8. Update Frontend `.env.production`

In `neuralgto-web/`:

```bash
VITE_API_URL=https://neuralgto-api-abc123def.a.run.app
```

Rebuild and redeploy frontend to Cloudflare Pages.

---

## Important Notes

### Service Account & IAM Permissions

Cloud Run uses a default service account. **Recommended: Create a minimal service account with explicit permissions:**

```bash
# Create a dedicated service account
gcloud iam service-accounts create neuralgto-api-runner \
  --display-name="NeuralGTO API Runtime"

# Grant only necessary permissions
gcloud projects add-iam-policy-binding neuralgto-backend \
  --member="serviceAccount:neuralgto-api-runner@neuralgto-backend.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding neuralgto-backend \
  --member="serviceAccount:neuralgto-api-runner@neuralgto-backend.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"

# Deploy with the service account
gcloud run deploy neuralgto-api \
  --image gcr.io/neuralgto-backend/neuralgto-api:latest \
  --service-account=neuralgto-api-runner@neuralgto-backend.iam.gserviceaccount.com \
  ...
```

**API Key Security:**
- Store Gemini API key in **Google Secret Manager**, not `.env`
- Rotate keys regularly (especially if accidentally exposed)
- Use Cloud Run IAM to limit who can view deployment environment variables
Cloud Run has **no TexasSolver binary**. The backend runs in `mode=fast` (Gemini parsing + advice only, no GTO solver).

To add TexasSolver later:
1. Download Linux ARM binary from [TexasSolver releases](https://github.com/bupticybee/TexasSolver/releases)
2. Copy into `solver_bin/` 
3. Rebuild & redeploy Docker image
4. Cloud Run will auto-detect and enable solver

### Always Free Limits

| Resource | Limit | Status |
|---|---|---|
| Invocations | 2M/month | ✅ Plenty |
| vCPU seconds | 360k/month | ✅ Plenty |
| GB-seconds | 1M/month | ✅ Plenty |
| Data out | 1 GB/month | ✅ Plenty |

At typical usage (REST API, <1 sec per request), you'll use ~100-200k vCPU-sec/month — well under limit.

### Monitoring & Logs

```bash
# View logs
gcloud run services describe neuralgto-api --region us-central1

# Stream logs
gcloud run services logs read neuralgto-api --region us-central1 --limit 50

# Monitor metrics
# Go to: https://console.cloud.google.com/run/detail/us-central1/neuralgto-api
```

### Cost After Free Tier (if exceeded)

- First 2M/month invocations: free
- Additional: $0.40 per 1M invocations
- vCPU-second: $0.000025 per vCPU-second
- Memory: $0.0000167 per GB-second

Realistically, staying free requires ~<20 active users.

## Rollback

If you need to revert to a previous version:

```bash
gcloud run deploy neuralgto-api \
  --image gcr.io/neuralgto-backend/neuralgto-api:v1 \
  --region us-central1
```

## Next Steps

1. **Update frontend** with Cloud Run URL
2. **Test API health:** 
   ```
   curl https://neuralgto-api-xxx.a.run.app/api/health
   ```
3. **Monitor logs** for errors
4. **When TexasSolver capacity opens on Oracle**, migrate to Oracle Always Free (Ampere) for full GTO solver support

---

**Created:** 2026-03-06  
**Status:** Always Free Tier  
**Timeout:** 120 seconds (Gemini-friendly)
