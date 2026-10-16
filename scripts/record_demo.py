"""Запись видео-демо с подписями по маршруту docs/demo.md.

Нужны Playwright с Chromium и ffmpeg (не входят в requirements):
    pip install playwright && playwright install chromium
    DVOINIK_AUTH_MODE=demo python serve.py            # в другом терминале, чистый демо-архив
    python scripts/record_demo.py --survey example-survey.csv
    ffmpeg -i raw/*.webm -vf fps=25 -c:v libx264 -pix_fmt yuv420p dvoinik-demo.mp4

CSV в ролике — пример для показа механизма загрузки, это подписано в кадре.
"""

import argparse
import asyncio

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8501/"
CAP = """(t)=>{let el=document.getElementById('demo-caption');if(!el){el=document.createElement('div');el.id='demo-caption';
Object.assign(el.style,{position:'fixed',left:'50%',bottom:'34px',transform:'translateX(-50%)',maxWidth:'1000px',
background:'rgba(20,41,67,.94)',color:'#fff',padding:'14px 24px',borderRadius:'14px',font:'600 20px/1.4 system-ui,sans-serif',
zIndex:99999,boxShadow:'0 8px 30px rgba(0,0,0,.25)',textAlign:'center',transition:'opacity .3s'});document.body.appendChild(el)}
el.style.opacity=t?'1':'0';if(t)el.textContent=t}"""


async def say(pg, text, ms=3500):
    await pg.evaluate(CAP, text)
    await pg.wait_for_timeout(ms)
    await pg.evaluate(CAP, "")
    await pg.wait_for_timeout(300)


async def scroll_to(pg, selector, offset=90, ms=1400):
    await pg.evaluate(
        "([s,o])=>{const e=document.querySelector(s);if(e)window.scrollTo({top:e.getBoundingClientRect().top+window.scrollY-o,behavior:'smooth'})}",
        [selector, offset],
    )
    await pg.wait_for_timeout(ms)


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir="raw",
            record_video_size={"width": 1440, "height": 900},
        )
        pg = await ctx.new_page()
        await pg.goto(BASE)
        await pg.wait_for_timeout(1500)
        await say(
            pg, "Двойник — синтетическая аудитория для подготовки исследований банковских предложений", 4500
        )
        await pg.get_by_role("link", name="Новое исследование").first.click()
        await pg.wait_for_timeout(1200)
        await say(pg, "Шаг 1. Выбираем сценарий и описываем 2–5 предложений", 3000)
        await pg.locator("select").first.select_option(label="Вклад для пенсионеров")
        await pg.wait_for_timeout(1200)
        await scroll_to(pg, "textarea", 260)
        await say(
            pg,
            "Три предложения вклада: оформление в приложении, в отделении и с защитой через родственника",
            4500,
        )
        await pg.get_by_role("button", name="Далее: аудитория").click()
        await pg.wait_for_timeout(1500)
        await say(
            pg,
            "Шаг 2. Аудитория: 200 двойников из сегмента 60+, одни и те же профили для всех предложений",
            4500,
        )
        await scroll_to(pg, ".run-estimate", 220, 1800)
        await say(pg, "До запуска видно, сколько запросов и токенов потребует подключённая LLM", 4000)
        await pg.get_by_role("button", name="Запустить исследование").click()
        await pg.wait_for_url("**/report/**", timeout=20000)
        await pg.wait_for_timeout(1500)
        await say(pg, "Отчёт. Демо-режим: проценты показывают работу продукта, а не прогноз спроса", 4500)
        await say(pg, "Полоса проверок: устойчивость лидера, сравнение с простым подходом, живой опрос", 4500)
        await scroll_to(pg, ".matrix", 150)
        await say(pg, "Матрица «сегменты × предложения»: доля согласий и покрытие ответов", 3500)
        await scroll_to(pg, ".analysis-grid", 120)
        await say(
            pg, "Лидер — гипотеза для живой проверки: чтобы различить C и B, нужно около 250 ответов", 5000
        )
        await scroll_to(pg, ".baseline-card", 120)
        await say(
            pg,
            "Сравнение с простым подходом: один запрос без персонажей. Если ответ тот же — персонажи не нужны",
            5500,
        )
        await scroll_to(pg, ".objections", 200)
        await say(pg, "Причины отказа: у варианта A главный барьер — неудобный канал", 4000)
        await pg.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        await pg.wait_for_timeout(1200)
        await pg.get_by_role("tab", name="Голоса").click()
        await pg.wait_for_timeout(1000)
        await scroll_to(pg, "#panel-voices", 120)
        await say(pg, "Голоса двойников: синтетические объяснения решений по сегментам", 4000)
        await pg.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        await pg.wait_for_timeout(1000)
        await pg.get_by_role("tab", name="Проверка опросом").click()
        await pg.wait_for_timeout(1000)
        await scroll_to(pg, ".live-plan", 120)
        await say(pg, "План живой проверки: размер выборки и вопросы для интервью из частых возражений", 5000)
        await scroll_to(pg, ".survey-preparation", 120)
        await say(pg, "Комплект опроса: нейтральная анкета, пустой CSV и инструкция с планом", 4000)
        await scroll_to(pg, ".survey-results", 100)
        await pg.locator("input[type=file]").set_input_files(ARGS.survey)
        await pg.wait_for_timeout(1500)
        await say(pg, "Загружаем ответы (здесь — пример CSV для показа механизма, не настоящий опрос)", 4500)
        await scroll_to(pg, ".baseline-validation", 160)
        await say(pg, "На одних данных видно, чья ошибка меньше: у двойников или у простого подхода", 5000)
        await pg.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        await pg.wait_for_timeout(1200)
        await say(
            pg, "«Следующая итерация» переносит настройки в конструктор; запуски сравниваются в архиве", 4500
        )
        await pg.get_by_role("link", name="Исследования").first.click()
        await pg.wait_for_timeout(1500)
        await say(
            pg, "Двойник не заменяет живое исследование — он помогает выбрать, что и на ком проверять", 5000
        )
        await say(pg, "MISIS X · github.com/NikitaMeshDS/dvoinik", 3500)
        await ctx.close()
        await b.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--survey", required=True, help="CSV segment,variant,decision для показа загрузки")
    parser.add_argument("--base", default=BASE)
    ARGS = parser.parse_args()
    BASE = ARGS.base
    asyncio.run(main())
