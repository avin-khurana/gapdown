#!/usr/bin/env python3
"""Daily gap-down scanner for the top 30 US companies by market cap.

Fetches live market cap + price data for a candidate universe of large-cap
US tickers, keeps the top 30 by market cap, flags any that gapped down more
than 5% at the open vs. the prior close, attaches recent news headlines for
each, and emails an HTML report.
"""

import os
import smtplib
import sys
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

import yfinance as yf

CENTRAL_TZ = ZoneInfo("America/Chicago")
TARGET_HOUR = 18  # 6 PM Central
GAP_THRESHOLD_PCT = -5.0

# Candidate universe of large-cap US tickers. The script ranks these by
# live market cap each run and keeps the top 30, so it stays accurate as
# rankings shift over time without needing manual updates. One share class
# per company (e.g. GOOGL not GOOG, BRK-B not BRK-A) to avoid double counts.
CANDIDATE_TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "BRK-B", "AVGO", "TSLA", "LLY",
    "WMT", "JPM", "V", "MA", "XOM", "UNH", "ORCL", "HD", "PG", "COST",
    "JNJ", "NFLX", "BAC", "ABBV", "CRM", "KO", "CVX", "AMD", "PEP", "TMUS",
    "MRK", "ADBE", "LIN", "PM", "WFC", "CSCO", "MCD", "ACN", "ABT", "GE",
    "IBM", "DIS", "TXN", "INTU", "VZ", "AXP", "PFE", "NOW", "CAT", "QCOM",
    "GS", "ISRG", "RTX", "UBER", "SPGI", "T", "PLTR", "BLK", "HON",
]


@dataclass
class StockAlert:
    ticker: str
    name: str
    market_cap: float
    prev_close: float
    open_price: float
    last_price: float
    gap_pct: float
    day_pct: float
    news: list = field(default_factory=list)


def is_scheduled_run_time() -> bool:
    """Only proceed around 6pm Central. GitHub Actions triggers this workflow
    at two fixed UTC times to cover both CDT and CST; whichever one lands
    near 6pm local time is the one that actually runs the scan."""
    if os.environ.get("FORCE_RUN") == "1":
        return True
    now = datetime.now(CENTRAL_TZ)
    if now.weekday() >= 5:  # Saturday/Sunday, markets closed
        return False
    return now.hour == TARGET_HOUR


def fetch_top30_by_market_cap():
    rows = []
    for ticker in CANDIDATE_TICKERS:
        try:
            info = yf.Ticker(ticker).info
            market_cap = info.get("marketCap")
            prev_close = info.get("previousClose")
            open_price = info.get("open") or info.get("regularMarketOpen")
            last_price = info.get("currentPrice") or info.get("regularMarketPrice")
            name = info.get("shortName") or ticker
            if not market_cap or not prev_close or not open_price:
                continue
            rows.append({
                "ticker": ticker,
                "name": name,
                "market_cap": market_cap,
                "prev_close": prev_close,
                "open": open_price,
                "last": last_price,
            })
        except Exception as exc:
            print(f"warning: failed to fetch {ticker}: {exc}", file=sys.stderr)
    rows.sort(key=lambda r: r["market_cap"], reverse=True)
    return rows[:30]


def find_gap_downs(top30):
    results = []
    for r in top30:
        gap_pct = (r["open"] - r["prev_close"]) / r["prev_close"] * 100
        day_pct = (
            (r["last"] - r["prev_close"]) / r["prev_close"] * 100
            if r["last"] else 0.0
        )
        if gap_pct <= GAP_THRESHOLD_PCT:
            results.append(StockAlert(
                ticker=r["ticker"],
                name=r["name"],
                market_cap=r["market_cap"],
                prev_close=r["prev_close"],
                open_price=r["open"],
                last_price=r["last"] or 0.0,
                gap_pct=gap_pct,
                day_pct=day_pct,
            ))
    return results


