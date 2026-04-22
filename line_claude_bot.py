"""
LINE Chatbot + Claude API
=========================
บอทแชท LINE ที่ใช้ Claude เป็นสมองในการตอบข้อความ

วิธีติดตั้ง:
1. pip install flask line-bot-sdk anthropic
2. ตั้งค่า Environment Variables:
   - LINE_CHANNEL_SECRET       (ได้จาก LINE Developers Console)
   - LINE_CHANNEL_ACCESS_TOKEN (ได้จาก LINE Developers Console)
   - ANTHROPIC_API_KEY         (ได้จาก console.anthropic.com)
3. รันด้วย: python line_claude_bot.py
4. ตั้ง Webhook URL ใน LINE Developers Console เป็น https://<your-server>/callback
"""

import os
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
import anthropic

# ============================================================
# ตั้งค่าต่าง ๆ (ใส่ค่าจริงใน Environment Variables นะคะ)
# ============================================================
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "ใส่ channel secret ที่นี่")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "ใส่ access token ที่นี่")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "ใส่ api key ที่นี่")

# ============================================================
# สร้าง App
# ============================================================
app = Flask(__name__)

# LINE SDK setup
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Anthropic (Claude) setup
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ============================================================
# System Prompt — ปรับแต่งบุคลิกบอทได้ตรงนี้เลยค่ะ
# ============================================================
SYSTEM_PROMPT = """คุณเป็นผู้ช่วยที่เป็นมิตรและพูดภาษาไทย 
ตอบสั้น กระชับ เข้าใจง่าย เหมาะกับการแชทใน LINE"""


def ask_claude(user_message: str) -> str:
    """ส่งข้อความไปถาม Claude แล้วรับคำตอบกลับมา"""
    try:
        response = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",  # รุ่นประหยัด เร็ว เหมาะกับแชทบอท
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_message}
            ],
        )
        return response.content[0].text
    except Exception as e:
        print(f"Claude API Error: {e}")
        return "ขอโทษค่ะ ตอนนี้ระบบมีปัญหา ลองใหม่อีกครั้งนะคะ 🙏"


# ============================================================
# LINE Webhook
# ============================================================
@app.route("/callback", methods=["POST"])
def callback():
    """LINE จะส่งข้อความมาที่นี่"""
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent):
    """เมื่อมีคนส่งข้อความมา → ถาม Claude → ตอบกลับ"""
    user_message = event.message.text

    # ส่งไปถาม Claude
    reply_text = ask_claude(user_message)

    # ตอบกลับใน LINE
    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)],
            )
        )


# ============================================================
# รัน Server
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 LINE Claude Bot กำลังทำงานที่ port {port}")
    app.run(host="0.0.0.0", port=port)
