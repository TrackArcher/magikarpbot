#!/usr/bin/env python3
"""
Unified Discord Message Scheduler
A single Python script that runs Discord bot, Celery worker, and Flask web app
"""

import os
import sys
import time
import threading
import asyncio
import signal
from datetime import datetime, timedelta
from multiprocessing import Process
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from celery import Celery
from celery.schedules import crontab
import discord
from discord.ext import commands
import pytz
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
class Config:
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    DISCORD_GUILD_ID = int(os.getenv('DISCORD_GUILD_ID', 0))
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///scheduled_messages.db')
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    WEB_HOST = os.getenv('WEB_HOST', '0.0.0.0')
    WEB_PORT = int(os.getenv('WEB_PORT', 5000))

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Database Models
class ScheduledMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.BigInteger, nullable=False)
    message_content = db.Column(db.Text, nullable=False)
    scheduled_time = db.Column(db.DateTime, nullable=False)
    is_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    celery_task_id = db.Column(db.String(255), nullable=True)
    
    def __repr__(self):
        return f'<ScheduledMessage {self.id}: {self.message_content[:50]}...>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'channel_id': self.channel_id,
            'message_content': self.message_content,
            'scheduled_time': self.scheduled_time.isoformat(),
            'is_sent': self.is_sent,
            'created_at': self.created_at.isoformat(),
            'celery_task_id': self.celery_task_id
        }

