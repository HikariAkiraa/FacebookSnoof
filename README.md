# FacebookSnoof: Autonomous Facebook Marketplace & Group Deal Evaluator

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/automation-Playwright%20Stealth-green.svg)](https://playwright.dev/python/)
[![Gemini API](https://img.shields.io/badge/evaluator-Google%20AI%20Studio%20Gemini-blue.svg)](https://aistudio.google.com/)
[![Database](https://img.shields.io/badge/database-SQLite3%20WAL-lightgrey.svg)](https://www.sqlite.org/)
[![Notifier](https://img.shields.io/badge/notifier-Telegram%20%26%20Discord-purple.svg)](https://discord.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An enterprise-grade, privacy-first scraper and valuation engine designed to monitor Indonesian PC hardware marketplace groups on Facebook. The system continuously extracts chronological listings, filters transaction intent (WTS vs WTB/WTT/WTA), runs cognitive valuation via **Google AI Studio Gemini API** (`gemini-3.5-flash-lite` with **Context Caching** and fallback), combined with a modular market **Lookup Table**, and dispatches real-time deal alerts to **Telegram** and **Discord Webhooks**.

---

## 1. Architectural Overview

The engine executes in a fully automated, decoupled pipeline to eliminate race conditions, duplicate alerts, and anti-bot rate limiting.

```
+-------------------------------------------------------------------------+
|                          CRON / APSCHEDULER                             |
|               Executes every 15 minutes with +/- 3m jitter              |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                PLAYWRIGHT STEALTH COLLECTOR & FALLBACK                  |
|  * Primary: Intercepts background `/api/graphql/` batch streams          |
|  * Fallback: DOM Feed Hybrid Parser (`div[role="article"]`)              |
|  * Loads authenticated cookies from `config/storage_state.json`         |
|  * Navigates to `?sorting_setting=CHRONOLOGICAL` on target groups       |
+------------------------------------+------------------------------------+
                                     | Raw Post Payloads
                                     v
+-------------------------------------------------------------------------+
|                     PERSISTENCE & DEDUPLICATION                         |
|  * SQLite database operating in Write-Ahead Logging (WAL) mode          |
|  * Drops processed `post_id` entries to guarantee zero overlap          |
+------------------------------------+------------------------------------+
                                     | New Candidate Posts
                                     v
+-------------------------------------------------------------------------+
|                     TIER 1: INTENT & NOISE FILTER                       |
|  * Regex pruning for WTB, WTT/Barter, WTA, and Price Check inquiries    |
|  * Normalizes text, sanitizes emojis, extracts basic price tags         |
+------------------------------------+------------------------------------+
                                     | Valid Hardware Listings
                                     v
+-------------------------------------------------------------------------+
|          TIER 2: GEMINI API COGNITIVE VALUATION & CONTEXT CACHING       |
|  * Primary Model: `gemini-3.5-flash-lite` (Fallback: `gemini-3.1-flash`) |
|  * Context Caching: Static prompt & `lookup_table.md` prefix caching    |
|  * Zero-Hallucination: Strictly enforces truthful post extractions      |
+------------------------------------+------------------------------------+
                                     | Validated Deal Evaluations
                                     v
+-------------------------------------------------------------------------+
|                     DISPATCH & NOTIFICATION LAYER                       |
|  * Discord Webhook Embeds: 🔥 Gold HOT DEAL vs ⚠️ Grey SKIPPED cards    |
|  * Telegram Bot Notifications: Markdown formatted deal alerts          |
+-------------------------------------------------------------------------+
```

---

## 2. Key Features

- **Playwright Stealth Collector:** Bypasses Facebook anti-scraping mechanisms using GraphQL stream interception and DOM fallback parsing.
- **Strict Deduplication:** Persistent SQLite WAL database ensures zero duplicate notifications.
- **Tier-1 Intent Filter:** Automatically discards non-sale posts (WTB, WTT, WTA, Ask, Chatting).
- **Google AI Studio Gemini Integration:** Evaluates components and Full PC Sets using `gemini-3.5-flash-lite` with Pydantic JSON schema validation.
- **Context Caching Acceleration:** Reuses static prompt and lookup table for ~0.2-0.5s response times and 90%+ token savings.
- **Rich Discord & Telegram Notifiers:** Dispatches high-impact Rich Embed cards to Discord channels and Telegram chats.

---

## 3. Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/FacebookSnoof.git
   cd FacebookSnoof
   ```

2. **Create Python virtual environment & install dependencies:**
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate

   pip install -r requirements.txt
   playwright install chromium
   ```

3. **Configure your settings:**
   Copy `config/config.yaml.example` to `config/config.yaml`:
   ```bash
   cp config/config.yaml.example config/config.yaml
   ```
   Add your Google AI Studio API Key and Discord Webhook URL into `config/config.yaml`.

4. **Generate Facebook Authentication Cookies:**
   ```bash
   python engine/auth.py
   ```
   Log in to Facebook in the launched browser window and press Enter to save `config/storage_state.json`.

5. **Run single cycle test or daemon mode:**
   ```bash
   # Single execution test:
   python main.py --single-run

   # Continuous 24/7 Daemon mode (runs every 15 mins):
   python main.py
   ```

---

## 4. License
MIT License.
