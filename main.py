import telebot
import os
import re
import requests
import locale
import logging
import urllib.parse
import json
import phonenumbers


from amocrm.v2 import Lead, custom_field, tokens, Contact
from io import BytesIO
from telebot import types
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs
from utils import (
    generate_encar_photo_url,
    clean_number,
    get_customs_fees,
    calculate_age,
    format_number,
)


CALCULATE_CAR_TEXT = "Расчёт по ссылке"
DEALER_COMMISSION = 0.02  # 2%

PROXY_URL = "http://B01vby:GBno0x@45.118.250.2:8000"
proxies = {"http": PROXY_URL, "https": PROXY_URL}


# Настройка БД
DATABASE_URL = "postgres://uea5qru3fhjlj:p44343a46d4f1882a5ba2413935c9b9f0c284e6e759a34cf9569444d16832d4fe@c97r84s7psuajm.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/d9pr93olpfl9bj"


# Configure logging
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Load keys from .env file
load_dotenv()
bot_token = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(bot_token)

# Set locale for number formatting
locale.setlocale(locale.LC_ALL, "en_US.UTF-8")

# Storage for the last error message ID
last_error_message_id = {}

# global variables
car_data = {}
car_id_external = ""
total_car_price = 0
usdt_krw_rate = 0
usdt_rub_rate = 0
usd_rate = 0
users = set()

admins = []
CHANNEL_USERNAME = "@mdmgroupkorea"  # Юзернейм канала

car_month = None
car_year = None

vehicle_id = None
vehicle_no = None

# Глобальные переменные для сбора данных пользователя
user_data = {}


def is_valid_phone(phone):
    try:
        parsed = phonenumbers.parse(phone, None)
        return phonenumbers.is_possible_number(parsed) and phonenumbers.is_valid_number(
            parsed
        )
    except phonenumbers.NumberParseException:
        return False


def print_message(message):
    print("\n\n##############")
    print(f"{message}")
    print("##############\n\n")
    return None


def is_subscribed(user_id):
    try:
        chat_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"Ошибка при проверке подписки: {e}")
        return False  # Если ошибка, считаем, что не подписан


# Функция для установки команд меню
def set_bot_commands():
    commands = [
        types.BotCommand("start", "Запустить бота"),
        types.BotCommand("cbr", "Курсы валют"),
        # types.BotCommand("stats", "Статистика"),
    ]
    bot.set_my_commands(commands)


def get_usdt_to_rub_rate():
    global usdt_rub_rate

    url = "https://api.coinbase.com/v2/prices/USDT-RUB/spot"

    try:
        response = requests.get(url)
        response.raise_for_status()  # Проверяем, что запрос успешный (код 200)
        data = response.json()

        # Получаем курс USDT к рублю из ответа
        usdt_rub_rate = float(data["data"]["amount"])

        # Округляем до двух знаков после запятой и добавляем 2 рубля
        usdt_rub_rate = round(usdt_rub_rate, 2) + 2

        # Вычисляем курс рубля к воне через курс USDT

        print_message(f"Курс USDT-RUB: {usdt_rub_rate} ₽")

    except requests.RequestException as e:
        print_message(f"Ошибка при получении курса: {e}")
        return None


# Функция для получения курсов валют с API
def get_currency_rates():
    global usd_rate, usdt_krw_rate

    print_message("ПОЛУЧАЕМ КУРС USDT/KRW")

    # Получаем курс USDT/KRW с Naver
    try:
        usdt_krw_url = "https://search.naver.com/search.naver?sm=tab_hty.top&where=nexearch&ssc=tab.nx.all&query=USDT"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        naver_response = requests.get(usdt_krw_url, headers=headers)

        # Используем BeautifulSoup для парсинга HTML
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(naver_response.text, "html.parser")

        # Извлекаем значение курса из strong.price
        price_element = soup.select_one("strong.price em")
        if price_element:
            krw_rate_text = price_element.text.strip().replace(",", "")
            krw = float(krw_rate_text) - 10

            # Устанавливаем глобальные переменные
            usd_rate = 1.0  # USDT курс к доллару 1:1
            usdt_krw_rate = krw

            rates_text = f"USDT/KRW: <b>{krw:.2f} ₩</b>"
            return rates_text
        else:
            print_message("Не удалось получить курс USDT/KRW с Naver")
            return "Не удалось получить курс USDT/KRW"
    except Exception as e:
        print_message(f"Ошибка при получении курса USDT/KRW: {e}")
        return "Ошибка при получении курса валют"


# Обработчик команды /cbr
@bot.message_handler(commands=["cbr"])
def cbr_command(message):
    global usdt_rub_rate

    user_id = message.from_user.id

    if not is_subscribed(user_id):
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "🔗 Подписаться", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "🔄 Проверить подписку", callback_data="check_subscription"
            )
        )

        bot.send_message(
            message.chat.id,
            f"🚫 Доступ ограничен! Подпишитесь на наш канал {CHANNEL_USERNAME}, чтобы пользоваться ботом.",
            reply_markup=keyboard,
        )
        return  # Прерываем выполнение, если не подписан

    try:
        rates_text = get_currency_rates()

        # Получаем курс USDT/RUB
        try:
            get_usdt_to_rub_rate()
            rates_text += f"\nUSDT/RUB: <b>{usdt_rub_rate:.2f} ₽</b>"
        except Exception as e:
            print_message(f"Ошибка при получении курса USDT/RUB: {e}")
            rates_text += "\nНе удалось получить курс USDT/RUB"

        # Создаем клавиатуру с кнопкой для расчета автомобиля
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "Рассчитать стоимость автомобиля", callback_data="calculate_another"
            )
        )

        # Отправляем сообщение с курсами и клавиатурой
        bot.send_message(
            message.chat.id, rates_text, reply_markup=keyboard, parse_mode="HTML"
        )
    except Exception as e:
        bot.send_message(
            message.chat.id, "Не удалось получить курсы валют. Попробуйте позже."
        )
        print(f"Ошибка при получении курсов валют: {e}")


# Main menu creation function
def main_menu():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    keyboard.add(
        types.KeyboardButton(CALCULATE_CAR_TEXT), types.KeyboardButton("Ручной расчёт")
    )
    keyboard.add(
        types.KeyboardButton("Написать менеджеру"),
        types.KeyboardButton("О нас"),
        types.KeyboardButton("Telegram-канал"),
        types.KeyboardButton("Instagram"),
        types.KeyboardButton("Tik-Tok"),
    )
    return keyboard


