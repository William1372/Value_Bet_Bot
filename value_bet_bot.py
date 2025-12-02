import requests
import json
import time
from dotenv import load_dotenv
import os
from datetime import datetime
from zoneinfo import ZoneInfo

load_dotenv()

# ------------------------------------------------------------
# KONFIGURATION
# ------------------------------------------------------------

THE_ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SPORT = "soccer_epl"  # fx "soccer_denmark_superliga"
REGION = "eu"
MARKETS = "h2h"

TARGET_BOOKMAKERS = ["unibet_se", "sport888", "betsson", "leovegas_se", "nordicbet", "mrgreen_se"]

VALUE_THRESHOLD = 0.10      # 10% value
ODDS_JUMP_THRESHOLD = 0.20  # hvor meget et odds skal ændre sig før jump besked

CHECK_INTERVAL = 900        # hvert 15. minut
VALUE_SEND_EVERY = 3        # value bets kun hver 3 iteration

iteration_counter = 0
previous_odds = {}          # gemmer tidligere odds for jump-detection


# ------------------------------------------------------------
# TELEGRAM
# ------------------------------------------------------------
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload, timeout=10)
    except:
        pass


# ------------------------------------------------------------
# HENT ODDS
# ------------------------------------------------------------
def fetch_odds():
    url = (
        f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds/"
        f"?apiKey={THE_ODDS_API_KEY}&regions={REGION}&markets={MARKETS}"
    )
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json()
    except:
        return None


# ------------------------------------------------------------
# HJÆLPERE
# ------------------------------------------------------------
def get_market_average(bookmakers, outcome_name):
    prices = []
    for b in bookmakers:
        for m in b.get("markets", []):
            for o in m.get("outcomes", []):
                if o["name"] == outcome_name:
                    prices.append(o["price"])
    return sum(prices) / len(prices) if prices else None


def extract_prices_from_outcomes(outcomes, home, away):
    home_odds = next((o["price"] for o in outcomes if o["name"] == home), None)
    draw_odds = next((o["price"] for o in outcomes if o["name"] == "Draw"), None)
    away_odds = next((o["price"] for o in outcomes if o["name"] == away), None)
    return {"home": home_odds, "draw": draw_odds, "away": away_odds}


def get_match_time_danish(utc_string):
    if not utc_string:
        return "Ukendt tidspunkt"
    try:
        utc_time = datetime.fromisoformat(utc_string.replace("Z", "+00:00"))
        dk_time = utc_time.astimezone(ZoneInfo("Europe/Copenhagen"))
        return dk_time.strftime("%d-%m-%Y %H:%M")
    except:
        return "Ukendt tidspunkt"


# ------------------------------------------------------------
# BEDSTE BOOKMAKER PR. UDFALD
# ------------------------------------------------------------
def get_best_odds(bookmakers, home, away):
    best = {"home": (None, None), "draw": (None, None), "away": (None, None)}

    for b in bookmakers:
        key = b.get("key")
        if key not in TARGET_BOOKMAKERS:
            continue

        for m in b.get("markets", []):
            for o in m.get("outcomes", []):
                name = o["name"]
                price = o["price"]

                if name == home and (best["home"][0] is None or price > best["home"][0]):
                    best["home"] = (price, key)
                elif name == "Draw" and (best["draw"][0] is None or price > best["draw"][0]):
                    best["draw"] = (price, key)
                elif name == away and (best["away"][0] is None or price > best["away"][0]):
                    best["away"] = (price, key)

    return best


# ------------------------------------------------------------
# FAVORIT OG BEDSTE PRIS PÅ FAVORITTEN
# ------------------------------------------------------------
def get_favorite_and_best_price(bookmakers, home, away):
    avg_home = get_market_average(bookmakers, home)
    avg_draw = get_market_average(bookmakers, "Draw")
    avg_away = get_market_average(bookmakers, away)

    outcome_avgs = {}
    if avg_home: outcome_avgs["home"] = avg_home
    if avg_draw: outcome_avgs["draw"] = avg_draw
    if avg_away: outcome_avgs["away"] = avg_away

    if not outcome_avgs:
        return None, None, None

    favorite = min(outcome_avgs, key=lambda k: outcome_avgs[k])  # laveste odds = favorit

    best_price = None
    best_bookmaker = None

    for b in bookmakers:
        key = b.get("key")
        if key not in TARGET_BOOKMAKERS:
            continue

        for m in b.get("markets", []):
            for o in m.get("outcomes", []):
                if (favorite == "home" and o["name"] == home) or \
                   (favorite == "draw" and o["name"] == "Draw") or \
                   (favorite == "away" and o["name"] == away):

                    if best_price is None or o["price"] > best_price:
                        best_price = o["price"]
                        best_bookmaker = key

    return favorite, best_price, best_bookmaker


