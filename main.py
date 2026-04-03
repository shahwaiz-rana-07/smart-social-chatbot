from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import os
import httpx
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = FastAPI()

# Global auto-reply status (in production, this should be stored in database)
auto_reply_enabled = True

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
INSTAGRAM_ID = os.getenv("INSTAGRAM_ID")

# Facebook configuration
FACEBOOK_VERIFY_TOKEN = os.getenv("FACEBOOK_VERIFY_TOKEN", VERIFY_TOKEN)
FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN", ACCESS_TOKEN)
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
FACEBOOK_ID = os.getenv("FACEBOOK_ID")


@app.get("/")
def home():
    return {"status": "Bot is running!"}


@app.get("/api/status")
def get_status():
    return {
        "server": "online",
        "webhook": "active",
        "instagram_api": "pending_approval",
        "instagram_id": INSTAGRAM_ID,
        "facebook_id": FACEBOOK_ID,
        "facebook_page_id": FACEBOOK_PAGE_ID,
        "auto_reply": auto_reply_enabled,
    }


@app.get("/api/auto-reply/status")
def get_auto_reply_status():
    return {"enabled": auto_reply_enabled}


@app.post("/api/auto-reply/toggle")
async def toggle_auto_reply(request: Request):
    global auto_reply_enabled
    data = await request.json()
    auto_reply_enabled = data.get("enabled", True)
    return {"enabled": auto_reply_enabled}