def attach_news(stocks, max_items=3):
    for s in stocks:
        try:
            items = yf.Ticker(s.ticker).news or []
            headlines = []
            for item in items[:max_items]:
                # yfinance has nested news fields under "content" in newer
                # versions; fall back to the flat shape from older ones.
                content = item.get("content", item)
                title = content.get("title") or item.get("title")
                link = (
                    (content.get("canonicalUrl") or {}).get("url")
                    or item.get("link")
                )
                publisher = (
                    (content.get("provider") or {}).get("displayName")
                    or item.get("publisher")
                )
                if title:
                    headlines.append({"title": title, "link": link, "publisher": publisher})
            s.news = headlines
        except Exception as exc:
            print(f"warning: failed to fetch news for {s.ticker}: {exc}", file=sys.stderr)


def format_pct(x):
    return f"{x:+.2f}%"


def build_email_html(stocks, run_date):
    if not stocks:
        return f"""
        <html><body style="font-family:Arial,sans-serif;">
        <h2>Gap-Down Alert &mdash; {run_date}</h2>
        <p>No stocks in today's top 30 US companies by market cap gapped down
        more than 5% at the open vs. the prior close.</p>
        </body></html>
        """

    rows_html = ""
    for s in sorted(stocks, key=lambda s: s.gap_pct):
        if s.news:
            news_html = "<br>".join(
                f'<a href="{n["link"]}">{n["title"]}</a>'
                f' <span style="color:#888;">({n.get("publisher") or "source"})</span>'
                for n in s.news
            )
        else:
            news_html = "<span style='color:#888;'>No recent news found</span>"
        day_color = "#c0392b" if s.day_pct < 0 else "#27ae60"
        rows_html += f"""
        <tr>
          <td style="padding:8px;border:1px solid #ddd;"><b>{s.ticker}</b><br>{s.name}</td>
          <td style="padding:8px;border:1px solid #ddd;">${s.market_cap / 1e9:,.0f}B</td>
          <td style="padding:8px;border:1px solid #ddd;">${s.prev_close:.2f}</td>
          <td style="padding:8px;border:1px solid #ddd;">${s.open_price:.2f}</td>
          <td style="padding:8px;border:1px solid #ddd;color:#c0392b;"><b>{format_pct(s.gap_pct)}</b></td>
          <td style="padding:8px;border:1px solid #ddd;color:{day_color};">{format_pct(s.day_pct)}</td>
          <td style="padding:8px;border:1px solid #ddd;font-size:13px;">{news_html}</td>
        </tr>
        """

    return f"""
    <html><body style="font-family:Arial,sans-serif;">
    <h2>&#128315; Gap-Down Alert &mdash; {run_date}</h2>
    <p>{len(stocks)} of today's top 30 US companies by market cap gapped down
    more than 5% at the open vs. the prior close.</p>
    <table style="border-collapse:collapse;width:100%;">
      <tr style="background:#f4f4f4;">
        <th style="padding:8px;border:1px solid #ddd;text-align:left;">Company</th>
        <th style="padding:8px;border:1px solid #ddd;text-align:left;">Market Cap</th>
        <th style="padding:8px;border:1px solid #ddd;text-align:left;">Prev Close</th>
        <th style="padding:8px;border:1px solid #ddd;text-align:left;">Open</th>
        <th style="padding:8px;border:1px solid #ddd;text-align:left;">Gap %</th>
        <th style="padding:8px;border:1px solid #ddd;text-align:left;">Day %</th>
        <th style="padding:8px;border:1px solid #ddd;text-align:left;">News</th>
      </tr>
      {rows_html}
    </table>
    </body></html>
    """


def send_email(subject, html_body):
    gmail_user = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ.get("RECIPIENT_EMAIL") or "avin.khurana18@gmail.com"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, recipient, msg.as_string())


def main():
    if not is_scheduled_run_time():
        print("Not the scheduled Central-Time hour (or a weekend); skipping.")
        return

    run_date = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
    top30 = fetch_top30_by_market_cap()
    if len(top30) < 20:
        print(
            f"warning: only resolved {len(top30)}/30 tickers; "
            "market may be closed or data unavailable",
            file=sys.stderr,
        )

    gap_downs = find_gap_downs(top30)
    attach_news(gap_downs)

    if gap_downs:
        subject = f"\U0001F53B {len(gap_downs)} Gap-Down Alert(s) — {run_date}"
    else:
        subject = f"✅ No Gap-Downs Today — {run_date}"

    html = build_email_html(gap_downs, run_date)
    send_email(subject, html)
    print(f"Sent report: {subject}")


if __name__ == "__main__":
    main()
