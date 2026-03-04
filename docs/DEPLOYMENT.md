# NeuralGTO — Deployment Runbook

**Stack:** React (Vite) on Cloudflare Pages · FastAPI on Oracle Cloud Always Free  
**Cost:** $0/month  
**Last updated:** 2026-03-03

---

## Architecture Overview

```
Browser
  │
  ├── Static assets ──→ Cloudflare Pages (CDN edge, auto HTTPS)
  │                       React + Vite build → neuralgto.pages.dev
  │                       SPA routing via _redirects
  │
  └── API calls ─────→ Cloudflare Tunnel (HTTPS at CF edge)
                           │
                        Oracle Cloud Always Free VM
                           Ubuntu 22.04, 4 ARM cores / 24 GB RAM
                           FastAPI + uvicorn (port 8000, localhost only)
                           TexasSolver Linux binary
                           poker_gpt pipeline
```

**Why this stack:**
- Cloudflare Pages: free, unlimited bandwidth, global CDN, no cold starts
- Oracle Cloud Always Free: 4 ARM OCPU + 24 GB RAM total (A1.Flex) — far exceeds Render/Railway free tiers; critical for 30–60s TexasSolver subprocesses
- Cloudflare Tunnel: no need to expose VM ports or manage SSL certs; CF handles TLS at edge

---

## §1 — Oracle Cloud VM Setup

### 1.1 Create the VM

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com) (requires credit card for verification, free tier never charges)
2. **Compute → Instances → Create Instance**
3. Settings:
   - **Shape:** VM.Standard.A1.Flex (ARM, Always Free)
   - **OCPUs:** 4  · **RAM:** 24 GB  (use all your free allocation on one VM)
   - **Image:** Ubuntu 22.04 (Canonical)
   - **Networking:** create a new VCN + public subnet
   - **SSH keys:** paste your public key (`~/.ssh/id_ed25519.pub`)
4. Note the **Public IP** after creation

### 1.2 Open Oracle Cloud firewall ports

Oracle adds an `iptables REJECT` rule by default. The setup script handles this, but
you also need to allow port 8000 in the **VCN Security List**:

1. Networking → Virtual Cloud Networks → your VCN → Security Lists → Default
2. **Ingress Rules → Add** :
   - Source CIDR: `0.0.0.0/0`
   - Protocol: TCP
   - Destination Port Range: `8000`
3. Also add port `22` (SSH) if not present

> **Tunnel-only deploy:** If using Cloudflare Tunnel (recommended), skip opening
> port 8000 publicly — `cloudflared` connects outbound, requiring no inbound firewall holes.

### 1.3 SSH into the VM

```bash
ssh ubuntu@<oracle-public-ip>
```

### 1.4 Run the setup script

```bash
# On the Oracle VM:
git clone https://github.com/adihebbalae/neus_nlhe.git /tmp/neus_nlhe_setup
chmod +x /tmp/neus_nlhe_setup/backend/deploy/setup_oracle.sh
/tmp/neus_nlhe_setup/backend/deploy/setup_oracle.sh
```

The script:
- Updates Ubuntu packages
- Installs Python 3.13 via deadsnakes PPA
- Clones `neus_nlhe` to `/opt/neuralgto`
- Creates a Python venv + installs `requirements.oracle.txt`
- Downloads TexasSolver Linux binary from GitHub releases
- Creates `/opt/neuralgto/.env` template
- Installs `cloudflared`
- Registers the `neuralgto-api` systemd service

### 1.5 Fill in the .env file

```bash
nano /opt/neuralgto/.env
```

Required values:

| Variable | Value |
|---|---|
| `GEMINI_API_KEY` | Your Google Gemini API key |
| `ALLOWED_ORIGINS` | Your Cloudflare Pages URL (add after §2) |
| `NEURALGTO_SOLVER_TIMEOUT` | `120` (default mode) |

### 1.6 Start the API

```bash
sudo systemctl start neuralgto-api
sudo systemctl status neuralgto-api    # should show "active (running)"

# Health check (local — before tunnel is set up)
curl http://localhost:8000/api/health
# Expected: {"status":"ok","solver_available":true,"version":"0.1.0"}
```

Logs:
```bash
sudo journalctl -u neuralgto-api -f   # follow live logs
```

---

## §2 — Cloudflare Pages (Frontend)

### 2.1 Build the frontend locally (verify first)

```bash
cd neuralgto-web
npm install
npm run build
# Should produce dist/ with no errors
```

### 2.2 Create the Cloudflare Pages project

