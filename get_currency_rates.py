import requests
from main import print_message


def get_currency_rates():
    global usd_rate

    print_message("ПОЛУЧАЕМ КУРС ЦБ")

    url = "https://www.cbr-xml-daily.ru/daily_json.js"
    response = requests.get(url)
    data = response.json()

    # Получаем курсы валют
    eur = data["Valute"]["EUR"]["Value"]
    usd = data["Valute"]["USD"]["Value"]
    krw = data["Valute"]["KRW"]["Value"] / data["Valute"]["KRW"]["Nominal"]
    cny = data["Valute"]["CNY"]["Value"]

    # Сохраняем глобально usd
    usd_rate = usd

    # Форматируем текст
    rates_text = (
        f"EUR {eur:.4f} ₽\n"
        f"USD {usd:.4f} ₽\n"
        f"KRW {krw:.4f} ₽\n"
        f"CNY {cny:.4f} ₽"
    )

    print_message(rates_text)

    return rates_text
