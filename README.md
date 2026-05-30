# Astana New Apartments Scraper

Сборщик и анализатор данных о квартирах в новостройках Астаны от застройщиков.

## Структура проекта

```
Kobylandy/
├── main.py                    # Точка входа
├── requirements.txt
├── scrapers/
│   ├── base.py                # Базовый класс скрапера
│   ├── bigroup_scraper.py     # bi.group
│   ├── krisha_scraper.py      # krisha.kz
│   ├── korter_scraper.py      # korter.kz
│   ├── svoydom_scraper.py     # svoydom.kz
│   ├── homsters_scraper.py    # homsters.kz
│   ├── kapster_scraper.py     # kapster.kz
│   ├── other_scrapers.py      # qazaqstroy, sensata, ramsqz, gbg, sat-ns
│   ├── deduplication.py       # Удаление дублей
│   ├── analytics.py           # Аналитика и скоринг
│   ├── report_generator.py    # Генератор Markdown-отчёта
│   └── demo_data.py           # Реалистичные демо-данные
├── data/
│   ├── raw/                   # Сырые JSON от каждого источника
│   └── processed/             # Итоговые файлы
│       ├── apartments_astana.csv
│       ├── apartments_astana.xlsx
│       └── apartments_astana.json
└── reports/
    └── report.md              # Аналитический отчёт
```

## Установка

```bash
pip install -r requirements.txt
playwright install chromium
```

## Запуск

```bash
# Демо-режим (не делает сетевых запросов)
python main.py --demo

# Полный парсинг (только с домашнего/мобильного интернета)
python main.py

# Только один источник
python main.py --source bi.group
python main.py --source qazaqstroy
python main.py --source korter

# Отладка
python main.py --demo --debug
```

## Важно: блокировка cloud-IP

**Все казахстанские сайты недвижимости блокируют запросы с cloud-серверов**
(AWS, GCP, Azure, DigitalOcean и т.д.) через Cloudflare WAF.

**Решения:**
1. Запускать с домашнего интернета (наилучший вариант)
2. Использовать казахстанский VPN или proxy с жилыми IP
3. Использовать мобильный интернет (hotspot) — надёжно работает

## Источники данных

| Сайт | Тип | Метод парсинга |
|------|-----|---------------|
| bi.group | Застройщик | REST API + Next.js SSR + Playwright |
| qazaqstroy.kz | Застройщик | REST API + HTML |
| sensata.kz | Застройщик | REST API + Playwright (SPA) |
| ramsqz.com | Застройщик | REST API + Nuxt SSR |
| gbg.kz | Застройщик | REST API + Vue SPA |
| svoydom.kz | Застройщик | REST API + Next.js |
| sat-ns.kz | Застройщик | REST API + HTML |
| korter.kz | Агрегатор | REST API v2 |
| krisha.kz | Агрегатор | AJAX API + HTML |
| homsters.kz | Агрегатор | REST API v1 |
| kapster.kz | Агрегатор | REST API |

## Формула скоринга

```
score = 0.45 × (низкая цена/м²)
      + 0.25 × (срок сдачи / готовность)
      + 0.15 × (престижность района)
      + 0.10 × (надёжность застройщика)
      + 0.05 × (наличие ипотеки/рассрочки)
```

## Собираемые поля

- застройщик, название ЖК, город, район/адрес
- ссылка на ЖК и на конкретную квартиру/планировку
- комнат, площадь м², цена полная ₸, цена за м² ₸
- этаж, блок/секция, срок сдачи, статус
- отделка, класс жилья, условия покупки
- дата и время парсинга, источник данных

## Дедупликация

При нахождении одной квартиры на нескольких сайтах — приоритет отдаётся:
`Застройщик (1) > korter.kz (2) > krisha.kz (3) > homsters.kz (4) > kapster.kz (5)`

Детекция дублей: совпадение названия ЖК + кол-во комнат + площадь (±2 м²).
