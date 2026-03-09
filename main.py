import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import requests
import time
import threading
import re
import os
import json
import pyotp
from datetime import datetime
from collections import deque
from flask import Flask

# ================= কনফিগারেশন =================
BOT_TOKEN = "8613173512:AAG1og51c3VYgdHvS_lh9QGP4Fpkc0bDanY" # বটের টোকেন
ADMIN_ID = 7291250175 # মেইন এডমিন টেলিগ্রাম আইডি
GROUP_ID = -1003838868506 # আপনার টেলিগ্রাম গ্রুপের আইডি (যেখানে কনসোলের ম্যাসেজ যাবে)

STEX_EMAIL = "arafatrahul369@gmail.com"
STEX_PASSWORD = "Yasin12@#"
STEX_LOGIN_URL = "https://stexsms.com/mapi/v1/mauth/login"

# ================= গ্লোবাল ভেরিয়েবল =================
bot = telebot.TeleBot(BOT_TOKEN)
AUTH_TOKEN = ""
user_temp_data = {}
posted_console_ids = deque(maxlen=500) # ডুপ্লিকেট ঠেকানোর জন্য
db_lock = threading.Lock()

app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running perfectly on Render!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ================= ডাটাবেস ফাংশন =================
def load_json(filename, default_data):
    if not os.path.exists(filename):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, indent=4)
        return default_data
    with open(filename, 'r', encoding='utf-8') as f:
        try: return json.load(f)
        except: return default_data

def save_json(filename, data):
    with db_lock:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

default_settings = {
    "reward_per_otp": 0.25,
    "withdraw_status": True,
    "withdraw_notice": "উইথড্র সাময়িকভাবে বন্ধ আছে।",
    "min_withdraw": {"Bkash": 50, "Nagad": 50, "Rocket": 50},
    "sub_admins":[],
    "force_channel_id": "@ANNUMBERPANELL",
    "force_channel_url": "https://t.me/ANNUMBERPANELL",
    "force_group_id": "", 
    "force_group_url": "https://t.me/+-XHCsEd9WhMzNjVl",
    "services": {}
}
settings = load_json("settings.json", default_settings)
users_db = load_json("users.json", {})

def is_admin(user_id):
    return user_id == ADMIN_ID or user_id in settings.get("sub_admins",[])

def save_user(message):
    chat_id = str(message.chat.id)
    if chat_id not in users_db:
        users_db[chat_id] = {
            "first_name": message.from_user.first_name or "",
            "username": message.from_user.username or "N/A",
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "balance": 0.0
        }
        save_json("users.json", users_db)

# ================= Force Join Verification =================
def check_joined(user_id):
    if is_admin(user_id): return True
    
    ch_id = settings.get("force_channel_id", "").strip()
    gr_id = settings.get("force_group_id", "").strip()
    
    joined_ch = True
    joined_gr = True
    
    try:
        if ch_id:
            stat = bot.get_chat_member(ch_id, user_id).status
            if stat in ['left', 'kicked']: joined_ch = False
    except: pass 
    
    try:
        if gr_id:
            stat = bot.get_chat_member(gr_id, user_id).status
            if stat in ['left', 'kicked']: joined_gr = False
    except: pass

    return joined_ch and joined_gr

def force_join_msg(chat_id):
    markup = InlineKeyboardMarkup(row_width=1)
    if settings.get("force_channel_url"):
        markup.add(InlineKeyboardButton("📢 Join Channel", url=settings["force_channel_url"]))
    if settings.get("force_group_url"):
        markup.add(InlineKeyboardButton("💬 Join Group", url=settings["force_group_url"]))
    markup.add(InlineKeyboardButton("✅ Verify", callback_data="verify_join"))
    
    bot.send_message(chat_id, "⚠️ **বটটি ব্যবহার করতে অবশ্যই আমাদের চ্যানেল ও গ্রুপে যুক্ত হোন!**\nযুক্ত হওয়ার পর 'Verify' বাটনে ক্লিক করুন।", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "verify_join")
def verify_join_callback(call):
    if check_joined(call.message.chat.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "✅ ভেরিফিকেশন সফল হয়েছে!", reply_markup=main_menu(call.message.chat.id))
    else:
        bot.answer_callback_query(call.id, "❌ আপনি এখনো যুক্ত হননি!", show_alert=True)

