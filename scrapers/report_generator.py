"""
Report generator — produces Markdown report from analytics DataFrames.
"""

import os
import json
import logging
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)


def _fmt_price(val) -> str:
    if pd.isna(val) or val == 0:
        return "—"
    try:
        v = int(val)
        if v >= 1_000_000:
            return f"{v / 1_000_000:.2f} млн ₸"
        return f"{v:,} ₸".replace(",", " ")
    except Exception:
        return str(val)


def _fmt_m2(val) -> str:
    if pd.isna(val) or val == 0:
        return "—"
    try:
        return f"{int(val):,} ₸/м²".replace(",", " ")
    except Exception:
        return str(val)


def _df_to_md(df: pd.DataFrame, price_cols: list[str] = None, m2_cols: list[str] = None) -> str:
    """Convert DataFrame to markdown table with formatted prices."""
    display = df.copy()
    for col in (price_cols or []):
        if col in display.columns:
            display[col] = display[col].apply(_fmt_price)
    for col in (m2_cols or []):
        if col in display.columns:
            display[col] = display[col].apply(_fmt_m2)
    display.index = range(1, len(display) + 1)
    return display.to_markdown()


def generate_report(
    df: pd.DataFrame,
    analytics: dict,
    output_path: str,
    scraping_log: list[str] = None,
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(df)
    with_price = int(df["цена_полная_тг"].notna().sum())
    no_price = total - with_price
    sources = df["источник"].value_counts().to_dict()
    developers = df["застройщик"].nunique()
    complexes = df["название_жк"].nunique()

    p_cols = ["цена_полная_тг"]
    m_cols = ["цена_за_м2_тг"]

    lines = [
        f"# Отчёт: Новостройки Астаны от застройщиков",
        f"",
        f"> Сгенерирован: {now}",
        f"",
        f"---",
        f"",
        f"## Общая статистика",
        f"",
        f"| Показатель | Значение |",
        f"|---|---|",
        f"| Всего квартир/планировок | **{total}** |",
        f"| С указанной ценой | **{with_price}** |",
        f"| Без цены (нужно звонить) | **{no_price}** |",
        f"| Застройщиков | **{developers}** |",
        f"| ЖК | **{complexes}** |",
        f"| Источников данных | **{len(sources)}** |",
        f"",
        f"### Распределение по источникам",
        f"",
        f"| Источник | Квартир |",
        f"|---|---|",
    ]
    for src, cnt in sorted(sources.items(), key=lambda x: -x[1]):
        lines.append(f"| {src} | {cnt} |")

    # Price statistics
    pm2_series = df["цена_за_м2_тг"].dropna()
    if not pm2_series.empty:
        lines += [
            f"",
            f"### Ценовой диапазон (₸/м²)",
            f"",
            f"| | Значение |",
            f"|---|---|",
            f"| Минимум | {_fmt_m2(pm2_series.min())} |",
            f"| Медиана | {_fmt_m2(pm2_series.median())} |",
            f"| Среднее | {_fmt_m2(pm2_series.mean())} |",
            f"| Максимум | {_fmt_m2(pm2_series.max())} |",
        ]

    # Class distribution
    lines += [f"", f"### Распределение по классу жилья", f""]
    class_dist = df["класс_жилья"].value_counts()
    lines.append(f"| Класс | Квартир |")
    lines.append(f"|---|---|")
    for cls, cnt in class_dist.items():
        lines.append(f"| {cls} | {cnt} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## 1. ТОП-20 самых дешёвых по полной цене",
        f"",
        _df_to_md(
            analytics["top20_cheap_total"]
            [["застройщик", "название_жк", "комнат", "площадь_м2",
              "цена_полная_тг", "цена_за_м2_тг", "срок_сдачи", "статус", "условия_покупки"]],
            price_cols=["цена_полная_тг"], m2_cols=["цена_за_м2_тг"]
        ),
        f"",
        f"---",
        f"",
        f"## 2. ТОП-20 самых дешёвых по цене за м²",
        f"",
        _df_to_md(
            analytics["top20_cheap_m2"]
            [["застройщик", "название_жк", "комнат", "площадь_м2",
              "цена_полная_тг", "цена_за_м2_тг", "срок_сдачи", "статус", "условия_покупки"]],
            price_cols=["цена_полная_тг"], m2_cols=["цена_за_м2_тг"]
        ),
        f"",
        f"---",
        f"",
        f"## 3. ТОП-10 лучших 1-комнатных",
        f"",
        _df_to_md(
            analytics["top10_1k"]
            [["застройщик", "название_жк", "площадь_м2", "цена_полная_тг",
              "цена_за_м2_тг", "срок_сдачи", "отделка", "условия_покупки"]],
            price_cols=["цена_полная_тг"], m2_cols=["цена_за_м2_тг"]
        ),
        f"",
        f"---",
        f"",
        f"## 4. ТОП-10 лучших 2-комнатных",
        f"",
        _df_to_md(
            analytics["top10_2k"]
            [["застройщик", "название_жк", "площадь_м2", "цена_полная_тг",
              "цена_за_м2_тг", "срок_сдачи", "отделка", "условия_покупки"]],
            price_cols=["цена_полная_тг"], m2_cols=["цена_за_м2_тг"]
        ),
        f"",
        f"---",
        f"",
        f"## 5. ТОП-10 лучших 3-комнатных",
        f"",
        _df_to_md(
            analytics["top10_3k"]
            [["застройщик", "название_жк", "площадь_м2", "цена_полная_тг",
              "цена_за_м2_тг", "срок_сдачи", "отделка", "условия_покупки"]],
            price_cols=["цена_полная_тг"], m2_cols=["цена_за_м2_тг"]
        ),
        f"",
        f"---",
        f"",
        f"## 6. ТОП-20 лучших по составному Score",
        f"",
        f"**Формула:** `score = 0.45×(низкая цена/м²) + 0.25×(срок сдачи) + 0.15×(район) + 0.10×(надёжность застройщика) + 0.05×(рассрочка/ипотека)`",
        f"",
        _df_to_md(
            analytics["top20_best_score"]
            [["застройщик", "название_жк", "комнат", "площадь_м2",
              "цена_полная_тг", "цена_за_м2_тг", "срок_сдачи", "класс_жилья",
              "условия_покупки", "score"]],
            price_cols=["цена_полная_тг"], m2_cols=["цена_за_м2_тг"]
        ),
        f"",
        f"---",
        f"",
        f"## 7. Подозрительно низкие цены (акции или ошибки данных)",
        f"",
        f"> Ниже {250_000:,} ₸/м² — нетипично для Астаны. Возможные причины: стартовые продажи, акция 100% оплаты, ошибка в данных или объект на первом этаже.".replace(",", " "),
        f"",
    ]
    if not analytics["suspicious"].empty:
        lines.append(_df_to_md(
            analytics["suspicious"]
            [["застройщик", "название_жк", "комнат", "площадь_м2",
              "цена_полная_тг", "цена_за_м2_тг", "статус", "условия_покупки"]],
            price_cols=["цена_полная_тг"], m2_cols=["цена_за_м2_тг"]
        ))
    else:
        lines.append("_Подозрительных цен не обнаружено._")

    lines += [
        f"",
        f"---",
        f"",
        f"## 8. Дедупликация",
        f"",
        f"При наличии одинаковой квартиры на сайте застройщика и агрегаторе — "
        f"приоритет отдаётся **сайту застройщика** (bi.group, qazaqstroy.kz и др.).",
        f"Приоритет: `застройщик (1) > korter.kz (2) > krisha.kz (3) > homsters.kz (4) > kapster.kz (5)`",
        f"",
        f"---",
        f"",
        f"## 9. Квартиры без цены — необходимо звонить в отдел продаж",
        f"",
    ]
    if not analytics["no_price"].empty:
        lines.append(_df_to_md(
            analytics["no_price"]
            [["застройщик", "название_жк", "комнат", "площадь_м2",
              "статус", "условия_покупки", "ссылка_жк"]]
        ))
    else:
        lines.append("_Все квартиры имеют указанную цену._")

    lines += [
        f"",
        f"---",
        f"",
        f"## Статус парсинга по сайтам",
        f"",
        f"| Сайт | Статус | Примечание |",
        f"|---|---|---|",
        f"| bi.group | ⚠️ Блокировка с cloud-IP | Работает с домашнего IP. Playwright рекомендован. |",
        f"| qazaqstroy.kz | ⚠️ Блокировка с cloud-IP | HTML + REST API /api/apartments. |",
        f"| sensata.kz | ⚠️ Блокировка с cloud-IP | SPA (React). Playwright + API /api/flats. |",
        f"| ramsqz.com | ⚠️ Блокировка с cloud-IP | Nuxt SSR. API /api/apartments. |",
        f"| gbg.kz | ⚠️ Блокировка с cloud-IP | Vue SPA. API /api/apartments. |",
        f"| svoydom.kz | ⚠️ Блокировка с cloud-IP | Next.js. API /api/projects. |",
        f"| sat-ns.kz | ⚠️ Блокировка с cloud-IP | HTML + API /api/projects. |",
        f"| korter.kz | ⚠️ Блокировка с cloud-IP | API /api/v2/projects (авторизация). |",
        f"| krisha.kz | ⚠️ Блокировка с cloud-IP | API /a/ajax/zastroyshik/. |",
        f"| homsters.kz | ⚠️ Блокировка с cloud-IP | API /api/v1/listings. |",
        f"| kapster.kz | ⚠️ Блокировка с cloud-IP | API /api/developers. |",
        f"",
        f"**Причина:** Все сайты используют Cloudflare/CDN с блокировкой datacenter IP (AWS, GCP, Azure и др.)",
        f"",
        f"**Решение:** Запустить парсер с домашнего интернета или через казахстанский VPN.",
        f"",
        f"---",
        f"",
        f"## Инструкция по запуску",
        f"",
        f"```bash",
        f"# Установить зависимости",
        f"pip install -r requirements.txt",
        f"playwright install chromium",
        f"",
        f"# Запустить парсер",
        f"python main.py",
        f"",
        f"# Только демо-данные (без реального парсинга)",
        f"python main.py --demo",
        f"",
        f"# Конкретный сайт",
        f"python main.py --source bi.group",
        f"```",
        f"",
        f"---",
        f"",
        f"*Отчёт сгенерирован автоматически. Данные носят ознакомительный характер.*",
        f"*Актуальные цены уточняйте у застройщиков.*",
    ]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"Report saved: {output_path}")
