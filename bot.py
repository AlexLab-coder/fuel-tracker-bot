import os
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler
from flask import Flask
from threading import Thread
import time
import psycopg2

app = Flask('')

@app.route('/')
def home():
    return "🚗 Fuel Bot is Alive!"

def run_flask():
    try:
        print("🔄 Starting Flask server...")
        app.run(host='0.0.0.0', port=8080, debug=False)
    except Exception as e:
        print(f"❌ Flask error: {e}")

def keep_alive():
    print("🔧 Starting keep_alive...")
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    time.sleep(2)

keep_alive()
print("✅ Flask server should be running")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database class for PostgreSQL
class FuelDatabase:
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.init_db()
    
    def get_connection(self):
        return psycopg2.connect(self.database_url)
    
    def init_db(self):
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS refills
                         (id SERIAL PRIMARY KEY,
                          user_id BIGINT, 
                          timestamp TEXT,
                          amount REAL, 
                          cost REAL, 
                          odometer INTEGER)''')
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Database init error: {e}")
    
    def add_refill(self, user_id, amount, cost, odometer):
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("INSERT INTO refills (user_id, timestamp, amount, cost, odometer) VALUES (%s, %s, %s, %s, %s)",
                     (user_id, datetime.now().isoformat(), amount, cost, odometer))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Add refill error: {e}")
            return False
    
    def get_current_consumption(self, user_id):
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM refills WHERE user_id = %s ORDER BY odometer DESC LIMIT 2", (user_id,))
            refills = c.fetchall()
            conn.close()
            
            if len(refills) < 2:
                return None
            
            latest = refills[0]
            previous = refills[1]
            
            distance = latest[5] - previous[5]
            fuel_used = previous[3]
            
            if distance > 0:
                consumption = (fuel_used / distance) * 100
                return {
                    'consumption': f"{consumption:.1f}",
                    'distance': distance,
                    'fuel_used': fuel_used
                }
        except Exception as e:
            logging.error(f"Get consumption error: {e}")
        return None
    
    def get_monthly_statistics(self, user_id):
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute('''SELECT 
                        TO_CHAR(TO_TIMESTAMP(timestamp, 'YYYY-MM-DD"T"HH24:MI:SS.MS'), 'Month YYYY') as month,
                        SUM(amount) as total_liters,
                        SUM(cost) as total_cost,
                        AVG(cost/amount) as avg_price
                        FROM refills 
                        WHERE user_id = %s 
                        GROUP BY TO_CHAR(TO_TIMESTAMP(timestamp, 'YYYY-MM-DD"T"HH24:MI:SS.MS'), 'Month YYYY')
                        ORDER BY MIN(TO_TIMESTAMP(timestamp, 'YYYY-MM-DD"T"HH24:MI:SS.MS')) DESC''', (user_id,))
            
            results = []
            for row in c.fetchall():
                results.append({
                    'month': row[0].strip(),
                    'liters': f"{row[1]:.1f}",
                    'cost': f"{row[2]:.0f}",
                    'avg_price_per_liter': f"{row[3]:.1f}" if row[3] else "0.0"
                })
            conn.close()
            return results
        except Exception as e:
            logging.error(f"Monthly stats error: {e}")
            return []
    
    def get_user_refills(self, user_id, limit=10):
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM refills WHERE user_id = %s ORDER BY timestamp DESC LIMIT %s", (user_id, limit))
            refills = []
            for row in c.fetchall():
                refills.append({
                    'timestamp': row[2],
                    'amount': row[3],
                    'cost': row[4],
                    'odometer': row[5]
                })
            conn.close()
            return refills
        except Exception as e:
            logging.error(f"Get refills error: {e}")
            return []
    
    def delete_user_data(self, user_id):
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM refills WHERE user_id = %s", (user_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Delete error: {e}")
            return False

# Initialize database
db = FuelDatabase()

# Conversation states
WAITING_REFILL_DATA, CONFIRM_RESET = range(2)

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("⛽ Заправиться"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("🗑️ Сбросить данные"), KeyboardButton("ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    keyboard = get_main_keyboard()
    update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Добро пожаловать в бот учета расхода топлива!\n\n"
        "Используйте кнопки ниже или команды:\n"
        "/refill - Записать заправку\n"
        "/stats - Статистика расхода\n"
        "/reset - Сбросить данные\n"
        "/help - Помощь",
        reply_markup=keyboard
    )

def help_command(update: Update, context: CallbackContext):
    keyboard = get_main_keyboard()
    update.message.reply_text(
        "ℹ️ ПОМОЩЬ:\n\n"
        "⛽ Заправиться:\n"
        "Введите данные в формате:\n"
        "литры цена пробег\n"
        "Пример: 45 2500 155000\n\n"
        "📊 Статистика:\n"
        "Показывает расход топлива и помесячную статистику\n\n"
        "🗑️ Сбросить данные:\n"
        "Удаляет всю историю заправок\n\n"
        "Все данные сохраняются автоматически!",
        reply_markup=keyboard
    )

def refill_start(update: Update, context: CallbackContext):
    keyboard = get_main_keyboard()
    update.message.reply_text(
        "⛽ ЗАПРАВКА\n\n"
        "Введите данные в формате:\n"
        "литры цена пробег\n\n"
        "Пример: 45 2500 155000\n\n"
        "Или /cancel для отмены",
        reply_markup=keyboard
    )
    return WAITING_REFILL_DATA

def refill_data(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    keyboard = get_main_keyboard()
    
    try:
        parts = update.message.text.strip().split()
        
        if len(parts) != 3:
            update.message.reply_text(
                "❌ Неверный формат!\n\n"
                "Введите данные в формате:\n"
                "литры цена пробег\n\n"
                "Пример: 45 2500 155000",
                reply_markup=keyboard
            )
            return WAITING_REFILL_DATA
        
        amount = float(parts[0])
        cost = float(parts[1])
        odometer = int(parts[2])
        
        if db.add_refill(user_id, amount, cost, odometer):
            price_per_liter = cost / amount
            update.message.reply_text(
                "✅ Заправка записана!\n\n"
                f"📊 Сводка:\n"
                f"• Топливо: {amount} л\n"
                f"• Стоимость: {cost} руб\n"
                f"• Одометр: {odometer} км\n"
                f"• Цена за литр: {price_per_liter:.2f} руб/л\n\n"
                "Используйте 📊 Статистика для просмотра расхода!",
                reply_markup=keyboard
            )
        else:
            update.message.reply_text(
                "❌ Ошибка сохранения. Попробуйте снова.",
                reply_markup=keyboard
            )
        
        return ConversationHandler.END
        
    except ValueError:
        update.message.reply_text(
            "❌ Неверный формат данных!\n\n"
            "Убедитесь, что:\n"
            "• Литры и цена - числа (можно с точкой)\n"
            "• Пробег - целое число\n\n"
            "Пример: 45.5 2500 155000",
            reply_markup=keyboard
        )
        return WAITING_REFILL_DATA

def stats(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    keyboard = get_main_keyboard()
    
    current = db.get_current_consumption(user_id)
    monthly = db.get_monthly_statistics(user_id)
    
    if not current and not monthly:
        update.message.reply_text(
            "📊 Нет данных для статистики.\n\n"
            "Добавьте минимум 2 заправки для расчета расхода.\n"
            "Используйте ⛽ Заправиться!",
            reply_markup=keyboard
        )
        return
    
    message = "📊 СТАТИСТИКА:\n\n"
    
    if current:
        message += (
            "🎯 ТЕКУЩИЙ РАСХОД:\n"
            f"• Расход: {current['consumption']} л/100км\n"
            f"• Пробег: {current['distance']} км\n"
            f"• Израсходовано: {current['fuel_used']} л\n\n"
        )
    
    if monthly:
        message += "📅 ПО МЕСЯЦАМ:\n"
        for month_data in monthly:
            message += (
                f"• {month_data['month']}: {month_data['liters']} л, "
                f"{month_data['cost']} руб, "
                f"{month_data['avg_price_per_liter']} руб/л\n"
            )
    
    update.message.reply_text(message, reply_markup=keyboard)

def reset_start(update: Update, context: CallbackContext):
    keyboard = [[KeyboardButton("Да"), KeyboardButton("Нет")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    update.message.reply_text(
        "🗑️ СБРОС ДАННЫХ\n\n"
        "⚠️ Вы уверены?\n"
        "Это удалит ВСЮ историю заправок!\n\n"
        "Отправьте Да или Нет",
        reply_markup=reply_markup
    )
    return CONFIRM_RESET

def reset_confirm(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    keyboard = get_main_keyboard()
    response = update.message.text.lower()
    
    if response == "да":
        if db.delete_user_data(user_id):
            update.message.reply_text(
                "✅ Все данные удалены!\n\n"
                "Можете начать заново с ⛽ Заправиться",
                reply_markup=keyboard
            )
        else:
            update.message.reply_text(
                "❌ Ошибка при удалении данных.",
                reply_markup=keyboard
            )
    else:
        update.message.reply_text(
            "❌ Сброс отменен.\n\n"
            "Ваши данные сохранены.",
            reply_markup=keyboard
        )
    
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    keyboard = get_main_keyboard()
    update.message.reply_text(
        "❌ Операция отменена.\n\n"
        "Используйте кнопки меню.",
        reply_markup=keyboard
    )
    return ConversationHandler.END

def main():
    token = os.getenv('BOT_TOKEN')
    
    if not token:
        logger.error("BOT_TOKEN not found in environment variables!")
        return
    
    updater = Updater(token, use_context=True)
    application = updater.dispatcher
    
    refill_handler = ConversationHandler(
        entry_points=[
            CommandHandler('refill', refill_start),
            MessageHandler(Filters.regex('^⛽ Заправиться$'), refill_start)
        ],
        states={
            WAITING_REFILL_DATA: [MessageHandler(Filters.text & ~Filters.command, refill_data)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    reset_handler = ConversationHandler(
        entry_points=[
            CommandHandler('reset', reset_start),
            MessageHandler(Filters.regex('^🗑️ Сбросить данные$'), reset_start)
        ],
        states={
            CONFIRM_RESET: [MessageHandler(Filters.text & ~Filters.command, reset_confirm)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(refill_handler)
    application.add_handler(reset_handler)
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("help", help_command))
    
    application.add_handler(MessageHandler(Filters.regex('^📊 Статистика$'), stats))
    application.add_handler(MessageHandler(Filters.regex('^ℹ️ Помощь$'), help_command))
    
    logger.info("Bot is starting...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