# ================= API Auth & Robust Request =================
def refresh_jwt_token():
    global AUTH_TOKEN
    try:
        response = requests.post(STEX_LOGIN_URL, json={"email": STEX_EMAIL, "password": STEX_PASSWORD})
        if response.status_code == 200:
            AUTH_TOKEN = response.json().get("token") or response.json().get("data", {}).get("token")
            return True
    except: pass
    return False

def get_headers():
    return {
        "mauthtoken": AUTH_TOKEN,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Origin": "https://stexsms.com",
        "Referer": "https://stexsms.com/mdashboard/getnum"
    }

def make_api_request(method, url, payload=None):
    for _ in range(2):
        headers = get_headers()
        try:
            res = requests.get(url, headers=headers) if method == "GET" else requests.post(url, json=payload, headers=headers)
            if res.status_code == 401: 
                refresh_jwt_token()
                continue
            return res
        except: return None
    return None

# ================= Console Monitor (Group Post Only) =================
def console_monitor_thread():
    while True:
        try:
            url = "https://stexsms.com/mapi/v1/mdashboard/console/info"
            res = make_api_request("GET", url)
            if res and res.status_code == 200:
                logs = res.json().get("data", {}).get("logs",[])
                
                for log in reversed(logs):
                    log_id = log.get("id")
                    if log_id in posted_console_ids: continue
                    
                    app_name, country_str, range_val = log.get("app_name", "Unknown"), log.get("country", "Unknown"), log.get("range", "")
                    sms, time_val = log.get("sms", ""), log.get("time", "")
                    
                    # Group Broadcast
                    msg = f"✅ 📘 {app_name} | 🌍 {country_str}\n\n📱Range: `{range_val}`\n\n🔑 Code: `{sms}` | {time_val}"
                    try:
                        bot.send_message(GROUP_ID, msg, parse_mode="Markdown")
                        posted_console_ids.append(log_id)
                    except: pass
        except: pass
        time.sleep(5)

# ================= Main Menus =================
def main_menu(user_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("☎️ Get Number"), KeyboardButton("💰 Balance"))
    markup.add(KeyboardButton("👤 Profile"), KeyboardButton("💬 Support"), KeyboardButton("🔐 2FA"))
    if is_admin(user_id): markup.add(KeyboardButton("⚙️ Admin Panel"), KeyboardButton("👥 Users"))
    return markup

def back_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🔙 Back to Home"))
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(message):
    save_user(message)
    if not check_joined(message.chat.id):
        force_join_msg(message.chat.id)
        return
    bot.send_message(message.chat.id, f"স্বাগতম {message.from_user.first_name}! 🤖", reply_markup=main_menu(message.chat.id))

@bot.message_handler(func=lambda m: m.text == "🔙 Back to Home")
def back_home(m): bot.send_message(m.chat.id, "🏠 হোমে ফিরে এসেছেন।", reply_markup=main_menu(m.chat.id))

@bot.message_handler(func=lambda m: m.text == "👤 Profile")
def profile_cmd(m):
    if not check_joined(m.chat.id): return force_join_msg(m.chat.id)
    uid = str(m.chat.id)
    bal = users_db.get(uid, {}).get('balance', 0.0)
    bot.send_message(m.chat.id, f"👤 **প্রোফাইল**\n\n🔹 **নাম:** {m.from_user.first_name}\n🔹 **আইডি:** `{m.chat.id}`\n💰 **ব্যালেন্স:** ৳{bal}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💬 Support")
def support_cmd(m):
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("💬 Support Chat", url="https://t.me/MEeASDF"))
    bot.send_message(m.chat.id, "যেকোনো প্রয়োজনে আমাদের সাপোর্ট টিমের সাথে যোগাযোগ করুন:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🔐 2FA")
