from fastapi import FastAPI, Request, Depends, HTTPException, status, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import httpx
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Import our modules
from database import get_db, create_tables
from models import (
    User, FacebookPage, Subscriber, Message, BotFlow, BotFlowStep,
    Campaign, CampaignMessage, Post, Subscription, Analytics, WebhookLog,
    Platform, MessageType, UserRole, SubscriptionPlan
)
from auth import verify_password, get_password_hash, create_access_token, verify_token

load_dotenv()

app = FastAPI(title="XeroChat Pro", description="Complete Messenger Marketing Software")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# Configuration
FACEBOOK_VERIFY_TOKEN = os.getenv("FACEBOOK_VERIFY_TOKEN")
FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID")
INSTAGRAM_VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
INSTAGRAM_ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
INSTAGRAM_ID = os.getenv("INSTAGRAM_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Dependency to get current user
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    username = verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user

# Authentication endpoints
@app.post("/api/auth/login")
async def login(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    username = data.get("username")
    password = data.get("password")

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer", "user": {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "subscription_plan": user.subscription_plan.value
    }}

@app.post("/api/auth/register")
async def register(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    # Check if user exists
    if db.query(User).filter((User.username == username) | (User.email == email)).first():
        raise HTTPException(status_code=400, detail="User already exists")

    # Create user
    hashed_password = get_password_hash(password)
    user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        full_name=data.get("full_name", "")
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer", "user": {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "subscription_plan": user.subscription_plan.value
    }}

# Dashboard endpoints
@app.get("/api/dashboard/stats")
async def get_dashboard_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Get basic stats
    total_subscribers = db.query(Subscriber).filter(Subscriber.user_id == current_user.id).count()
    total_messages = db.query(Message).filter(Message.user_id == current_user.id).count()
    active_campaigns = db.query(Campaign).filter(
        Campaign.user_id == current_user.id,
        Campaign.status == 'running'
    ).count()
    total_pages = db.query(FacebookPage).filter(FacebookPage.user_id == current_user.id).count()

    return {
        "total_subscribers": total_subscribers,
        "total_messages": total_messages,
        "active_campaigns": active_campaigns,
        "total_pages": total_pages,
        "subscription_plan": current_user.subscription_plan.value
    }

@app.get("/api/messages")
async def get_messages(
    platform: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Message).filter(Message.user_id == current_user.id)

    if platform:
        query = query.filter(Message.platform == Platform(platform))

    messages = query.order_by(Message.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "messages": [
            {
                "id": msg.id,
                "platform": msg.platform.value,
                "direction": msg.direction,
                "content": msg.content,
                "subscriber": {
                    "username": msg.subscriber.username if msg.subscriber else None,
                    "first_name": msg.subscriber.first_name if msg.subscriber else None,
                    "last_name": msg.subscriber.last_name if msg.subscriber else None
                },
                "created_at": msg.created_at.isoformat(),
                "is_read": msg.is_read,
                "is_replied": msg.is_replied
            }
            for msg in messages
        ]
    }

