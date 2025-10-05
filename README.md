# Discord Message Scheduler

A unified Discord bot with a web-based calendar interface for scheduling messages. Built with Python, Flask, Celery, and Redis - all in a single script!

## Features

- 🗓️ **Calendar Interface**: Visual calendar to view and manage scheduled messages
- ⏰ **Message Scheduling**: Schedule Discord messages for specific times
- 🤖 **Discord Bot**: Automated message sending to Discord channels
- 📱 **Web UI**: Easy-to-use web interface for managing messages
- 🔄 **Background Processing**: Uses Celery for reliable message scheduling
- 💾 **Database Storage**: SQLite database for persistent message storage
- 🚀 **Single Script**: Everything runs from one Python file!

## Prerequisites

- Python 3.8 or higher
- Redis server
- Discord bot token
- Discord server with appropriate permissions

## Installation

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Redis**:
   - **Linux**: `sudo apt-get install redis-server`
   - **macOS**: `brew install redis`

3. **Create a Discord Bot**:
   - Go to https://discord.com/developers/applications
   - Create a new application
   - Go to "Bot" section and create a bot
   - Copy the bot token
   - Enable "Message Content Intent" in bot settings

4. **Configure the bot**:
   - Create a `.env` file in the project root:
   ```env
   # ONLY CHANGE THIS VALUE (REQUIRED):
   DISCORD_TOKEN=your_discord_bot_token_here
   
   # OPTIONAL (can leave as default):
   DISCORD_GUILD_ID=0
   
   # THESE WORK AS-IS (DON'T CHANGE):
   REDIS_URL=redis://localhost:6379/0
   DATABASE_URL=sqlite:///scheduled_messages.db
   SECRET_KEY=dev-secret-key-change-in-production
   WEB_HOST=0.0.0.0
   WEB_PORT=5000
   ```

5. **Invite the bot to your Discord server**:
   - In Discord Developer Portal, go to OAuth2 > URL Generator
   - Select "bot" scope and "Send Messages" permission
   - Use the generated URL to invite the bot

## Usage

### Quick Start

1. **Start Redis server**:
   ```bash
   redis-server
   ```

2. **Run the unified script**:
   ```bash
   python discord_scheduler.py
   ```

3. **Access the web interface**:
   - Open http://localhost:5000 in your browser
   - Use the calendar to schedule messages

## Web Interface

The web interface provides:

- **Calendar View**: Visual representation of scheduled messages
- **Message Form**: Easy scheduling of new messages
- **Message Management**: View, edit, and delete scheduled messages
- **Channel Selection**: Choose target Discord channels
- **Time Selection**: Pick exact date and time for messages

## Discord Bot Commands

- `!ping` - Check bot latency
- `!schedule #channel "2024-01-01 12:00" Your message here` - Schedule a message

## Raspberry Pi Deployment

For Raspberry Pi deployment:

1. **Install dependencies**:
   ```bash
   sudo apt-get update
   sudo apt-get install python3-pip redis-server
   pip3 install -r requirements.txt
   ```

2. **Configure for local network access**:
   - Set `WEB_HOST=0.0.0.0` in `.env`
   - Access from other devices: `http://[PI_IP]:5000`

3. **Run as service** (optional):
   - Create systemd service files for auto-start
   - Use `screen` or `tmux` for persistent sessions

## File Structure

```
magikarpbot/
├── discord_scheduler.py  # Unified script (everything in one file!)
├── requirements.txt      # Python dependencies
├── .env                 # Configuration file (create this)
└── README.md            # This file
```

## Troubleshooting

### Common Issues

1. **Redis connection error**:
   - Ensure Redis is running: `redis-cli ping`
   - Check Redis URL in `.env` file

2. **Discord bot not responding**:
   - Verify bot token in `.env`
   - Check bot permissions in Discord server
   - Ensure bot is online in Discord

3. **Web interface not loading**:
   - Check if Flask app is running on correct port
   - Verify no firewall blocking port 5000

4. **Messages not sending**:
   - Check Celery worker is running
   - Verify scheduled time is in the future
   - Check Discord bot permissions

### Logs

- Check terminal output for error messages
- Celery logs will show task execution status
- Discord bot logs will show connection status

## Development

To contribute or modify:

1. **Database migrations**:
   ```bash
   flask db init
   flask db migrate -m "Description"
   flask db upgrade
   ```

2. **Testing**:
   - Test individual components separately
   - Use Discord test server for bot testing
   - Verify message scheduling with short delays

## License

This project is open source. Feel free to modify and distribute.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Verify all prerequisites are installed
3. Check component logs for error messages
