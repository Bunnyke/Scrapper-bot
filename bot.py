import re
import os
import asyncio
from aiogram import Bot, Dispatcher, types, executor
from pyrogram import Client

# ======= CONFIGURATION =======
BOT_TOKEN = "8149868870:AAEHI6JPA6DqTUfO9WvxssvEQzbx4mXQPJg"  # Replace with your BotFather token
api_id = "23925218"        # Replace with your api_id
api_hash = "396fd3b1c29a427df8cc6fb54f3d307c"    # Replace with your api_hash
phone_number = "+918123407093"  # Replace with your Telegram account phone

# ======= AIROGRAM/PYROGRAM SETUP =======
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
user_client = Client("my_account", api_id=api_id, api_hash=api_hash, phone_number=phone_number)
scrape_queue = asyncio.Queue()

# ======= CARD TYPE BIN MAPPING =======
CARD_TYPE_BINS = {
    "amex": ["34", "37"],  # 15 digits
    "americanexpress": ["34", "37"],
    "visa": ["4"],         # 13,16,19 digits
    "mastercard": ["51", "52", "53", "54", "55"] + [str(i) for i in range(2221, 2721)],
    "discover": ["6011", "65"] + [str(i) for i in range(644, 650)],
}

def match_card_type(card_number, card_type):
    card_type = card_type.lower()
    if card_type in CARD_TYPE_BINS:
        for bin_prefix in CARD_TYPE_BINS[card_type]:
            if card_number.startswith(bin_prefix):
                length = len(card_number)
                if card_type in ["amex", "americanexpress"] and length == 15:
                    return True
                elif card_type == "visa" and length in [13, 16, 19]:
                    return True
                elif card_type in ["mastercard", "discover"] and length == 16:
                    return True
        return False
    elif card_type.isdigit():
        return card_number.startswith(card_type)
    return False

def remove_duplicates(messages):
    unique_messages = list(set(messages))
    duplicates_removed = len(messages) - len(unique_messages)
    return unique_messages, duplicates_removed

async def scrape_messages(user_client, channel_username, limit, start_number=None, card_filter=None):
    messages = []
    count = 0
    pattern = r'\d{13,19}\D*\d{2}\D*\d{2,4}\D*\d{3,4}'

    async for message in user_client.search_messages(channel_username):
        if count >= limit:
            break
        text = message.text if message.text else message.caption
        if text:
            matched_messages = re.findall(pattern, text)
            for matched_message in matched_messages:
                extracted_values = re.findall(r'\d+', matched_message)
                if len(extracted_values) >= 4:
                    card_number, mo, year, cvv = extracted_values[:4]
                    year = year[-2:]
                    if card_filter:
                        if not match_card_type(card_number, card_filter):
                            continue
                    if start_number:
                        if not card_number.startswith(start_number):
                            continue
                    formatted = f"{card_number}|{mo}|{year}|{cvv}"
                    messages.append(formatted)
                    count += 1
                    if count >= limit:
                        break
    messages = messages[:limit]
    return messages

async def process_scrape_queue(user_client, bot):
    while True:
        task = await scrape_queue.get()
        if len(task) == 5:
            message, channel_username, limit, start_number, temporary_msg = task
            card_filter = None
        else:
            message, channel_username, limit, start_number, temporary_msg, card_filter = task

        try:
            scrapped_results = await scrape_messages(user_client, channel_username, limit, start_number, card_filter)
        except Exception as e:
            await temporary_msg.delete()
            await bot.send_message(message.chat.id, f"❌ Scraping error: {str(e)}")
            scrape_queue.task_done()
            continue

        if scrapped_results:
            unique_messages, duplicates_removed = remove_duplicates(scrapped_results)
            if unique_messages:
                file_name = f"x{len(unique_messages)}_{channel_username}.txt"
                with open(file_name, 'w') as f:
                    f.write("\n".join(unique_messages))

                with open(file_name, 'rb') as f:
                    caption = (
                        f"<b>CC Scrapped Successful ✅</b>\n"
                        f"<b>━━━━━━━━━━━━━━━━</b>\n"
                        f"<b>Source:</b> <code>{channel_username}</code>\n"
                        f"<b>Amount:</b> <code>{len(unique_messages)}</code>\n"
                        f"<b>Duplicates Removed:</b> <code>{duplicates_removed}</code>\n"
                        f"<b>━━━━━━━━━━━━━━━━</b>\n"
                        f"<b>Card-Scrapper By: <a href='https://t.me/ApprovedScrapper1'>𝙱𝚞𝚗𝚗𝚢</a></b>\n"
                    )
                    await temporary_msg.delete()
                    await bot.send_document(message.chat.id, f, caption=caption, parse_mode='html')
                os.remove(file_name)
            else:
                await temporary_msg.delete()
                await bot.send_message(message.chat.id, "Sorry Bro ❌ No Credit Card Found")
        else:
            await temporary_msg.delete()
            await bot.send_message(message.chat.id, "Sorry Bro ❌ No Credit Card Found")

        scrape_queue.task_done()

