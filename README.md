# JiakAI - Food Tracking Telegram Bot

A Telegram bot that helps users track their meals and nutrition by analyzing food photos and text descriptions using AI.

## Features

- 📸 Photo analysis using OpenAI Vision
- 💬 Text-based meal logging
- 🔥 Nutrition tracking with Nutritionix API
- 📊 Daily nutrition summaries
- 📝 Meal history tracking
- 🔒 Secure data storage with Firebase

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables:**
   Edit the `.env` file with your API keys:
   - `TELEGRAM_BOT_TOKEN`: Get from @BotFather on Telegram
   - `OPENAI_API_KEY`: Get from OpenAI Platform
   - `NUTRITIONIX_APP_ID` & `NUTRITIONIX_API_KEY`: Get from Nutritionix Developer Portal
   - Firebase credentials: Get from Firebase Console

3. **Set up Firebase:**
   - Create a new Firebase project
   - Enable Firestore Database
   - Generate a service account key
   - Add the credentials to your `.env` file

4. **Run the bot:**
   ```bash
   python main.py
   ```

## Usage

- Start the bot: `/start`
- Send a photo of your meal for analysis
- Or describe your meal in text
- Get daily summary: `/summary`
- View meal history: `/history`
- Get help: `/help`

## API Keys Required

- **Telegram Bot Token**: Create a bot via @BotFather
- **OpenAI API Key**: For food image and text analysis
- **Nutritionix API**: For nutrition data lookup
- **Firebase Credentials**: For data storage

## Project Structure

```
JiakAI/
├── main.py                 # Main bot application
├── requirements.txt        # Python dependencies
├── .env                   # Environment variables
├── src/
│   ├── services/
│   │   ├── openai_service.py      # OpenAI integration
│   │   ├── nutritionix_service.py # Nutritionix API
│   │   └── firebase_service.py    # Firebase/Firestore
│   ├── models/            # Data models (future)
│   └── utils/            # Utility functions (future)
└── README.md
```

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request