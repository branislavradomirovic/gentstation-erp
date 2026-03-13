from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import sqlite3

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Extract the '15' from '/start 15'
    if context.args:
        erp_employee_id = context.args[0]
        
        # Connect to your ERP database
        conn = sqlite3.connect('gentstation.db') # Ensure path is correct
        cursor = conn.cursor()
        
        # Update the employee record with their Telegram Chat ID
        cursor.execute("UPDATE employees SET telegram_chat_id = ? WHERE id = ?", 
                       (chat_id, erp_employee_id))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Registration Successful! Your account (ID: {erp_employee_id}) is now linked to this Telegram chat. You can now send video reports.")
    else:
        await update.message.reply_text("Welcome to GentStation! Please use the link provided in your welcome email to register.")

if __name__ == '__main__':
    # Use the TOKEN from your .env
    app = ApplicationBuilder().token("YOUR_TELEGRAM_BOT_TOKEN").build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()