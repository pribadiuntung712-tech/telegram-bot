import os
import json
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN", "").strip()
DATA_FILE = "bot_data.json"
CONFIG_FILE = "config.json"

# =========================================================================
# 📌 BACA CONFIG.JSON (MAPPING PASANGAN GRUP STAFF <-> VENDOR)
# =========================================================================
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
                return cfg.get("GROUP_PAIRS", {})
        except Exception as e:
            logger.error(f"Gagal membaca {CONFIG_FILE}: {e}")
    return {}

# 📌 DAFTAR PEMETAAN USERNAME -> NAME TAG (Gunakan huruf kecil)
USER_NAME_TAGS = {
    "@lubu_hiat": "LUBU PAKAM",
    "@zkyy07": "ADS",
    "@max77kix": "MAX",
    "@tiliqua_gigas": "TILIQUA_AG",
}

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"known_groups": {}, "active_target": {}, "vendor_links": {}, "messages": {}}
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            data.setdefault("known_groups", {})
            data.setdefault("active_target", {})
            data.setdefault("vendor_links", {})
            data.setdefault("messages", {})
            return data
    except Exception:
        return {"known_groups": {}, "active_target": {}, "vendor_links": {}, "messages": {}}

def save_data(data):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Gagal simpan DB: {e}")

async def is_admin(bot, chat_id, user_id):
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except Exception:
        return False

def is_staff_group(title):
    return "STAFF" in (title or "").upper()

def clean_mentions_from_message(message):
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []

    if not text:
        return ""

    mention_entities = [
        e for e in entities if e.type in ["mention", "text_mention"]
    ]
    mention_entities.sort(key=lambda x: x.offset, reverse=True)

    text_list = list(text)
    for ent in mention_entities:
        start = ent.offset
        end = ent.offset + ent.length
        del text_list[start:end]

    cleaned_text = "".join(text_list)
    cleaned_text = re.sub(r'@[^\s]+', '', cleaned_text)
    cleaned_text = re.sub(r' +', ' ', cleaned_text).strip()

    return cleaned_text

def silent_register_group(chat):
    if chat.type in ['group', 'supergroup']:
        data = load_data()
        data["known_groups"][str(chat.id)] = chat.title or f"Grup {chat.id}"
        save_data(data)

# Perintah Cek ID Grup
async def get_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await update.message.reply_text(f"📌 **ID Grup ini:** `{chat.id}`\n**Judul:** {chat.title}", parse_mode="Markdown")

