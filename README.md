# JiakAI - AI-Powered Food Tracking Bot

🍽️ A Telegram bot that helps you track your meals and nutrition using AI-powered food recognition and analysis.

## ⚠️ Disclaimer

**This entire codebase was built 100% with AI assistance.** The code was generated through AI tools and is provided for experimental and educational purposes. Use at your own risk.

This project is created for my own experimental purposes and is made available for others to use, learn from, and modify.

## Features

- 📸 **Photo Recognition**: Send photos of your food and get automatic nutritional analysis
- 💬 **Text Input**: Describe your meals in text and get nutritional breakdowns
- 📊 **Daily Summaries**: Track your daily calorie and macro intake
- 📈 **History & Trends**: View your meal history and nutrition trends
- 🔒 **Access Control**: Built-in user authorization system
- ☁️ **Firebase Storage**: All data stored securely in Firebase
- 🔄 **Docker Support**: Easy deployment with Docker

## Setup Instructions

### Prerequisites

1. **Telegram Bot Token**
   - Message [@BotFather](https://t.me/botfather) on Telegram
   - Create a new bot with `/newbot`
   - Save the bot token

2. **OpenAI API Key**
   - Sign up at [OpenAI](https://platform.openai.com/)
   - Generate an API key from the dashboard

3. **Nutritionix API Credentials**
   - Sign up at [Nutritionix](https://www.nutritionix.com/business/api)
   - Get your App ID and App Key

4. **Firebase Project**
   - Create a new project at [Firebase Console](https://console.firebase.google.com/)
   - Enable Firestore Database
   - Generate a service account key (JSON format)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd JiakAI
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   ```

3. **Configure your .env file**
   
   Open `.env` and fill in the following required variables:

   ```env
   # Telegram Bot Configuration
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
   
   # Authorized Users (comma-separated Telegram user IDs)
   AUTHORIZED_TELEGRAM_IDS=123456789,987654321
   
   # OpenAI Configuration
   OPENAI_API_KEY=your_openai_api_key_here
   
   # Nutritionix Configuration
   NUTRITIONIX_APP_ID=your_nutritionix_app_id_here
   NUTRITIONIX_APP_KEY=your_nutritionix_app_key_here
   
   # Firebase Configuration
   FIREBASE_TYPE=service_account
   FIREBASE_PROJECT_ID=your_firebase_project_id
   FIREBASE_PRIVATE_KEY_ID=your_firebase_private_key_id
   FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nyour_firebase_private_key_here\n-----END PRIVATE KEY-----"
   FIREBASE_CLIENT_EMAIL=your_firebase_client_email
   FIREBASE_CLIENT_ID=your_firebase_client_id
   FIREBASE_AUTH_URI=https://accounts.google.com/o/oauth2/auth
   FIREBASE_TOKEN_URI=https://oauth2.googleapis.com/token
   FIREBASE_AUTH_PROVIDER_X509_CERT_URL=https://www.googleapis.com/oauth2/v1/certs
   FIREBASE_CLIENT_X509_CERT_URL=your_firebase_client_x509_cert_url
   
   # Logging Configuration
   LOG_LEVEL=INFO
   ```

### Getting Required API Keys

#### Telegram Bot Token
1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow the instructions
3. Copy the bot token provided

#### Your Telegram User ID
1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. It will reply with your user ID
3. Add this ID to `AUTHORIZED_TELEGRAM_IDS`

#### Firebase Configuration
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create a new project or select existing one
3. Go to Project Settings → Service Accounts
4. Click "Generate new private key"
5. Download the JSON file
6. Extract the values from the JSON file to your `.env`:
   - `project_id` → `FIREBASE_PROJECT_ID`
   - `private_key_id` → `FIREBASE_PRIVATE_KEY_ID`
   - `private_key` → `FIREBASE_PRIVATE_KEY`
   - `client_email` → `FIREBASE_CLIENT_EMAIL`
   - `client_id` → `FIREBASE_CLIENT_ID`
   - `client_x509_cert_url` → `FIREBASE_CLIENT_X509_CERT_URL`

### Running the Bot

#### Option 1: Docker (Recommended)
```bash
docker compose up --build
```

#### Option 2: Local Python
```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python main.py
```

### Usage

1. Start a chat with your bot on Telegram
2. Send `/start` to begin
3. Send photos of your food or describe your meals in text
4. Use `/summary` to see your daily nutrition summary
5. Use `/history` to view your meal history

### Access Control

The bot includes an access control system:
- Only users listed in `AUTHORIZED_TELEGRAM_IDS` can use the bot
- Unauthorized users can request access through the bot
- Access requests are stored in Firebase for review

## Project Structure

```
JiakAI/
├── src/
│   ├── services/           # External API services
│   ├── models/            # Data models
│   └── utils/             # Utility functions
├── main.py                # Bot entry point
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker configuration
├── docker-compose.yml    # Docker Compose setup
└── .env.example          # Environment variables template
```

## Contributing

This is an experimental project. Feel free to fork, modify, and improve upon it. All contributions are welcome!

## License

This project is provided as-is for experimental and educational purposes. Use at your own discretion.

---

**Remember**: This codebase was generated entirely with AI assistance. Please review and test thoroughly before using in production environments.