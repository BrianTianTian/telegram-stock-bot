# Telegram Stock Bot

## 📌 功能介紹
使用 Python 撰寫的 Telegram 股票分析機器人，透過 FinMind API 抓取使用者輸入的股票代碼資訊（如開盤價、收盤價、成交量等），並進行以下分析：

- 計算 RSI4 及 RSI14 指標
- 根據 RSI 分析結果與自定義的成交量基準，判斷買入或賣出時機
- 將分析結果製作成圖表，透過 Telegram Bot 傳送給使用者，提升資料可讀性
- 把抓取下來的原始資料與分析結果分別儲存到 SQLite3 資料庫（同一個 DB 的不同 Table）

---

## 🚀 使用技術
- Python
- SQLite3
- FinMind API
- Telegram Bot API
- Matplotlib
- Pandas

---

## 💻 安裝與執行方式

### 1️⃣ 安裝相依套件

在終端機執行以下指令：
pip install logging pandas matplotlib sqlite3 python-telegram-bot FinMind

🔔 **注意：**
- `sqlite3` 為 Python 內建套件，通常不需要額外安裝。
- `matplotlib.pyplot` 為 `matplotlib` 套件的一部分，安裝 `matplotlib` 即可。
- `telegram` 與 `telegram.ext` 均包含於 `python-telegram-bot` 套件內。

---

### 2️⃣ 執行程式
python 股票分析+tg機器人.py
