import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "prayerbot")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.getenv("PORT", "10000"))
TIMEZONE = os.getenv("TIMEZONE", "Africa/Algiers")
LAT = float(os.getenv("LAT", "36.7538"))
LON = float(os.getenv("LON", "3.0588"))
METHOD = int(os.getenv("PRAYER_METHOD", "3"))