@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def check_subscription(call):
    user_id = call.from_user.id

    if is_subscribed(user_id):
        bot.answer_callback_query(call.id, "✅ Вы подписаны!")
        bot.send_message(
            call.message.chat.id,
            "✅ Спасибо за подписку! Теперь вы можете пользоваться ботом.",
            reply_markup=main_menu(),
        )
    else:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "🔗 Подписаться", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "🔄 Проверить подписку", callback_data="check_subscription"
            )
        )

        bot.send_message(
            call.message.chat.id,
            "🚫 Вы ещё не подписались! Подпишитесь и нажмите кнопку 🔄 Проверить подписку.",
            reply_markup=keyboard,
        )


# Start command handler
@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.from_user.id

    if not is_subscribed(user_id):
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "🔗 Подписаться", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "🔄 Проверить подписку", callback_data="check_subscription"
            )
        )

        bot.send_message(
            message.chat.id,
            f"🚫 Доступ ограничен! Подпишитесь на наш канал {CHANNEL_USERNAME}, чтобы пользоваться ботом.",
            reply_markup=keyboard,
        )
        return  # Прерываем выполнение, если не подписан

    get_currency_rates()

    # Отправляем приветственное видео
    video_url = "https://res.cloudinary.com/dazj4gjli/video/upload/v1744443895/IMG_9266_guzqka.mp4"
    bot.send_video(message.chat.id, video_url)

    user_first_name = message.from_user.first_name
    welcome_message = (
        f"Здравствуйте, {user_first_name}!\n\n"
        "Я бот компании MDM GROUP. Я помогу вам рассчитать стоимость понравившегося вам автомобиля из Южной Кореи до Владивостока.\n\n"
        "Выберите действие из меню ниже."
    )
    bot.send_message(message.chat.id, welcome_message, reply_markup=main_menu())


# Error handling function
def send_error_message(message, error_text):
    global last_error_message_id

    # Remove previous error message if it exists
    if last_error_message_id.get(message.chat.id):
        try:
            bot.delete_message(message.chat.id, last_error_message_id[message.chat.id])
        except Exception as e:
            logging.error(f"Error deleting message: {e}")

    # Send new error message and store its ID
    error_message = bot.reply_to(message, error_text, reply_markup=main_menu())
    last_error_message_id[message.chat.id] = error_message.id
    logging.error(f"Error sent to user {message.chat.id}: {error_text}")


def get_car_info(url):
    global car_id_external, vehicle_no, vehicle_id, car_year, car_month

    # driver = create_driver()

    car_id_match = re.findall(r"\d+", url)
    car_id = car_id_match[0]
    car_id_external = car_id

    url = f"https://api.encar.com/v1/readside/vehicle/{car_id}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "http://www.encar.com/",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
    }

    response = requests.get(url, headers=headers).json()

    # Информация об автомобиле
    car_make = response["category"]["manufacturerEnglishName"]  # Марка
    car_model = response["category"]["modelGroupEnglishName"]  # Модель
    car_trim = response["category"]["gradeDetailEnglishName"] or ""  # Комплектация

    car_title = f"{car_make} {car_model} {car_trim}"  # Заголовок

    # Получаем все необходимые данные по автомобилю
    car_price = str(response["advertisement"]["price"])
    car_date = response["category"]["yearMonth"]
    year = car_date[2:4]
    month = car_date[4:]
    car_year = year
    car_month = month

    # Пробег (форматирование)
    mileage = response["spec"]["mileage"]
    formatted_mileage = f"{mileage:,} км"

    # Тип КПП
    transmission = response["spec"]["transmissionName"]
    formatted_transmission = "Автомат" if "오토" in transmission else "Механика"

    car_engine_displacement = str(response["spec"]["displacement"])
    car_type = response["spec"]["bodyName"]

    # Список фотографий (берем первые 10)
    car_photos = [
        generate_encar_photo_url(photo["path"]) for photo in response["photos"][:10]
    ]
    car_photos = [url for url in car_photos if url]

    # Дополнительные данные
    vehicle_no = response["vehicleNo"]
    vehicle_id = response["vehicleId"]

    # Форматируем
    formatted_car_date = f"01{month}{year}"
    formatted_car_type = "crossover" if car_type == "SUV" else "sedan"

    print_message(
        f"ID: {car_id}\nType: {formatted_car_type}\nDate: {formatted_car_date}\nCar Engine Displacement: {car_engine_displacement}\nPrice: {car_price} KRW"
    )

    return [
        car_price,
        car_engine_displacement,
        formatted_car_date,
        car_title,
        formatted_mileage,
        formatted_transmission,
        car_photos,
        year,
        month,
    ]


