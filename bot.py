import os
import logging
import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler

from flask import Flask
from threading import Thread
import time

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
    time.sleep(2)  # Даем время запуститься

# ЗАПУСКАЕМ FLASK ПЕРВЫМ ДЕЛОМ
keep_alive()
print("✅ Flask server should be running")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database class directly in the code (instead of separate file)
class FuelDatabase:
    def __init__(self):
        self.conn = sqlite3.connect('fuel.db', check_same_thread=False)
        self.init_db()

    def init_db(self):
        c = self.conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS refills
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER, 
                      timestamp TEXT,
                      amount REAL, 
                      cost REAL, 
                      odometer INTEGER)''')
        self.conn.commit()

    def add_refill(self, user_id, amount, cost, odometer):
        try:
            c = self.conn.cursor()
            c.execute("INSERT INTO refills (user_id, timestamp, amount, cost, odometer) VALUES (?, ?, ?, ?, ?)",
                     (user_id, datetime.now().isoformat(), amount, cost, odometer))
            self.conn.commit()
            return True
        except:
            return False

    def get_current_consumption(self, user_id):
        try:
            c = self.conn.cursor()
            c.execute("SELECT * FROM refills WHERE user_id = ? ORDER BY odometer DESC LIMIT 2", (user_id,))
            refills = c.fetchall()

            if len(refills) < 2:
                return None

            latest = refills[0]  # [id, user_id, timestamp, amount, cost, odometer]
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
        except:
            pass
        return None

    def get_monthly_statistics(self, user_id):
        try:
            c = self.conn.cursor()
            c.execute('''SELECT 
                        strftime('%Y-%m', timestamp) as month,
                        SUM(amount) as total_liters,
                        SUM(cost) as total_cost,
                        AVG(cost/amount) as avg_price
                        FROM refills 
                        WHERE user_id = ? 
                        GROUP BY strftime('%Y-%m', timestamp)
                        ORDER BY month DESC''', (user_id,))

            results = []
            for row in c.fetchall():
                month_name = datetime.strptime(row[0], '%Y-%m').strftime('%B %Y')
                results.append({
                    'month': month_name,
                    'liters': f"{row[1]:.1f}",
                    'cost': f"{row[2]:.0f}",
                    'avg_price_per_liter': f"{row[3]:.1f}" if row[3] else "0.0"
                })
            return results
        except:
            return []

    def get_user_refills(self, user_id, limit=10):
        try:
            c = self.conn.cursor()
            c.execute("SELECT * FROM refills WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?", (user_id, limit))
            refills = []
            for row in c.fetchall():
                refills.append({
                    'timestamp': row[2],
                    'amount': row[3],
                    'cost': row[4],
                    'odometer': row[5]
                })
            return refills
        except:
            return []

    def delete_user_data(self, user_id):
        try:
            c = self.conn.cursor()
            c.execute("DELETE FROM refills WHERE user_id = ?", (user_id,))
            self.conn.commit()
            return True
        except:
            return False

# Initialize database
db = FuelDatabase()

# Conversation states
WAITING_REFILL_DATA, CONFIRM_RESET = range(2)

# Store temporary data
user_temp_data = {}

def get_main_keyboard():
    """Create and return the main keyboard with Russian buttons"""
    keyboard = [
        [KeyboardButton("⛽ Заправиться"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("🗑️ Сбросить данные"), KeyboardButton("ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def start(update: Update, context: CallbackContext):
    """Send a message when the command /start is issued."""
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
    """Display help information"""
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
    """Start the refill recording process"""
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
    """Process refill data from single line input"""
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

        if amount <= 0 or cost <= 0 or odometer <= 0:
            update.message.reply_text(
                "❌ Все значения должны быть положительными!\n\n"
                "Попробуйте снова:",
                reply_markup=keyboard
            )
            return WAITING_REFILL_DATA

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
    """Display enhanced fuel consumption statistics"""
    user_id = update.effective_user.id
    keyboard = get_main_keyboard()

    # Get current consumption
    current = db.get_current_consumption(user_id)

    # Get monthly statistics
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

    # Current consumption
    if current:
        message += (
            "🎯 ТЕКУЩИЙ РАСХОД:\n"
            f"• Расход: {current['consumption']} л/100км\n"
            f"• Пробег: {current['distance']} км\n"
            f"• Израсходовано: {current['fuel_used']} л\n\n"
        )

    # Monthly statistics
    if monthly:
        message += "📅 ПО МЕСЯЦАМ:\n"
        for month_data in monthly:
            # Convert English month names to Russian
            month_ru = month_data['month']
            month_ru = month_ru.replace('January', 'Январь')
            month_ru = month_ru.replace('February', 'Февраль')
            month_ru = month_ru.replace('March', 'Март')
            month_ru = month_ru.replace('April', 'Апрель')
            month_ru = month_ru.replace('May', 'Май')
            month_ru = month_ru.replace('June', 'Июнь')
            month_ru = month_ru.replace('July', 'Июль')
            month_ru = month_ru.replace('August', 'Август')
            month_ru = month_ru.replace('September', 'Сентябрь')
            month_ru = month_ru.replace('October', 'Октябрь')
            month_ru = month_ru.replace('November', 'Ноябрь')
            month_ru = month_ru.replace('December', 'Декабрь')

            message += (
                f"• {month_ru}: {month_data['liters']} л, "
                f"{month_data['cost']} руб, "
                f"{month_data['avg_price_per_liter']} руб/л\n"
            )

    update.message.reply_text(message, reply_markup=keyboard)

def history(update: Update, context: CallbackContext):
    """Display refill history"""
    user_id = update.effective_user.id
    keyboard = get_main_keyboard()
    refills = db.get_user_refills(user_id)

    if not refills:
        update.message.reply_text(
            "📝 Нет истории заправок.\n\n"
            "Используйте ⛽ Заправиться для добавления записи!",
            reply_markup=keyboard
        )
        return

    message = "📝 ИСТОРИЯ ЗАПРАВОК:\n\n"

    for i, refill in enumerate(refills, 1):
        date = refill['timestamp'].split('T')[0]
        price_per_liter = refill['cost'] / refill['amount']
        message += (
            f"{i}. {date}\n"
            f"   ⛽ {refill['amount']} л | 💰 {refill['cost']} руб | "
            f"🛣 {refill['odometer']} км\n"
            f"   Цена: {price_per_liter:.2f} руб/л\n\n"
        )

    update.message.reply_text(message, reply_markup=keyboard)

def reset_start(update: Update, context: CallbackContext):
    """Start the data reset process"""
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
    """Confirm and execute data reset"""
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
    """Cancel the current operation"""
    keyboard = get_main_keyboard()
    update.message.reply_text(
        "❌ Операция отменена.\n\n"
        "Используйте кнопки меню.",
        reply_markup=keyboard
    )
    return ConversationHandler.END

def main():
    """Start the bot"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')

    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
        return

    updater = Updater(token, use_context=True)
    application = updater.dispatcher

    # Conversation handler for refill
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

    # Conversation handler for reset
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

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(refill_handler)
    application.add_handler(reset_handler)
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("help", help_command))

    # Add button handlers
    application.add_handler(MessageHandler(Filters.regex('^📊 Статистика$'), stats))
    application.add_handler(MessageHandler(Filters.regex('^ℹ️ Помощь$'), help_command))

    # Start the Bot
    logger.info("Bot is starting...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
