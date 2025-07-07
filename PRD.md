# JiakAI - Product Requirements Document (PRD)

## 1. Overview
A Telegram bot that enables users to log their meals by sending photos or text. The bot uses OpenAI to analyze the food, queries Nutritionix for nutritional data (calories, macros, etc.), and stores logs in Firebase. Users can view daily summaries and historical logs.

---

## 2. Goals
- Simplify food logging and calorie tracking for daily use.
- Provide instant, AI-powered nutrition feedback from photos or text.
- Store and summarize user meal data for easy review and habit tracking.

---

## 3. Stakeholders
- **Owner/Product Manager:** @You
- **Design:** @You (or N/A for bot UI)
- **Development:** @You

---

## 4. Background and Strategic Fit
Manual food logging is tedious and often leads to poor adherence. By leveraging AI and chat-based interfaces, this bot makes food tracking frictionless and accessible, fitting into the growing trend of health-focused, AI-powered personal tools.

---

## 5. Success Criteria
- Users can log a meal and receive nutrition info in <10 seconds.
- Users can retrieve daily summaries with a single command.
- >90% uptime and reliable data storage.

---

## 6. Scope

### 6.1. User Stories and Requirements
| User Story | Requirement | Priority |
|------------|-------------|----------|
| As a user, I want to send a photo of my meal and get calories/macros. | Bot receives photo, uses OpenAI, queries Nutritionix, replies with nutrition info. | High |
| As a user, I want to send a text description if I forget a photo. | Bot parses text, uses OpenAI/Nutritionix, replies with nutrition info. | High |
| As a user, I want to view my daily calorie/macro summary. | Bot aggregates and displays daily totals. | High |
| As a user, I want to view my meal history for a given day. | Bot retrieves and displays meal logs for a date. | Medium |
| As a user, I want my data to be private and secure. | Store only Telegram IDs, use Firebase security rules. | High |

### 6.2. Out of Scope
- Social features (sharing, leaderboards)
- Manual editing of nutrition data (MVP)
- Advanced analytics (beyond daily/meal summaries)

---

## 7. Features
- Telegram bot interface (photo and text input)
- OpenAI Vision (image-to-food description)
- Nutritionix API (nutrition lookup)
- Firebase Firestore (user data, meal logs, summaries)
- Daily and historical summaries
- Friendly, conversational UI/UX

---

## 8. Technical Architecture
- **Bot Framework:** Python (`python-telegram-bot` or `aiogram`)
- **AI:** OpenAI GPT-4 Vision API
- **Nutrition Data:** Nutritionix API
- **Database:** Firebase Firestore
- **Deployment:** Railway, Render, Heroku, or Google Cloud Run

### System Flow
1. User sends photo or text
2. Bot receives input
   - If photo: download image, send to OpenAI Vision
   - If text: send to OpenAI for food parsing
3. OpenAI returns food description
4. Bot queries Nutritionix API with food description
5. Bot receives nutrition data
6. Bot stores meal log in Firestore
7. Bot replies to user with nutrition info
8. User can request daily summary or history

---

## 9. Data Model (Firestore)
- **users/{user_id}**
  - `telegram_id`: string
  - `created_at`: timestamp
- **users/{user_id}/meals/{meal_id}**
  - `timestamp`: timestamp
  - `input_type`: "photo" | "text"
  - `input_value`: string (text or Telegram file_id)
  - `food_description`: string
  - `nutrition`: object (calories, macros, etc.)
  - `raw_openai_response`: object
  - `raw_nutritionix_response`: object
- **users/{user_id}/summaries/{date}**
  - `date`: YYYY-MM-DD
  - `total_calories`: number
  - `total_protein`: number
  - `total_fat`: number
  - `total_carbs`: number
  - `meal_count`: number

---

## 10. Security & Privacy
- Store only Telegram user IDs, not phone numbers or names
- Use Firebase security rules to restrict access
- Do not store images, only Telegram file_ids (unless needed for external processing)
- All API keys and credentials stored in environment variables

---

## 11. Milestones
1. Telegram bot receives photo/text and replies with food description (OpenAI)
2. Nutritionix API integration for calorie/macro lookup
3. Store logs in Firestore
4. Daily summary command
5. Historical log retrieval

---

## 12. References
- [Nutritionix API Docs](https://developer.nutritionix.com/docs/v2)
- [OpenAI API Docs](https://platform.openai.com/docs/guides/vision)
- [python-telegram-bot Docs](https://python-telegram-bot.org/)
- [Firebase Admin SDK Docs](https://firebase.google.com/docs/admin/setup) 