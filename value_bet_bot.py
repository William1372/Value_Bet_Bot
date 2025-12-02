import requests
import json
import time
from dotenv import load_dotenv
import os

load_dotenv()

# ------------------------------------------------------------
# KONFIGURATION
# ------------------------------------------------------------

THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SPORT = "soccer_epl" #soccer_denmark_superliga for (DK) Superligaen
REGION = "eu"
MARKETS = "h2h"

TARGET_BOOKMAKER = "unibet_se"
VALUE_THRESHOLD = 0.10
ODDS_JUMP_THRESHOLD = 0.20   # stor ændring i odds

CHECK_INTERVAL = 1800

# ------------------------------------------------------------
# STATE: GEM TIDLIGERE ODDS
# ------------------------------------------------------------

previous_odds = {}  # { match_id: { bookmaker: {home, draw, away} } }


# ------------------------------------------------------------
# TELEGRAM
# ------------------------------------------------------------

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})


# ------------------------------------------------------------
# HENT ODDS
# ------------------------------------------------------------

def fetch_odds():
    url = (
        f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds/"
        f"?apiKey={THE_ODDS_API_KEY}&regions={REGION}&markets={MARKETS}"
    )

    r = requests.get(url)
    if r.status_code != 200:
        print("API-fejl:", r.status_code, r.text)
        return None

    return r.json()


# ------------------------------------------------------------
# HJÆLPERE
# ------------------------------------------------------------

def get_market_average(bookmakers, outcome_name):
    prices = []
    for b in bookmakers:
        for m in b["markets"]:
            for o in m["outcomes"]:
                if o["name"] == outcome_name:
                    prices.append(o["price"])
    if not prices:
        return None
    return sum(prices) / len(prices)


def find_bookmaker(bookmakers, name):
    for b in bookmakers:
        if b["key"] == name:
            return b
    return None


# ------------------------------------------------------------
# ODDS CHANGE DETECTION
# ------------------------------------------------------------

def check_odds_jump(match_id, match_name, bookmaker_key, new_odds):
    global previous_odds

    if match_id not in previous_odds:
        previous_odds[match_id] = {}

    if bookmaker_key not in previous_odds[match_id]:
        previous_odds[match_id][bookmaker_key] = new_odds
        return

    old = previous_odds[match_id][bookmaker_key]

    for outcome in ["home", "draw", "away"]:
        old_price = old.get(outcome)
        new_price = new_odds.get(outcome)

        if old_price is None or new_price is None:
            continue

        diff = new_price - old_price

        if abs(diff) >= ODDS_JUMP_THRESHOLD:
            direction = "↑" if diff > 0 else "↓"

            send_telegram(
                f"⚠️ Odds ændring opdaget!\n\n"
                f"{match_name}\n"
                f"{outcome.capitalize()} ODDS: {old_price} → {new_price} ({direction}{diff:.2f})\n"
                f"BOOKMAKER: {bookmaker_key}"
            )

    # opdater lagret odds
    previous_odds[match_id][bookmaker_key] = new_odds


# ------------------------------------------------------------
# VALUE BET LOGIK
# ------------------------------------------------------------

def check_value_for_match(match):
    home = match["home_team"]
    away = match["away_team"]
    match_name = f"{home} vs {away}"
    match_id = match["id"]

    bookmakers = match["bookmakers"]
    if not bookmakers:
        return

    # MARKET AVERAGE
    avg_home = get_market_average(bookmakers, home)
    avg_draw = get_market_average(bookmakers, "Draw")
    avg_away = get_market_average(bookmakers, away)

    # TARGET BOOKMAKER
    book = find_bookmaker(bookmakers, TARGET_BOOKMAKER)
    if not book:
        return

    outcomes = book["markets"][0]["outcomes"]

    # Dine odds
    your_home = next((o["price"] for o in outcomes if o["name"] == home), None)
    your_draw = next((o["price"] for o in outcomes if o["name"] == "Draw"), None)
    your_away = next((o["price"] for o in outcomes if o["name"] == away), None)

    # --- ODDS JUMP CHECK ---
    new_odds = {
        "home": your_home,
        "draw": your_draw,
        "away": your_away
    }
    check_odds_jump(match_id, match_name, TARGET_BOOKMAKER, new_odds)

    # --- VALUE CHECK ---
    def value(y, avg):
        if y is None or avg is None:
            return None
        return (y / avg) - 1

    v_home = value(your_home, avg_home)
    v_draw = value(your_draw, avg_draw)
    v_away = value(your_away, avg_away)

    if v_home and v_home >= VALUE_THRESHOLD:
        send_telegram(
            f"🔥 VALUE BET!\n\n"
            f"{match_name}\n"
            f"HOME TEAM\n"
            f"AVG. ODDS: {avg_home:.2f}\n, {TARGET_BOOKMAKER}: {your_home:.2f}\n"
            f"VALUE: {v_home*100:.2f}%"
        )

    if v_draw and v_draw >= VALUE_THRESHOLD:
        send_telegram(
            f"🔥 VALUE BET!\n\n"
            f"{match_name}\n"
            f"DRAW\n"
            f"AVG. ODDS: {avg_draw:.2f}\n, {TARGET_BOOKMAKER}: {your_draw:.2f}\n"
            f"VALUE: {v_draw*100:.2f}%"
        )

    if v_away and v_away >= VALUE_THRESHOLD:
        send_telegram(
            f"🔥 VALUE BET!\n\n"
            f"{match_name}\n"
            f"AWAY TEAM\n"
            f"AVG. ODDS: {avg_away:.2f}\n, {TARGET_BOOKMAKER}: {your_away:.2f}\n"
            f"VALUE: {v_away*100:.2f}%"
        )


# ------------------------------------------------------------
# MAIN LOOP
# ------------------------------------------------------------

def main():
    send_telegram("🟢 Value Bet Bot + Odds Jump Detector startet!")

    while True:
        matches = fetch_odds()

        if matches:
            for match in matches:
                check_value_for_match(match)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
