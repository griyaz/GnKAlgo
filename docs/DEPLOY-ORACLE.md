# Deploy GnKAlgo on Oracle Cloud (Ubuntu 24.04) + Nginx + Cloudflare

Use this for production (`www.gnkalgo.com` + `api.gnkalgo.com`).

Traffic path:

```
User → Cloudflare (HTTPS) → Oracle public IP :80/:443 → Nginx → Docker
                                                      ├ www → :3000 Next.js
                                                      └ api → :8000 FastAPI
```

Docker binds only to `127.0.0.1`. Do **not** open 3000/8000 on the internet.

---

## 0. What you need

- Oracle Cloud account (Always Free is enough: 1× Ampere or AMD VM)
- Domain `gnkalgo.com` in Cloudflare
- GitHub access to `griyaz/GnKAlgo`
- SMTP mailbox (`noreply@gnkalgo.com`)
- SSH key pair on your laptop/phone (or Oracle Cloud Shell)

Suggested sizes: **VM.Standard.A1.Flex** 2 OCPU / 12 GB RAM, Ubuntu **24.04**, boot volume 50 GB+.

---

## 1. Oracle Cloud — network (must do this or 80/443 stay blocked)

1. **Networking → Virtual cloud networks** → your VCN → **Security Lists** (or NSG on the instance).
2. **Ingress** rules (source `0.0.0.0/0`):

   | Port | Protocol | Reason |
   |------|----------|--------|
   | 22 | TCP | SSH |
   | 80 | TCP | HTTP / Cloudflare |
   | 443 | TCP | HTTPS |

3. **Egress**: allow all (default).
4. Create **Compute → Instance**:
   - Image: Ubuntu 24.04
   - Assign a **public IPv4**
   - Paste your SSH public key
5. Note the **public IP** (example: `132.x.x.x`).

Oracle images also filter with `iptables`. After SSH (step 3), open 80/443 on the VM too (step 4).

---

## 2. Cloudflare — DNS (do before or after the VM exists)

1. Add site `gnkalgo.com` if not already (update registrar nameservers to Cloudflare).
2. **DNS → Records** (proxy **Proxied** / orange cloud):

   | Type | Name | Content |
   |------|------|---------|
   | A | `@` | Oracle public IP |
   | A | `www` | Oracle public IP |
   | A | `api` | Oracle public IP |

3. **SSL/TLS → Overview**: set **Full (strict)** after origin certs are installed (step 7).  
   Until then you can use **Flexible** (HTTP to origin only). Prefer Full (strict).
4. **SSL/TLS → Edge Certificates**: always use HTTPS **On**.

---

## 3. SSH into Ubuntu 24

From your computer:

```bash
ssh -i /path/to/oracle-key ubuntu@YOUR_PUBLIC_IP
```

Update:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl ca-certificates gnupg ufw nginx
```

---

## 4. Open ports on the VM (Oracle-specific)

```bash
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 22 -j ACCEPT
sudo apt install -y iptables-persistent
sudo netfilter-persistent save
```

UFW (optional extra):

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

---

## 5. Install Docker Engine + Compose plugin

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-buildx-plugin
sudo usermod -aG docker ubuntu
```

Log out and SSH back in, then:

```bash
docker --version
docker compose version
```

---

## 6. Clone the app and create `.env`

```bash
cd /opt
sudo mkdir -p /opt/gnkalgo
sudo chown ubuntu:ubuntu /opt/gnkalgo
cd /opt/gnkalgo
git clone -b main https://github.com/griyaz/GnKAlgo.git .
cp .env.production.example .env
nano .env
```

Set at least:

```env
APP_ENV=production
DEBUG=false
SECRET_KEY=<run: openssl rand -hex 32>
ENCRYPTION_KEY=<run: openssl rand -hex 32>
POSTGRES_PASSWORD=<strong password>
FRONTEND_URL=https://www.gnkalgo.com
BACKEND_PUBLIC_URL=https://www.gnkalgo.com
NEXT_PUBLIC_API_URL=
ALLOWED_ORIGINS=https://www.gnkalgo.com,https://gnkalgo.com
ADMIN_EMAILS=your-login-email@gnkalgo.com
UPI_VPA=yourrealvpa@oksbi
UPI_PAYEE_NAME=GNK ALGO

SMTP_HOST=mail.privateemail.com
SMTP_PORT=465
SMTP_SSL=true
SMTP_STARTTLS=false
SMTP_USER=noreply@gnkalgo.com
SMTP_PASSWORD=<mailbox password>
SMTP_FROM=noreply@gnkalgo.com
```

Leave `NEXT_PUBLIC_API_URL` empty so the browser calls `/api` on the same host (`www.gnkalgo.com`).

`NEXT_PUBLIC_API_URL` is baked into the frontend **at Docker build time**. If you change it later, rebuild:

```bash
docker compose -f docker-compose.prod.yml build --no-cache frontend
```

---

## 7. Cloudflare Origin Certificate (for Full strict)

1. Cloudflare → **SSL/TLS → Origin Server → Create Certificate**
2. Hostnames: `gnkalgo.com`, `*.gnkalgo.com`
3. Copy the **Origin Certificate** and **Private Key**

