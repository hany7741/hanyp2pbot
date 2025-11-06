import os
import requests
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler
from supabase import create_client, Client 

# --- 1. تحميل المفاتيح والإعدادات وسعر الصرف الثابت ---
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PRICING_TABLE = os.getenv("PRICING_TABLE") 
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID") 

# تحديد سعر الصرف الثابت (الدولار مقابل الجنيه المصري)
USD_BUY_RATE_EGP = 49.0 
USD_SELL_RATE_EGP = 47.0 

# إعداد مراحل المحادثة
(CHOOSE_OPERATION, CHOOSE_CRYPTO_CURRENCY, ENTER_AMOUNT, FINAL_CONFIRMATION) = range(4) 

# إعداد اتصال Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# --- دوال جلب البيانات (لم تتغير) ---

async def get_realtime_pricing_data():
    if not supabase:
        print("❌ Supabase غير مُهيأ بشكل صحيح. (تحقق من SUPABASE_URL و SUPABASE_KEY)")
        return None
    try:
        response = supabase.table(PRICING_TABLE).select("name, fee_fory_buy, fee_fory_sell, address").execute()
        db_data = {}
        if not response.data:
            print("❌ Supabase: جدول العملات فارغ أو غير متاح.")
            return None
        for row in response.data:
            db_data[row['name']] = row
        final_pricing = {}
        base_currency = "USDT" 
        for currency, data in db_data.items():
            if currency == base_currency:
                buy_rate_okx = 1.0
                sell_rate_okx = 1.0
            else:
                inst_id = f"{currency}-{base_currency}"
                okx_ticker_url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
                okx_response = requests.get(okx_ticker_url, timeout=10)
                okx_response.raise_for_status()
                okx_data = okx_response.json()
                if okx_data.get('code') == '0' and okx_data.get('data') and okx_data['data'][0]:
                    ticker = okx_data['data'][0]
                    buy_rate_okx = float(ticker.get('askPx', 0))
                    sell_rate_okx = float(ticker.get('bidPx', 0))
                else:
                    continue 
            if buy_rate_okx > 0 and sell_rate_okx > 0:
                final_pricing[currency] = {
                    'buy_rate': buy_rate_okx,      
                    'sell_rate': sell_rate_okx,      
                    'fee_fory_buy': data['fee_fory_buy'],
                    'fee_fory_sell': data['fee_fory_sell'],
                    'address': data['address'] 
                }
        return final_pricing
    except requests.exceptions.RequestException as e:
        print(f"❌ خطأ في الاتصال بـ OKX API أو Supabase: {e}")
        return None
    except Exception as e:
        print(f"❌ خطأ عام في جلب البيانات: {e}")
        return None

# --- دوال مراحل المحادثة ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_name = update.effective_user.first_name or "عزيزي المستخدم"
    bot_username = context.bot.username
    if update.effective_chat.type in ["group", "supergroup"]:
        if not bot_username:
            await update.message.reply_text(
                f"❌ عذراً، لم أتمكن من الحصول على اسم المستخدم الخاص بي. يرجى البحث عني في المحادثات الخاصة والضغط على /start للمتابعة.",
                parse_mode="Markdown"
            )
            return ConversationHandler.END 
        await update.message.reply_text(
            f"👋 مرحباً بك يا **{user_name}** في خدمة التداول P2P! 🤝\n\n"
            "لإكمال عملية **الشراء/البيع بأمان وخصوصية،** يجب أن تبدأ الطلب في المحادثة الخاصة مع البوت.\n"
            "**للبدء، يرجى الضغط على اسم البوت التالي والتوجه للخاص:**\n"
            f"👈 **@{bot_username}**\n\n"
            "أرسل /start في الخاص لتبدأ.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    welcome_message = (
        f"👋 أهلاً بك يا **{user_name}** في بوت تبادل العملات المشفرة P2P! 🤝\n\n"
        "يسرنا خدمتك بأفضل الأسعار وأسرع طريقة.\n"
        "أسعار الصرف الثابتة لدينا لعملة **USDT**: \n"
        f"**سعر بيع الدولار (تدفعه للبوت):** **{USD_BUY_RATE_EGP:,.2f جنيه}**\n"
        f"**سعر شراء الدولار (تستلمه من البوت):** **{USD_SELL_RATE_EGP:,.2f جنيه}**\n\n"
        "برجاء اختيار نوع العملية للمتابعة:"
    )
    reply_keyboard = [["شراء (BUY) 🛒", "بيع (SELL) 💸"]]
    image_path = "welcome_image.jpg"
    if os.path.exists(image_path):
        with open(image_path, 'rb') as photo_file:
            await update.message.reply_photo(
                photo=InputFile(photo_file),
                caption=welcome_message,
                reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
                parse_mode="Markdown"
            )
    else:
        await update.message.reply_text(
            welcome_message,
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
            parse_mode="Markdown"
        )
    return CHOOSE_OPERATION 

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.callback_query.message if update.callback_query else update.message
    await message.reply_text(
        'تم إلغاء الطلب. شكراً لاستخدامك البوت.', 
        reply_markup=ReplyKeyboardRemove()
    )
    if 'order_data' in context.user_data:
        del context.user_data['order_data']
    return ConversationHandler.END