def ask_2fa(m):
    msg = bot.send_message(m.chat.id, "🔐 আপনার 2FA Secret Key পাঠান:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, process_2fa)

def process_2fa(m):
    if m.text == "🔙 Back to Home": return back_home(m)
    secret = m.text.replace(" ", "").upper()
    try:
        bot.send_message(m.chat.id, f"✅ **আপনার OTP তৈরি হয়েছে!**\n\n🔑 Code: `{pyotp.TOTP(secret).now()}`", parse_mode='Markdown', reply_markup=main_menu(m.chat.id))
    except:
        bot.send_message(m.chat.id, "❌ Error: Secret Key টি সঠিক নয়।", reply_markup=main_menu(m.chat.id))

# ================= Earn & Withdraw =================
@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def balance_cmd(m):
    if not check_joined(m.chat.id): return force_join_msg(m.chat.id)
    uid = str(m.chat.id)
    bal = users_db.get(uid, {}).get('balance', 0.0)
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("💸 Withdraw", callback_data="req_withdraw"))
    bot.send_message(m.chat.id, f"💰 **বর্তমান ব্যালেন্স:** ৳{bal}", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "req_withdraw")
def withdraw_req(call):
    if not settings.get("withdraw_status", True):
        return bot.answer_callback_query(call.id, settings.get('withdraw_notice', 'Withdraw closed.'), show_alert=True)
        
    text = "🏦 **Withdraw Methods:**\n\n"
    for method, minim in settings["min_withdraw"].items(): text += f"🔹 {method}: Min ৳{minim}\n"
    
    markup = InlineKeyboardMarkup(row_width=3).add(
        InlineKeyboardButton("Bkash", callback_data="wth_Bkash"),
        InlineKeyboardButton("Nagad", callback_data="wth_Nagad"),
        InlineKeyboardButton("Rocket", callback_data="wth_Rocket")
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("wth_"))
def wth_amount(call):
    method = call.data.split("_")[1]
    uid = str(call.message.chat.id)
    bal, min_w = users_db.get(uid, {}).get('balance', 0.0), settings["min_withdraw"].get(method, 50)
    
    if bal < min_w: return bot.answer_callback_query(call.id, f"❌ আপনার ব্যালেন্স কম! মিনিমাম ৳{min_w} প্রয়োজন।", show_alert=True)
    msg = bot.send_message(call.message.chat.id, f"✅ Method: {method}\n💰 Available: ৳{bal}\n\nকতো টাকা তুলতে চান?", reply_markup=back_menu())
    bot.register_next_step_handler(msg, lambda m: process_wth_amount(m, method, bal))

def process_wth_amount(m, method, bal):
    if m.text == "🔙 Back to Home": return back_home(m)
    try:
        amount = float(m.text)
        if amount < settings["min_withdraw"].get(method, 50) or amount > bal:
            return bot.send_message(m.chat.id, "❌ এমাউন্ট সঠিক নয় বা ব্যালেন্স কম।", reply_markup=main_menu(m.chat.id))
        msg = bot.send_message(m.chat.id, f"✅ আপনার {method} নাম্বারটি লিখুন:")
        bot.register_next_step_handler(msg, lambda mx: process_wth_final(mx, method, amount))
    except: bot.send_message(m.chat.id, "❌ শুধুমাত্র সংখ্যা ব্যবহার করুন।", reply_markup=main_menu(m.chat.id))

def process_wth_final(m, method, amount):
    if m.text == "🔙 Back to Home": return back_home(m)
    uid = str(m.chat.id)
    users_db[uid]["balance"] -= amount
    save_json("users.json", users_db)
    bot.send_message(m.chat.id, f"✅ উইথড্র রিকোয়েস্ট সফল!\n💳 {method}: ৳{amount}\n📱 Number: {m.text}", reply_markup=main_menu(m.chat.id))
    admin_msg = f"🔔 **NEW WITHDRAW**\n👤 User:[{m.from_user.first_name}](tg://user?id={uid})\n💳 {method} ৳{amount}\n📱 Num: `{m.text}`"
    bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")