def parse_channel_identifier(channel_identifier):
    channel_identifier = channel_identifier.strip()
    if channel_identifier.startswith("https://t.me/"):
        id_part = channel_identifier.replace("https://t.me/", "")
        if id_part.startswith("joinchat/") or id_part.startswith("+"):
            return channel_identifier
        id_part = id_part.lstrip("@")
        return id_part
    if channel_identifier.startswith("@"):
        return channel_identifier[1:]
    if channel_identifier.isdigit():
        return int(channel_identifier)
    if channel_identifier.startswith("joinchat/") or channel_identifier.startswith("+"):
        return "https://t.me/" + channel_identifier
    return channel_identifier

async def ensure_joined(user_client, channel_identifier):
    try:
        if (str(channel_identifier).startswith("https://t.me/joinchat/") or
            str(channel_identifier).startswith("https://t.me/+")):
            try:
                chat = await user_client.join_chat(channel_identifier)
                return chat.id
            except Exception as e:
                if "USER_ALREADY_PARTICIPANT" in str(e):
                    chat = await user_client.get_chat(channel_identifier)
                    return chat.id
                else:
                    raise e
        chat = await user_client.get_chat(channel_identifier)
        return chat.id if hasattr(chat, "id") else channel_identifier
    except Exception as e:
        raise e

def get_help_message():
    return (
        "<b>Welcome! Available Commands:\n"
        "Usage: /scr &lt;channel|user_id|link&gt; &lt;amount&gt; [card_type|BIN]\n"
        "Examples:\n"
        "/scr @examplechannel 100 AmericanExpress\n"
        "/scr 1234567890 50 Visa\n"
        "/scr https://t.me/examplechannel 20 4\n"
        "/scr https://t.me/joinchat/XXXXXXXXXXX 50\n"
        "More tools & gateways coming soon!\n"
        "\nMax scrape amount per request: 50,000\n"
        "Total commands: 2 (/scr and /cmds)</b>"
    )

@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    await bot.send_message(message.chat.id, get_help_message(), parse_mode='html')

@dp.message_handler(commands=['cmds'])
async def cmds_cmd(message: types.Message):
    await bot.send_message(message.chat.id, get_help_message(), parse_mode='html')

@dp.message_handler(commands=['scr'])
async def scr_cmd(message: types.Message):
    args = message.text.split()[1:]
    if len(args) < 2:
        await bot.send_message(
            message.chat.id,
            "<b>Usage: /scr &lt;channel|user_id|link&gt; &lt;amount&gt; [card_type|BIN]</b>",
            parse_mode='html'
        )
        return

    channel_identifier = args[0]
    try:
        limit = int(args[1])
    except Exception:
        await bot.send_message(
            message.chat.id,
            "<b>Invalid amount. Must be a number.</b>",
            parse_mode='html'
        )
        return

    card_filter = args[2] if len(args) >= 3 else None

    max_lim = 50000
    if limit > max_lim:
        await bot.send_message(
            message.chat.id,
            f"<b>Sorry Bro! Amount over Max limit is {max_lim} ❌</b>",
            parse_mode='html'
        )
        return

    channel_username = parse_channel_identifier(channel_identifier)

    try:
        real_channel_id = await ensure_joined(user_client, channel_username)
    except Exception as e:
        await bot.send_message(
            message.chat.id,
            f"<b>Hey Bro! 🥲 Can't access this channel/group/link!<br><code>{str(e)}</code></b>",
            parse_mode='html'
        )
        return

    temporary_msg = await bot.send_message(message.chat.id, "<b>Scraping in progress wait.....</b>", parse_mode='html')
    await scrape_queue.put((message, channel_username, limit, None, temporary_msg, card_filter))

@dp.message_handler()
async def reply_with_commands(message: types.Message):
    await bot.send_message(message.chat.id, get_help_message(), parse_mode='html')

async def on_startup(dp):
    await user_client.start()
    for _ in range(5):  # Adjust number of workers as you like
        asyncio.create_task(process_scrape_queue(user_client, bot))

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