async def render_main_menu(update_or_query, context, chat, user, is_edit=False):
    silent_register_group(chat)
    
    if not is_staff_group(chat.title):
        text = "⛔ Menu ini hanya dapat diakses di Grup Staff!"
        if is_edit:
            await update_or_query.message.edit_text(text)
        else:
            await update_or_query.message.reply_text(text)
        return

    data = load_data()
    chat_id_str = str(chat.id)
    
    current_target_id = data["active_target"].get(chat_id_str)
    current_target_name = data["known_groups"].get(current_target_id, "Belum Dipilih") if current_target_id else "Belum Dipilih"

    text = (
        f"🏠 **TAMPILAN UTAMA STAFF HUB**\n\n"
        f"📍 **Grup Ini:** {chat.title}\n"
        f"💬 **Target Percakapan Aktif:** **{current_target_name}**\n\n"
        f"Silakan pilih grup vendor di bawah untuk berpindah percakapan:"
    )

    keyboard = []
    has_vendor = False
    for g_id, g_title in data["known_groups"].items():
        if not is_staff_group(g_title) and g_id != chat_id_str:
            has_vendor = True
            prefix = "✅ " if g_id == current_target_id else "📌 "
            keyboard.append([
                InlineKeyboardButton(f"{prefix}{g_title}", callback_data=f"switch_{g_id}")
            ])

    if not has_vendor:
        text = (
            "⚠️ **Belum ada grup vendor yang terdeteksi!**\n\n"
            "**Cara Menambah Vendor:**\n"
            "Masukkan bot ini ke grup vendor & jadikan Admin."
        )

    keyboard.append([InlineKeyboardButton("🔄 Refresh Tampilan Utama", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if is_edit:
        await update_or_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update_or_query.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    silent_register_group(chat)

    if is_staff_group(chat.title):
        keyboard = [[InlineKeyboardButton("🏠 Tampilan Utama (/menu)", callback_data="main_menu")]]
        await update.message.reply_text(
            f"Bot Staff Hub aktif di **{chat.title}**.\n\n"
            "Gunakan perintah `/menu` atau tombol di bawah untuk memilih tujuan percakapan.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if not is_staff_group(chat.title):
        return

    if not await is_admin(context.bot, chat.id, user.id):
        await update.message.reply_text("⛔ Hanya Admin Staff yang dapat mengakses menu!")
        return

    await render_main_menu(update, context, chat, user, is_edit=False)

async def reset_groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if not is_staff_group(chat.title) or not await is_admin(context.bot, chat.id, user.id):
        return

    data = load_data()
    data["known_groups"] = {str(chat.id): chat.title or f"Grup {chat.id}"}
    data["active_target"] = {}
    data["vendor_links"] = {}
    save_data(data)

    keyboard = [[InlineKeyboardButton("🏠 Kembali ke Tampilan Utama", callback_data="main_menu")]]
    await update.message.reply_text(
        "🧹 **Daftar grup berhasil dibersihkan!**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    data_code = query.data

    silent_register_group(chat)

    if data_code == "main_menu":
        if not is_staff_group(chat.title):
            await query.answer("⛔ Hanya berlaku di Grup Staff!", show_alert=True)
            return
        await query.answer()
        await render_main_menu(query, context, chat, user, is_edit=True)
        return

    if data_code.startswith("switch_"):
        if not is_staff_group(chat.title):
            await query.answer("⛔ Hanya berlaku di Grup Staff!", show_alert=True)
            return

        target_id = data_code.replace("switch_", "", 1)
        data = load_data()
        
        data["active_target"][str(chat.id)] = str(target_id)
        data["vendor_links"][str(target_id)] = str(chat.id)
        save_data(data)

        target_name = data["known_groups"].get(target_id, "Grup Vendor")
        await query.answer(f"✅ Berhasil gabung percakapan dengan: {target_name}", show_alert=True)
        
        if query.message.text and "TAMPILAN UTAMA" in query.message.text:
            await render_main_menu(query, context, chat, user, is_edit=True)
        else:
            keyboard = [[InlineKeyboardButton("🏠 Kembali ke Tampilan Utama", callback_data="main_menu")]]
            await query.message.reply_text(
                f"🟢 **BERHASIL GABUNG PERCAKAPAN**\n\n"
                f"Sekarang pesan yang Anda ketik di grup staff ini akan langsung terkirim ke **{target_name}**.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        return

    if data_code.startswith("info_"):
        msg_key = data_code[5:]
        data = load_data()
        msg_info = data["messages"].get(f"info_{msg_key}")

        if not await is_admin(context.bot, chat.id, user.id):
            await query.answer("⛔ Hanya Admin yang dapat melihat info pengirim.", show_alert=True)
            return

        if msg_info:
            info_text = (
                f"👤 DETAIL PENGIRIM\n\n"
                f"• Nama: {msg_info.get('sender_name')}\n"
                f"• User ID: {msg_info.get('sender_id')}\n"
                f"• Username: @{msg_info.get('sender_username')}\n"
                f"• Asal Grup: {msg_info.get('from_chat_title')}"
            )
            await query.answer(info_text, show_alert=True)
        else:
            await query.answer("ℹ️ Informasi pengirim tidak ditemukan di database.", show_alert=True)

async def noop_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or (update.message.text and update.message.text.startswith('/')):
        return

    chat = update.effective_chat
    silent_register_group(chat)

    chat_id_str = str(chat.id)
    message_id = update.message.message_id
    user = update.effective_user
    chat_title = chat.title or "Grup"

    data = load_data()
    pairs = load_config()

    target_chat_id = None
    reply_to_target_msg_id = None

    # 1. Prioritas Balasan (Reply)
    if update.message.reply_to_message:
        replied_msg_id = update.message.reply_to_message.message_id
        target_chat_id = data["messages"].get(f"origin_chat_{chat_id_str}_{replied_msg_id}")
        reply_to_target_msg_id = data["messages"].get(f"map_{chat_id_str}_{replied_msg_id}")

    # 2. Cari dari config.json (jika ada pemetaan spesifik)
    if not target_chat_id:
        if chat_id_str in pairs:
            target_chat_id = pairs[chat_id_str]
        else:
            for staff_id, vendor_id in pairs.items():
                if vendor_id == chat_id_str:
                    target_chat_id = staff_id
                    break

    # 3. Mode Dinamis (Gunakan active_target jika tidak ada di config.json)
    is_from_staff = is_staff_group(chat_title)
    if not target_chat_id:
        if is_from_staff:
            target_chat_id = data["active_target"].get(chat_id_str)
        else:
            target_chat_id = data["vendor_links"].get(chat_id_str)

    if not target_chat_id:
        if is_from_staff:
            keyboard = [[InlineKeyboardButton("🏠 Tampilan Utama", callback_data="main_menu")]]
            await update.message.reply_text(
                "⚠️ **Target vendor belum dipilih!**\n\n"
                "Klik tombol di bawah untuk memilih vendor yang ingin diajak percakapan.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        return

    try:
        msg_key = f"{chat_id_str}_{message_id}"
        sender_name = user.full_name or user.first_name or "Pengirim"
        username_key = f"@{user.username.lower()}" if user.username else ""
        name_tag = USER_NAME_TAGS.get(username_key, "-")

        header_block = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Pengirim : {sender_name}\n"
            f"🏷 Name Tag  : {name_tag}\n"
            f"📍 Asal Grup : {chat_title}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
        )

        if not is_from_staff:
            # DARI VENDOR KE STAFF
            keyboard_buttons = [
                [InlineKeyboardButton(f"📍 Vendor: {chat_title}", callback_data="noop")],
                [
                    InlineKeyboardButton("💬 Gabung Percakapan", callback_data=f"switch_{chat_id_str}"),
                    InlineKeyboardButton("👤 Info Pengirim", callback_data=f"info_{msg_key}")
                ],
                [InlineKeyboardButton("🏠 Tampilan Utama", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard_buttons)

            clean_text = clean_mentions_from_message(update.message)
            full_text = f"{header_block}{clean_text}"

            if update.message.text:
                sent_msg = await context.bot.send_message(
                    chat_id=int(target_chat_id),
                    text=full_text,
                    reply_to_message_id=reply_to_target_msg_id,
                    reply_markup=reply_markup
                )
            elif update.message.photo:
                photo_file_id = update.message.photo[-1].file_id
                sent_msg = await context.bot.send_photo(
                    chat_id=int(target_chat_id),
                    photo=photo_file_id,
                    caption=full_text,
                    reply_to_message_id=reply_to_target_msg_id,
                    reply_markup=reply_markup
                )
            elif update.message.document:
                doc_file_id = update.message.document.file_id
                sent_msg = await context.bot.send_document(
                    chat_id=int(target_chat_id),
                    document=doc_file_id,
                    caption=full_text,
                    reply_to_message_id=reply_to_target_msg_id,
                    reply_markup=reply_markup
                )
            else:
                sent_msg = await context.bot.copy_message(
                    chat_id=int(target_chat_id),
                    from_chat_id=int(chat_id_str),
                    message_id=message_id,
                    reply_to_message_id=reply_to_target_msg_id,
                    reply_markup=reply_markup
                )

        else:
            # DARI STAFF KE VENDOR (Pesan Polos)
            sent_msg = await context.bot.copy_message(
                chat_id=int(target_chat_id),
                from_chat_id=int(chat_id_str),
                message_id=message_id,
                reply_to_message_id=reply_to_target_msg_id,
                reply_markup=None
            )

        data["messages"][f"info_{msg_key}"] = {
            "sender_name": user.full_name,
            "sender_id": user.id,
            "sender_username": user.username or "-",
            "from_chat_title": chat_title
        }
        
        data["messages"][f"origin_chat_{target_chat_id}_{sent_msg.message_id}"] = chat_id_str
        data["messages"][f"map_{target_chat_id}_{sent_msg.message_id}"] = message_id
        data["messages"][f"map_{chat_id_str}_{message_id}"] = sent_msg.message_id

        save_data(data)

    except Exception as e:
        if is_from_staff:
            await update.message.reply_text(
                f"❌ **GAGAL MENGIRIM PESAN!**\nError: `{e}`",
                parse_mode="Markdown"
            )

def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN belum diisi di Environment Variables!")
    
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("id", get_id_command))
    app.add_handler(CommandHandler("resetgrup", reset_groups_command))
    app.add_handler(CallbackQueryHandler(noop_click, pattern="^noop$"))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    logger.info("Bot Staff Hub Berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