# Function to calculate the total cost
def calculate_cost(link, message):
    global car_data, car_id_external, car_month, car_year, usdt_krw_rate, usdt_rub_rate, usd_rate

    print_message("ЗАПРОС НА РАСЧЁТ АВТОМОБИЛЯ")

    # Получаем актуальный курс валют
    get_usdt_to_rub_rate()
    get_currency_rates()

    # Отправляем сообщение и сохраняем его ID
    processing_message = bot.send_message(
        message.chat.id, "Обрабатываю данные. Пожалуйста подождите ⏳"
    )

    car_id = None

    # Проверка ссылки на мобильную версию
    if "fem.encar.com" in link:
        car_id_match = re.findall(r"\d+", link)
        if car_id_match:
            car_id = car_id_match[0]  # Use the first match of digits
            car_id_external = car_id
            link = f"https://fem.encar.com/cars/detail/{car_id}"
        else:
            send_error_message(message, "🚫 Не удалось извлечь carid из ссылки.")
            return
    else:
        # Извлекаем carid с URL encar
        parsed_url = urlparse(link)
        query_params = parse_qs(parsed_url.query)
        car_id = query_params.get("carid", [None])[0]

    result = get_car_info(link)
    (
        car_price,
        car_engine_displacement,
        formatted_car_date,
        car_title,
        formatted_mileage,
        formatted_transmission,
        car_photos,
        year,
        month,
    ) = result

    if not car_price and car_engine_displacement and formatted_car_date:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "Оставить заявку",
                callback_data="add_crm_deal",
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Рассчитать стоимость другого автомобиля",
                callback_data="calculate_another",
            )
        )
        bot.send_message(
            message.chat.id, "Ошибка", parse_mode="Markdown", reply_markup=keyboard
        )
        bot.delete_message(message.chat.id, processing_message.message_id)
        return

    # Если есть новая ссылка
    if car_price and car_engine_displacement and formatted_car_date:
        car_engine_displacement = int(car_engine_displacement)

        # Форматирование данных
        formatted_car_year = f"20{car_year}"
        engine_volume_formatted = f"{format_number(car_engine_displacement)} cc"
        age = calculate_age(int(formatted_car_year), car_month)

        age_formatted = (
            "до 3 лет"
            if age == "0-3"
            else (
                "от 3 до 5 лет"
                if age == "3-5"
                else "от 5 до 7 лет" if age == "5-7" else "от 7 лет"
            )
        )

        # Конвертируем стоимость авто в рубли
        price_krw = int(car_price) * 10000
        price_usdt = int(price_krw) / usdt_krw_rate
        price_rub = int(price_usdt) * usdt_rub_rate

        response = get_customs_fees(
            car_engine_displacement,
            price_krw,
            int(f"20{car_year}"),
            car_month,
            engine_type=1,
        )

        # Таможенный сбор
        customs_fee = clean_number(response["sbor"])
        customs_duty = clean_number(response["tax"])
        recycling_fee = clean_number(response["util"])

        # Расчет итоговой стоимости автомобиля в рублях
        total_cost = (
            price_rub  # Стоимость автомобиля в рублях
            + customs_fee  # Таможенный сбор
            + customs_duty  # Таможенная пошлина
            + recycling_fee  # Утилизационный сбор
            + 100000  # ФРАХТ
            + 100000  # Брокерские услуги
        )

        car_data["freight_rub"] = 100000
        car_data["freight_usdt"] = 1000

        car_data["broker_rub"] = 100000
        car_data["broker_usdt"] = 100000 / usdt_rub_rate

        car_data["customs_fee_rub"] = customs_fee
        car_data["customs_fee_usdt"] = customs_fee / usdt_rub_rate

        car_data["customs_duty_rub"] = customs_duty
        car_data["customs_duty_usdt"] = customs_duty / usdt_rub_rate

        car_data["util_fee_rub"] = recycling_fee
        car_data["util_fee_usdt"] = recycling_fee / usdt_rub_rate

        preview_link = f"https://fem.encar.com/cars/detail/{car_id}"

        # Формирование сообщения результата
        result_message = (
            f"🚗 <b>{car_title}</b>\n\n"
            f"📅 Возраст: {age_formatted} (дата регистрации: {month}/{year})\n"
            f"🛣️ Пробег: {formatted_mileage}\n"
            f"🔧 Объём двигателя: {engine_volume_formatted}\n"
            f"⚙️ КПП: {formatted_transmission}\n\n"
            f"💱 Актуальные курсы валют:\nUSDT/KRW: <b>₩{usdt_krw_rate:.2f}</b>\nUSDT/RUB: <b>{usdt_rub_rate:.2f} ₽</b>\n\n"
            f"💰 <b>Стоимость:</b>\n"
            f"• Цена авто:\n₩<b>{format_number(price_krw)}</b> | <b>{format_number(price_rub)}</b> ₽\n\n"
            f"• ФРАХТ:\n<b>{format_number(car_data['freight_rub'])}</b> ₽\n\n"
            f"• Брокерские услуги:\n<b>{format_number(car_data['broker_rub'])}</b> ₽\n\n"
            f"📝 <b>Таможенные платежи:</b>\n"
            f"• Таможенный сбор:\n<b>{format_number(car_data['customs_fee_rub'])}</b> ₽\n\n"
            f"• Таможенная пошлина:\n<b>{format_number(car_data['customs_duty_rub'])}</b> ₽\n\n"
            f"• Утилизационный сбор:\n<b>{format_number(car_data['util_fee_rub'])}</b> ₽\n\n"
            f"💵 <b>Итоговая стоимость под ключ до Владивостока:</b>\n"
            f"<b>{format_number(total_cost)} ₽</b>\n\n"
            f"🔗 <a href='{preview_link}'>Ссылка на автомобиль</a>\n\n"
            f"👨‍💼 🇰🇷 +82 10 2382 4808 <a href='https://wa.me/821023824808'>Александр</a>\n"
            f"👨‍💼 🇰🇷 +82 10 7928 8398 <a href='https://wa.me/821079288398'>Сергей</a>\n"
            f"👨‍💼 🇰🇷 +82 10 2235 4808 <a href='https://wa.me/821022354808'>Александр</a>\n"
            f"📢 <a href='https://t.me/mdmgroupkorea'>Официальный телеграм канал</a>\n"
        )

        # Клавиатура с дальнейшими действиями
        keyboard = types.InlineKeyboardMarkup()
        # keyboard.add(
        #     types.InlineKeyboardButton("Детали расчёта", callback_data="detail")
        # )
        # keyboard.add(
        #     types.InlineKeyboardButton(
        #         "Оставить заявку",
        #         callback_data="",
        #     )
        # )
        keyboard.add(
            types.InlineKeyboardButton(
                "Выплаты по ДТП",
                callback_data="technical_report",
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Оставить заявку",
                callback_data="add_crm_deal",
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Расчёт другого автомобиля",
                callback_data="calculate_another",
            )
        )

        # Отправляем до 10 фотографий
        media_group = []
        for photo_url in sorted(car_photos):
            try:
                response = requests.get(photo_url)
                if response.status_code == 200:
                    photo = BytesIO(response.content)  # Загружаем фото в память
                    media_group.append(
                        types.InputMediaPhoto(photo)
                    )  # Добавляем в список

                    # Если набрали 10 фото, отправляем альбом
                    if len(media_group) == 10:
                        bot.send_media_group(message.chat.id, media_group)
                        media_group.clear()  # Очищаем список для следующей группы
                else:
                    print(f"Ошибка загрузки фото: {photo_url} - {response.status_code}")
            except Exception as e:
                print(f"Ошибка при обработке фото {photo_url}: {e}")

        # Отправка оставшихся фото, если их меньше 10
        if media_group:
            bot.send_media_group(message.chat.id, media_group)

        bot.send_message(
            message.chat.id,
            result_message,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

        bot.delete_message(
            message.chat.id, processing_message.message_id
        )  # Удаляем сообщение о передаче данных в обработку

    else:
        send_error_message(
            message,
            "🚫 Произошла ошибка при получении данных. Проверьте ссылку и попробуйте снова.",
        )
        bot.delete_message(message.chat.id, processing_message.message_id)


# Function to get insurance total
def get_insurance_total():
    global car_id_external, vehicle_no, vehicle_id

    print_message("[ЗАПРОС] ТЕХНИЧЕСКИЙ ОТЧËТ ОБ АВТОМОБИЛЕ")

    formatted_vehicle_no = urllib.parse.quote(str(vehicle_no).strip())
    url = f"https://api.encar.com/v1/readside/record/vehicle/{str(vehicle_id)}/open?vehicleNo={formatted_vehicle_no}"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": "http://www.encar.com/",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
        }

        response = requests.get(url, headers)
        json_response = response.json()

        # Форматируем данные
        damage_to_my_car = json_response["myAccidentCost"]
        damage_to_other_car = json_response["otherAccidentCost"]

        print(
            f"Выплаты по представленному автомобилю: {format_number(damage_to_my_car)}"
        )
        print(f"Выплаты другому автомобилю: {format_number(damage_to_other_car)}")

        return [format_number(damage_to_my_car), format_number(damage_to_other_car)]

    except Exception as e:
        print(f"Произошла ошибка при получении данных: {e}")
        return ["", ""]