# ================= GET NUMBER =================
@bot.message_handler(func=lambda m: m.text == "☎️ Get Number")
def get_number_start(m):
    if not check_joined(m.chat.id): return force_join_msg(m.chat.id)
    if not settings.get("services"): return bot.send_message(m.chat.id, "❌ কোনো সার্ভিস নেই।")
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(*[InlineKeyboardButton(srv, callback_data=f"getSrv_{srv}") for srv in settings["services"].keys()])
    bot.send_message(m.chat.id, "🔧 **কোন সার্ভিসের নাম্বার নিবেন?**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("getSrv_"))
def select_country(call):
    srv = call.data.split("_")[1]
    countries = settings.get("services", {}).get(srv, {})
    if not countries: return bot.edit_message_text("❌ এই সার্ভিসে দেশ নেই।", call.message.chat.id, call.message.message_id)
    markup = InlineKeyboardMarkup(row_width=2)
    for code, details in countries.items(): 
        btn_text = f"{details.get('flag','🏳')} #{code} | {details.get('name','Unknown')}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"getCnt_{srv}_{code}"))
    bot.edit_message_text("🌍 **দেশ সিলেক্ট করুন:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("getCnt_"))
def select_range(call):
    _, srv, code = call.data.split("_")
    ranges = settings.get("services", {}).get(srv, {}).get(code, {}).get("ranges", {})
    if not ranges: return bot.edit_message_text("❌ কোনো রেঞ্জ নেই।", call.message.chat.id, call.message.message_id)
    markup = InlineKeyboardMarkup(row_width=2)
    for r in ranges.keys():
        markup.add(InlineKeyboardButton(f"{r}", callback_data=f"getRng_{srv}_{code}_{r}"))
    bot.edit_message_text("🔢 **রেঞ্জ সিলেক্ট করুন:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("getRng_") or call.data.startswith("reRng_"))
def fetch_number(call):
    parts = call.data.split("_")
    srv, code, range_val = parts[1], parts[2], parts[3]
    chat_id, msg_id = call.message.chat.id, call.message.message_id
    c_details = settings["services"][srv][code]
    reward = settings.get("reward_per_otp", 0.25)
    
    bot.edit_message_text("⏳ *নাম্বার খোঁজা হচ্ছে...*", chat_id, msg_id, parse_mode="Markdown")
    
    res = make_api_request("POST", "https://stexsms.com/mapi/v1/mdashboard/getnum/number", {"range": range_val})
    raw_number = None
    
    # Robust API Checking
    if res and res.status_code in[200, 201]:
        try:
            data = res.json()
            raw_number = data.get('number')
            if not raw_number and isinstance(data.get('data'), dict):
                raw_number = data['data'].get('number')
        except: pass
        
        # Fallback regex if API format changes
        if not raw_number:
            match = re.search(r'"number"\s*:\s*"?(\d+)"?', res.text)
            if match: raw_number = match.group(1)

    if raw_number:
        clean_num = str(raw_number).replace("+", "").strip()
        text = f"┌── NUMBER VERIFIED ──┐\n✨ যাচাই সম্পন্ন\n🌍 দেশ ও দাম: {c_details['flag']} {c_details['name']} (৳{reward})\n\n📱 Number : `{clean_num}`\n\n🔑 OTP কোড: ⏳ অপেক্ষা করুন...\n└── NUMBER VERIFIED ──┘"
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("🆕 Same Range", callback_data=f"reRng_{srv}_{code}_{range_val}"))
        if settings.get("force_group_url"):
            markup.row(InlineKeyboardButton("💬 OTP Group", url=settings["force_group_url"]))
            
        bot.edit_message_text(text, chat_id, msg_id, parse_mode="Markdown", reply_markup=markup)
        threading.Thread(target=auto_check_otp, args=(chat_id, msg_id, clean_num, srv, c_details, reward), daemon=True).start()
    else: 
        bot.edit_message_text("❌ নাম্বার পাওয়া যায়নি। অন্য রেঞ্জ ট্রাই করুন।", chat_id, msg_id)

def auto_check_otp(chat_id, msg_id, number, srv, c_details, reward):
    for _ in range(60):
        time.sleep(5)
        res = make_api_request("GET", f"https://stexsms.com/mapi/v1/mdashboard/getnum/info?date={datetime.now().strftime('%Y-%m-%d')}&page=1&search={number}&status=")
        if res and res.status_code == 200:
            items = res.json().get("data", {}).get("numbers",[])
            if items:
                status, full_msg = items[0].get("status", "pending"), items[0].get("message", "")
                if status == "success" and full_msg:
                    code_match = re.search(r'\b\d{4,8}\b', full_msg)
                    code = code_match.group(0) if code_match else "N/A"
                    
                    uid = str(chat_id)
                    users_db[uid]["balance"] = round(users_db[uid].get("balance", 0.0) + reward, 2)
                    save_json("users.json", users_db)
                    
                    text = f"🔰 {bot.get_me().first_name} | OTP RCV\n\n📞 Number: `{number}`\n🌐 Country: {c_details['name']}\n🔧 Service: {srv}\n\n📊 Status: 🔒 CLAIMED\n\n🔑 OTP Code: `{code}`\n\n\"{full_msg}\"\n\n💰 আপনার ব্যালেন্সে ৳{reward} যোগ হয়েছে!\nমোট ব্যালেন্স: ৳{users_db[uid]['balance']}"
                    try:
                        bot.send_message(chat_id, text, parse_mode="Markdown")
                        bot.edit_message_text(f"✅ OTP Received for `{number}`.", chat_id, msg_id, parse_mode="Markdown")
                    except: pass
                    return
                elif status == "failed":
                    try: bot.edit_message_text(f"❌ নাম্বার বাতিল!\n📱 `{number}`", chat_id, msg_id)
                    except: pass
                    return

# ================= ADMIN PANEL =================
@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel" and is_admin(m.chat.id))
def admin_panel(m):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("💰 Earn Setup", callback_data="adm_earn"), InlineKeyboardButton("🔧 Services Setup", callback_data="adm_srv"))
    if m.chat.id == ADMIN_ID: markup.add(InlineKeyboardButton("👮 Sub Admins & Links", callback_data="adm_sub"))
    bot.send_message(m.chat.id, "⚙️ **Admin Dashboard**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_") and is_admin(call.message.chat.id))