1. Log into [dash.cloudflare.com](https://dash.cloudflare.com)
2. **Pages → Create a project → Connect to Git**
3. Authorize GitHub and select the `neus_nlhe` repository
4. Build settings:

| Setting | Value |
|---|---|
| Framework preset | Vite |
| Build command | `cd neuralgto-web && npm install && npm run build` |
| Build output directory | `neuralgto-web/dist` |
| Root directory | `/` (repo root) |

5. **Environment variables → Production:**

| Variable | Value |
|---|---|
| `VITE_API_URL` | (leave empty for now — fill in after §3) |

6. Click **Save and Deploy**

> The first deploy will have `VITE_API_URL` empty. That is fine — the frontend
> will fail API calls until §3 is complete. The static build still works.

### 2.3 Confirm deploy

Visit the generated URL: `https://neuralgto-<hash>.pages.dev`

- Page loads ✓
- Form renders ✓
- Submitting a query shows a network error (expected — backend URL not set yet) ✓

### 2.4 Custom domain (optional)

Pages → your project → Custom domains → Add → enter `neuralgto.com` (or subdomain).
Cloudflare will auto-provision a certificate.

---

## §3 — Cloudflare Tunnel (HTTPS for Backend)

Cloudflare Tunnel lets the Oracle VM connect outbound to Cloudflare's edge.
No inbound ports need to be open. CF terminates TLS and forwards traffic to
`http://localhost:8000` on the VM.

### 3.1 Authenticate cloudflared

```bash
# On the Oracle VM:
cloudflared tunnel login
# Opens a browser link — visit it, authorize for your domain
```

### 3.2 Create the tunnel

```bash
cloudflared tunnel create neuralgto-api
# Output: Created tunnel neuralgto-api with id <TUNNEL_ID>
# Credentials at ~/.cloudflared/<TUNNEL_ID>.json
```

Note the `<TUNNEL_ID>` (UUID format).

### 3.3 Configure the tunnel

```bash
# Edit the config template installed by the setup script:
nano /opt/neuralgto/backend/deploy/cloudflare-tunnel.yml
```

Replace:
- `<TUNNEL_ID>` with your actual tunnel UUID (two places)
- `api.your-domain.com` with your actual subdomain (e.g. `api.neuralgto.com`)

Then install the config:

```bash
sudo mkdir -p /etc/cloudflared
sudo cp /opt/neuralgto/backend/deploy/cloudflare-tunnel.yml /etc/cloudflared/config.yml
```

### 3.4 Add DNS record in Cloudflare

```bash
cloudflared tunnel route dns neuralgto-api api.your-domain.com
```

This adds a `CNAME api → <TUNNEL_ID>.cfargotunnel.com` in your Cloudflare DNS
automatically.

### 3.5 Install and start the cloudflared service

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sudo systemctl status cloudflared    # should be "active (running)"
```

### 3.6 Verify HTTPS endpoint

From your local machine:

```bash
curl https://api.your-domain.com/api/health
# {"status":"ok","solver_available":true,"version":"0.1.0"}
```

---

## §4 — Integration: Wire Frontend to Backend

### 4.1 Set VITE_API_URL in Cloudflare Pages

1. Cloudflare Dashboard → Pages → neuralgto → Settings → Environment variables
2. Under **Production**:

| Variable | Value |
|---|---|
| `VITE_API_URL` | `https://api.your-domain.com` |

3. Save → **Deployments → Retry deployment** (or push a commit to trigger a new build)

### 4.2 Update ALLOWED_ORIGINS on the backend

```bash
# On the Oracle VM:
nano /opt/neuralgto/.env
# Set: ALLOWED_ORIGINS=https://neuralgto.pages.dev,https://neuralgto.com
sudo systemctl restart neuralgto-api
```

### 4.3 End-to-end test

```bash
# From your local machine:
curl -s -X POST https://api.your-domain.com/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "I have QhQd on BTN 100bb, folds to me, what do I do?", "mode": "fast"}' \
  | python3 -m json.tool
```

Expected: `{"advice": "...", "source": "gemini", ...}`

Then open the Cloudflare Pages URL in a browser, submit the same query, and
verify the advice renders in the UI.

---

## §5 — Load Testing

Verify the server handles concurrent requests before announcing availability.
Uses `curl` in parallel — no extra tooling required.

```bash
# Save as load_test.sh and run from your local machine.
# Replace URL with your backend URL.
BACKEND="https://api.your-domain.com"
PAYLOAD='{"query": "QhQd BTN 100bb, I open, BB calls, flop Ts9d4h, BB checks", "mode": "fast"}'

echo "Sending 10 concurrent requests..."
for i in $(seq 1 10); do
  curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" \
    -X POST "${BACKEND}/api/analyze" \
    -H "Content-Type: application/json" \
    -d "${PAYLOAD}" &
done
wait
echo "Done."
```

Expected: all 10 return `200` within a few seconds (fast mode — no solver).

For solver-mode load testing (30–60s each), run max 2 concurrent:

```bash
PAYLOAD='{"query": "QhQd BTN 100bb, I open, BB calls, flop Ts9d4h, BB checks", "mode": "default"}'
for i in 1 2; do
  time curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST "${BACKEND}/api/analyze" \
    -H "Content-Type: application/json" \
    -d "${PAYLOAD}" &
done
wait
```

With 2 uvicorn workers and default mode, expect ~120s per request.
The server will queue the second request and serve it when the first completes.

---

## §6 — Ongoing Maintenance

### Deploy a new version

```bash
# From your local machine — trigger a new CF Pages build:
git push origin main
# Cloudflare Pages rebuilds and deploys automatically.

# Update the Oracle VM backend:
ssh ubuntu@<oracle-ip> "bash /opt/neuralgto/backend/deploy/update.sh"
```

### Monitor the backend

```bash
# Live logs:
ssh ubuntu@<oracle-ip> "sudo journalctl -u neuralgto-api -f"

# Service status:
ssh ubuntu@<oracle-ip> "sudo systemctl status neuralgto-api"

# Disk usage (TexasSolver writes work files to _work/):
ssh ubuntu@<oracle-ip> "du -sh /opt/neuralgto/_work"
```

### Rotate the Gemini API key

```bash
ssh ubuntu@<oracle-ip> "nano /opt/neuralgto/.env"
# Update GEMINI_API_KEY
ssh ubuntu@<oracle-ip> "sudo systemctl restart neuralgto-api"
```

---

## §7 — Alternative: nginx + Let's Encrypt (no Cloudflare for domain)

Use this if you're pointing a non-Cloudflare domain directly to the Oracle IP.  
**Skip §3 entirely** and follow these steps instead.

```bash
# On Oracle VM — install and configure nginx:
sudo cp /opt/neuralgto/backend/deploy/nginx.conf /etc/nginx/sites-available/neuralgto
sudo ln -s /etc/nginx/sites-available/neuralgto /etc/nginx/sites-enabled/
sudo nginx -t

# Replace placeholder domain in nginx config:
sudo sed -i 's/api.your-domain.com/api.actualdomain.com/g' \
    /etc/nginx/sites-available/neuralgto

# Obtain certificate:
sudo certbot --nginx -d api.actualdomain.com

# Enable nginx:
sudo systemctl enable nginx
sudo systemctl start nginx
```

Certbot auto-renews via its own systemd timer. Verify: `sudo certbot renew --dry-run`

> Make sure Oracle VCN Security List allows ports **80** and **443** inbound for certbot.

---

## §8 — Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| CF Pages build fails | `npm run build` error | Check build logs in CF dashboard; run `npm run build` locally |
| `VITE_API_URL` missing | CF env var not set | Settings → Env vars → Production → add `VITE_API_URL` |
| `curl health` returns 502 | `neuralgto-api` service not running | `sudo systemctl restart neuralgto-api` |
| Solver returns `solver_available: false` | Wrong binary path or missing binary | Check `NEURALGTO_SOLVER_PATH` in `.env`; re-run solver download section of `setup_oracle.sh` |
| CORS error in browser | `ALLOWED_ORIGINS` not set | Edit `.env` → add CF Pages URL → restart service |
| `cloudflared` disconnects | Tunnel credentials expired | `cloudflared tunnel login` → update credentials JSON |
| 429 rate limit | Too many requests | slowapi limit (60/min by default) — adjust in `app/config.py` if needed |
| High memory on ARM VM | Multiple solver subprocesses | Oracle A1.Flex has 24 GB; solver uses ~500 MB each — 10 concurrent is fine |

---

## §9 — Security Checklist

- [ ] `.env` file is chmod 600 on Oracle VM
- [ ] Port 8000 is **not** open in Oracle Security List if using Cloudflare Tunnel
- [ ] `ALLOWED_ORIGINS` is set to your exact CF Pages URL (not `*`)
- [ ] Gemini API key has a daily budget cap set in Google AI Console
- [ ] `neuralgto-api` systemd service runs as `ubuntu` user (not root)
- [ ] `PrivateTmp=yes` and `NoNewPrivileges=yes` set in service file ✓
- [ ] CF Pages has HTTPS-only enforced (default — no action needed)
- [ ] Oracle VM login is SSH key only (no password auth) — verify: `sudo grep PasswordAuthentication /etc/ssh/sshd_config`