# Callback query handler
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    global car_data, car_id_external, usd_rate, user_data

    # Обработка ручного расчёта - выбор возраста
    if call.data.startswith("manual_age_"):
        bot.answer_callback_query(call.id)
        age = call.data.replace("manual_age_", "")

        # Сохраняем возраст в данных пользователя
        if call.from_user.id not in user_data:
            user_data[call.from_user.id] = {}
        user_data[call.from_user.id]["manual_age"] = age

        # Запрашиваем объём двигателя
        msg = bot.send_message(
            call.message.chat.id,
            "Введите объём двигателя в кубических сантиметрах (например, 2000):",
        )
        bot.register_next_step_handler(msg, process_manual_engine_volume)

    elif call.data == "manual_calculation":
        bot.answer_callback_query(call.id)
        start_manual_calculation(call.message.chat.id)

    elif call.data == "add_crm_deal":
        # Отвечаем на callback, чтобы убрать индикатор загрузки у кнопки
        bot.answer_callback_query(call.id, "Начинаем оформление заявки")

        # Отправляем сообщение о начале процесса
        bot.send_message(
            call.message.chat.id,
            "✏️ Оформление заявки на автомобиль\n\nДля связи с вами нам потребуется некоторая информация.",
        )

        # Запрашиваем ФИО
        msg = bot.send_message(call.message.chat.id, "Пожалуйста, введите ваше ФИО:")
        # Регистрируем следующий шаг - сбор телефона
        user_data[call.from_user.id] = {
            "step": "waiting_name",
            "msg_id": msg.message_id,
        }
        # Устанавливаем обработчик для следующего сообщения от этого пользователя
        bot.register_next_step_handler(msg, process_name_step)

    elif call.data.startswith("detail"):
        print_message("[ЗАПРОС] ДЕТАЛИЗАЦИЯ РАСЧËТА")

        detail_message = (
            f"<i>ПЕРВАЯ ЧАСТЬ ОПЛАТЫ</i>:\n\n"
            f"Агентские услуги по договору:\n<b>${format_number(car_data['agent_korea_usd'])}</b> | <b>₩{format_number(car_data['agent_korea_krw'])}</b> | <b>50000 ₽</b>\n\n"
            f"Задаток (бронь авто):\n<b>${format_number(car_data['advance_usd'])}</b> | <b>₩1,000,000</b> | <b>{format_number(car_data['advance_rub'])} ₽</b>\n\n\n"
            f"<i>ВТОРАЯ ЧАСТЬ ОПЛАТЫ</i>:\n\n"
            # f"Стоимость автомобиля (за вычетом задатка):\n<b>${format_number(car_data['car_price_usd'])}</b> | <b>₩{format_number(car_data['car_price_krw'])}</b> | <b>{format_number(car_data['car_price_rub'])} ₽</b>\n\n"
            f"Диллерский сбор:\n<b>${format_number(car_data['dealer_korea_usd'])}</b> | <b>₩{format_number(car_data['dealer_korea_krw'])}</b> | <b>{format_number(car_data['dealer_korea_rub'])} ₽</b>\n\n"
            f"Доставка, снятие с учёта, оформление:\n<b>${format_number(car_data['delivery_korea_usd'])}</b> | <b>₩{format_number(car_data['delivery_korea_krw'])}</b> | <b>{format_number(car_data['delivery_korea_rub'])} ₽</b>\n\n"
            f"Транспортировка авто в порт:\n<b>${format_number(car_data['transfer_korea_usd'])}</b> | <b>₩{format_number(car_data['transfer_korea_krw'])}</b> | <b>{format_number(car_data['transfer_korea_rub'])} ₽</b>\n\n"
            f"Фрахт (Паром до Владивостока):\n<b>${format_number(car_data['freight_korea_usd'])}</b> | <b>₩{format_number(car_data['freight_korea_krw'])}</b> | <b>{format_number(car_data['freight_korea_rub'])} ₽</b>\n\n\n"
            f"<b>Итого расходов по Корее</b>:\n<b>${format_number(car_data['korea_total_usd'])}</b> | <b>₩{format_number(car_data['korea_total_krw'])}</b> | <b>{format_number(car_data['korea_total_rub'])} ₽</b>\n\n"
            f"<b>Стоимость автомобиля</b>:\n<b>${format_number(car_data['car_price_usd'])}</b> | <b>₩{format_number(car_data['car_price_krw'])}</b> | <b>{format_number(car_data['car_price_rub'])} ₽</b>\n\n"
            f"<b>Итого</b>:\n<b>${format_number(car_data['korea_total_plus_car_usd'])}</b> | <b>₩{format_number(car_data['korea_total_plus_car_krw'])}</b> | <b>{format_number(car_data['korea_total_plus_car_rub'])} ₽</b>\n\n\n"
            f"<i>РАСХОДЫ РОССИЯ</i>:\n\n\n"
            f"Единая таможенная ставка:\n<b>${format_number(car_data['customs_duty_usd'])}</b> | <b>₩{format_number(car_data['customs_duty_krw'])}</b> | <b>{format_number(car_data['customs_duty_rub'])} ₽</b>\n\n"
            f"Таможенное оформление:\n<b>${format_number(car_data['customs_fee_usd'])}</b> | <b>₩{format_number(car_data['customs_fee_krw'])}</b> | <b>{format_number(car_data['customs_fee_rub'])} ₽</b>\n\n"
            f"Утилизационный сбор:\n<b>${format_number(car_data['util_fee_usd'])}</b> | <b>₩{format_number(car_data['util_fee_krw'])}</b> | <b>{format_number(car_data['util_fee_rub'])} ₽</b>\n\n\n"
            f"Брокер-Владивосток:\n<b>${format_number(car_data['broker_russia_usd'])}</b> | <b>₩{format_number(car_data['broker_russia_krw'])}</b> | <b>{format_number(car_data['broker_russia_rub'])} ₽</b>\n\n"
            f"СВХ-Владивосток:\n<b>${format_number(car_data['svh_russia_usd'])}</b> | <b>₩{format_number(car_data['svh_russia_krw'])}</b> | <b>{format_number(car_data['svh_russia_rub'])} ₽</b>\n\n"
            f"Лаборатория, СБКТС, ЭПТС:\n<b>${format_number(car_data['lab_russia_usd'])}</b> | <b>₩{format_number(car_data['lab_russia_krw'])}</b> | <b>{format_number(car_data['lab_russia_rub'])} ₽</b>\n\n"
            f"Временная регистрация-Владивосток:\n<b>${format_number(car_data['perm_registration_russia_usd'])}</b> | <b>₩{format_number(car_data['perm_registration_russia_krw'])}</b> | <b>{format_number(car_data['perm_registration_russia_rub'])} ₽</b>\n\n"
            f"Итого расходов по России: \n<b>${format_number(car_data['russia_total_usd'])}</b> | <b>₩{format_number(car_data['russia_total_krw'])}</b> | <b>{format_number(car_data['russia_total_rub'])} ₽</b>\n\n\n"
            f"Итого под ключ во Владивостоке: \n<b>${format_number(car_data['total_cost_usd'])}</b> | <b>₩{format_number(car_data['total_cost_krw'])}</b> | <b>{format_number(car_data['total_cost_rub'])} ₽</b>\n\n"
            f"<b>Доставку до вашего города уточняйте у менеджеров:</b>\n\n"
            f"🇰🇷 +82 10 2382 4808 <a href='https://wa.me/821023824808'>Александр</a>\n"
            f"🇰🇷 +82 10 7928 8398 <a href='https://wa.me/821079288398'>Сергей</a>\n"
            f"🇰🇷 +82 10 2235 4808 <a href='https://wa.me/821022354808'>Александр</a>\n"
        )

        # Inline buttons for further actions
        keyboard = types.InlineKeyboardMarkup()

        if call.data.startswith("detail_manual"):
            keyboard.add(
                types.InlineKeyboardButton(
                    "Рассчитать стоимость другого автомобиля",
                    callback_data="calculate_another_manual",
                )
            )
        else:
            keyboard.add(
                types.InlineKeyboardButton(
                    "Рассчитать стоимость другого автомобиля",
                    callback_data="calculate_another",
                )
            )

        keyboard.add(
            types.InlineKeyboardButton(
                "Оставить заявку",
                callback_data="add_crm_deal",
            )
        )

        bot.send_message(
            call.message.chat.id,
            detail_message,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    elif call.data == "technical_report":
        bot.send_message(
            call.message.chat.id,
            "Запрашиваю отчёт по ДТП. Пожалуйста подождите ⏳",
        )

        # Retrieve insurance information
        insurance_info = get_insurance_total()

        # Проверка на наличие ошибки
        if (
            insurance_info is None
            or "Нет данных" in insurance_info[0]
            or "Нет данных" in insurance_info[1]
        ):
            error_message = (
                "Не удалось получить данные о страховых выплатах. \n\n"
                f'<a href="https://fem.encar.com/cars/report/accident/{car_id_external}">🔗 Посмотреть страховую историю вручную 🔗</a>\n\n\n'
                f"<b>Найдите две строки:</b>\n\n"
                f"보험사고 이력 (내차 피해) - Выплаты по представленному автомобилю\n"
                f"보험사고 이력 (타차 가해) - Выплаты другим участникам ДТП"
            )

            # Inline buttons for further actions
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    "Рассчитать стоимость другого автомобиля",
                    callback_data="calculate_another",
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    "Оставить заявку",
                    callback_data="add_crm_deal",
                )
            )

            # Отправка сообщения об ошибке
            bot.send_message(
                call.message.chat.id,
                error_message,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            current_car_insurance_payments = (
                "0" if len(insurance_info[0]) == 0 else insurance_info[0]
            )
            other_car_insurance_payments = (
                "0" if len(insurance_info[1]) == 0 else insurance_info[1]
            )

            # Construct the message for the technical report
            tech_report_message = (
                f"Страховые выплаты по представленному автомобилю: \n<b>{current_car_insurance_payments} ₩</b>\n\n"
                f"Страховые выплаты другим участникам ДТП: \n<b>{other_car_insurance_payments} ₩</b>\n\n"
                f'<a href="https://fem.encar.com/cars/report/inspect/{car_id_external}">🔗 Ссылка на схему повреждений кузовных элементов 🔗</a>'
            )

            # Inline buttons for further actions
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    "Рассчитать стоимость другого автомобиля",
                    callback_data="calculate_another",
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    "Оставить заявку",
                    callback_data="add_crm_deal",
                )
            )

            bot.send_message(
                call.message.chat.id,
                tech_report_message,
                parse_mode="HTML",
                reply_markup=keyboard,
            )

    elif call.data == "calculate_another":
        bot.send_message(
            call.message.chat.id,
            "Пожалуйста, введите ссылку на автомобиль с сайта www.encar.com:",
        )


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_message = message.text.strip()

    # Проверяем нажатие кнопки "Рассчитать автомобиль"
    if user_message == CALCULATE_CAR_TEXT:
        bot.send_message(
            message.chat.id,
            "Пожалуйста, введите ссылку на автомобиль с сайта www.encar.com:",
        )

    # Обработка кнопки "Ручной расчёт"
    elif user_message == "Ручной расчёт":
        start_manual_calculation(message.chat.id)

    # Проверка на корректность ссылки
    elif re.match(r"^https?://(www|fem)\.encar\.com/.*", user_message):
        calculate_cost(user_message, message)

    # Проверка на другие команды
    elif user_message == "Написать менеджеру":
        bot.send_message(
            message.chat.id,
            f"Вы можете связаться с нашими менеджерами:\n"
            f"🇰🇷 +82 10 2382 4808 (https://wa.me/821023824808) «Александр»\n"
            f"🇰🇷 +82 10 7928 8398 (https://wa.me/821079288398) «Сергей»\n"
            f"🇰🇷 +82 10 2235 4808 (https://wa.me/821022354808) «Александр»",
        )

    elif user_message == "О нас":
        about_message = "MDM GROUP\nЮжнокорейская экспортная компания.\nСпециализируемся на поставках автомобилей из Южной Кореи в страны СНГ.\nОпыт работы более 5 лет.\n\nПочему выбирают нас?\n• Надежность и скорость доставки.\n• Индивидуальный подход к каждому клиенту.\n• Полное сопровождение сделки.\n\n💬 Ваш путь к надежным автомобилям начинается здесь!"
        bot.send_message(message.chat.id, about_message)

    elif user_message == "Telegram-канал":
        channel_link = "https://t.me/mdmgroupkorea"
        bot.send_message(
            message.chat.id, f"Подписывайтесь на наш Telegram-канал: {channel_link}"
        )

    elif user_message == "Instagram":
        instagram_link = "https://www.instagram.com/mdm_group.kr/"
        bot.send_message(
            message.chat.id,
            f"Посетите наш Instagram: {instagram_link}",
        )

    elif user_message == "Tik-Tok":
        tiktok_link = "https://www.tiktok.com/@mdm_group"
        bot.send_message(
            message.chat.id,
            f"Следите за свежим контентом на нашем TikTok: {tiktok_link}",
        )

    else:
        bot.send_message(
            message.chat.id,
            "Пожалуйста, введите корректную ссылку на автомобиль с сайта www.encar.com или fem.encar.com.",
        )