def admin_nav(call):
    act, cid, mid = call.data, call.message.chat.id, call.message.message_id
    if act == "adm_earn":
        st = "✅ ON" if settings["withdraw_status"] else "❌ OFF"
        text = f"💰 **Earn Settings**\nReward/OTP: ৳{settings['reward_per_otp']}\nWithdraw: {st}\nMin WTH: Bkash:{settings['min_withdraw']['Bkash']} | Nagad:{settings['min_withdraw']['Nagad']}"
        markup = InlineKeyboardMarkup(row_width=2).add(
            InlineKeyboardButton("Edit Reward", callback_data="set_reward"),
            InlineKeyboardButton("Edit Min WTH", callback_data="set_minwth"),
            InlineKeyboardButton("Toggle Withdraw", callback_data="tog_withdraw"),
            InlineKeyboardButton("🔙 Back", callback_data="adm_home")
        )
        bot.edit_message_text(text, cid, mid, reply_markup=markup, parse_mode="Markdown")
        
    elif act == "adm_srv":
        markup = InlineKeyboardMarkup(row_width=2)
        for srv in settings.get("services", {}).keys(): markup.add(InlineKeyboardButton(srv, callback_data=f"eds_{srv}"))
        markup.add(InlineKeyboardButton("➕ Add Service", callback_data="add_srv"), InlineKeyboardButton("🔙 Back", callback_data="adm_home"))
        bot.edit_message_text("🔧 **Services Management**", cid, mid, reply_markup=markup, parse_mode="Markdown")
        
    elif act == "adm_sub" and cid == ADMIN_ID:
        text = f"👮 **Sub Admins:** {len(settings['sub_admins'])}\n\n📢 **Ch ID:** {settings['force_channel_id']}\n💬 **Gr ID:** {settings['force_group_id']}"
        markup = InlineKeyboardMarkup(row_width=2).add(
            InlineKeyboardButton("➕ Add Sub Admin", callback_data="sub_add"),
            InlineKeyboardButton("➖ Rem Sub Admin", callback_data="sub_rem"),
            InlineKeyboardButton("🔗 Set Channel", callback_data="set_chl"),
            InlineKeyboardButton("🔗 Set Group", callback_data="set_grl"),
            InlineKeyboardButton("🔙 Back", callback_data="adm_home")
        )
        bot.edit_message_text(text, cid, mid, reply_markup=markup, parse_mode="Markdown")
        
    elif act == "adm_home":
        admin_panel(call.message); bot.delete_message(cid, mid)

# --- Earn Setup Actions ---
@bot.callback_query_handler(func=lambda call: call.data in["set_reward", "set_minwth", "tog_withdraw"] and is_admin(call.message.chat.id))
def earn_actions(call):
    if call.data == "tog_withdraw":
        settings["withdraw_status"] = not settings["withdraw_status"]; save_json("settings.json", settings)
        bot.answer_callback_query(call.id, "Withdraw Status Changed!", show_alert=True)
    elif call.data == "set_reward":
        msg = bot.send_message(call.message.chat.id, "নতুন Reward Amount লিখুন (যেমন: 0.50):", reply_markup=back_menu())
        bot.register_next_step_handler(msg, process_reward)
    elif call.data == "set_minwth":
        msg = bot.send_message(call.message.chat.id, "বিকাশ, নগদ, রকেট এর মিনিমাম কমা দিয়ে লিখুন\n(যেমন: 50, 50, 50):", reply_markup=back_menu())
        bot.register_next_step_handler(msg, process_minwth)

