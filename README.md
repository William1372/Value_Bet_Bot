# Value Bet Bot + Odds Jump Detector
A simple Python bot that fetches odds from TheOddsAPI, compares bookmakers, finds value bets, and detects major odds jumps. Results are automatically sent to Telegram.

## Features
- Finds the best odds across selected bookmakers  
- Detects value bets using market average odds  
- Detects odds jumps (±0.20 changes)  
- Sends alerts to Telegram  
- Runs every X minutes  
- Value bets can be sent every Nth iteration to reduce spam  
- Shows which bookmaker offers the best odds on the match favourite  

## Requirements
- Python 3.10+
- Install packages: pip install requests python-dotenv

## Setup
1. Create a `.env` file:
   THE_ODDS_API_KEY=your_api_key
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_CHAT_ID=your_chat_id
   
3. Edit configuration in `main.py`:
- `SPORT` (e.g. `soccer_epl`, `soccer_denmark_superliga`)
- `TARGET_BOOKMAKERS`
- `VALUE_THRESHOLD`
- `CHECK_INTERVAL`

3. Run the bot: python main.py

## Environment Variables
- `THE_ODDS_API_KEY` – API key from theoddsapi.com  
- `TELEGRAM_BOT_TOKEN` – Telegram bot token  
- `TELEGRAM_CHAT_ID` – Chat ID to receive alerts