def process_name_step(message):
    """Обработчик для ввода имени пользователя"""
    user_id = message.from_user.id
    if user_id in user_data:
        # Сохраняем имя
        user_data[user_id]["name"] = message.text
        user_data[user_id]["step"] = "waiting_phone"

        # Запрашиваем номер телефона
        msg = bot.send_message(message.chat.id, "Теперь введите ваш номер телефона:")
        bot.register_next_step_handler(msg, process_phone_step)
    else:
        bot.send_message(
            message.chat.id,
            "Произошла ошибка. Пожалуйста, начните заново.",
            reply_markup=main_menu(),
        )


def process_phone_step(message):
    """Обработчик для ввода номера телефона"""
    user_id = message.from_user.id
    phone = message.text.strip()

    if not is_valid_phone(phone):
        msg = bot.send_message(
            message.chat.id,
            "❌ Пожалуйста, введите корректный номер телефона в международном формате (например, +7..., +82..., +1...).",
        )
        bot.register_next_step_handler(msg, process_phone_step)  # Повтор ввода
        return

    if user_id in user_data:
        user_data[user_id]["phone"] = phone
        user_data[user_id]["step"] = "waiting_budget"

        msg = bot.send_message(message.chat.id, "Введите ваш бюджет (в рублях):")
        bot.register_next_step_handler(msg, process_budget_step)
    else:
        bot.send_message(
            message.chat.id,
            "Произошла ошибка. Пожалуйста, начните заново.",
            reply_markup=main_menu(),
        )