def process_reward(m):
    if m.text == "🔙 Back to Home": return back_home(m)
    try:
        settings["reward_per_otp"] = float(m.text)
        save_json("settings.json", settings); bot.send_message(m.chat.id, "✅ Reward Update Success!", reply_markup=main_menu(m.chat.id))
    except: bot.send_message(m.chat.id, "❌ Error! শুধুমাত্র সংখ্যা দিন।", reply_markup=main_menu(m.chat.id))

def process_minwth(m):
    if m.text == "🔙 Back to Home": return back_home(m)
    try:
        parts =[int(x.strip()) for x in m.text.split(",")]
        if len(parts) >= 3:
            settings["min_withdraw"] = {"Bkash": parts[0], "Nagad": parts[1], "Rocket": parts[2]}
            save_json("settings.json", settings); bot.send_message(m.chat.id, "✅ Saved!", reply_markup=main_menu(m.chat.id))
        else:
            bot.send_message(m.chat.id, "❌ Error! ৩টি সংখ্যা কমা দিয়ে লিখুন।", reply_markup=main_menu(m.chat.id))
    except: bot.send_message(m.chat.id, "❌ Error! সঠিক ফরম্যাটে দিন।", reply_markup=main_menu(m.chat.id))

# --- Services Setup Actions (Specific Regex/Prefix Fix) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith(("del_srv", "del_cnt", "del_rng", "add_srv", "add_cnt", "add_rng")) and is_admin(call.message.chat.id))
def service_mutations(call):
    parts = call.data.split("_")
    act = parts[0] + "_" + parts[1]
    
    if act == "del_srv":
        del settings["services"][parts[2]]; save_json("settings.json", settings)
        bot.answer_callback_query(call.id, "Service Deleted!"); bot.delete_message(call.message.chat.id, call.message.message_id)
    elif act == "del_cnt":
        del settings["services"][parts[2]][parts[3]]; save_json("settings.json", settings)
        bot.answer_callback_query(call.id, "Country Deleted!"); bot.delete_message(call.message.chat.id, call.message.message_id)
    elif act == "add_srv":
        msg = bot.send_message(call.message.chat.id, "Service এর নাম লিখুন:", reply_markup=back_menu())
        bot.register_next_step_handler(msg, process_add_srv)
    elif act == "add_cnt":
        msg = bot.send_message(call.message.chat.id, "Code, Name, Flag কমা দিয়ে লিখুন\n(যেমন: BD, Bangladesh, 🇧🇩):", reply_markup=back_menu())
        bot.register_next_step_handler(msg, lambda m: process_add_cnt(m, parts[2]))
    elif act == "add_rng":
        msg = bot.send_message(call.message.chat.id, "Range লিখুন (যেমন: 88017):", reply_markup=back_menu())
        bot.register_next_step_handler(msg, lambda m: process_add_rng(m, parts[2], parts[3]))
    elif act == "del_rng":
        msg = bot.send_message(call.message.chat.id, "যে Range ডিলিট করবেন তা লিখুন:", reply_markup=back_menu())
        bot.register_next_step_handler(msg, lambda m: process_del_rng(m, parts[2], parts[3]))

def process_add_srv(m):
    if m.text == "🔙 Back to Home": return back_home(m)
    settings["services"][m.text.strip()] = {}
    save_json("settings.json", settings); bot.send_message(m.chat.id, "✅ Added!", reply_markup=main_menu(m.chat.id))

def process_add_cnt(m, srv):
    if m.text == "🔙 Back to Home": return back_home(m)
    try:
        args =[x.strip() for x in m.text.split(",")]
        cd, nm = args[0], args[1]
        fl = args[2] if len(args) > 2 else "🏳"
        settings["services"][srv][cd.upper()] = {"name": nm, "flag": fl, "ranges": {}}
        save_json("settings.json", settings); bot.send_message(m.chat.id, "✅ Added!", reply_markup=main_menu(m.chat.id))
    except: bot.send_message(m.chat.id, "❌ Error! সঠিক ফরম্যাটে দিন।", reply_markup=main_menu(m.chat.id))

