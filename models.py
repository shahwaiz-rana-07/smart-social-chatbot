from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Float, JSON, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()

class UserRole(enum.Enum):
    ADMIN = "admin"
    USER = "user"
    PREMIUM = "premium"

class SubscriptionPlan(enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class MessageType(enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    FILE = "file"

class Platform(enum.Enum):
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"

class BotFlowType(enum.Enum):
    KEYWORD = "keyword"
    SEQUENCE = "sequence"
    AI = "ai"
    WEBHOOK = "webhook"

# User Management
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(Enum(UserRole), default=UserRole.USER)
    subscription_plan = Column(Enum(SubscriptionPlan), default=SubscriptionPlan.FREE)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    pages = relationship("FacebookPage", back_populates="user")
    campaigns = relationship("Campaign", back_populates="user")
    subscribers = relationship("Subscriber", back_populates="user")
    messages = relationship("Message", back_populates="user")
    bot_flows = relationship("BotFlow", back_populates="user")

class FacebookPage(Base):
    __tablename__ = "facebook_pages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    page_id = Column(String, nullable=False)
    page_name = Column(String, nullable=False)
    page_access_token = Column(String, nullable=False)
    page_picture = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="pages")
    subscribers = relationship("Subscriber", back_populates="page")
    messages = relationship("Message", back_populates="page")
    posts = relationship("Post", back_populates="page")

# Subscriber Management
class Subscriber(Base):
    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    page_id = Column(Integer, ForeignKey("facebook_pages.id"))
    subscriber_id = Column(String, nullable=False)  # Facebook/Instagram user ID
    platform = Column(Enum(Platform), nullable=False)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    profile_pic = Column(String)
    locale = Column(String)
    timezone = Column(Float)
    gender = Column(String)
    is_active = Column(Boolean, default=True)
    subscribed_at = Column(DateTime, default=datetime.utcnow)
    last_message_at = Column(DateTime)
    tags = Column(JSON, default=list)  # List of tags
    custom_fields = Column(JSON, default=dict)  # Custom field data

    # Relationships
    user = relationship("User", back_populates="subscribers")
    page = relationship("FacebookPage", back_populates="subscribers")
    messages = relationship("Message", back_populates="subscriber")

# Message Management
class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    page_id = Column(Integer, ForeignKey("facebook_pages.id"))
    subscriber_id = Column(Integer, ForeignKey("subscribers.id"))
    message_id = Column(String, unique=True)  # Platform message ID
    platform = Column(Enum(Platform), nullable=False)
    message_type = Column(Enum(MessageType), default=MessageType.TEXT)
    direction = Column(String, nullable=False)  # 'inbound' or 'outbound'
    content = Column(Text)
    attachments = Column(JSON, default=list)  # Media attachments
    is_read = Column(Boolean, default=False)
    is_replied = Column(Boolean, default=False)
    reply_to_message_id = Column(Integer, ForeignKey("messages.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="messages")
    page = relationship("FacebookPage", back_populates="messages")
    subscriber = relationship("Subscriber", back_populates="messages")
    reply_to = relationship("Message", remote_side=[id])

# Bot Flow Management
class BotFlow(Base):
    __tablename__ = "bot_flows"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    description = Column(Text)
    flow_type = Column(Enum(BotFlowType), default=BotFlowType.KEYWORD)
    platform = Column(Enum(Platform), nullable=False)
    is_active = Column(Boolean, default=True)
    config = Column(JSON, default=dict)  # Flow configuration
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="bot_flows")
    steps = relationship("BotFlowStep", back_populates="flow", cascade="all, delete-orphan")

class BotFlowStep(Base):
    __tablename__ = "bot_flow_steps"

    id = Column(Integer, primary_key=True, index=True)
    flow_id = Column(Integer, ForeignKey("bot_flows.id"))
    step_order = Column(Integer, nullable=False)
    step_type = Column(String, nullable=False)  # 'message', 'delay', 'condition', etc.
    config = Column(JSON, default=dict)  # Step configuration
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    flow = relationship("BotFlow", back_populates="steps")

# Campaign Management
class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    description = Column(Text)
    campaign_type = Column(String, nullable=False)  # 'broadcast', 'sequence', 'auto-reply'
    platform = Column(Enum(Platform), nullable=False)
    status = Column(String, default='draft')  # 'draft', 'scheduled', 'running', 'completed', 'paused'
    target_audience = Column(JSON, default=dict)  # Targeting criteria
    scheduled_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="campaigns")
    messages = relationship("CampaignMessage", back_populates="campaign", cascade="all, delete-orphan")
    analytics = relationship("CampaignAnalytics", back_populates="campaign", cascade="all, delete-orphan")

class CampaignMessage(Base):
    __tablename__ = "campaign_messages"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    message_order = Column(Integer, nullable=False)
    message_type = Column(Enum(MessageType), default=MessageType.TEXT)
    content = Column(Text)
    attachments = Column(JSON, default=list)
    delay_minutes = Column(Integer, default=0)  # Delay before sending this message
    sent_count = Column(Integer, default=0)
    delivered_count = Column(Integer, default=0)
    read_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    campaign = relationship("Campaign", back_populates="messages")

class CampaignAnalytics(Base):
    __tablename__ = "campaign_analytics"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    date = Column(DateTime, default=datetime.utcnow)
    sent_count = Column(Integer, default=0)
    delivered_count = Column(Integer, default=0)
    read_count = Column(Integer, default=0)
    clicked_count = Column(Integer, default=0)
    unsubscribed_count = Column(Integer, default=0)

    # Relationships
    campaign = relationship("Campaign", back_populates="analytics")

# Post Management
class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    page_id = Column(Integer, ForeignKey("facebook_pages.id"))
    platform = Column(Enum(Platform), nullable=False)
    post_type = Column(String, nullable=False)  # 'text', 'image', 'video', 'carousel'
    content = Column(Text)
    media_urls = Column(JSON, default=list)
    scheduled_at = Column(DateTime)
    posted_at = Column(DateTime)
    status = Column(String, default='draft')  # 'draft', 'scheduled', 'posted', 'failed'
    post_id = Column(String)  # Platform post ID
    engagement = Column(JSON, default=dict)  # Likes, comments, shares
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="posts")
    page = relationship("FacebookPage", back_populates="posts")