def process_budget_step(message):
    """Обработчик для ввода бюджета"""
    user_id = message.from_user.id
    if user_id in user_data:
        try:
            # Проверяем, что введено число
            budget = float(message.text.replace(" ", "").replace(",", "."))

            # Сохраняем бюджет
            user_data[user_id]["budget"] = budget
            user_data[user_id]["step"] = "waiting_car_link"

            # Запрашиваем ссылку на автомобиль
            msg = bot.send_message(
                message.chat.id,
                "Введите ссылку на интересующий автомобиль (если есть) или напишите 'нет':",
            )
            bot.register_next_step_handler(msg, process_car_link_step)
        except ValueError:
            # Если бюджет введен некорректно, просим повторить
            msg = bot.send_message(
                message.chat.id, "Пожалуйста, введите корректную сумму (только цифры):"
            )
            bot.register_next_step_handler(msg, process_budget_step)
    else:
        bot.send_message(
            message.chat.id,
            "Произошла ошибка. Пожалуйста, начните заново.",
            reply_markup=main_menu(),
        )


def process_car_link_step(message):
    """Обработчик для ввода ссылки на автомобиль"""
    user_id = message.from_user.id
    if user_id in user_data:
        # Получаем все данные пользователя
        name = user_data[user_id]["name"]
        phone = user_data[user_id]["phone"]
        budget = user_data[user_id]["budget"]
        car_link = message.text

        # Отправляем сообщение о том, что заявка обрабатывается
        processing_msg = bot.send_message(
            message.chat.id, "⏳ Отправляем вашу заявку... Пожалуйста, подождите."
        )

        # Создаем сделку в amoCRM
        try:
            if create_amocrm_lead(name, phone, budget, car_link):
                # Успешное создание сделки
                bot.edit_message_text(
                    "✅ Заявка успешно создана!",
                    message.chat.id,
                    processing_msg.message_id,
                )

                success_msg = (
                    f"Спасибо, {name}!\n\n"
                    f"✅ Ваша заявка успешно отправлена.\n"
                    f"📞 С вами свяжутся в ближайшее время по указанному номеру телефона: {phone}\n\n"
                    f"Если у вас возникли вопросы, вы можете связаться с нашими менеджерами напрямую:\n"
                    f"🇰🇷 +82 10 2382 4808 (https://wa.me/821023824808) «Александр»\n"
                    f"🇰🇷 +82 10 7928 8398 (https://wa.me/821079288398) «Сергей»\n"
                    f"🇰🇷 +82 10 2235 4808 (https://wa.me/821022354808) «Александр»"
                )
                bot.send_message(message.chat.id, success_msg, reply_markup=main_menu())
            else:
                # Ошибка при создании сделки
                bot.edit_message_text(
                    "❌ Произошла ошибка при отправке заявки.",
                    message.chat.id,
                    processing_msg.message_id,
                )

                error_msg = (
                    f"Извините, {name}, не удалось создать заявку.\n\n"
                    f"Пожалуйста, попробуйте позже или свяжитесь с нашими менеджерами напрямую:"
                )
                bot.send_message(message.chat.id, error_msg, reply_markup=main_menu())
                logging.error(
                    f"Ошибка при создании заявки для user_id={user_id}, name={name}"
                )
        except Exception as e:
            logging.exception(
                "Ошибка при создании заявки в amoCRM"
            )  # выводит traceback
            print_message(f"❌ Внутренняя ошибка: {str(e)}")
            return False

        # Очищаем данные пользователя
        del user_data[user_id]
    else:
        bot.send_message(
            message.chat.id,
            "Произошла ошибка. Пожалуйста, начните заново.",
            reply_markup=main_menu(),
        )


def format_phone(phone):
    """
    Форматирует номер телефона, удаляя лишние символы
    и добавляя +7 в начало, если нужно
    """
    # Удаляем все символы, кроме цифр
    clean_phone = re.sub(r"\D", "", phone)

    # Если номер начинается с 8 или 7, конвертируем в +7
    if clean_phone.startswith("8") and len(clean_phone) == 11:
        clean_phone = "7" + clean_phone[1:]

    # Если нет кода страны, предполагаем +7
    if len(clean_phone) == 10:
        clean_phone = "7" + clean_phone

    # Добавляем +
    if not clean_phone.startswith("+"):
        clean_phone = "+" + clean_phone

    logging.info(f"Отформатирован номер телефона: {phone} -> {clean_phone}")
    return clean_phone