def process_add_rng(m, srv, cnt):
    if m.text == "🔙 Back to Home": return back_home(m)
    settings["services"][srv][cnt]["ranges"][m.text.strip()] = {}
    save_json("settings.json", settings); bot.send_message(m.chat.id, "✅ Added!", reply_markup=main_menu(m.chat.id))

def process_del_rng(m, srv, cnt):
    if m.text == "🔙 Back to Home": return back_home(m)
    try:
        del settings["services"][srv][cnt]["ranges"][m.text.strip()]
        save_json("settings.json", settings); bot.send_message(m.chat.id, "✅ Deleted!", reply_markup=main_menu(m.chat.id))
    except: bot.send_message(m.chat.id, "❌ Not Found", reply_markup=main_menu(m.chat.id))

@bot.callback_query_handler(func=lambda call: call.data.startswith("eds_") and is_admin(call.message.chat.id))
def edit_srv(call):
    srv = call.data.split("_")[1]
    if srv not in settings["services"]: return bot.answer_callback_query(call.id, "Already deleted!")
    markup = InlineKeyboardMarkup(row_width=2)
    for cnt, data in settings["services"][srv].items(): markup.add(InlineKeyboardButton(f"{data['flag']} {data['name']}", callback_data=f"edc_{srv}_{cnt}"))
    markup.add(InlineKeyboardButton("➕ Add Country", callback_data=f"add_cnt_{srv}"), InlineKeyboardButton("🗑 Delete Service", callback_data=f"del_srv_{srv}"), InlineKeyboardButton("🔙 Back", callback_data="adm_srv"))
    bot.edit_message_text(f"⚙️ **Service:** {srv}", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("edc_") and is_admin(call.message.chat.id))
