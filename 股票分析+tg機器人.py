import logging
import pandas as pd
import sqlite3
import json
import datetime
import requests
import matplotlib.pyplot as plt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    ConversationHandler, CallbackContext, CallbackQueryHandler)
from FinMind.data import DataLoader

TELEGRAM_TOKEN = "8045459043:AAGHTuk4lT2HPcYM5YA3HhIGnpxUqW59Arg"

# 設定支援中文字體
plt.rcParams['font.family'] = 'Microsoft JhengHei'
plt.rcParams['axes.unicode_minus'] = False

# 狀態定義
WAITING_STOCK_ID, WAITING_CHOICE = range(2)

# 資料庫初始化
def init_database():
    """初始化SQLite資料庫和資料表"""
    conn = sqlite3.connect('stock.db')
    cursor = conn.cursor()
    
    # 建立stock_data資料表 - 儲存股票原始資料
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_data (
            stock_id TEXT PRIMARY KEY,
            start_date TEXT,
            end_date TEXT,
            raw_data TEXT,  -- 儲存JSON格式的原始資料
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 建立analysed_results資料表 - 儲存分析結果
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analysed_results (
            stock_id TEXT PRIMARY KEY,
            analysis_date TEXT,
            open_price REAL,
            close_price REAL,
            high_price REAL,
            low_price REAL,
            ma4 REAL,
            ma10 REAL,
            ma20 REAL,
            ma60 REAL,
            trading_volume INTEGER,
            rsi4_value REAL,
            rsi14_value REAL,
            condition1_met BOOLEAN,  -- 最近3天收盤價都低於20日均線
            condition2_met BOOLEAN,  -- 最近3天收盤價都低於60日均線
            volume_condition_met BOOLEAN,  -- 最近5日有3天成交量高於10日均量
            rsi4_signal TEXT,  -- RSI4訊號
            rsi14_signal TEXT,  -- RSI14訊號
            综合_signal TEXT,  -- 綜合訊號
            analysis_result TEXT,  -- 完整分析結果文字
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def save_stock_data(stock_id, start_date, end_date, df):
    """儲存或更新股票原始資料"""
    conn = sqlite3.connect('stock.db')
    cursor = conn.cursor()
    
    # 將DataFrame轉換為JSON格式儲存
    data_json = df.to_json(orient='records', date_format='iso')
    
    # 檢查是否已存在該股票資料
    cursor.execute('SELECT stock_id FROM stock_data WHERE stock_id = ?', (stock_id,))
    exists = cursor.fetchone()
    
    if exists:
        # 更新現有資料
        cursor.execute('''
            UPDATE stock_data 
            SET start_date = ?, end_date = ?, raw_data = ?, last_updated = CURRENT_TIMESTAMP
            WHERE stock_id = ?
        ''', (start_date, end_date, data_json, stock_id))
        print(f"更新股票 {stock_id} 的資料")
    else:
        # 插入新資料
        cursor.execute('''
            INSERT INTO stock_data (stock_id, start_date, end_date, raw_data)
            VALUES (?, ?, ?, ?)
        ''', (stock_id, start_date, end_date, data_json))
        print(f"新增股票 {stock_id} 的資料")
    
    conn.commit()
    conn.close()

def save_analysis_result(stock_id, analysis_data, analysis_text):
    """儲存或更新分析結果"""
    conn = sqlite3.connect('stock.db')
    cursor = conn.cursor()
    
    # 檢查是否已存在該股票分析結果
    cursor.execute('SELECT stock_id FROM analysed_results WHERE stock_id = ?', (stock_id,))
    exists = cursor.fetchone()
    
    if exists:
        # 更新現有分析結果
        cursor.execute('''
            UPDATE analysed_results 
            SET analysis_date = ?, open_price = ?, close_price = ?, high_price = ?, low_price = ?,
                ma4 = ?, ma10 = ?, ma20 = ?, ma60 = ?, trading_volume = ?, 
                rsi4_value = ?, rsi14_value = ?, condition1_met = ?, condition2_met = ?, 
                volume_condition_met = ?, rsi4_signal = ?, rsi14_signal = ?, 综合_signal = ?,
                analysis_result = ?, last_updated = CURRENT_TIMESTAMP
            WHERE stock_id = ?
        ''', (
            analysis_data['analysis_date'], analysis_data['open_price'], 
            analysis_data['close_price'], analysis_data['high_price'], analysis_data['low_price'],
            analysis_data['ma4'], analysis_data['ma10'], analysis_data['ma20'], analysis_data['ma60'], 
            analysis_data['trading_volume'], analysis_data['rsi4_value'], analysis_data['rsi14_value'],
            analysis_data['condition1_met'], analysis_data['condition2_met'],
            analysis_data['volume_condition_met'], analysis_data['rsi4_signal'], 
            analysis_data['rsi14_signal'], analysis_data['综合_signal'], analysis_text, stock_id
        ))
        print(f"更新股票 {stock_id} 的分析結果")
    else:
        # 插入新分析結果
        cursor.execute('''
            INSERT INTO analysed_results 
            (stock_id, analysis_date, open_price, close_price, high_price, low_price,
             ma4, ma10, ma20, ma60, trading_volume, rsi4_value, rsi14_value, 
             condition1_met, condition2_met, volume_condition_met, rsi4_signal, 
             rsi14_signal, 综合_signal, analysis_result)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            stock_id, analysis_data['analysis_date'], analysis_data['open_price'],
            analysis_data['close_price'], analysis_data['high_price'], analysis_data['low_price'],
            analysis_data['ma4'], analysis_data['ma10'], analysis_data['ma20'], analysis_data['ma60'],
            analysis_data['trading_volume'], analysis_data['rsi4_value'], analysis_data['rsi14_value'],
            analysis_data['condition1_met'], analysis_data['condition2_met'],
            analysis_data['volume_condition_met'], analysis_data['rsi4_signal'],
            analysis_data['rsi14_signal'], analysis_data['综合_signal'], analysis_text
        ))
        print(f"新增股票 {stock_id} 的分析結果")
    
    conn.commit()
    conn.close()

def calculate_rsi_ema(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    使用 EMA 指數移動平均計算 RSI
    """
    # 計算每日漲跌幅
    delta = prices.diff()

    # 將漲跌分離為漲幅和跌幅（跌幅取正值）
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # 用 EMA 平滑計算平均漲幅與平均跌幅
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

    # 計算相對強弱值 RS
    rs = avg_gain / avg_loss

    # 計算 RSI
    rsi = 100 - (100 / (1 + rs))

    return rsi

def create_stock_chart(stock_id, end_date, df):
    """創建股票分析圖表"""
    print("開始繪製圖表...")
    
    # 取最近30天的資料用於繪圖
    recent_data = df.iloc[-30:].copy()

    # 建立圖表 - 3個子圖
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10))

    # 圖1：股價與移動平均線 (MA4綠色, MA10紅色, MA20紫色)
    ax1.plot(recent_data.index, recent_data['close'], label='收盤價', color='black', linewidth=2)
    ax1.plot(recent_data.index, recent_data['MA4'], label='MA4', color='green', alpha=0.8)
    ax1.plot(recent_data.index, recent_data['MA10'], label='MA10', color='red', alpha=0.8)
    ax1.plot(recent_data.index, recent_data['MA20'], label='MA20', color='purple', alpha=0.8)
    ax1.set_title(f'{stock_id} 股價走勢圖 (最近30天)', fontsize=14, fontweight='bold')
    ax1.set_ylabel('價格 (元)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # 圖2：成交量與平均成交量
    ax2.bar(recent_data.index, recent_data['Trading_Volume'], 
            label='成交量', color='lightblue', alpha=0.7)
    ax2.plot(recent_data.index, recent_data['Volume_MA10'], 
             label='10日平均量', color='orange', linewidth=2)
    ax2.set_title('成交量分析', fontsize=12)
    ax2.set_ylabel('成交量')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # 圖3：合併RSI指標 (RSI4綠色, RSI14紅色)
    ax3.plot(recent_data.index, recent_data['RSI4'], 
             label='RSI4', color='green', linewidth=2)
    ax3.plot(recent_data.index, recent_data['RSI14'], 
             label='RSI14', color='red', linewidth=2)
    ax3.axhline(y=80, color='darkblue', linestyle='-', alpha=0.8, label='超買線(80)')
    ax3.axhline(y=20, color='darkblue', linestyle='-', alpha=0.8, label='超賣線(20)')
    ax3.set_title('RSI 指標分析', fontsize=12)
    ax3.set_ylabel('RSI值')
    ax3.set_xlabel('日期')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    ax3.set_ylim(0, 100)

    # 調整佈局
    plt.tight_layout()

    # 存檔
    filename = f"{stock_id}_股票分析圖_{end_date}.png"
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"✅ 圖表已儲存為 {filename}")
    
    return filename

def start(update: Update, context: CallbackContext):
    update.message.reply_text("您好，請輸入股票代碼:")
    return WAITING_STOCK_ID

def analyze_stock(update: Update, context: CallbackContext):
    """分析股票 - 固定使用RSI4和RSI14"""
    stock_id = update.message.text.strip()
    start_date = "1990-01-01"
    end_date = datetime.date.today().strftime("%Y-%m-%d")

    try:
        # 取得股票資料
        api = DataLoader()
        data = api.taiwan_stock_daily(
            stock_id=stock_id,
            start_date=start_date,
            end_date=end_date
        )

        if data.empty:
            update.message.reply_text(f"查不到 {stock_id} 的資料，請確認輸入是否正確。")
            send_continue_buttons(update)
            return WAITING_CHOICE

        # 資料處理
        df = data[['date', 'stock_id', 'Trading_Volume', 'open', 'max', 'min', 'close', 'spread']].copy()
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df.sort_index(inplace=True)

        # 計算移動平均線
        df["MA4"] = df["close"].rolling(window=4).mean()
        df["MA10"] = df["close"].rolling(window=10).mean()
        df["MA20"] = df["close"].rolling(window=20).mean()
        df["MA60"] = df["close"].rolling(window=60).mean()
        df["Volume_MA10"] = df["Trading_Volume"].rolling(window=10).mean()

        # 計算RSI4和RSI14
        print("正在計算 RSI4 和 RSI14...")
        df["RSI4"] = calculate_rsi_ema(df["close"], 4)
        df["RSI14"] = calculate_rsi_ema(df["close"], 14)

        # 儲存股票原始資料到資料庫
        save_stock_data(stock_id, start_date, end_date, df)

        # 分析邏輯
        today_data = df.iloc[-1]
        last3 = df.iloc[-3:]
        recent5 = df.iloc[-5:]
        messages = []

        # 條件分析
        cond1 = (last3["close"] < last3["MA20"]).all()
        cond2 = (last3["close"] < last3["MA60"]).all()

        messages.append("***股票資訊***")
        messages.append(f"📈 股票代碼：{stock_id}")
        messages.append(f"📅 分析日期：{end_date}")
        messages.append(f"📊 開盤價：{today_data['open']:.2f}")
        messages.append(f"💰 收盤價：{today_data['close']:.2f}")
        messages.append(f"📈 最高價：{today_data['max']:.2f}")
        messages.append(f"📉 最低價：{today_data['min']:.2f}")
        messages.append(f"📊 MA4：{today_data['MA4']:.2f}")
        messages.append(f"📊 MA10：{today_data['MA10']:.2f}")
        messages.append(f"📊 MA20：{today_data['MA20']:.2f}")
        messages.append(f"📊 MA60：{today_data['MA60']:.2f}")
        messages.append(f"📊 成交量：{today_data['Trading_Volume']:,} 張")
        messages.append("\n" + "="*20)

        # 條件1分析
        messages.append("***分析結果***")
        if cond1:
            messages.append("✅ 最近3天收盤價都低於20日均線")
            messages.append("✅ 同時也低於60日均線" if cond2 else "❌ 但沒有全部低於60日均線")
        else:
            messages.append("❌ 沒有連續3天下跌至均線之下")

        # 條件2分析
        vol_over = recent5["Trading_Volume"] > recent5["Volume_MA10"]
        volume_condition_met = vol_over.sum() >= 3
        
        if volume_condition_met:
            messages.append("✅ 最近5日有3天成交量高於10日均量")
            messages.append("符合的日期：")
            vol_data = recent5[vol_over][["Trading_Volume", "Volume_MA10"]]
            for date, row in vol_data.iterrows():
                date_str = date.strftime("%Y-%m-%d")
                vol_str = f"  {date_str}： 成交量={row['Trading_Volume']:,.0f}, 10日均量={row['Volume_MA10']:,.0f}"
                messages.append(vol_str)
        else:
            messages.append("❌ 最近5日成交量未達標")

        messages.append("\n" + "="*20)

        # RSI分析
        latest_rsi4 = df["RSI4"].iloc[-1]
        latest_rsi14 = df["RSI14"].iloc[-1]

        messages.append("***投資建議***")
        messages.append(f"📊 RSI4 (短期)：{latest_rsi4:.3f}")
        messages.append(f"📊 RSI14 (中期)：{latest_rsi14:.3f}")

        # RSI4 信號判斷
        if latest_rsi4 < 20:
            rsi4_signal = "嚴重超賣"
            messages.append("🔴 RSI4 < 20，短期嚴重超賣，可能反彈")
        elif latest_rsi4 > 80:
            rsi4_signal = "嚴重超買"
            messages.append("🔴 RSI4 > 80，短期嚴重超買，可能回調")
        elif latest_rsi4 < 30:
            rsi4_signal = "超賣"
            messages.append("🟡 RSI4 < 30，短期超賣")
        elif latest_rsi4 > 70:
            rsi4_signal = "超買"
            messages.append("🟡 RSI4 > 70，短期超買")
        else:
            rsi4_signal = "中性"
            messages.append("🟢 RSI4 處於中性區間")

        # RSI14 信號判斷
        if latest_rsi14 < 30:
            rsi14_signal = "超賣"
            messages.append("🟡 RSI14 < 30，中期超賣，可以準備買進")
        elif latest_rsi14 > 70:
            rsi14_signal = "超買"
            messages.append("🟡 RSI14 > 70，中期超買，可以準備賣出")
        else:
            rsi14_signal = "中性"
            messages.append("🟢 RSI14 處於中性區間")

        # 綜合判斷
        messages.append("\n🔍 綜合判斷：")
        if latest_rsi4 < 30 and latest_rsi14 < 30:
            综合_signal = "強烈買進"
            messages.append("💚 短期和中期都超賣，買進訊號較強")
        elif latest_rsi4 > 70 and latest_rsi14 > 70:
            综合_signal = "強烈賣出"
            messages.append("❤️ 短期和中期都超買，賣出訊號較強")
        elif latest_rsi4 < 30 and latest_rsi14 > 50:
            综合_signal = "短線反彈"
            messages.append("💛 短期超賣但中期偏強，可能短線反彈")
        elif latest_rsi4 > 70 and latest_rsi14 < 50:
            综合_signal = "短線回調"
            messages.append("💛 短期超買但中期偏弱，可能短線回調")
        else:
            综合_signal = "觀望"
            messages.append("⚪ 訊號不明確，建議觀望")

        # 準備分析資料用於儲存
        analysis_data = {
            'analysis_date': end_date,
            'open_price': float(today_data['open']),
            'close_price': float(today_data['close']),
            'high_price': float(today_data['max']),
            'low_price': float(today_data['min']),
            'ma4': float(today_data['MA4']),
            'ma10': float(today_data['MA10']),
            'ma20': float(today_data['MA20']),
            'ma60': float(today_data['MA60']),
            'trading_volume': int(today_data['Trading_Volume']),
            'rsi4_value': float(latest_rsi4),
            'rsi14_value': float(latest_rsi14),
            'condition1_met': bool(cond1),
            'condition2_met': bool(cond2),
            'volume_condition_met': volume_condition_met,
            'rsi4_signal': rsi4_signal,
            'rsi14_signal': rsi14_signal,
            '综合_signal': 综合_signal
        }

        # 儲存分析結果到資料庫
        analysis_text = "\n".join(messages)
        save_analysis_result(stock_id, analysis_data, analysis_text)

        # 創建圖表
        chart_filename = create_stock_chart(stock_id, end_date, df)

        # 發送分析結果
        update.message.reply_text(analysis_text)
        
        # 發送圖表
        send_chart_to_telegram(update, chart_filename)
        
        send_continue_buttons(update)
        return WAITING_CHOICE

    except Exception as e:
        update.message.reply_text(f"⚠️ 發生錯誤：{str(e)}")
        send_continue_buttons(update)
        return WAITING_CHOICE

def send_chart_to_telegram(update: Update, chart_filename):
    """發送圖表到Telegram"""
    try:
        chat_id = update.effective_chat.id  # ✅ 改成使用者的 chat_id
        url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto'
        
        with open(chart_filename, 'rb') as photo:
            response = requests.post(
                url, 
                data={'chat_id': chat_id}, 
                files={'photo': photo}
            )

        if response.status_code == 200:
            print("圖片已成功傳送！✅")
        else:
            print("❌ 發送圖片時發生錯誤：", response.text)
            update.message.reply_text("⚠️ 圖表生成成功，但發送失敗")
            
    except Exception as e:
        print(f"❌ 發送圖片異常：{str(e)}")
        update.message.reply_text("⚠️ 圖表發送時發生錯誤")

def send_continue_buttons(update: Update):
    """發送繼續查詢按鈕"""
    keyboard = [
        [InlineKeyboardButton("是", callback_data="yes"),
         InlineKeyboardButton("否", callback_data="no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("是否想再查詢其他股票？", reply_markup=reply_markup)

def button_handler(update: Update, context: CallbackContext):
    """處理按鈕點擊"""
    query = update.callback_query
    query.answer()

    if query.data == "yes":
        # 清除之前的資料
        context.user_data.clear()
        query.edit_message_text("請輸入股票代碼:")
        return WAITING_STOCK_ID
    else:
        query.edit_message_text("感謝使用，祝您投資順利💰")
        return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    """取消查詢"""
    update.message.reply_text("已取消查詢。")
    return ConversationHandler.END

def main():
    """主程序"""
    logging.basicConfig(level=logging.INFO)
    
    # 初始化資料庫
    init_database()
    
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_STOCK_ID: [MessageHandler(Filters.text & ~Filters.command, analyze_stock)],
            WAITING_CHOICE: [CallbackQueryHandler(button_handler)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    dp.add_handler(conv_handler)
    
    print("🤖 Telegram機器人已啟動，等待用戶輸入...")
    print("📊 RSI分析固定使用4天和14天")
    print("📈 圖表將自動生成並發送")
    
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()