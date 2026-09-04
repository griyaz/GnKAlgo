# Next product steps (after login)

Do these in order on https://www.gnkalgo.com

## 1. Enable MFA

Dashboard → **Start** on Enable MFA, or open **Settings**.

1. Generate TOTP secret  
2. Add it in Google Authenticator or Authy  
3. Enter the 6-digit code → Enable MFA  

Paper orders work without MFA. Live orders are rejected until MFA is on.

## 2. Connect Dhan (paper first)

Settings → Connect Dhan.

1. In DhanHQ, create API access (token / key + client ID)  
2. Paste into Settings → Save encrypted  
3. Do **not** send live orders until Dhan has your Oracle **static public IP** on the allowlist  

## 3. Place a paper order

Orders → symbol e.g. RELIANCE → BUY → qty 1 → **Paper order**.

Status should be `PAPER_FILLED`. No money moves.

## 4. Optional: Groww + live

- Groww: Trading API subscription, then Settings → Groww  
- Live: MFA on, broker connected, static IP for Dhan, market hours  

## 5. Build a scheduled strategy (no webhook)

Strategies → **Strategy builder**:

1. Set symbol, **BUY** or **SELL**, quantity  
2. Paper mode on for testing  
3. Enable **Run on schedule** and set minutes (e.g. 15)  
4. Save — the backend runs it every N minutes automatically  
5. Use **Pause schedule** to stop without deleting  

Manual **Run once** still works anytime.

## 6. Deploy from GitHub (production)

Repo: https://github.com/griyaz/GnKAlgo

Production deploys from `main`. On the server: `git pull origin main`.
