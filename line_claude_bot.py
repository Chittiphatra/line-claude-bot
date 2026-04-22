"""
LINE Chatbot + Claude API (มีความจำแยกตามกรุ๊ป/แชทเดี่ยว)
============================================================
บอทแชท LINE ที่ใช้ Claude เป็นสมองในการตอบข้อความ
มีระบบความจำแยกตามแต่ละกรุ๊ปและแต่ละคน

วิธีติดตั้ง:
1. pip install flask gunicorn line-bot-sdk anthropic
2. ตั้งค่า Environment Variables:
   - LINE_CHANNEL_SECRET       (ได้จาก LINE Developers Console)
   - LINE_CHANNEL_ACCESS_TOKEN (ได้จาก LINE Developers Console)
   - ANTHROPIC_API_KEY         (ได้จาก console.anthropic.com)
3. รันด้วย: python line_claude_bot.py
4. ตั้ง Webhook URL ใน LINE Developers Console เป็น https://<your-server>/callback
"""

import os
import time
from collections import defaultdict
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
# ตั้งค่าความจำ
# ============================================================
MAX_HISTORY = 100          # จำได้สูงสุดกี่ข้อความต่อห้อง (20 คู่สนทนา)
HISTORY_TIMEOUT = 86400    # ลบความจำหลังไม่มีคนคุย (วินาที) = 1 ชั่วโมง

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
# ระบบความจำ — เก็บประวัติแชทแยกตาม chat_id
# chat_id = group_id (ถ้าอยู่ในกรุ๊ป) หรือ user_id (ถ้าแชทเดี่ยว)
# ============================================================
chat_histories = defaultdict(list)       # {chat_id: [messages]}
chat_last_active = defaultdict(float)    # {chat_id: timestamp}

# ============================================================
# System Prompt — ปรับแต่งบุคลิกบอทได้ตรงนี้เลยค่ะ
# ============================================================
SYSTEM_PROMPT = """คุณเป็นผู้ช่วยที่เป็นมิตรและพูดภาษาไทย เป็นเพศหญิง เรียกแทนตัวเองว่า "หนู" เรียกผู้ใช้ว่า "พี่" 
ตอบสั้น กระชับ เข้าใจง่าย อ่อนหวาน ใส่อิโมจิบ้าง เหมาะกับการแชทใน LINE ไม่ต้องบอกว่าตัวเองเป็น claude ให้ปกปิดไว้ เป็นสิ่งที่น่าค้นหา"""


def cleanup_old_histories():
    """ลบประวัติแชทที่ไม่มีคนคุยนานเกิน HISTORY_TIMEOUT"""
    now = time.time()
    expired = [
        chat_id for chat_id, last in chat_last_active.items()
        if now - last > HISTORY_TIMEOUT
    ]
    for chat_id in expired:
        del chat_histories[chat_id]
        del chat_last_active[chat_id]


def get_chat_id(event):
    """ดึง chat_id — ใช้ group_id ถ้าอยู่ในกรุ๊ป, ใช้ room_id ถ้าอยู่ในห้อง, ไม่งั้นใช้ user_id"""
    source = event.source
    if source.type == "group":
        return source.group_id
    elif source.type == "room":
        return source.room_id
    else:
        return source.user_id


def ask_claude(chat_id: str, user_message: str) -> str:
    """ส่งข้อความไปถาม Claude พร้อมประวัติแชท"""
    try:
        # ลบประวัติเก่าที่หมดอายุ
        cleanup_old_histories()

        # บันทึกข้อความผู้ใช้
        chat_histories[chat_id].append({"role": "user", "content": user_message})
        chat_last_active[chat_id] = time.time()

        # ตัดประวัติเก่าถ้าเยอะเกินไป (เก็บแค่ MAX_HISTORY คู่ล่าสุด)
        if len(chat_histories[chat_id]) > MAX_HISTORY * 2:
            chat_histories[chat_id] = chat_histories[chat_id][-(MAX_HISTORY * 2):]

        # ส่งไปถาม Claude พร้อมประวัติทั้งหมด
        response = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=chat_histories[chat_id],
        )

        assistant_reply = response.content[0].text

        # บันทึกคำตอบของบอทลงประวัติ
        chat_histories[chat_id].append({"role": "assistant", "content": assistant_reply})

        return assistant_reply

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
    chat_id = get_chat_id(event)

    # ส่งไปถาม Claude พร้อมประวัติ
    reply_text = ask_claude(chat_id, user_message)

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