# Initialize Celery
celery_app = Celery('discord_scheduler')
celery_app.conf.update(
    broker_url=Config.REDIS_URL,
    result_backend=Config.REDIS_URL,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# Global Discord bot instance
discord_bot = None

# Discord Bot Class
class DiscordBot:
    def __init__(self):
        self.bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())
        self.setup_commands()
    
    def setup_commands(self):
        @self.bot.event
        async def on_ready():
            print(f'{self.bot.user} has connected to Discord!')
            print(f'Bot is in {len(self.bot.guilds)} guilds')
            print('Bot is ready to send scheduled messages!')
    
    async def send_message(self, channel_id: int, message_content: str):
        """Send a message to a specific channel"""
        try:
            channel = self.bot.get_channel(channel_id)
            if channel:
                print(f"Sending message to channel {channel.name} (ID: {channel_id})")
                print(f"Message content: {message_content}")
                
                # Send the message
                sent_message = await channel.send(message_content)
                print(f"Message sent successfully! Message ID: {sent_message.id}")
                return True
            else:
                print(f"Channel with ID {channel_id} not found")
                return False
        except Exception as e:
            print(f"Error sending message to channel {channel_id}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run(self):
        self.bot.run(Config.DISCORD_TOKEN)

# Celery Tasks
@celery_app.task
def schedule_discord_message(channel_id, message_content, scheduled_time):
    """Schedule a Discord message to be sent at a specific time"""
    try:
        # Parse the scheduled time
        scheduled_dt = datetime.fromisoformat(scheduled_time)
        
        # Create database record
        with app.app_context():
            scheduled_msg = ScheduledMessage(
                channel_id=channel_id,
                message_content=message_content,
                scheduled_time=scheduled_dt,
                celery_task_id=schedule_discord_message.request.id
            )
            
            db.session.add(scheduled_msg)
            db.session.commit()
        
        # Calculate delay in seconds
        now = datetime.utcnow()
        delay_seconds = (scheduled_dt - now).total_seconds()
        
        if delay_seconds > 0:
            # Schedule the message to be sent
            send_discord_message.apply_async(
                args=[channel_id, message_content],
                countdown=delay_seconds
            )
            return f"Message scheduled for {scheduled_dt}"
        else:
            return "Scheduled time is in the past"
            
    except Exception as e:
        return f"Error scheduling message: {str(e)}"

@celery_app.task
def send_discord_message(channel_id, message_content):
    """Send a Discord message to a specific channel"""
    try:
        print(f"=== SENDING DISCORD MESSAGE ===")
        print(f"Channel ID: {channel_id}")
        print(f"Message: {message_content}")
        print(f"Timestamp: {datetime.now()}")
        
        # Use requests instead of aiohttp for simpler HTTP calls
        import requests
        import json
        
        # Discord API endpoint for sending messages
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        
        headers = {
            'Authorization': f'Bot {Config.DISCORD_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'content': message_content
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Message sent successfully! Message ID: {result.get('id')}")
                return f"✅ Message sent to channel {channel_id} successfully"
            else:
                print(f"❌ Discord API error {response.status_code}: {response.text}")
                return f"❌ Discord API error {response.status_code}: {response.text}"
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request error: {e}")
            return f"❌ Request error: {e}"
        except Exception as e:
            print(f"❌ Error sending message via API: {e}")
            import traceback
            traceback.print_exc()
            return f"❌ Error sending message: {e}"
        
    except Exception as e:
        print(f"❌ Critical error in send_discord_message: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"❌ Critical error: {str(e)}"

@celery_app.task
def check_overdue_messages():
    """Check for messages that should have been sent but weren't"""
    try:
        print(f"=== CHECKING OVERDUE MESSAGES ===")
        print(f"Current time: {datetime.utcnow()}")
        
        with app.app_context():
            now = datetime.utcnow()
            
            # Find overdue messages that haven't been sent
            overdue_messages = ScheduledMessage.query.filter(
                ScheduledMessage.scheduled_time <= now,
                ScheduledMessage.is_sent == False
            ).all()
            
            print(f"Found {len(overdue_messages)} overdue messages")
            
            # Find very old messages (more than 1 hour past) to delete
            old_cutoff = now - timedelta(hours=1)
            old_messages = ScheduledMessage.query.filter(
                ScheduledMessage.scheduled_time <= old_cutoff,
                ScheduledMessage.is_sent == False
            ).all()
            
            print(f"Found {len(old_messages)} old messages to delete")
            
            # Send overdue messages directly (not via delay)
            for msg in overdue_messages:
                print(f"Processing overdue message {msg.id}: {msg.message_content[:50]}...")
                result = send_discord_message(msg.channel_id, msg.message_content)
                print(f"Send result: {result}")
                msg.is_sent = True
                db.session.commit()
                print(f"✅ Marked message {msg.id} as sent")
            
            # Delete very old unsent messages
            for msg in old_messages:
                db.session.delete(msg)
                print(f"🗑️ Deleted old message {msg.id}")
            
            db.session.commit()
            
            return f"Processed {len(overdue_messages)} overdue messages, deleted {len(old_messages)} old messages"
        
    except Exception as e:
        print(f"❌ Error checking overdue messages: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Error checking overdue messages: {str(e)}"

@celery_app.task
def cleanup_stuck_tasks():
    """Clean up any stuck or unacknowledged tasks"""
    try:
        print("Cleaning up stuck tasks...")
        
        # Revoke all active tasks
        try:
            celery_app.control.revoke(terminate=True)
            print("Revoked all active tasks")
        except Exception as e:
            print(f"Could not revoke tasks: {e}")
        
        # Purge the queue
        try:
            celery_app.control.purge()
            print("Purged Celery queue")
        except Exception as e:
            print(f"Could not purge queue: {e}")
        
        return "Cleanup completed"
        
    except Exception as e:
        return f"Error during cleanup: {str(e)}"

# Schedule the periodic task to run every minute
celery_app.conf.beat_schedule = {
    'check-overdue-messages': {
        'task': 'discord_scheduler.check_overdue_messages',
        'schedule': 60.0,  # Run every 60 seconds
    },
}

# Flask Routes
@app.route('/')
def index():
    """Main calendar interface"""
    return render_template('index.html')

@app.route('/debug')
def debug_page():
    """Debug page to test channel loading"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Debug Channels</title>
    </head>
    <body>
        <h1>Channel Debug Page</h1>
        <button onclick="testAPI()">Test API</button>
        <button onclick="loadChannels()">Load Channels</button>
        <div id="output"></div>
        <select id="channelSelect">
            <option value="">Select a channel...</option>
        </select>
        
        <script>
            function testAPI() {
                fetch('/api/test')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('output').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                    });
            }
            
            function loadChannels() {
                console.log('Loading channels...');
                fetch('/api/channels')
                    .then(response => {
                        console.log('Response status:', response.status);
                        return response.json();
                    })
                    .then(channels => {
                        console.log('Received channels:', channels);
                        const select = document.getElementById('channelSelect');
                        select.innerHTML = '<option value="">Select a channel...</option>';
                        
                        channels.forEach(channel => {
                            const option = document.createElement('option');
                            option.value = channel.id;
                            option.textContent = channel.guild_name + ' - #' + channel.name;
                            select.appendChild(option);
                        });
                        
                        document.getElementById('output').innerHTML = '<pre>Loaded ' + channels.length + ' channels</pre>';
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        document.getElementById('output').innerHTML = '<pre>Error: ' + error + '</pre>';
                    });
            }
        </script>
    </body>
    </html>
    '''

@app.route('/api/scheduled-messages')
def get_scheduled_messages():
    """Get all scheduled messages"""
    messages = ScheduledMessage.query.order_by(ScheduledMessage.scheduled_time).all()
    return jsonify([msg.to_dict() for msg in messages])

@app.route('/api/schedule-message', methods=['POST'])
def schedule_message():
    """Schedule a new message"""
    try:
        print("=== SCHEDULE MESSAGE API CALLED ===")
        data = request.get_json()
        print("Received data:", data)
        
        # Parse the scheduled time
        scheduled_time = datetime.fromisoformat(data['scheduled_time'])
        print("Parsed scheduled time:", scheduled_time)
        
        # Create new scheduled message
        scheduled_msg = ScheduledMessage(
            channel_id=data['channel_id'],
            message_content=data['message_content'],
            scheduled_time=scheduled_time
        )
        print("Created scheduled message object")
        
        db.session.add(scheduled_msg)
        db.session.commit()
        print("Added to database, ID:", scheduled_msg.id)
        
        # Schedule the message with Celery
        task = schedule_discord_message.delay(
            channel_id=data['channel_id'],
            message_content=data['message_content'],
            scheduled_time=scheduled_time.isoformat()
        )
        print("Celery task created:", task.id)
        
        # Update the record with the Celery task ID
        scheduled_msg.celery_task_id = task.id
        db.session.commit()
        print("Updated with Celery task ID")
        
        return jsonify({
            'success': True,
            'message': 'Message scheduled successfully',
            'task_id': task.id
        })
        
    except Exception as e:
        print("Error scheduling message:", str(e))
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@app.route('/api/delete-message/<int:message_id>', methods=['DELETE'])
def delete_message(message_id):
    """Delete a scheduled message"""
    try:
        print(f"=== DELETE MESSAGE API CALLED for ID {message_id} ===")
        message = ScheduledMessage.query.get_or_404(message_id)
        print(f"Found message: {message.message_content}")
        
        # Cancel the Celery task if it exists
        if message.celery_task_id:
            try:
                # Revoke the task
                celery_app.control.revoke(message.celery_task_id, terminate=True)
                print(f"Revoked Celery task: {message.celery_task_id}")
                
                # Also try to purge the task from the queue
                celery_app.control.purge()
                print("Purged Celery queue")
            except Exception as e:
                print(f"Error revoking task: {e}")
        
        db.session.delete(message)
        db.session.commit()
        print(f"Deleted message {message_id}")
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error deleting message: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/clear-all-messages', methods=['DELETE'])
def clear_all_messages():
    """Delete all scheduled messages"""
    try:
        print(f"=== CLEAR ALL MESSAGES API CALLED ===")
        
        # Get all messages
        messages = ScheduledMessage.query.all()
        print(f"Found {len(messages)} messages to delete")
        
        # Cancel all Celery tasks
        task_ids = [msg.celery_task_id for msg in messages if msg.celery_task_id]
        if task_ids:
            try:
                for task_id in task_ids:
                    celery_app.control.revoke(task_id, terminate=True)
                    print(f"Revoked Celery task: {task_id}")
                
                # Purge the entire queue
                celery_app.control.purge()
                print("Purged entire Celery queue")
            except Exception as e:
                print(f"Error revoking tasks: {e}")
        
        # Delete all messages
        for message in messages:
            db.session.delete(message)
        
        db.session.commit()
        print(f"Deleted all {len(messages)} messages")
        
        return jsonify({
            'success': True,
            'deleted_count': len(messages)
        })
        
    except Exception as e:
        print(f"Error clearing all messages: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/test')
def test_api():
    """Test endpoint to check if API is working"""
    return jsonify({'status': 'API working', 'bot_connected': discord_bot is not None})

@app.route('/api/db-check')
def db_check():
    """Check database and show all scheduled messages"""
    try:
        messages = ScheduledMessage.query.all()
        return jsonify({
            'total_messages': len(messages),
            'messages': [msg.to_dict() for msg in messages]
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/test-send/<int:channel_id>')
def test_send_message(channel_id):
    """Test sending a message to a specific channel"""
    try:
        print(f"=== TEST SEND MESSAGE API ===")
        print(f"Channel ID: {channel_id}")
        
        # Trigger a test message send
        task = send_discord_message.delay(
            channel_id=channel_id,
            message_content="🧪 Test message from Discord Scheduler Bot!"
        )
        
        return jsonify({
            'success': True,
            'message': 'Test message queued',
            'task_id': task.id
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/test-send-direct/<int:channel_id>')
def test_send_message_direct(channel_id):
    """Test sending a message directly (synchronously) to a specific channel"""
    try:
        print(f"=== TEST SEND MESSAGE DIRECT API ===")
        print(f"Channel ID: {channel_id}")
        
        # Send message directly without Celery
        result = send_discord_message(channel_id, "🧪 Direct test message from Discord Scheduler Bot!")
        
        return jsonify({
            'success': True,
            'message': 'Direct test message sent',
            'result': result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/test-send-simple/<int:channel_id>')
def test_send_message_simple(channel_id):
    """Test sending a message using simple requests approach"""
    try:
        print(f"=== TEST SEND MESSAGE SIMPLE API ===")
        print(f"Channel ID: {channel_id}")
        
        import requests
        
        # Discord API endpoint for sending messages
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        
        headers = {
            'Authorization': f'Bot {Config.DISCORD_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'content': "🧪 Simple test message from Discord Scheduler Bot!"
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            return jsonify({
                'success': True,
                'message': 'Simple test message sent successfully',
                'message_id': result.get('id'),
                'status_code': response.status_code
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Discord API error {response.status_code}: {response.text}',
                'status_code': response.status_code
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/channels')
def get_channels():
    """Get available Discord channels from the bot"""
    try:
        global discord_bot
        print(f"=== CHANNEL API CALLED ===")
        print(f"Discord bot status: {discord_bot is not None}")
        
        if discord_bot and discord_bot.bot:
            print(f"Bot guilds: {len(discord_bot.bot.guilds)}")
            channels = []
            
            for guild in discord_bot.bot.guilds:
                print(f"Guild: {guild.name}, Channels: {len(guild.text_channels)}")
                for channel in guild.text_channels:
                    try:
                        # Check if bot can send messages to this channel
                        permissions = channel.permissions_for(guild.me)
                        can_send = permissions.send_messages
                        print(f"Channel #{channel.name}: can_send={can_send}")
                        
                        if can_send:
                            channels.append({
                                'id': channel.id,
                                'name': channel.name,
                                'guild_name': guild.name
                            })
                            print(f"Added channel: {guild.name} - #{channel.name}")
                    except Exception as e:
                        print(f"Error checking permissions for channel {channel.name}: {e}")
            
            print(f"Total channels found: {len(channels)}")
            return jsonify(channels)
        else:
            print("Discord bot not available - returning empty list")
            return jsonify([])
    except Exception as e:
        print(f"Error fetching channels: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([])

# HTML Template
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Discord Message Scheduler</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/fullcalendar/6.1.8/main.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        .fc-event { cursor: pointer; }
        .message-form { background: #f8f9fa; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
        .calendar-container { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                <h1 class="text-center my-4">
                    <i class="fab fa-discord"></i> Discord Message Scheduler
                </h1>
            </div>
        </div>
        
        <div class="row">
            <!-- Message Form -->
            <div class="col-md-4">
                <div class="message-form">
                    <h4><i class="fas fa-plus"></i> Schedule New Message</h4>
                    <form id="messageForm">
                        <div class="mb-3">
                            <label for="channelSelect" class="form-label">Channel</label>
                            <div class="input-group">
                                <select class="form-select" id="channelSelect" required>
                                    <option value="">Select a channel...</option>
                                </select>
                                <button class="btn btn-outline-secondary" type="button" id="reloadChannelsBtn">
                                    <i class="fas fa-sync-alt"></i>
                                </button>
                            </div>
                            <div class="mt-2">
                                <button class="btn btn-sm btn-warning" type="button" onclick="loadChannels()">
                                    Force Load Channels
                                </button>
                            </div>
                        </div>
                        
                        <div class="mb-3">
                            <label for="messageContent" class="form-label">Message Content</label>
                            <textarea class="form-control" id="messageContent" rows="3" required 
                                placeholder="Enter your message here..."></textarea>
                        </div>
                        
                        <div class="mb-3">
                            <label for="scheduledDate" class="form-label">Date</label>
                            <input type="date" class="form-control" id="scheduledDate" required>
                        </div>
                        
                        <div class="mb-3">
                            <label for="scheduledTime" class="form-label">Time</label>
                            <input type="time" class="form-control" id="scheduledTime" required>
                        </div>
                        
                        <button type="button" class="btn btn-primary w-100" onclick="scheduleMessage()">
                            <i class="fas fa-calendar-plus"></i> Schedule Message
                        </button>
                    </form>
                </div>
                
                <!-- Scheduled Messages List -->
                <div class="mt-4">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <h5><i class="fas fa-list"></i> Scheduled Messages</h5>
                        <button class="btn btn-sm btn-danger" id="clearAllBtn" onclick="clearAllMessages()">
                            <i class="fas fa-trash"></i> Clear All
                        </button>
                    </div>
                    <div id="scheduledMessages" class="list-group">
                        <!-- Messages will be loaded here -->
                    </div>
                </div>
            </div>
            
            <!-- Calendar -->
            <div class="col-md-8">
                <div class="calendar-container">
                    <div id="calendar"></div>
                </div>
            </div>
        </div>
    </div>

    <!-- Message Details Modal -->
    <div class="modal fade" id="messageModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Message Details</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <p><strong>Channel:</strong> <span id="modalChannel"></span></p>
                    <p><strong>Message:</strong> <span id="modalMessage"></span></p>
                    <p><strong>Scheduled Time:</strong> <span id="modalTime"></span></p>
                    <p><strong>Status:</strong> <span id="modalStatus"></span></p>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-danger" id="deleteMessageBtn">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/fullcalendar/6.1.8/main.min.js"></script>
    <script>
        let calendar;
        let currentMessageId = null;
        
        // Initialize the application
        document.addEventListener('DOMContentLoaded', function() {
            console.log('DOM loaded, initializing...');
            initializeCalendar();
            loadScheduledMessages();
            setupEventListeners();
            
            // Load channels automatically - try immediately and then with delays
            console.log('Auto-loading channels (immediate)...');
            loadChannels();
            
            setTimeout(function() {
                console.log('Auto-loading channels (attempt 1)...');
                loadChannels();
            }, 2000);
            
            setTimeout(function() {
                console.log('Auto-loading channels (attempt 2)...');
                loadChannels();
            }, 5000);
        });
        
        function initializeCalendar() {
            const calendarEl = document.getElementById('calendar');
            calendar = new FullCalendar.Calendar(calendarEl, {
                initialView: 'dayGridMonth',
                headerToolbar: {
                    left: 'prev,next today',
                    center: 'title',
                    right: 'dayGridMonth,timeGridWeek,timeGridDay'
                },
                events: function(info, successCallback, failureCallback) {
                    fetch('/api/scheduled-messages')
                        .then(response => response.json())
                        .then(data => {
                            const events = data.map(msg => ({
                                id: msg.id,
                                title: msg.message_content.substring(0, 50) + (msg.message_content.length > 50 ? '...' : ''),
                                start: msg.scheduled_time,
                                backgroundColor: msg.is_sent ? '#28a745' : '#007bff',
                                borderColor: msg.is_sent ? '#28a745' : '#007bff',
                                extendedProps: {
                                    channelId: msg.channel_id,
                                    messageContent: msg.message_content,
                                    isSent: msg.is_sent
                                }
                            }));
                            successCallback(events);
                        })
                        .catch(failureCallback);
                },
                eventClick: function(info) {
                    showMessageDetails(info.event);
                }
            });
            calendar.render();
        }
        
        function loadChannels() {
            console.log('=== LOADCHANNELS FUNCTION CALLED ===');
            console.log('Loading channels...');
            
            const select = document.getElementById('channelSelect');
            console.log('Channel select element:', select);
            
            if (!select) {
                console.error('Channel select element not found!');
                return;
            }
            
            // Show loading state
            select.innerHTML = '<option value="">Loading channels...</option>';
            
            fetch('/api/channels')
                .then(response => {
                    console.log('Response status:', response.status);
                    if (!response.ok) {
                        throw new Error('Network response was not ok');
                    }
                    return response.json();
                })
                .then(channels => {
                    console.log('Received channels:', channels);
                    console.log('Number of channels:', channels.length);
                    
                    // Clear and reset
                    select.innerHTML = '<option value="">Select a channel...</option>';
                    
                    if (channels.length === 0) {
                        console.log('No channels received, retrying in 2 seconds...');
                        select.innerHTML = '<option value="">No channels available - retrying...</option>';
                        setTimeout(loadChannels, 2000);
                        return;
                    }
                    
                    // Add channels
                    channels.forEach((channel, index) => {
                        const option = document.createElement('option');
                        option.value = channel.id;
                        option.textContent = channel.guild_name + ' - #' + channel.name;
                        select.appendChild(option);
                        console.log(`Added channel ${index + 1}:`, option.textContent);
                    });
                    
                    console.log('Successfully loaded', channels.length, 'channels');
                    console.log('Select element now has', select.options.length, 'options');
                })
                .catch(error => {
                    console.error('Error loading channels:', error);
                    select.innerHTML = '<option value="">Error loading channels - retrying...</option>';
                    setTimeout(loadChannels, 2000);
                });
        }
        
        function loadScheduledMessages() {
            fetch('/api/scheduled-messages')
                .then(response => response.json())
                .then(messages => {
                    const container = document.getElementById('scheduledMessages');
                    container.innerHTML = '';
                    
                    messages.forEach(msg => {
                        const messageEl = document.createElement('div');
                        messageEl.className = 'list-group-item';
                        messageEl.innerHTML = `
                            <div class="d-flex w-100 justify-content-between">
                                <h6 class="mb-1">${msg.message_content.substring(0, 30)}${msg.message_content.length > 30 ? '...' : ''}</h6>
                                <small>${new Date(msg.scheduled_time).toLocaleString()}</small>
                            </div>
                            <p class="mb-1">Channel: ${msg.channel_id}</p>
                            <small>Status: ${msg.is_sent ? 'Sent' : 'Pending'}</small>
                        `;
                        messageEl.addEventListener('click', () => showMessageDetails(msg));
                        container.appendChild(messageEl);
                    });
                });
        }
        
        function setupEventListeners() {
            console.log('Setting up event listeners...');
            
            document.getElementById('deleteMessageBtn').addEventListener('click', function() {
                if (currentMessageId) {
                    deleteMessage(currentMessageId);
                }
            });
            
            document.getElementById('reloadChannelsBtn').addEventListener('click', function() {
                console.log('Manual channel reload requested');
                loadChannels();
            });
            
            const clearAllBtn = document.getElementById('clearAllBtn');
            if (clearAllBtn) {
                clearAllBtn.addEventListener('click', function() {
                    clearAllMessages();
                });
                console.log('Clear All button event listener added');
            } else {
                console.error('Clear All button not found!');
            }
        }
        
        
        function scheduleMessage() {
            console.log('=== SCHEDULING MESSAGE ===');
            
            const channelId = document.getElementById('channelSelect').value;
            const messageContent = document.getElementById('messageContent').value;
            const scheduledDate = document.getElementById('scheduledDate').value;
            const scheduledTime = document.getElementById('scheduledTime').value;
            
            console.log('Channel ID:', channelId);
            console.log('Message:', messageContent);
            console.log('Date:', scheduledDate);
            console.log('Time:', scheduledTime);
            
            // Validate form data
            if (!channelId || !messageContent || !scheduledDate || !scheduledTime) {
                alert('Please fill in all fields!');
                return;
            }
            
            const formData = {
                channel_id: parseInt(channelId),
                message_content: messageContent,
                scheduled_time: scheduledDate + 'T' + scheduledTime
            };
            
            console.log('Form data:', formData);
            console.log('Sending request to /api/schedule-message...');
            
            fetch('/api/schedule-message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(formData)
            })
            .then(response => {
                console.log('Response status:', response.status);
                return response.json();
            })
            .then(data => {
                console.log('Response data:', data);
                if (data.success) {
                    alert('Message scheduled successfully!');
                    document.getElementById('messageForm').reset();
                    if (calendar) {
                        calendar.refetchEvents();
                    }
                    loadScheduledMessages();
                } else {
                    alert('Error: ' + data.error);
                }
            })
            .catch(error => {
                console.error('Error scheduling message:', error);
                alert('Error scheduling message: ' + error);
            });
        }
        
        function showMessageDetails(messageData) {
            currentMessageId = messageData.id || messageData.extendedProps?.id;
            
            document.getElementById('modalChannel').textContent = messageData.channelId || messageData.channel_id;
            document.getElementById('modalMessage').textContent = messageData.messageContent || messageData.message_content;
            document.getElementById('modalTime').textContent = new Date(messageData.start || messageData.scheduled_time).toLocaleString();
            document.getElementById('modalStatus').textContent = messageData.extendedProps?.isSent || messageData.is_sent ? 'Sent' : 'Pending';
            
            const modal = new bootstrap.Modal(document.getElementById('messageModal'));
            modal.show();
        }
        
        function deleteMessage(messageId) {
            if (confirm('Are you sure you want to delete this message?')) {
                fetch(`/api/delete-message/${messageId}`, {
                    method: 'DELETE'
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Message deleted successfully!');
                        calendar.refetchEvents();
                        loadScheduledMessages();
                        bootstrap.Modal.getInstance(document.getElementById('messageModal')).hide();
                    } else {
                        alert('Error deleting message: ' + data.error);
                    }
                })
                .catch(error => {
                    alert('Error deleting message: ' + error);
                });
            }
        }
        
        function clearAllMessages() {
            console.log('clearAllMessages function called');
            
            if (confirm('Are you sure you want to delete ALL scheduled messages? This action cannot be undone!')) {
                console.log('User confirmed - clearing all messages...');
                
                fetch('/api/clear-all-messages', {
                    method: 'DELETE'
                })
                .then(response => {
                    console.log('Clear all response status:', response.status);
                    return response.json();
                })
                .then(data => {
                    console.log('Clear all response data:', data);
                    if (data.success) {
                        alert(`Successfully deleted ${data.deleted_count} messages!`);
                        if (calendar) {
                            calendar.refetchEvents();
                        }
                        loadScheduledMessages();
                    } else {
                        alert('Error clearing messages: ' + data.error);
                    }
                })
                .catch(error => {
                    console.error('Error clearing messages:', error);
                    alert('Error clearing messages: ' + error);
                });
            } else {
                console.log('User cancelled clear all');
            }
        }
    </script>
</body>
</html>'''

# Create templates directory and write HTML
def create_templates():
    os.makedirs('templates', exist_ok=True)
    with open('templates/index.html', 'w') as f:
        f.write(HTML_TEMPLATE)

# Main application class
class DiscordScheduler:
    def __init__(self):
        self.processes = []
        self.running = True
        
    def start_discord_bot(self):
        """Start Discord bot in a separate thread"""
        global discord_bot
        discord_bot = DiscordBot()
        discord_bot.run()
    
    def start_celery_worker(self):
        """Start Celery worker"""
        try:
            # Clean up any stuck tasks first
            try:
                cleanup_stuck_tasks.delay()
                print("Queued cleanup of stuck tasks")
            except Exception as e:
                print(f"Could not queue cleanup: {e}")
            
            # Purge any existing tasks before starting
            try:
                celery_app.control.purge()
                print("Purged existing Celery queue")
            except Exception as e:
                print(f"Could not purge queue: {e}")
            
            celery_app.worker_main(['worker', '--loglevel=info'])
        except Exception as e:
            print(f"Error starting Celery worker: {e}")
    
    def start_celery_beat(self):
        """Start Celery beat scheduler"""
        celery_app.start(['beat', '--loglevel=info'])
    
    def start_flask_app(self):
        """Start Flask web application"""
        with app.app_context():
            db.create_all()
        app.run(host=Config.WEB_HOST, port=Config.WEB_PORT, debug=False)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print("\nShutting down Discord Scheduler...")
        self.running = False
        for process in self.processes:
            if process.is_alive():
                process.terminate()
        sys.exit(0)
    
    def run(self):
        """Run all components"""
        print("Discord Message Scheduler - Starting all components")
        print("=" * 50)
        
        # Check if .env file exists
        if not os.path.exists('.env'):
            print("ERROR: .env file not found!")
            print("Please create a .env file with your configuration.")
            print("Example .env file:")
            print("DISCORD_TOKEN=your_discord_bot_token_here")
            print("DISCORD_GUILD_ID=your_guild_id_here")
            print("REDIS_URL=redis://localhost:6379/0")
            print("DATABASE_URL=sqlite:///scheduled_messages.db")
            print("SECRET_KEY=your_secret_key_here")
            print("WEB_HOST=0.0.0.0")
            print("WEB_PORT=5000")
            sys.exit(1)
        
        # Create templates directory
        create_templates()
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        try:
            # Start Discord bot in a separate thread
            discord_thread = threading.Thread(target=self.start_discord_bot, daemon=True)
            discord_thread.start()
            
            # Start Celery worker
            celery_worker = Process(target=self.start_celery_worker, daemon=True)
            celery_worker.start()
            self.processes.append(celery_worker)
            
            # Start Celery beat
            celery_beat = Process(target=self.start_celery_beat, daemon=True)
            celery_beat.start()
            self.processes.append(celery_beat)
            
            print("All components started!")
            print(f"Web interface: http://{Config.WEB_HOST}:{Config.WEB_PORT}")
            print("Press Ctrl+C to stop all components")
            
            # Start Flask app (this will block)
            self.start_flask_app()
            
        except KeyboardInterrupt:
            self.signal_handler(None, None)

if __name__ == '__main__':
    scheduler = DiscordScheduler()
    scheduler.run()
