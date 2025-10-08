import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from database import FuelDatabase

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    keyboard = get_main_keyboard()
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Добро пожаловать в бот учета расхода топлива!\n\n"
        "Используйте кнопки ниже или команды:\n"
        "/refill - Записать заправку\n"
        "/stats - Статистика расхода\n"
        "/reset - Сбросить данные\n"
        "/help - Помощь",
        reply_markup=keyboard
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display help information"""
    keyboard = get_main_keyboard()
    await update.message.reply_text(
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

async def refill_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the refill recording process"""
    keyboard = get_main_keyboard()
    await update.message.reply_text(
        "⛽ ЗАПРАВКА\n\n"
        "Введите данные в формате:\n"
        "литры цена пробег\n\n"
        "Пример: 45 2500 155000\n\n"
        "Или /cancel для отмены",
        reply_markup=keyboard
    )
    return WAITING_REFILL_DATA

async def refill_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process refill data from single line input"""
    user_id = update.effective_user.id
    keyboard = get_main_keyboard()
    
    try:
        parts = update.message.text.strip().split()
        
        if len(parts) != 3:
            await update.message.reply_text(
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
            await update.message.reply_text(
                "❌ Все значения должны быть положительными!\n\n"
                "Попробуйте снова:",
                reply_markup=keyboard
            )
            return WAITING_REFILL_DATA
        
        if db.add_refill(user_id, amount, cost, odometer):
            price_per_liter = cost / amount
            await update.message.reply_text(
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
            await update.message.reply_text(
                "❌ Ошибка сохранения. Попробуйте снова.",
                reply_markup=keyboard
            )
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат данных!\n\n"
            "Убедитесь, что:\n"
            "• Литры и цена - числа (можно с точкой)\n"
            "• Пробег - целое число\n\n"
            "Пример: 45.5 2500 155000",
            reply_markup=keyboard
        )
        return WAITING_REFILL_DATA

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display enhanced fuel consumption statistics"""
    user_id = update.effective_user.id
    keyboard = get_main_keyboard()
    
    # Get current consumption
    current = db.get_current_consumption(user_id)
    
    # Get monthly statistics
    monthly = db.get_monthly_statistics(user_id)
    
    if not current and not monthly:
        await update.message.reply_text(
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
    
    await update.message.reply_text(message, reply_markup=keyboard)

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display refill history"""
    user_id = update.effective_user.id
    keyboard = get_main_keyboard()
    refills = db.get_user_refills(user_id)
    
    if not refills:
        await update.message.reply_text(
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
    
    await update.message.reply_text(message, reply_markup=keyboard)

async def reset_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the data reset process"""
    keyboard = [[KeyboardButton("Да"), KeyboardButton("Нет")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "🗑️ СБРОС ДАННЫХ\n\n"
        "⚠️ Вы уверены?\n"
        "Это удалит ВСЮ историю заправок!\n\n"
        "Отправьте Да или Нет",
        reply_markup=reply_markup
    )
    return CONFIRM_RESET

async def reset_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm and execute data reset"""
    user_id = update.effective_user.id
    keyboard = get_main_keyboard()
    response = update.message.text.lower()
    
    if response == "да":
        if db.delete_user_data(user_id):
            await update.message.reply_text(
                "✅ Все данные удалены!\n\n"
                "Можете начать заново с ⛽ Заправиться",
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text(
                "❌ Ошибка при удалении данных.",
                reply_markup=keyboard
            )
    else:
        await update.message.reply_text(
            "❌ Сброс отменен.\n\n"
            "Ваши данные сохранены.",
            reply_markup=keyboard
        )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the current operation"""
    keyboard = get_main_keyboard()
    await update.message.reply_text(
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
    
    application = Application.builder().token(token).build()
    
    # Conversation handler for refill
    refill_handler = ConversationHandler(
        entry_points=[
            CommandHandler('refill', refill_start),
            MessageHandler(filters.Regex('^⛽ Заправиться$'), refill_start)
        ],
        states={
            WAITING_REFILL_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, refill_data)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Conversation handler for reset
    reset_handler = ConversationHandler(
        entry_points=[
            CommandHandler('reset', reset_start),
            MessageHandler(filters.Regex('^🗑️ Сбросить данные$'), reset_start)
        ],
        states={
            CONFIRM_RESET: [MessageHandler(filters.TEXT & ~filters.COMMAND, reset_confirm)],
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
    application.add_handler(MessageHandler(filters.Regex('^📊 Статистика$'), stats))
    application.add_handler(MessageHandler(filters.Regex('^ℹ️ Помощь$'), help_command))
    
    # Start the Bot
    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