def edit_cnt(call):
    _, srv, cnt = call.data.split("_")
    data = settings["services"].get(srv, {}).get(cnt, {})
    if not data: return bot.answer_callback_query(call.id, "Not found!")
    markup = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("➕ Add Range", callback_data=f"add_rng_{srv}_{cnt}"),
        InlineKeyboardButton("🗑 Remove Range", callback_data=f"del_rng_{srv}_{cnt}"),
        InlineKeyboardButton("🗑 Delete Country", callback_data=f"del_cnt_{srv}_{cnt}"),
        InlineKeyboardButton("🔙 Back", callback_data=f"eds_{srv}")
    )
    bot.edit_message_text(f"🌍 **Country:** {data['flag']} {data['name']}\nRanges: {', '.join(data['ranges'].keys())}", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

# --- Sub Admin & Links Handlers ---
@bot.callback_query_handler(func=lambda call: call.data in["sub_add", "sub_rem", "set_chl", "set_grl"] and call.message.chat.id == ADMIN_ID)
def sub_admin_actions(call):
    act = call.data
    if act == "sub_add":
        msg = bot.send_message(call.message.chat.id, "নতুন সাব-এডমিনের Telegram ID দিন:", reply_markup=back_menu())
        bot.register_next_step_handler(msg, lambda m: process_sub_admin(m, True))
    elif act == "sub_rem":
        msg = bot.send_message(call.message.chat.id, "রিমুভ করতে এডমিনের Telegram ID দিন:", reply_markup=back_menu())
        bot.register_next_step_handler(msg, lambda m: process_sub_admin(m, False))
    elif act == "set_chl":
        msg = bot.send_message(call.message.chat.id, "Channel এর Chat ID দিন (যেমন: @channelname বা -100...):", reply_markup=back_menu())
        bot.register_next_step_handler(msg, lambda m: process_link_id(m, "channel"))
    elif act == "set_grl":
        msg = bot.send_message(call.message.chat.id, "Group এর Chat ID দিন (যেমন: -100...):", reply_markup=back_menu())
        bot.register_next_step_handler(msg, lambda m: process_link_id(m, "group"))

def process_sub_admin(m, is_add):
    if m.text == "🔙 Back to Home": return back_home(m)
    try:
        sub_id = int(m.text.strip())
        if is_add and sub_id not in settings["sub_admins"]: settings["sub_admins"].append(sub_id)
        elif not is_add and sub_id in settings["sub_admins"]: settings["sub_admins"].remove(sub_id)
        save_json("settings.json", settings); bot.send_message(m.chat.id, "✅ Done!", reply_markup=main_menu(m.chat.id))
    except: bot.send_message(m.chat.id, "❌ Error! শুধুমাত্র সংখ্যা দিন।", reply_markup=main_menu(m.chat.id))

def process_link_id(m, chat_type):
    if m.text == "🔙 Back to Home": return back_home(m)
    chat_id = m.text.strip()
    msg = bot.send_message(m.chat.id, f"এবার {chat_type.title()} এর Invite Link টি দিন:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, lambda mx: process_link_url(mx, chat_type, chat_id))

def process_link_url(m, chat_type, chat_id):
    if m.text == "🔙 Back to Home": return back_home(m)
    url = m.text.strip()
    if chat_type == "channel":
        settings["force_channel_id"] = chat_id
        settings["force_channel_url"] = url
    else:
        settings["force_group_id"] = chat_id
        settings["force_group_url"] = url
    save_json("settings.json", settings); bot.send_message(m.chat.id, "✅ Successfully Updated!", reply_markup=main_menu(m.chat.id))

# ================= USERS PANEL & EDIT BALANCE =================
@bot.message_handler(func=lambda m: m.text == "👥 Users" and is_admin(m.chat.id))
def users_panel(m):
    markup = InlineKeyboardMarkup().add(
        InlineKeyboardButton("📢 Broadcast", callback_data="do_broadcast"),
        InlineKeyboardButton("👤 Top Users (Edit Balance)", callback_data="view_users")
    )
    bot.send_message(m.chat.id, f"👥 **Total Users:** {len(users_db)}", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "view_users" and is_admin(call.message.chat.id))
def view_users(call):
    top_users = sorted(users_db.items(), key=lambda x: x[1].get('balance', 0), reverse=True)[:15]
    markup = InlineKeyboardMarkup(row_width=2)
    for uid, data in top_users:
        markup.add(InlineKeyboardButton(f"{data['first_name'][:10]} | ৳{data['balance']}", callback_data=f"edBal_{uid}"))
    bot.edit_message_text("👤 **Top Users**\nব্যালেন্স এডিট করতে বাটনে ক্লিক করুন:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("edBal_") and is_admin(call.message.chat.id))
def ask_new_balance(call):
    uid = call.data.split("_")[1]
    msg = bot.send_message(call.message.chat.id, f"User `{uid}` এর নতুন ব্যালেন্স লিখুন:", parse_mode="Markdown", reply_markup=back_menu())
    bot.register_next_step_handler(msg, lambda m: _save_balance(m, uid))

def _save_balance(m, uid):
    if m.text == "🔙 Back to Home": return back_home(m)
    try:
        users_db[uid]["balance"] = float(m.text)
        save_json("users.json", users_db); bot.send_message(m.chat.id, "✅ ব্যালেন্স আপডেট হয়েছে!", reply_markup=main_menu(m.chat.id))
    except: bot.send_message(m.chat.id, "❌ Error", reply_markup=main_menu(m.chat.id))

@bot.callback_query_handler(func=lambda call: call.data == "do_broadcast" and is_admin(call.message.chat.id))
def ask_broadcast(call):
    msg = bot.send_message(call.message.chat.id, "📢 ব্রডকাস্ট মেসেজ পাঠান:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(m):
    if m.text == "🔙 Back to Home": return back_home(m)
    bot.send_message(m.chat.id, "⏳ পাঠানো শুরু হয়েছে...")
    success = 0
    for uid in users_db.keys():
        try: bot.copy_message(chat_id=uid, from_chat_id=m.chat.id, message_id=m.message_id); success += 1
        except: pass
    bot.send_message(m.chat.id, f"✅ সফলভাবে {success} জনকে পাঠানো হয়েছে!", reply_markup=main_menu(m.chat.id))

# ================= BOT RUNNER =================
if __name__ == "__main__":
    refresh_jwt_token()
    threading.Thread(target=console_monitor_thread, daemon=True).start()
    threading.Thread(target=run_flask, daemon=True).start()
    
    print("✅ Bot is running properly!")
    while True:
        try: bot.infinity_polling(timeout=20, long_polling_timeout=15)
        except Exception as e: time.sleep(5)