def create_amocrm_lead(name, phone, budget, car_link=None):
    import os
    import requests
    import json
    import logging
    from os.path import exists

    logging.info(
        f"Создаем заявку: имя={name}, телефон={phone}, бюджет={budget}, ссылка={car_link}"
    )

    try:
        price = int(float(budget))
    except (ValueError, TypeError):
        price = 0

    formatted_phone = format_phone(phone)

    access_token = os.getenv("AMOCRM_ACCESS_TOKEN")
    refresh_token = os.getenv("AMOCRM_REFRESH_TOKEN")

    # if exists("access_token.txt"):
    #     with open("access_token.txt", "r") as f:
    #         access_token = f.read().strip()
    # if exists("refresh_token.txt"):
    #     with open("refresh_token.txt", "r") as f:
    #         refresh_token = f.read().strip()

    if not access_token or not refresh_token:
        logging.error("Отсутствуют токены доступа к AmoCRM")
        return False

    subdomain = os.getenv("AMOCRM_SUBDOMAIN")
    client_id = os.getenv("AMOCRM_CLIENT_ID")
    client_secret = os.getenv("AMOCRM_CLIENT_SECRET")
    redirect_url = os.getenv("AMOCRM_REDIRECT_URL")
    base_url = f"https://{subdomain}.amocrm.ru/api/v4"

    def refresh_access_token():
        nonlocal access_token, refresh_token
        token_url = f"https://{subdomain}.amocrm.ru/oauth2/access_token"
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "redirect_uri": redirect_url,
        }
        res = requests.post(token_url, json=data)
        if res.status_code == 200:
            result = res.json()
            access_token = result.get("access_token")
            refresh_token = result.get("refresh_token")
            with open("access_token.txt", "w") as f:
                f.write(access_token)
            with open("refresh_token.txt", "w") as f:
                f.write(refresh_token)
            return True
        else:
            logging.error(
                f"Ошибка при обновлении токена: {res.status_code}, {res.text}"
            )
            return False

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # --- Шаг 1: создание контакта ---
    contact_data = [
        {
            "name": name,
            "responsible_user_id": 12208190,
            "custom_fields_values": [
                {
                    "field_code": "PHONE",
                    "values": [
                        {
                            "value": formatted_phone,
                            "enum_code": "WORK",  # можно также "MOB" или "WORK"
                        }
                    ],
                }
            ],
        }
    ]

    contacts_url = f"{base_url}/contacts"
    contact_response = requests.post(contacts_url, headers=headers, json=contact_data)

    if contact_response.status_code == 401 and refresh_access_token():
        headers["Authorization"] = f"Bearer {access_token}"
        contact_response = requests.post(
            contacts_url, headers=headers, json=contact_data
        )

    if contact_response.status_code >= 400:
        logging.error(
            f"Ошибка при создании контакта: {contact_response.status_code}, {contact_response.text}"
        )
        return False

    contact_id = contact_response.json().get("id")
    if not contact_id:
        contact_id = (
            contact_response.json()
            .get("_embedded", {})
            .get("contacts", [{}])[0]
            .get("id")
        )
    if not contact_id:
        logging.error("Не удалось получить ID контакта")
        return False

    logging.info(f"Контакт успешно создан с ID: {contact_id}")

    # --- Шаг 2: создание сделки ---
    custom_fields = [{"field_id": 1069807, "values": [{"value": price}]}]
    if car_link and car_link.lower() != "нет":
        custom_fields.append({"field_id": 1295963, "values": [{"value": car_link}]})

    lead_data = [
        {
            "name": f"Заявка от {name}",
            "price": price,
            "_embedded": {
                "contacts": [{"id": contact_id}],
                "tags": [{"name": "telegram_bot"}],
            },
        }
    ]

    leads_url = f"{base_url}/leads"
    lead_response = requests.post(leads_url, headers=headers, json=lead_data)

    if lead_response.status_code == 401 and refresh_access_token():
        headers["Authorization"] = f"Bearer {access_token}"
        lead_response = requests.post(leads_url, headers=headers, json=lead_data)

    if lead_response.status_code >= 400:
        logging.error(
            f"Ошибка при создании сделки: {lead_response.status_code}, {lead_response.text}"
        )
        return False

    lead_id = lead_response.json().get("id")
    if not lead_id:
        lead_id = (
            lead_response.json().get("_embedded", {}).get("leads", [{}])[0].get("id")
        )

    if not lead_id:
        logging.error("Не удалось получить ID сделки")
        return False

    logging.info(f"Сделка успешно создана с ID: {lead_id}")

    # --- Шаг 3: добавляем примечание ---
    notes_url = f"{base_url}/leads/notes"
    if car_link and car_link.lower() != "нет":
        note_text = f"Заявка из Telegram\nФИО: {name}\nТелефон: {formatted_phone}\nБюджет: {price}₽\nСсылка: {car_link}"
    else:
        note_text = f"Заявка из Telegram\nФИО: {name}\nТелефон: {formatted_phone}\nБюджет: {price}₽"

    note_data = [
        {"entity_id": lead_id, "note_type": "common", "params": {"text": note_text}}
    ]

    note_response = requests.post(notes_url, headers=headers, json=note_data)

    if note_response.status_code == 401 and refresh_access_token():
        headers["Authorization"] = f"Bearer {access_token}"
        note_response = requests.post(notes_url, headers=headers, json=note_data)

    if note_response.status_code >= 400:
        logging.warning(
            f"Ошибка при создании примечания: {note_response.status_code}, {note_response.text}"
        )
    else:
        logging.info("Примечание успешно добавлено")

    print_message(f"✅ Заявка отправлена в amoCRM (ID сделки: {lead_id})")
    return True