On the VM:

```bash
sudo mkdir -p /etc/ssl/cloudflare
sudo nano /etc/ssl/cloudflare/gnkalgo.pem    # paste certificate
sudo nano /etc/ssl/cloudflare/gnkalgo.key    # paste private key
sudo chmod 640 /etc/ssl/cloudflare/gnkalgo.key
sudo chown root:www-data /etc/ssl/cloudflare/gnkalgo.key
```

Cloudflare → SSL/TLS → **Full (strict)**.

---

## 8. Nginx reverse proxy

```bash
sudo cp /opt/gnkalgo/deploy/nginx/www.gnkalgo.com.conf /etc/nginx/sites-available/
sudo cp /opt/gnkalgo/deploy/nginx/api.gnkalgo.com.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/www.gnkalgo.com.conf /etc/nginx/sites-enabled/
sudo ln -sf /etc/nginx/sites-available/api.gnkalgo.com.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

If origin certs are not ready yet, comment out the `listen 443` server blocks and use Cloudflare **Flexible** temporarily.

---

## 9. Start the stack

```bash
cd /opt/gnkalgo
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
curl -sS http://127.0.0.1:8000/health
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3000/
```

Expect health JSON `status: ok` and frontend HTTP 200.

Useful:

```bash
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f frontend
```

---

## 10. Cloudflare extras (recommended)

- **SSL/TLS → Edge Certificates**: Always Use HTTPS **On**
- **Speed → Optimization**: Auto Minify optional
- **Security → WAF**: enable managed rules if on a paid plan
- **Network**: HTTP/2, HTTP/3 on
- **DNS**: keep orange cloud **on** so the Oracle IP is hidden

**Do not** set SSL to **Flexible** after origin 443 is working (mixed/redirect loops). Use **Full (strict)**.

---

## 11. Smoke test

1. https://www.gnkalgo.com  
2. https://api.gnkalgo.com/health  
3. https://api.gnkalgo.com/docs  
4. Register → verification email → login  
5. Place a **paper** order  

If register shows **Failed to fetch**, the browser could not reach the API (often the UI still called `localhost:8000`). Nginx now proxies `/api/` on `www.gnkalgo.com` to FastAPI. After `git pull`, copy the updated nginx file, reload nginx, and rebuild frontend:

```bash
cd /opt/gnkalgo
git pull origin main
sudo cp deploy/nginx/www.gnkalgo.com.conf /etc/nginx/sites-available/
sudo nginx -t && sudo systemctl reload nginx
docker compose -f docker-compose.prod.yml up -d --build
```

Then test https://www.gnkalgo.com/health and register again.

---

## 11b. UPI subscribe + admin (share with all users)

**Customer link (share this):** https://www.gnkalgo.com/subscribe

Prices: ₹199 (1 day), ₹999 (5 days), ₹1,999 (22 days). **UPI only** (PhonePe, GPay, Paytm). User pays, enters UTR, you confirm on Admin.

Add to `/opt/gnkalgo/.env`:

```
ADMIN_EMAILS=your-login-email@gnkalgo.com
UPI_VPA=yourrealvpa@oksbi
UPI_PAYEE_NAME=GNK ALGO
```

Then recreate backend and rebuild frontend. Log in once so that email becomes admin. Open https://www.gnkalgo.com/admin

- **Registered** = accounts created  
- **Active** = logged in within 7 days  
- **Inactive** = registered but no login in 7 days  
- **Never logged in** = registered, never signed in  

---

## 12. Updates later

```bash
cd /opt/gnkalgo
git pull origin main
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Timeout on 80/443 | Security List **and** `iptables` both need 80/443 |
| 522 from Cloudflare | Origin down, or SSL mode Full but Nginx has no 443 cert |
| 525 SSL handshake | Wrong origin cert/key, or Full vs Flexible mismatch |
| Email not arriving | SMTP in `.env`, restart `backend` container |
| CORS errors | `ALLOWED_ORIGINS` must include exact `https://www.gnkalgo.com` |
| **Failed to fetch / ERR_NAME_NOT_RESOLVED** | Leave `NEXT_PUBLIC_API_URL` empty and register from https://www.gnkalgo.com so the browser calls `/api/v1/...` on the same host. |
| **Verify link points to the wrong host** | Set `FRONTEND_URL=https://www.gnkalgo.com` in `.env`, then `docker compose -f docker-compose.prod.yml up -d --force-recreate backend`. Open the same token on https://www.gnkalgo.com/verify-email?token=... |
| **Method Not Allowed** on `/auth/register` | Opening the URL in a browser sends **GET**. Register is **POST** only. Use the Create account form, not the address bar. |
| Old API URL in browser | Rebuild frontend image after changing `NEXT_PUBLIC_API_URL` |
| `Permission denied` git clone | Use HTTPS + PAT, or add a deploy SSH key on the VM |

Oracle **Always Free** IPs can change if you stop the instance without a reserved public IP. Create a **reserved public IPv4** and attach it so Cloudflare A records stay valid.