# Subscription/Payment Management
class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    plan = Column(Enum(SubscriptionPlan), nullable=False)
    stripe_subscription_id = Column(String)
    status = Column(String, nullable=False)  # 'active', 'canceled', 'past_due', 'unpaid'
    current_period_start = Column(DateTime)
    current_period_end = Column(DateTime)
    cancel_at_period_end = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="subscription")

# Analytics
class Analytics(Base):
    __tablename__ = "analytics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(DateTime, default=datetime.utcnow)
    platform = Column(Enum(Platform), nullable=False)
    messages_sent = Column(Integer, default=0)
    messages_received = Column(Integer, default=0)
    subscribers_gained = Column(Integer, default=0)
    subscribers_lost = Column(Integer, default=0)
    campaigns_run = Column(Integer, default=0)

    # Relationships
    user = relationship("User", back_populates="analytics")

# Webhook Logs
class WebhookLog(Base):
    __tablename__ = "webhook_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    platform = Column(Enum(Platform), nullable=False)
    event_type = Column(String, nullable=False)
    payload = Column(JSON)
    status = Column(String, default='received')  # 'received', 'processed', 'failed'
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="webhook_logs")

# API Keys/Integrations
class Integration(Base):
    __tablename__ = "integrations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    integration_type = Column(String, nullable=False)  # 'webhook', 'api', 'email', 'sms'
    config = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="integrations")

# Add missing relationships to User model
User.subscription = relationship("Subscription", back_populates="user", uselist=False)
User.posts = relationship("Post", back_populates="user")
User.analytics = relationship("Analytics", back_populates="user")
User.webhook_logs = relationship("WebhookLog", back_populates="user")
User.integrations = relationship("Integration", back_populates="user")


