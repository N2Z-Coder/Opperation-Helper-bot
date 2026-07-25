import os
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from openai import OpenAI

# Environment Variable ကနေ Key တွေယူမယ်
TELEGRAM_TOKEN = os.environ["8900511388:AAFtHhva5BN0xLNtZoFauD3s3C1bILbNf6g"]
OPENAI_KEY = os.environ["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"]

client = OpenAI(api_key=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)


async def reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    try:
        result = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "သင်သည် မြန်မာဘာသာဖြင့် နည်းပညာဆိုင်ရာ "
                        "အချက်အလက်များကို ရှင်းပြပေးသော Assistant ဖြစ်သည်။ "
                        "Userပို့သော စာတွင်ပါသောစကားလုံးကို အဓိပ္ပာယ်၊ အသုံးပြုပုံ၊ "
                        "အလုပ်လုပ်ပုံတို့ဖြင့် လွယ်ကူစွာရှင်းပြပါ။ပြီးတော့ စာကြောင်းနောက်ဆုံးမှာ Create by N2 ဆိုတာထည့်ပေးပါ။"
                    )
                },
                {
                    "role": "user",
                    "content": user_text
                }
            ]
        )

        answer = result.choices[0].message.content

    except Exception as e:
        answer = "အခုအချိန်မှာ အဖြေထုတ်မပေးနိုင်သေးပါ။"

    await update.message.reply_text(answer)


app = Application.builder().token(TELEGRAM_TOKEN).build()

app.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, reply_message)
)

print("Bot Started")

app.run_polling()