@app.get("/api/messages")
def get_messages():
    messages = []
    try:
        with open("messages.txt", "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {"messages": []}

            # entries written by save_message as:
            # \n--- {timestamp} ---\nFrom: ...\nMessage: ...\nReply: ...
            entries = content.split("\n--- ")
            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue

                lines = entry.split("\n")
                if len(lines) < 4:
                    continue

                raw_ts = lines[0].replace("---", "").strip()
                from_line = lines[1]
                msg_line = lines[2]
                reply_line = lines[3]

                messages.append(
                    {
                        "timestamp": raw_ts,
                        "from": from_line.replace("From:", "").strip(),
                        "message": msg_line.replace("Message:", "").strip(),
                        "reply": reply_line.replace("Reply:", "").strip(),
                    }
                )
    except FileNotFoundError:
        pass

    return {"messages": messages}


@app.get("/api/facebook/messages")
def get_facebook_messages():
    messages = []
    try:
        with open("facebook_messages.txt", "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {"messages": []}

            # entries written by save_facebook_message as:
            # \n--- {timestamp} ---\nFrom: ...\nMessage: ...\nReply: ...
            entries = content.split("\n--- ")
            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue

                lines = entry.split("\n")
                if len(lines) < 4:
                    continue

                raw_ts = lines[0].replace("---", "").strip()
                from_line = lines[1]
                msg_line = lines[2]
                reply_line = lines[3]

                messages.append(
                    {
                        "timestamp": raw_ts,
                        "from": from_line.replace("From:", "").strip(),
                        "message": msg_line.replace("Message:", "").strip(),
                        "reply": reply_line.replace("Reply:", "").strip(),
                    }
                )
    except FileNotFoundError:
        pass

    return {"messages": messages}


@app.get("/api/keywords")
def get_keywords():
    keywords = []
    try:
        with open("replies.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "|" in line:
                    keyword, reply = line.split("|", 1)
                    keywords.append({"keyword": keyword, "reply": reply})
    except FileNotFoundError:
        pass

    return {"keywords": keywords}


@app.get("/api/facebook/keywords")
def get_facebook_keywords():
    keywords = []
    try:
        with open("facebook_replies.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "|" in line:
                    keyword, reply = line.split("|", 1)
                    keywords.append({"keyword": keyword, "reply": reply})
    except FileNotFoundError:
        pass

    return {"keywords": keywords}


@app.post("/api/keywords")
async def add_keyword(request: Request):
    data = await request.json()
    keyword = data.get("keyword", "").strip().lower()
    reply = data.get("reply", "").strip()

    if not keyword or not reply:
        return JSONResponse({"error": "Keyword and reply required"}, status_code=400)

    with open("replies.txt", "a", encoding="utf-8") as f:
        f.write(f"{keyword}|{reply}\n")

    return {"success": True, "keyword": keyword}


@app.delete("/api/keywords/{keyword}")
def delete_keyword(keyword: str):
    try:
        with open("replies.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()

        with open("replies.txt", "w", encoding="utf-8") as f:
            for line in lines:
                if not line.startswith(f"{keyword}|"):
                    f.write(line)

        return {"success": True}
    except FileNotFoundError:
        return JSONResponse({"error": "File not found"}, status_code=404)


@app.delete("/api/messages/{message_id}")
def delete_message(message_id: str):
    try:
        # Delete from Instagram messages
        try:
            with open("messages.txt", "r", encoding="utf-8") as f:
                content = f.read()

            # Find and remove the message entry
            entries = content.split("\n--- ")
            filtered_entries = []
            deleted = False

            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue

                # Check if this entry contains the message_id (timestamp)
                if message_id in entry:
                    deleted = True
                    continue
                filtered_entries.append("--- " + entry if entry else "")

            if deleted:
                with open("messages.txt", "w", encoding="utf-8") as f:
                    f.write("\n".join(filtered_entries))
                return {"success": True, "platform": "instagram"}
        except FileNotFoundError:
            pass

        # Delete from Facebook messages
        try:
            with open("facebook_messages.txt", "r", encoding="utf-8") as f:
                content = f.read()

            # Find and remove the message entry
            entries = content.split("\n--- ")
            filtered_entries = []
            deleted = False

            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue

                # Check if this entry contains the message_id (timestamp)
                if message_id in entry:
                    deleted = True
                    continue
                filtered_entries.append("--- " + entry if entry else "")

            if deleted:
                with open("facebook_messages.txt", "w", encoding="utf-8") as f:
                    f.write("\n".join(filtered_entries))
                return {"success": True, "platform": "facebook"}
        except FileNotFoundError:
            pass

        return JSONResponse({"error": "Message not found"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/facebook/keywords")
async def add_facebook_keyword(request: Request):
    data = await request.json()
    keyword = data.get("keyword", "").strip().lower()
    reply = data.get("reply", "").strip()

    if not keyword or not reply:
        return JSONResponse({"error": "Keyword and reply required"}, status_code=400)

    with open("facebook_replies.txt", "a", encoding="utf-8") as f:
        f.write(f"{keyword}|{reply}\n")

    return {"success": True, "keyword": keyword}


@app.delete("/api/facebook/keywords/{keyword}")
def delete_facebook_keyword(keyword: str):
    try:
        with open("facebook_replies.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()

        with open("facebook_replies.txt", "w", encoding="utf-8") as f:
            for line in lines:
                if not line.startswith(f"{keyword}|"):
                    f.write(line)

        return {"success": True}
    except FileNotFoundError:
        return JSONResponse({"error": "File not found"}, status_code=404)


@app.post("/api/test-message")
async def test_message(request: Request):
    data = await request.json()
    sender = data.get("sender", "test_user")
    message = data.get("message", "Hello")

    reply = generate_reply(message)
    save_message(sender, message, reply)

    return {
        "success": True,
        "from": sender,
        "message": message,
        "reply": reply,
    }


@app.post("/api/facebook/test-message")
async def test_facebook_message(request: Request):
    data = await request.json()
    sender = data.get("sender", "test_user")
    message = data.get("message", "Hello")

    reply = generate_facebook_reply(message)
    save_facebook_message(sender, message, reply)

    return {
        "success": True,
        "from": sender,
        "message": message,
        "reply": reply,
    }


@app.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        print("Webhook verified!")
        return int(hub_challenge)
    return JSONResponse({"error": "Verification failed"}, status_code=403)


@app.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.json()
    print("Received webhook:")
    print(body)

    try:
        entry = body.get("entry", [])[0]
        messaging_events = entry.get("messaging", [])

        for event in messaging_events:
            sender_id = event.get("sender", {}).get("id")
            recipient_id = event.get("recipient", {}).get("id")
            message = event.get("message", {}) or {}

            text = message.get("text", "")
            is_echo = message.get("is_echo", False)

            # Skip echoes (messages sent by the IG business account itself) [web:41][web:96]
            if is_echo:
                print("Skipping echo message")
                continue

            # Extra safety: skip if sender is your own IG id
            if sender_id == INSTAGRAM_ID:
                print("Skipping message from own IG id")
                continue

            if sender_id and text:
                print(f"Incoming message from {sender_id} to {recipient_id}: {text}")

                if auto_reply_enabled:
                    reply = generate_reply(text)
                    await send_reply(sender_id, reply)

                    username = await get_username(sender_id)
                    save_message(username, text, reply)
                else:
                    # Save message without reply when auto-reply is disabled
                    username = await get_username(sender_id)
                    save_message(username, text, "Auto-reply disabled")

    except Exception as e:
        print(f"Error processing message: {e}")

    return {"status": "received"}


@app.get("/facebook/webhook")
def verify_facebook_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == FACEBOOK_VERIFY_TOKEN:
        print("Facebook webhook verified!")
        return int(hub_challenge)
    return JSONResponse({"error": "Facebook verification failed"}, status_code=403)


@app.post("/facebook/webhook")
async def receive_facebook_webhook(request: Request):
    body = await request.json()
    print("Received Facebook webhook:")
    print(body)

    try:
        entry = body.get("entry", [])[0]
        messaging_events = entry.get("messaging", [])

        for event in messaging_events:
            sender_id = event.get("sender", {}).get("id")
            recipient_id = event.get("recipient", {}).get("id")
            message = event.get("message", {}) or {}

            text = message.get("text", "")
            is_echo = message.get("is_echo", False)

            # Skip echoes (messages sent by the page itself)
            if is_echo:
                print("Skipping Facebook echo message")
                continue

            # Extra safety: skip if sender is your own page id
            if sender_id == FACEBOOK_PAGE_ID:
                print("Skipping message from own Facebook page")
                continue

            if sender_id and text:
                print(f"Incoming Facebook message from {sender_id} to {recipient_id}: {text}")

                if auto_reply_enabled:
                    reply = generate_facebook_reply(text)
                    await send_facebook_reply(sender_id, reply)

                    username = await get_facebook_username(sender_id)
                    save_facebook_message(username, text, reply)
                else:
                    # Save message without reply when auto-reply is disabled
                    username = await get_facebook_username(sender_id)
                    save_facebook_message(username, text, "Auto-reply disabled")

    except Exception as e:
        print(f"Error processing Facebook message: {e}")

    return {"status": "received"}


def load_replies():
    replies = {}
    try:
        with open("replies.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "|" in line:
                    keyword, reply = line.split("|", 1)
                    replies[keyword.lower()] = reply
    except Exception:
        pass
    return replies


def load_facebook_replies():
    replies = {}
    try:
        with open("facebook_replies.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "|" in line:
                    keyword, reply = line.split("|", 1)
                    replies[keyword.lower()] = reply
    except Exception:
        pass
    return replies


def generate_reply(message: str) -> str:
    message_lower = message.lower()
    replies = load_replies()

    for keyword, reply in replies.items():
        if keyword in message_lower:
            return reply

    return "Thanks for your message! Someone will get back to you soon."


def generate_facebook_reply(message: str) -> str:
    message_lower = message.lower()
    replies = load_facebook_replies()

    for keyword, reply in replies.items():
        if keyword in message_lower:
            return reply

    return "Thanks for your Facebook message! Someone will get back to you soon."


async def get_username(user_id: str) -> str:
    try:
        url = f"https://graph.facebook.com/v19.0/{user_id}"
        params = {
            "fields": "username",
            "access_token": ACCESS_TOKEN,
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            data = response.json()
            return data.get("username", user_id)
    except Exception:
        return user_id


async def get_facebook_username(user_id: str) -> str:
    try:
        url = f"https://graph.facebook.com/v19.0/{user_id}"
        params = {
            "fields": "first_name,last_name",
            "access_token": FACEBOOK_ACCESS_TOKEN,
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            data = response.json()
            first_name = data.get("first_name", "")
            last_name = data.get("last_name", "")
            if first_name and last_name:
                return f"{first_name} {last_name}"
            return user_id
    except Exception:
        return user_id


async def send_reply(recipient_id: str, message_text: str):
    url = "https://graph.facebook.com/v19.0/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
    }
    params = {"access_token": ACCESS_TOKEN}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, params=params)
        print(f"Instagram reply sent: {message_text}")
        print(f"Response: {response.json()}")


async def send_facebook_reply(recipient_id: str, message_text: str):
    url = f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
    }
    params = {"access_token": FACEBOOK_ACCESS_TOKEN}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, params=params)
        print(f"Facebook reply sent: {message_text}")
        print(f"Response: {response.json()}")


def save_message(sender: str, message: str, reply: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("messages.txt", "a", encoding="utf-8") as f:
        f.write(f"\n--- {timestamp} ---\n")
        f.write(f"From: {sender}\n")
        f.write(f"Message: {message}\n")
        f.write(f"Reply: {reply}\n")


def save_facebook_message(sender: str, message: str, reply: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("facebook_messages.txt", "a", encoding="utf-8") as f:
        f.write(f"\n--- {timestamp} ---\n")
        f.write(f"From: {sender}\n")
        f.write(f"Message: {message}\n")
        f.write(f"Reply: {reply}\n")


# Serve dashboard (root page)
@app.get("/")
async def serve_dashboard_page():
    return FileResponse("dashboard.html", media_type="text/html")

# Serve login page
@app.get("/login")
async def serve_login_page():
    return FileResponse("login.html", media_type="text/html")

# Serve dashboard (alternative route)
@app.get("/dashboard")
async def serve_dashboard_alt():
    return FileResponse("dashboard.html", media_type="text/html")

# Serve static files (but not at root to avoid conflicts)
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory=".", html=True), name="static")