async def choose_crypto_currency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if "شراء" in text:
        operation = "شراء"
    elif "بيع" in text:
        operation = "بيع"
    else:
        await update.message.reply_text("اختيار غير صحيح. يرجى الضغط على زر 'شراء' أو 'بيع'.")
        return CHOOSE_OPERATION 
    context.user_data['order_data'] = {'operation': operation}
    all_prices = await get_realtime_pricing_data()
    if not all_prices or not list(all_prices.keys()):
        await update.message.reply_text("عذراً، لم نتمكن من جلب الأسعار اللحظية حالياً.")
        return ConversationHandler.END
    context.user_data['pricing_data'] = all_prices 
    currencies = list(all_prices.keys())
    reply_keyboard = [[sym] for sym in currencies]
    await update.message.reply_text(
        f"لقد اخترت: **{operation}**. \nبرجاء الضغط على رمز العملة المشفرة للمتابعة:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return CHOOSE_CRYPTO_CURRENCY 

async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    currency = update.message.text.upper()
    pricing_data = context.user_data.get('pricing_data', {})
    if currency not in pricing_data:
        await update.message.reply_text("رمز عملة غير صالح. يرجى اختيار عملة من الخيارات المتاحة.")
        return CHOOSE_CRYPTO_CURRENCY 
    context.user_data['order_data']['currency'] = currency
    price_info = pricing_data[currency]
    operation = context.user_data['order_data']['operation']
    try:
        if operation == "شراء":
            rate = float(price_info.get('buy_rate', 0)) 
            fee_column = 'fee_fory_buy'
        else: 
            rate = float(price_info.get('sell_rate', 0))
            fee_column = 'fee_fory_sell'
        fee = float(price_info.get(fee_column, 0)) 
    except ValueError:
        await update.message.reply_text("خطأ في بيانات الأسعار/الرسوم.")
        return ConversationHandler.END
    context.user_data['order_data']['rate'] = rate
    context.user_data['order_data']['fee_rate'] = fee
    details_message = f"✅ تم اختيار العملة: **{currency}**.\n"
    details_message += f"سعر الصرف الحالي ({operation}): **{rate:,.4f}** | الرسوم: **{fee:.2f}%**\n\n"
    details_message += "**برجاء إدخال الكمية التي تريدها الآن (بالأرقام فقط):**"
    await update.message.reply_text(details_message, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return ENTER_AMOUNT 

async def process_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if not update.message or not update.message.text:
            raise ValueError("المدخل ليس نصًا صالحًا.") 
        amount = float(update.message.text.strip()) 
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("الكمية غير صحيحة. يرجى إدخال رقم موجب فقط:")
        return ENTER_AMOUNT 
    context.user_data['order_data']['amount'] = amount
    reply_keyboard = [["دولار أمريكي (USD)", "جنيه مصري (EGP)"]]
    await update.message.reply_text(
        "✅ تم استلام الكمية. \n\n"
        "برجاء اختيار العملة التي تفضل الدفع بها/الاستلام بها:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return FINAL_CONFIRMATION

async def process_final_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_response = update.message.text
    order_data = context.user_data['order_data']
    if 'payment_currency' not in order_data:
        if "USD" in user_response:
            order_data['payment_currency'] = 'USD'
            order_data['exchange_rate'] = 1.0
        elif "EGP" in user_response:
            order_data['payment_currency'] = 'EGP'
            if order_data['operation'] == "شراء":
                order_data['exchange_rate'] = USD_BUY_RATE_EGP
            else:
                order_data['exchange_rate'] = USD_SELL_RATE_EGP
        else:
            await update.message.reply_text("اختيار عملة دفع غير صالح. يرجى اختيار 'دولار أمريكي (USD)' أو 'جنيه مصري (EGP)'.")
            return FINAL_CONFIRMATION
        rate = order_data['rate']
        amount = order_data['amount']
        fee_rate_decimal = order_data['fee_rate'] / 100 
        exchange_rate = order_data['exchange_rate']
        total_before_fee_usd = amount * rate
        if order_data['operation'] == "شراء":
            total_amount_usd = total_before_fee_usd * (1 + fee_rate_decimal)
            action = "تدفعه" 
        else: 
            total_amount_usd = total_before_fee_usd * (1 - fee_rate_decimal)
            action = "تستلمه" 
        fee_amount_usd = abs(total_amount_usd - total_before_fee_usd)
        total_amount_final = total_amount_usd * exchange_rate
        fee_amount_final = fee_amount_usd * exchange_rate
        order_data['total_amount'] = total_amount_final
        order_data['fee_amount'] = fee_amount_final 
        payment_currency_label = order_data['payment_currency']
        summary = f"**💰 ملخص الطلب - بانتظار التأكيد 💰**\n\n"
        summary += f"نوع العملية: **{order_data['operation']}**\n"
        summary += f"العملة المشفرة: **{order_data['currency']}**\n"
        summary += f"الكمية المطلوبة: **{order_data['amount']:,.4f} {order_data['currency']}**\n"
        summary += f"سعر الصرف: {rate:,.4f} | الرسوم: {order_data['fee_rate']:.2f}%\n"
        if payment_currency_label == 'EGP':
             summary += f"سعر صرف الدولار (ثابت): **1 USD = {order_data['exchange_rate']} EGP**\n"
        summary += f"قيمة الرسوم: {fee_amount_final:,.4f} {payment_currency_label}\n"
        summary += f"**المبلغ النهائي الذي {action}: {total_amount_final:,.4f} {payment_currency_label}**\n\n"
        summary += "لإرسال الطلب إلى الإدارة لتزويدك بتفاصيل الدفع/العنوان، اضغط على **إكمال الطلب**."
        reply_keyboard = [["✅ إكمال الطلب", "❌ إلغاء"]]
        await update.message.reply_text(
            summary, 
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return FINAL_CONFIRMATION
    if user_response == "❌ إلغاء":
        return await cancel_command(update, context)
    if user_response != "✅ إكمال الطلب":
        await update.message.reply_text("يرجى الضغط على زر **إكمال الطلب** أو **إلغاء**.", parse_mode="Markdown")
        return FINAL_CONFIRMATION
    if not ADMIN_CHAT_ID or not str(ADMIN_CHAT_ID).isdigit():
        await update.message.reply_text(
            "❌ عذراً، لم يتم إعداد معرف المدير (ADMIN_CHAT_ID) بشكل صحيح. لا يمكن إرسال الطلب."
        )
        return ConversationHandler.END
    user = update.effective_user
    admin_message = f"🔔 **طلب P2P جديد - تم إكماله في الخاص** 🔔\n\n"
    admin_message += f"**من:** [{user.full_name}](tg://user?id={user.id})\n"
    admin_message += f"**ID المستخدم:** `{user.id}`\n"
    admin_message += f"--- تفاصيل الطلب ---\n"
    admin_message += f"العملية: **{order_data['operation']}**\n"
    admin_message += f"العملة المشفرة: **{order_data['currency']}**\n"
    admin_message += f"عملة الدفع/الاستلام: **{order_data['payment_currency']}**\n"
    if order_data['payment_currency'] == 'EGP':
         admin_message += f"سعر الصرف الثابت: **1 USD = {order_data['exchange_rate']} EGP**\n"
    admin_message += f"الكمية المطلوبة: **{order_data['amount']:,.4f} {order_data['currency']}**\n"
    action_word = "يدفعه" if order_data['operation'] == "شراء" else "يستلمه"
    admin_message += f"المبلغ النهائي الذي {action_word}: **{order_data['total_amount']:,.4f} {order_data['payment_currency']}**\n"
    admin_message += f"الإجراء: **الرجاء التواصل مع المستخدم لإرسال طرق الدفع/العنوان المناسب لإتمام الطلب.**"
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID, 
        text=admin_message, 
        parse_mode="Markdown"
    )
    await update.message.reply_text(
        "✅ تم إرسال طلبك بنجاح. سيتم التواصل معك قريباً في هذه المحادثة الخاصة لإكمال العملية.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# --- دالة التشغيل الرئيسية ---
def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        print("❌ خطأ: مفتاح TELEGRAM_BOT_TOKEN غير موجود أو فارغ!")
        return
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start_request", start_command), CommandHandler("start", start_command)],
        states={
            CHOOSE_OPERATION: [MessageHandler(filters.Text(['شراء (BUY) 🛒', 'بيع (SELL) 💸']) & filters.ChatType.PRIVATE, choose_crypto_currency)],
            CHOOSE_CRYPTO_CURRENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, enter_amount)],
            ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, process_amount)], 
            FINAL_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, process_final_confirmation)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command), MessageHandler(filters.COMMAND, cancel_command)],
    )
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, lambda update, context: ConversationHandler.END))
    print("✅ البوت بدأ العمل بنجاح.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