# Функции для ручного расчёта
def start_manual_calculation(chat_id):
    """Начало процесса ручного расчёта"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("До 3 лет", callback_data="manual_age_0-3"),
        types.InlineKeyboardButton("От 3 до 5 лет", callback_data="manual_age_3-5"),
        types.InlineKeyboardButton("От 5 до 7 лет", callback_data="manual_age_5-7"),
        types.InlineKeyboardButton("От 7 лет", callback_data="manual_age_7-0"),
    )

    bot.send_message(chat_id, "Выберите возраст автомобиля:", reply_markup=markup)


def process_manual_engine_volume(message):
    """Обработчик ввода объёма двигателя при ручном расчёте"""
    try:
        engine_volume = int(message.text.strip())
        user_id = message.from_user.id

        if user_id in user_data and "manual_age" in user_data[user_id]:
            user_data[user_id]["engine_volume"] = engine_volume

            # Запрашиваем стоимость автомобиля
            msg = bot.send_message(
                message.chat.id,
                "Введите стоимость автомобиля в корейских вонах (например, 20000000):",
            )
            bot.register_next_step_handler(msg, process_manual_car_price)
        else:
            bot.send_message(
                message.chat.id,
                "Произошла ошибка. Начните ручной расчёт заново.",
                reply_markup=main_menu(),
            )
    except ValueError:
        msg = bot.send_message(
            message.chat.id,
            "Пожалуйста, введите корректное числовое значение объёма двигателя:",
        )
        bot.register_next_step_handler(msg, process_manual_engine_volume)


def process_manual_car_price(message):
    """Обработчик ввода стоимости автомобиля при ручном расчёте"""
    try:
        car_price = int(message.text.strip())
        user_id = message.from_user.id

        if (
            user_id in user_data
            and "manual_age" in user_data[user_id]
            and "engine_volume" in user_data[user_id]
        ):
            # Выполняем расчёт
            calculate_manual_cost(
                user_data[user_id]["manual_age"],
                user_data[user_id]["engine_volume"],
                car_price,
                message,
            )
        else:
            bot.send_message(
                message.chat.id,
                "Произошла ошибка. Начните ручной расчёт заново.",
                reply_markup=main_menu(),
            )
    except ValueError:
        msg = bot.send_message(
            message.chat.id,
            "Пожалуйста, введите корректное числовое значение стоимости:",
        )
        bot.register_next_step_handler(msg, process_manual_car_price)


def calculate_manual_cost(age, engine_volume, car_price, message):
    """Функция расчёта стоимости по введённым вручную параметрам"""
    global car_data, usdt_krw_rate, usdt_rub_rate

    print_message("ЗАПРОС НА РУЧНОЙ РАСЧЁТ АВТОМОБИЛЯ")

    # Получаем актуальный курс валют
    get_usdt_to_rub_rate()
    get_currency_rates()

    # Отправляем сообщение о том, что идёт расчёт
    processing_message = bot.send_message(
        message.chat.id, "Выполняю расчёт стоимости. Пожалуйста подождите ⏳"
    )

    try:
        # Возрастные категории для отображения пользователю
        age_formatted_map = {
            "0-3": "до 3 лет",
            "3-5": "от 3 до 5 лет",
            "5-7": "от 5 до 7 лет",
            "7-0": "от 7 лет",
        }
        age_formatted = age_formatted_map.get(age, "неизвестный возраст")

        # Форматирование объёма двигателя для отображения
        engine_volume_formatted = f"{format_number(engine_volume)} cc"

        # Расчёт стоимости в рублях
        price_krw = car_price
        price_usdt = int(price_krw) / usdt_krw_rate
        price_rub = int(price_usdt) * usdt_rub_rate

        # Получаем таможенные сборы
        from utils import get_customs_fees_manual

        logging.info(
            f"Запрос таможенных сборов: объем={engine_volume}, цена={car_price}, возраст={age}"
        )
        response = get_customs_fees_manual(engine_volume, price_krw, age, engine_type=1)
        logging.info(f"Ответ calcus.ru: {response}")

        # Таможенный сбор
        customs_fee = clean_number(response["sbor"])
        customs_duty = clean_number(response["tax"])
        recycling_fee = clean_number(response["util"])

        # Расчет итоговой стоимости автомобиля в рублях
        total_cost = (
            price_rub  # Стоимость автомобиля в рублях
            + customs_fee  # Таможенный сбор
            + customs_duty  # Таможенная пошлина
            + recycling_fee  # Утилизационный сбор
            + 100000  # ФРАХТ
            + 100000  # Брокерские услуги
        )

        car_data["freight_rub"] = 100000
        car_data["freight_usdt"] = 1000

        car_data["broker_rub"] = 100000
        car_data["broker_usdt"] = 100000 / usdt_rub_rate

        car_data["customs_fee_rub"] = customs_fee
        car_data["customs_fee_usdt"] = customs_fee / usdt_rub_rate

        car_data["customs_duty_rub"] = customs_duty
        car_data["customs_duty_usdt"] = customs_duty / usdt_rub_rate

        car_data["util_fee_rub"] = recycling_fee
        car_data["util_fee_usdt"] = recycling_fee / usdt_rub_rate

        # Формирование сообщения результата
        result_message = (
            f"🚗 <b>Ручной расчёт автомобиля</b>\n\n"
            f"📅 Возраст: {age_formatted}\n"
            f"🔧 Объём двигателя: {engine_volume_formatted}\n\n"
            f"💱 Актуальные курсы валют:\nUSDT/KRW: <b>₩{usdt_krw_rate:.2f}</b>\nUSDT/RUB: <b>{usdt_rub_rate:.2f} ₽</b>\n\n"
            f"💰 <b>Стоимость:</b>\n"
            f"• Цена авто:\n₩<b>{format_number(price_krw)}</b> | <b>{format_number(price_rub)}</b> ₽\n\n"
            f"• ФРАХТ:\n<b>{format_number(car_data['freight_rub'])}</b> ₽\n\n"
            f"• Брокерские услуги:\n<b>{format_number(car_data['broker_rub'])}</b> ₽\n\n"
            f"📝 <b>Таможенные платежи:</b>\n"
            f"• Таможенный сбор:\n<b>{format_number(car_data['customs_fee_rub'])}</b> ₽\n\n"
            f"• Таможенная пошлина:\n<b>{format_number(car_data['customs_duty_rub'])}</b> ₽\n\n"
            f"• Утилизационный сбор:\n<b>{format_number(car_data['util_fee_rub'])}</b> ₽\n\n"
            f"💵 <b>Итоговая стоимость под ключ до Владивостока:</b>\n"
            f"<b>{format_number(total_cost)} ₽</b>\n\n"
            f"👨‍💼 🇰🇷 +82 10 2382 4808 <a href='https://wa.me/821023824808'>Александр</a>\n"
            f"👨‍💼 🇰🇷 +82 10 7928 8398 <a href='https://wa.me/821079288398'>Сергей</a>\n"
            f"👨‍💼 🇰🇷 +82 10 2235 4808 <a href='https://wa.me/821022354808'>Александр</a>\n"
            f"📢 <a href='https://t.me/mdmgroupkorea'>Официальный телеграм канал</a>\n"
        )

        # Клавиатура с дальнейшими действиями
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "Оставить заявку",
                callback_data="add_crm_deal",
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Новый ручной расчёт",
                callback_data="manual_calculation",
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Расчёт по ссылке",
                callback_data="calculate_another",
            )
        )

        bot.send_message(
            message.chat.id,
            result_message,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"Произошла ошибка при расчёте: {str(e)}. Попробуйте снова.",
            reply_markup=main_menu(),
        )

    finally:
        # Удаляем сообщение о процессе расчёта
        bot.delete_message(message.chat.id, processing_message.message_id)


# Run the bot
if __name__ == "__main__":
    set_bot_commands()

    # Обновляем курсы валют каждый час
    import threading
    import time

    def update_currency_rates():
        while True:
            try:
                get_currency_rates()
                print_message("Курсы валют обновлены")
                time.sleep(3600)  # Обновление каждый час (3600 секунд)
            except Exception as e:
                print_message(f"Ошибка при обновлении курсов валют: {e}")
                time.sleep(60)  # При ошибке пробуем через минуту

    # Запускаем обновление курсов в отдельном потоке
    currency_thread = threading.Thread(target=update_currency_rates, daemon=True)
    currency_thread.start()

    # Получаем начальные курсы при запуске
    get_currency_rates()
    bot.polling(non_stop=True)
