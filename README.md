# gapdown

Daily scan of the top 30 US companies by market cap. Flags any that gapped
down more than 5% at the open vs. the prior close, attaches recent news
headlines for each, and emails an HTML report every day around 6pm Central
Time via a GitHub Actions scheduled workflow.

## How it works

- `gap_down_scanner.py` pulls live price/market-cap data (via `yfinance`)
  for a candidate list of ~58 large-cap US tickers, ranks them by market
  cap, and keeps the top 30.
- For any of those 30 where `open` is more than 5% below `previousClose`,
  it pulls the top 3 recent news headlines for that ticker.
- It emails an HTML table of the results (or a "no gap-downs today" email
  if none) via Gmail SMTP.
- The GitHub Actions workflow fires at both 23:00 UTC and 00:00 UTC every
  day to cover both US daylight-saving offsets; the script itself checks
  the current Central Time hour and only actually runs the scan on
  whichever trigger lands at 6pm local time. Weekends are skipped.

## One-time setup

1. Create a new empty GitHub repo (e.g. `gapdown`) under your account.
2. From this folder:
   ```bash
   git init
   git add .
   git commit -m "Initial gap-down scanner"
   git branch -M main
   git remote add origin https://github.com/<your-username>/gapdown.git
   git push -u origin main
   ```
3. Generate a Gmail **App Password**:
   - Enable 2-Step Verification on the Gmail account you want to send from.
   - Go to https://myaccount.google.com/apppasswords and create an app
     password (choose "Mail" / "Other").
4. In the GitHub repo, go to **Settings → Secrets and variables → Actions**
   and add:
   - `GMAIL_USER` — the sending Gmail address
   - `GMAIL_APP_PASSWORD` — the 16-character app password from step 3
   - `RECIPIENT_EMAIL` — where the report should be sent (optional; defaults
     to `avin.khurana18@gmail.com` if not set)
5. Go to the **Actions** tab and enable workflows if prompted. The
   `Gap Down Alert` workflow will now run automatically every day, and you
   can also trigger it manually from the Actions tab ("Run workflow") to
   test — manual runs always execute the scan regardless of the time.

## Running locally

```bash
pip install -r requirements.txt
export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxxxxxxxxxxxxxx"
export RECIPIENT_EMAIL="you@gmail.com"
export FORCE_RUN=1   # bypass the 6pm Central time-of-day check
python gap_down_scanner.py
```

## Adjusting

- **Gap threshold**: change `GAP_THRESHOLD_PCT` in `gap_down_scanner.py`.
- **Candidate universe**: edit `CANDIDATE_TICKERS`. The script always
  re-ranks by live market cap each run, so the list only needs to be a
  superset of companies that could plausibly be in the top 30.
- **Schedule**: edit the two `cron` lines in
  `.github/workflows/gap_down_alert.yml` and `TARGET_HOUR` in the script
  if you want a different local time.