# ------------------------------------------------------------
# ODDS JUMP
# ------------------------------------------------------------
def check_odds_jump(match_id, match_name, bookmaker_key, new_odds, match_time):
    global previous_odds

    if match_id not in previous_odds:
        previous_odds[match_id] = {}

    if bookmaker_key not in previous_odds[match_id]:
        previous_odds[match_id][bookmaker_key] = new_odds
        return

    old = previous_odds[match_id][bookmaker_key]

    for key in ["home", "draw", "away"]:
        old_price = old.get(key)
        new_price = new_odds.get(key)

        if isinstance(old_price, (int, float)) and isinstance(new_price, (int, float)):
            diff = new_price - old_price

            if abs(diff) >= ODDS_JUMP_THRESHOLD:
                arrow = "📈" if diff > 0 else "📉"
                send_telegram(
f"""⚠️ ODDS ÆNDRING {arrow}

{match_name}
Kickoff: {get_match_time_danish(match_time)}
Bookmaker: {bookmaker_key}

Marked: {key.upper()}
{old_price} → {new_price} ({arrow} {diff:.2f})
"""
                )

    previous_odds[match_id][bookmaker_key] = new_odds


# ------------------------------------------------------------
# VALUE BETS
# ------------------------------------------------------------
def check_value_for_match(match, should_send_value):
    home = match.get("home_team")
    away = match.get("away_team")
    match_name = f"{home} vs {away}"
    match_time = match.get("commence_time")
    match_id = match.get("id")
    start_time = get_match_time_danish(match_time)

    bookmakers = match.get("bookmakers", [])
    if not bookmakers:
        return

    # gennemsnit
    avg_home = get_market_average(bookmakers, home)
    avg_draw = get_market_average(bookmakers, "Draw")
    avg_away = get_market_average(bookmakers, away)

    # bedste odds
    best = get_best_odds(bookmakers, home, away)
    best_home, book_home = best["home"]
    best_draw, book_draw = best["draw"]
    best_away, book_away = best["away"]

    # favorit + bedste odds på favoritten
    favorite, fav_best_price, fav_best_book = get_favorite_and_best_price(bookmakers, home, away)

    # jumps på de bookmakere der har best odds
    if book_home:
        check_odds_jump(match_id, match_name, book_home, {"home": best_home}, match_time)
    if book_draw:
        check_odds_jump(match_id, match_name, book_draw, {"draw": best_draw}, match_time)
    if book_away:
        check_odds_jump(match_id, match_name, book_away, {"away": best_away}, match_time)

    # value udregning
    def value(y, avg):
        return (y / avg) - 1 if y and avg else None

    v_home = value(best_home, avg_home)
    v_draw = value(best_draw, avg_draw)
    v_away = value(best_away, avg_away)

    if not should_send_value:
        return

    # send value besked
    def send_value(label, avg, odds_val, val_pct, bookmaker, fav_text=""):
        send_telegram(
f"""🔥 VALUE BET 🔥

{match_name}
Kickoff: {start_time}

Spil: {label}
Bookmaker: {bookmaker}

Gennemsnit: {avg:.2f}
Bedste odds: {odds_val:.2f}
Value: {val_pct*100:.2f}%

{fav_text}
"""
        )

    if v_home and v_home >= VALUE_THRESHOLD:
        ft = ""
        if favorite == "home":
            ft = f"Favorit: {favorite.upper()} – bedste pris {fav_best_price} hos {fav_best_book}"
        send_value("HOME", avg_home, best_home, v_home, book_home, ft)

    if v_draw and v_draw >= VALUE_THRESHOLD:
        ft = ""
        if favorite == "draw":
            ft = f"Favorit: {favorite.upper()} – bedste pris {fav_best_price} hos {fav_best_book}"
        send_value("DRAW", avg_draw, best_draw, v_draw, book_draw, ft)

    if v_away and v_away >= VALUE_THRESHOLD:
        ft = ""
        if favorite == "away":
            ft = f"Favorit: {favorite.upper()} – bedste pris {fav_best_price} hos {fav_best_book}"
        send_value("AWAY", avg_away, best_away, v_away, book_away, ft)


# ------------------------------------------------------------
# MAIN LOOP
# ------------------------------------------------------------
def main():
    global iteration_counter
    send_telegram("🟢 Bot startet")

    while True:
        iteration_counter += 1
        should_send_value = (iteration_counter % VALUE_SEND_EVERY == 0)

        matches = fetch_odds()

        if matches:
            for match in matches:
                check_value_for_match(match, should_send_value)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