@app.post("/api/messages/send")
async def send_message(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()
    subscriber_id = data.get("subscriber_id")
    platform = data.get("platform")
    content = data.get("content")

    subscriber = db.query(Subscriber).filter(
        Subscriber.id == subscriber_id,
        Subscriber.user_id == current_user.id
    ).first()

    if not subscriber:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    # Save message to database
    message = Message(
        user_id=current_user.id,
        page_id=subscriber.page_id,
        subscriber_id=subscriber.id,
        platform=Platform(platform),
        direction="outbound",
        content=content,
        is_read=True
    )
    db.add(message)
    db.commit()

    # Send via platform API
    if platform == "facebook":
        await send_facebook_message(subscriber.subscriber_id, content)
    elif platform == "instagram":
        await send_instagram_message(subscriber.subscriber_id, content)

    return {"success": True, "message_id": message.id}

# Facebook Page Management
@app.get("/api/pages")
async def get_pages(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pages = db.query(FacebookPage).filter(FacebookPage.user_id == current_user.id).all()
    return {
        "pages": [
            {
                "id": page.id,
                "page_id": page.page_id,
                "page_name": page.page_name,
                "is_active": page.is_active,
                "created_at": page.created_at.isoformat()
            }
            for page in pages
        ]
    }

@app.post("/api/pages")
async def add_page(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()
    page_id = data.get("page_id")
    page_name = data.get("page_name")
    access_token = data.get("access_token")

    # Verify page access token
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://graph.facebook.com/v19.0/{page_id}",
                params={"access_token": access_token, "fields": "name,id"}
            )
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Invalid page access token")
    except:
        raise HTTPException(status_code=400, detail="Unable to verify page access token")

    page = FacebookPage(
        user_id=current_user.id,
        page_id=page_id,
        page_name=page_name,
        page_access_token=access_token
    )
    db.add(page)
    db.commit()
    db.refresh(page)

    return {"success": True, "page": {
        "id": page.id,
        "page_id": page.page_id,
        "page_name": page.page_name,
        "is_active": page.is_active
    }}

# Subscriber Management
@app.get("/api/subscribers")
async def get_subscribers(
    page_id: Optional[int] = None,
    platform: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Subscriber).filter(Subscriber.user_id == current_user.id)

    if page_id:
        query = query.filter(Subscriber.page_id == page_id)
    if platform:
        query = query.filter(Subscriber.platform == Platform(platform))

    subscribers = query.order_by(Subscriber.subscribed_at.desc()).offset(offset).limit(limit).all()

    return {
        "subscribers": [
            {
                "id": sub.id,
                "subscriber_id": sub.subscriber_id,
                "platform": sub.platform.value,
                "username": sub.username,
                "first_name": sub.first_name,
                "last_name": sub.last_name,
                "profile_pic": sub.profile_pic,
                "is_active": sub.is_active,
                "subscribed_at": sub.subscribed_at.isoformat(),
                "last_message_at": sub.last_message_at.isoformat() if sub.last_message_at else None,
                "tags": sub.tags
            }
            for sub in subscribers
        ]
    }

# Bot Flow Management
@app.get("/api/bot-flows")
async def get_bot_flows(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    flows = db.query(BotFlow).filter(BotFlow.user_id == current_user.id).all()
    return {
        "flows": [
            {
                "id": flow.id,
                "name": flow.name,
                "description": flow.description,
                "flow_type": flow.flow_type.value,
                "platform": flow.platform.value,
                "is_active": flow.is_active,
                "created_at": flow.created_at.isoformat()
            }
            for flow in flows
        ]
    }

@app.post("/api/bot-flows")
async def create_bot_flow(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()

    flow = BotFlow(
        user_id=current_user.id,
        name=data.get("name"),
        description=data.get("description"),
        flow_type=data.get("flow_type", "keyword"),
        platform=data.get("platform"),
        config=data.get("config", {})
    )
    db.add(flow)
    db.commit()
    db.refresh(flow)

    return {"success": True, "flow": {
        "id": flow.id,
        "name": flow.name,
        "flow_type": flow.flow_type.value,
        "platform": flow.platform.value,
        "is_active": flow.is_active
    }}

# Campaign Management
@app.get("/api/campaigns")
async def get_campaigns(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    campaigns = db.query(Campaign).filter(Campaign.user_id == current_user.id).all()
    return {
        "campaigns": [
            {
                "id": camp.id,
                "name": camp.name,
                "description": camp.description,
                "campaign_type": camp.campaign_type,
                "platform": camp.platform.value,
                "status": camp.status,
                "scheduled_at": camp.scheduled_at.isoformat() if camp.scheduled_at else None,
                "created_at": camp.created_at.isoformat()
            }
            for camp in campaigns
        ]
    }

@app.post("/api/campaigns")
async def create_campaign(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await request.json()

    campaign = Campaign(
        user_id=current_user.id,
        name=data.get("name"),
        description=data.get("description"),
        campaign_type=data.get("campaign_type", "broadcast"),
        platform=data.get("platform"),
        target_audience=data.get("target_audience", {}),
        scheduled_at=datetime.fromisoformat(data["scheduled_at"]) if data.get("scheduled_at") else None
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    return {"success": True, "campaign": {
        "id": campaign.id,
        "name": campaign.name,
        "status": campaign.status,
        "platform": campaign.platform.value
    }}

# Analytics
@app.get("/api/analytics/overview")
async def get_analytics_overview(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get analytics data for the specified period
    start_date = datetime.utcnow() - timedelta(days=days)

    analytics = db.query(Analytics).filter(
        Analytics.user_id == current_user.id,
        Analytics.date >= start_date
    ).all()

    total_messages_sent = sum(a.messages_sent for a in analytics)
    total_messages_received = sum(a.messages_received for a in analytics)
    total_subscribers_gained = sum(a.subscribers_gained for a in analytics)

    return {
        "period_days": days,
        "total_messages_sent": total_messages_sent,
        "total_messages_received": total_messages_received,
        "total_subscribers_gained": total_subscribers_gained,
        "engagement_rate": (total_messages_received / total_messages_sent * 100) if total_messages_sent > 0 else 0
    }

# Webhook endpoints for Facebook
@app.get("/webhooks/facebook")
def verify_facebook_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == FACEBOOK_VERIFY_TOKEN:
        print("Facebook webhook verified!")
        return int(hub_challenge)
    return JSONResponse({"error": "Verification failed"}, status_code=403)

@app.post("/webhooks/facebook")
async def receive_facebook_webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    body = await request.json()
    print("Received Facebook webhook:", json.dumps(body, indent=2))

    # Log webhook
    webhook_log = WebhookLog(
        platform=Platform.FACEBOOK,
        event_type="webhook_received",
        payload=body,
        status="received"
    )
    db.add(webhook_log)
    db.commit()

    try:
        entry = body.get("entry", [])[0]
        messaging_events = entry.get("messaging", [])

        for event in messaging_events:
            sender_id = event.get("sender", {}).get("id")
            recipient_id = event.get("recipient", {}).get("id")
            message = event.get("message", {}) or {}

            text = message.get("text", "")
            is_echo = message.get("is_echo", False)

            # Skip echoes
            if is_echo:
                continue

            # Find the page and user
            page = db.query(FacebookPage).filter(FacebookPage.page_id == recipient_id).first()
            if not page:
                continue

            # Get or create subscriber
            subscriber = db.query(Subscriber).filter(
                Subscriber.subscriber_id == sender_id,
                Subscriber.page_id == page.id
            ).first()

            if not subscriber:
                # Create new subscriber
                subscriber = Subscriber(
                    user_id=page.user_id,
                    page_id=page.id,
                    subscriber_id=sender_id,
                    platform=Platform.FACEBOOK,
                    first_name="Unknown",  # Would fetch from API
                    last_name="User"
                )
                db.add(subscriber)
                db.commit()
                db.refresh(subscriber)

            # Save incoming message
            if text:
                msg = Message(
                    user_id=page.user_id,
                    page_id=page.id,
                    subscriber_id=subscriber.id,
                    platform=Platform.FACEBOOK,
                    direction="inbound",
                    content=text,
                    message_id=message.get("mid")
                )
                db.add(msg)
                db.commit()

                # Process auto-reply
                background_tasks.add_task(process_auto_reply, subscriber.id, text, Platform.FACEBOOK, db)

        webhook_log.status = "processed"
        db.commit()

    except Exception as e:
        print(f"Error processing Facebook webhook: {e}")
        webhook_log.status = "failed"
        webhook_log.error_message = str(e)
        db.commit()

    return {"status": "received"}

# Webhook endpoints for Instagram
@app.get("/webhooks/instagram")
def verify_instagram_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == INSTAGRAM_VERIFY_TOKEN:
        print("Instagram webhook verified!")
        return int(hub_challenge)
    return JSONResponse({"error": "Verification failed"}, status_code=403)

@app.post("/webhooks/instagram")
async def receive_instagram_webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    body = await request.json()
    print("Received Instagram webhook:", json.dumps(body, indent=2))

    # Log webhook
    webhook_log = WebhookLog(
        platform=Platform.INSTAGRAM,
        event_type="webhook_received",
        payload=body,
        status="received"
    )
    db.add(webhook_log)
    db.commit()

    try:
        entry = body.get("entry", [])[0]
        messaging_events = entry.get("messaging", [])

        for event in messaging_events:
            sender_id = event.get("sender", {}).get("id")
            recipient_id = event.get("recipient", {}).get("id")
            message = event.get("message", {}) or {}

            text = message.get("text", "")
            is_echo = message.get("is_echo", False)

            # Skip echoes
            if is_echo:
                continue

            # Find the page (Instagram business account)
            page = db.query(FacebookPage).filter(FacebookPage.page_id == recipient_id).first()
            if not page:
                continue

            # Get or create subscriber
            subscriber = db.query(Subscriber).filter(
                Subscriber.subscriber_id == sender_id,
                Subscriber.page_id == page.id
            ).first()

            if not subscriber:
                # Create new subscriber
                subscriber = Subscriber(
                    user_id=page.user_id,
                    page_id=page.id,
                    subscriber_id=sender_id,
                    platform=Platform.INSTAGRAM,
                    first_name="Unknown",
                    last_name="User"
                )
                db.add(subscriber)
                db.commit()
                db.refresh(subscriber)

            # Save incoming message
            if text:
                msg = Message(
                    user_id=page.user_id,
                    page_id=page.id,
                    subscriber_id=subscriber.id,
                    platform=Platform.INSTAGRAM,
                    direction="inbound",
                    content=text,
                    message_id=message.get("mid")
                )
                db.add(msg)
                db.commit()

                # Process auto-reply
                background_tasks.add_task(process_auto_reply, subscriber.id, text, Platform.INSTAGRAM, db)

        webhook_log.status = "processed"
        db.commit()

    except Exception as e:
        print(f"Error processing Instagram webhook: {e}")
        webhook_log.status = "failed"
        webhook_log.error_message = str(e)
        db.commit()

    return {"status": "received"}

# Helper functions
async def process_auto_reply(subscriber_id: int, message_text: str, platform: Platform, db: Session):
    subscriber = db.query(Subscriber).filter(Subscriber.id == subscriber_id).first()
    if not subscriber:
        return

    # Find active bot flows for this platform
    flows = db.query(BotFlow).filter(
        BotFlow.user_id == subscriber.user_id,
        BotFlow.platform == platform,
        BotFlow.is_active == True
    ).all()

    for flow in flows:
        if flow.flow_type.value == "keyword":
            # Check keywords
            for step in flow.steps:
                if step.step_type == "keyword_trigger":
                    keywords = step.config.get("keywords", [])
                    for keyword in keywords:
                        if keyword.lower() in message_text.lower():
                            # Send reply
                            reply_text = step.config.get("reply", "")
                            if reply_text:
                                if platform == Platform.FACEBOOK:
                                    await send_facebook_message(subscriber.subscriber_id, reply_text)
                                elif platform == Platform.INSTAGRAM:
                                    await send_instagram_message(subscriber.subscriber_id, reply_text)

                                # Save reply message
                                reply_msg = Message(
                                    user_id=subscriber.user_id,
                                    page_id=subscriber.page_id,
                                    subscriber_id=subscriber.id,
                                    platform=platform,
                                    direction="outbound",
                                    content=reply_text
                                )
                                db.add(reply_msg)
                                db.commit()
                            break

async def send_facebook_message(recipient_id: str, message_text: str):
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

async def send_instagram_message(recipient_id: str, message_text: str):
    url = "https://graph.facebook.com/v19.0/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
    }
    params = {"access_token": INSTAGRAM_ACCESS_TOKEN}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, params=params)
        print(f"Instagram reply sent: {message_text}")
        print(f"Response: {response.json()}")

# Serve the dashboard
@app.get("/")
async def serve_dashboard():
    return FileResponse("dashboard_v2.html")

# Create tables on startup
@app.on_event("startup")
async def startup_event():
    create_tables()
    print("Database tables created/verified")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


