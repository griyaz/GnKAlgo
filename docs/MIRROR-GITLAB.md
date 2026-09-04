# Mirror GnKAlgo to GitLab

**GitLab project:** https://gitlab.com/gnk-algo-trade-group/gnk-algo-trade-project  
**GitHub source:** `griyaz/GnKAlgo`

---

## One-time: allow this server (or your laptop) to push to GitLab

### Option A — SSH key (recommended)

1. Open https://gitlab.com/-/user_settings/ssh_keys (or group deploy key on the project).
2. Add this public key (from the Oracle VM / your machine that will push):

```bash
cat ~/.ssh/id_ed25519.pub
```

3. Test:

```bash
ssh -T git@gitlab.com
# Expect: Welcome to GitLab, @yourname!
```

### Option B — Personal access token (HTTPS)

1. GitLab → **Preferences → Access tokens** → create token with `write_repository`.
2. Push with:

```bash
git push https://oauth2:<TOKEN>@gitlab.com/gnk-algo-trade-group/gnk-algo-trade-project.git --all
git push https://oauth2:<TOKEN>@gitlab.com/gnk-algo-trade-group/gnk-algo-trade-project.git --tags
```

---

## Full mirror (all branches + tags)

From the repo root:

```bash
chmod +x scripts/mirror-to-gitlab.sh
./scripts/mirror-to-gitlab.sh
```

Or manually:

```bash
git clone --mirror git@github.com:griyaz/GnKAlgo.git /tmp/gnkalgo-mirror
cd /tmp/gnkalgo-mirror
git push --mirror git@gitlab.com:gnk-algo-trade-group/gnk-algo-trade-project.git
```

---

## Push current workspace only

```bash
cd /opt/gnkalgo   # or your clone path
git remote add gitlab git@gitlab.com:gnk-algo-trade-group/gnk-algo-trade-project.git 2>/dev/null || true
git fetch origin
git push gitlab --all
git push gitlab --tags
```

**Main branch:** `main`

---

## Clone from GitLab (after mirror)

```bash
git clone git@gitlab.com:gnk-algo-trade-group/gnk-algo-trade-project.git
cd gnk-algo-trade-project
git checkout main
```

HTTPS:

```bash
git clone https://gitlab.com/gnk-algo-trade-group/gnk-algo-trade-project.git
```

---

## Public URLs (unchanged)

| Role | URL |
|------|-----|
| Website | https://www.gnkalgo.com |
| Admin | https://www.gnkalgo.com/admin |
| Subscribe | https://www.gnkalgo.com/subscribe |
| GitLab | https://gitlab.com/gnk-algo-trade-group/gnk-algo-trade-project |
