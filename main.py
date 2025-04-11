import telebot
import os
import re
import requests
import locale
import logging
import urllib.parse

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

CALCULATE_CAR_TEXT = "Расчёт Автомобиля"
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
        print(f"Ошибка при получении курса: {e}")
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
        soup = BeautifulSoup(naver_response.text, 'html.parser')
        
        # Извлекаем значение курса из strong.price
        price_element = soup.select_one("strong.price em")
        if price_element:
            krw_rate_text = price_element.text.strip().replace(',', '')
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
    keyboard.add(types.KeyboardButton(CALCULATE_CAR_TEXT))
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
                "Написать менеджеру (Александр)", url="https://t.me/kkkkww12"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Написать менеджеру (Сергей)", url="https://wa.me/821079288398"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Написать менеджеру (Александр)", url="https://wa.me/821022354808"
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
            price_rub +  # Стоимость автомобиля в рублях
            customs_fee +  # Таможенный сбор
            customs_duty +  # Таможенная пошлина
            recycling_fee +  # Утилизационный сбор
            100000 +  # ФРАХТ
            100000  # Брокерские услуги
        )

        total_cost_usdt = (
            price_usdt +  # Стоимость автомобиля в рублях
            (customs_fee / usdt_rub_rate) +  # Таможенный сбор
            (customs_duty / usdt_rub_rate) +  # Таможенная пошлина
            (recycling_fee / usdt_rub_rate) +  # Утилизационный сбор
            (100000 / usdt_rub_rate) +  # ФРАХТ
            (100000 / usdt_rub_rate)  # Брокерские услуги
        )

        car_data['freight_rub'] = 100000
        car_data['freight_usdt'] = 100000 / usdt_rub_rate

        car_data['broker_rub'] = 100000
        car_data['broker_usdt'] = 100000 / usdt_rub_rate

        car_data['customs_fee_rub'] = customs_fee
        car_data['customs_fee_usdt'] = customs_fee / usdt_rub_rate

        car_data['customs_duty_rub'] = customs_duty
        car_data['customs_duty_usdt'] = customs_duty / usdt_rub_rate

        car_data['util_fee_rub'] = recycling_fee
        car_data['util_fee_usdt'] = recycling_fee / usdt_rub_rate

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
            f"• Цена в Корее: ₩{format_number(price_krw)}\n"
            f"• Цена авто: ${format_number(price_usdt)} | {format_number(price_rub)} ₽\n"
            f"• ФРАХТ: ${format_number(car_data['freight_usdt'])} | {format_number(car_data['freight_rub'])} ₽\n"
            f"• Брокерские услуги: ${format_number(car_data['broker_usdt'])} | {format_number(car_data['broker_rub'])} ₽\n\n"
            f"📝 <b>Таможенные платежи:</b>\n"
            f"• Таможенный сбор: ${format_number(car_data['customs_fee_usdt'])} | {format_number(car_data['customs_fee_rub'])} ₽\n"
            f"• Таможенная пошлина: ${format_number(car_data['customs_duty_usdt'])} | {format_number(car_data['customs_duty_rub'])} ₽\n"
            f"• Утилизационный сбор: ${format_number(car_data['util_fee_usdt'])} | {format_number(car_data['util_fee_rub'])} ₽\n\n"
            f"💵 <b>Итоговая стоимость под ключ до Владивостока:</b>\n"
            f"<b>${format_number(total_cost_usdt)}</b> | <b>{format_number(total_cost)} ₽</b>\n\n"
            f"🔗 <a href='{preview_link}'>Ссылка на автомобиль</a>\n\n"
            f"⚠️ <i>Если данное авто попадает под санкции, пожалуйста уточните возможность отправки в вашу страну у менеджеров:</i>\n\n"
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
        keyboard.add(
            types.InlineKeyboardButton(
                "Выплаты по ДТП",
                callback_data="technical_report",
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Написать менеджеру (Александр)", url="https://t.me/kkkkww12"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Написать менеджеру (Сергей)", url="https://wa.me/821079288398"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Написать менеджеру (Александр)", url="https://wa.me/821022354808"
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
    global car_data, car_id_external, usd_rate

    if call.data.startswith("detail"):
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
                "Написать менеджеру (Александр)", url="https://t.me/kkkkww12"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Написать менеджеру (Сергей)", url="https://wa.me/821079288398"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Написать менеджеру (Александр)", url="https://wa.me/821022354808"
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
                    "Написать менеджеру (Александр)", url="https://t.me/kkkkww12"
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    "Написать менеджеру (Сергей)", url="https://wa.me/821079288398"
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    "Написать менеджеру (Александр)", url="https://wa.me/821022354808"
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
                    "Написать менеджеру (Александр)", url="https://t.me/kkkkww12"
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    "Написать менеджеру (Сергей)", url="https://wa.me/821079288398"
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    "Написать менеджеру (Александр)", url="https://wa.me/821022354808"
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
    elif user_message == "WhatsApp":
        contacts = [
            {"name": "Константин", "phone": "+82 10-7650-3034"},
            # {"name": "Владимир", "phone": "+82 10-7930-2218"},
            # {"name": "Илья", "phone": "+82 10-3458-2205"},
        ]

        message_text = "\n".join(
            [
                f"[{contact['name']}](https://wa.me/{contact['phone'].replace('+', '')})"
                for contact in contacts
            ]
        )
        bot.send_message(message.chat.id, message_text, parse_mode="Markdown")

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
