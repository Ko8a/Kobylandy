#!/usr/bin/env python3
"""
main.py — Astana New Apartments Scraper & Analyzer.

Usage:
    python main.py              # Full scrape + analysis
    python main.py --demo       # Demo data only (no network requests)
    python main.py --source bi.group  # Scrape single source
    python main.py --help
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

# ─── Project paths ────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROC = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"

for d in [DATA_RAW, DATA_PROC, REPORTS]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(ROOT / "scraper.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


def get_scrapers(source_filter: str = None):
    """Return list of (name, scraper_instance) to run."""
    from scrapers.bigroup_scraper import BiGroupScraper
    from scrapers.krisha_scraper import KrishaScraper
    from scrapers.korter_scraper import KorterScraper
    from scrapers.svoydom_scraper import SvoyDomScraper
    from scrapers.homsters_scraper import HomstersScraper
    from scrapers.kapster_scraper import KapsterScraper
    from scrapers.other_scrapers import (
        QazaqstroyScraper, SensataScraper, RamsqzScraper, GBGScraper, SatNsScraper
    )

    all_scrapers = [
        ("bi.group",       BiGroupScraper()),
        ("qazaqstroy.kz",  QazaqstroyScraper()),
        ("sensata.kz",     SensataScraper()),
        ("ramsqz.com",     RamsqzScraper()),
        ("gbg.kz",         GBGScraper()),
        ("svoydom.kz",     SvoyDomScraper()),
        ("sat-ns.kz",      SatNsScraper()),
        ("korter.kz",      KorterScraper()),
        ("krisha.kz",      KrishaScraper()),
        ("homsters.kz",    HomstersScraper()),
        ("kapster.kz",     KapsterScraper()),
    ]

    if source_filter:
        all_scrapers = [(n, s) for n, s in all_scrapers if source_filter.lower() in n.lower()]
        if not all_scrapers:
            logger.error(f"No scraper matches --source '{source_filter}'")
            sys.exit(1)

    return all_scrapers


def run_scrapers(source_filter: str = None) -> list[dict]:
    """Run all scrapers and collect raw data."""
    scrapers = get_scrapers(source_filter)
    all_apartments = []
    scraping_log = []

    for name, scraper in scrapers:
        logger.info(f"{'='*60}")
        logger.info(f"Starting: {name}")
        start = time.time()
        try:
            apartments = scraper.scrape()
            elapsed = time.time() - start
            logger.info(f"Done: {name} → {len(apartments)} apartments in {elapsed:.1f}s")
            all_apartments.extend(apartments)
            scraping_log.append(f"✅ {name}: {len(apartments)} квартир ({elapsed:.1f}s)")

            # Save intermediate raw data
            raw_file = DATA_RAW / f"{name.replace('.', '_').replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(raw_file, "w", encoding="utf-8") as f:
                json.dump(apartments, f, ensure_ascii=False, indent=2)
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"FAILED: {name}: {e}", exc_info=True)
            scraping_log.append(f"❌ {name}: ошибка — {e} ({elapsed:.1f}s)")

        time.sleep(2)

    logger.info(f"{'='*60}")
    logger.info(f"Total collected: {len(all_apartments)} apartments from {len(scrapers)} sources")
    return all_apartments, scraping_log


def load_demo_data() -> list[dict]:
    """Load realistic demo dataset (no network requests needed)."""
    from scrapers.demo_data import DEMO_APARTMENTS
    logger.info(f"[DEMO] Loaded {len(DEMO_APARTMENTS)} demo apartments")
    return DEMO_APARTMENTS, ["[DEMO] Данные загружены из demo_data.py (без сетевых запросов)"]


def process_and_save(apartments: list[dict], scraping_log: list[str]) -> None:
    """Deduplicate, analyse, and save all output files."""
    from scrapers.deduplication import deduplicate
    from scrapers.analytics import build_analytics
    from scrapers.report_generator import generate_report

    if not apartments:
        logger.warning("No apartments collected — nothing to process")
        return

    # Deduplicate
    logger.info(f"Before dedup: {len(apartments)}")
    apartments = deduplicate(apartments)
    logger.info(f"After dedup: {len(apartments)}")

    # Build DataFrame
    df = pd.DataFrame(apartments)

    # Coerce numeric columns
    for col in ["комнат", "площадь_м2", "цена_полная_тг", "цена_за_м2_тг"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Fill missing price_per_m2
    mask = df["цена_за_м2_тг"].isna() & df["цена_полная_тг"].notna() & df["площадь_м2"].notna()
    df.loc[mask, "цена_за_м2_тг"] = (
        df.loc[mask, "цена_полная_тг"] / df.loc[mask, "площадь_м2"]
    ).astype(int)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save processed JSON
    json_path = DATA_PROC / "apartments_astana.json"
    df.to_json(json_path, orient="records", force_ascii=False, indent=2)
    logger.info(f"Saved: {json_path}")

    # Save CSV
    csv_path = DATA_PROC / "apartments_astana.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    logger.info(f"Saved: {csv_path}")

    # Save Excel
    xlsx_path = DATA_PROC / "apartments_astana.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Все квартиры", index=False)

        # Format columns
        ws = writer.sheets["Все квартиры"]
        from openpyxl.styles import PatternFill, Font, Alignment
        from openpyxl.utils import get_column_letter

        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", wrap_text=True)

        for col_idx, col in enumerate(df.columns, 1):
            max_len = max(len(str(col)), df[col].astype(str).str.len().max() if not df.empty else 10)
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 40)

    logger.info(f"Saved: {xlsx_path}")

    # Run analytics
    analytics = build_analytics(df)

    # Add analytics sheets to Excel
    with pd.ExcelWriter(xlsx_path, engine="openpyxl", mode="a") as writer:
        sheet_map = {
            "top20_cheap_total": "ТОП20 по цене",
            "top20_cheap_m2":    "ТОП20 по цене_м²",
            "top10_1k":          "ТОП10 1-комн",
            "top10_2k":          "ТОП10 2-комн",
            "top10_3k":          "ТОП10 3-комн",
            "top20_best_score":  "Лучшие по Score",
            "suspicious":        "Подозрительные цены",
            "no_price":          "Без цены",
        }
        for key, sheet_name in sheet_map.items():
            if key in analytics and not analytics[key].empty:
                analytics[key].to_excel(writer, sheet_name=sheet_name, index=False)

    logger.info(f"Excel with analytics: {xlsx_path}")

    # Add charts sheet
    _add_charts_to_excel(xlsx_path, df, analytics)

    # Generate markdown report
    report_path = REPORTS / "report.md"
    generate_report(df, analytics, str(report_path), scraping_log)

    # Print summary to console
    _print_summary(df, analytics)


def _add_charts_to_excel(xlsx_path: Path, df: pd.DataFrame, analytics: dict) -> None:
    """Add charts sheet to the Excel workbook."""
    from openpyxl import load_workbook
    from openpyxl.chart import BarChart, Reference, PieChart
    from openpyxl.chart.series import SeriesLabel
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = load_workbook(xlsx_path)

    # ── Sheet: Графики ────────────────────────────────────────────────────────
    ws = wb.create_sheet("Графики и сводка", 1)

    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=12)
    title_font  = Font(bold=True, size=14, color="1F4E79")

    def write_header(ws, row, col, text):
        c = ws.cell(row=row, column=col, value=text)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center")

    def write_title(ws, row, col, text):
        c = ws.cell(row=row, column=col, value=text)
        c.font = title_font

    # ── 1. Средняя цена м² по застройщику ────────────────────────────────────
    write_title(ws, 1, 1, "Средняя цена ₸/м² по застройщику")
    write_header(ws, 2, 1, "Застройщик")
    write_header(ws, 2, 2, "Ср. цена ₸/м²")

    dev_avg = (
        df[df["цена_за_м2_тг"].notna()]
        .groupby("застройщик")["цена_за_м2_тг"]
        .mean()
        .round(0)
        .sort_values(ascending=False)
    )
    for i, (dev, val) in enumerate(dev_avg.items(), start=3):
        ws.cell(row=i, column=1, value=dev)
        ws.cell(row=i, column=2, value=int(val))
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 16

    bar1 = BarChart()
    bar1.type = "bar"
    bar1.title = "Средняя цена ₸/м² по застройщику"
    bar1.y_axis.title = "Застройщик"
    bar1.x_axis.title = "₸/м²"
    bar1.height = 14
    bar1.width = 22
    data_ref = Reference(ws, min_col=2, min_row=2, max_row=2 + len(dev_avg))
    cats_ref = Reference(ws, min_col=1, min_row=3, max_row=2 + len(dev_avg))
    bar1.add_data(data_ref, titles_from_data=True)
    bar1.set_categories(cats_ref)
    bar1.series[0].graphicalProperties.solidFill = "2E75B6"
    ws.add_chart(bar1, "D1")

    # ── 2. Количество квартир по классу ──────────────────────────────────────
    start_row = len(dev_avg) + 5
    write_title(ws, start_row, 1, "Квартиры по классу жилья")
    write_header(ws, start_row + 1, 1, "Класс жилья")
    write_header(ws, start_row + 1, 2, "Количество")

    class_cnt = df["класс_жилья"].value_counts()
    for i, (cls, cnt) in enumerate(class_cnt.items(), start=start_row + 2):
        ws.cell(row=i, column=1, value=cls)
        ws.cell(row=i, column=2, value=int(cnt))

    pie = PieChart()
    pie.title = "Распределение по классу жилья"
    pie.height = 12
    pie.width = 16
    pie_data = Reference(ws, min_col=2, min_row=start_row + 1, max_row=start_row + 1 + len(class_cnt))
    pie_cats = Reference(ws, min_col=1, min_row=start_row + 2, max_row=start_row + 1 + len(class_cnt))
    pie.add_data(pie_data, titles_from_data=True)
    pie.set_categories(pie_cats)
    ws.add_chart(pie, f"D{start_row}")

    # ── 3. Цены по районам ────────────────────────────────────────────────────
    start_row2 = start_row + len(class_cnt) + 4
    write_title(ws, start_row2, 1, "Средняя цена ₸/м² по ключевым районам")
    write_header(ws, start_row2 + 1, 1, "Район")
    write_header(ws, start_row2 + 1, 2, "Ср. цена ₸/м²")
    write_header(ws, start_row2 + 1, 3, "Кол-во кв.")

    def extract_district(addr: str) -> str:
        if not addr:
            return "Не указан"
        a = str(addr).lower()
        if "есиль" in a:
            return "Есиль"
        if "алматинский" in a:
            return "Алматинский"
        if "байконур" in a:
            return "Байконур"
        if "нура" in a:
            return "Нура"
        return "Другой"

    df2 = df[df["цена_за_м2_тг"].notna()].copy()
    df2["район_кат"] = df2["район_адрес"].apply(extract_district)
    dist_stats = df2.groupby("район_кат").agg(
        avg_price=("цена_за_м2_тг", "mean"),
        count=("цена_за_м2_тг", "count")
    ).round(0).sort_values("avg_price", ascending=False)

    for i, (dist, row_) in enumerate(dist_stats.iterrows(), start=start_row2 + 2):
        ws.cell(row=i, column=1, value=dist)
        ws.cell(row=i, column=2, value=int(row_["avg_price"]))
        ws.cell(row=i, column=3, value=int(row_["count"]))

    bar2 = BarChart()
    bar2.type = "col"
    bar2.title = "Средняя цена ₸/м² по районам Астаны"
    bar2.y_axis.title = "₸/м²"
    bar2.x_axis.title = "Район"
    bar2.height = 11
    bar2.width = 18
    d2_ref = Reference(ws, min_col=2, min_row=start_row2 + 1, max_row=start_row2 + 1 + len(dist_stats))
    c2_ref = Reference(ws, min_col=1, min_row=start_row2 + 2, max_row=start_row2 + 1 + len(dist_stats))
    bar2.add_data(d2_ref, titles_from_data=True)
    bar2.set_categories(c2_ref)
    bar2.series[0].graphicalProperties.solidFill = "ED7D31"
    ws.add_chart(bar2, f"D{start_row2}")

    # ── 4. Сводная таблица — лучшие предложения по Score ─────────────────────
    ws_sum = wb.create_sheet("🏆 Лучшие предложения", 2)
    write_title(ws_sum, 1, 1, "ТОП-20 ЛУЧШИХ ПРЕДЛОЖЕНИЙ ПО КОМПЛЕКСНОМУ SCORE")
    ws_sum.merge_cells("A1:M1")
    ws_sum["A1"].alignment = Alignment(horizontal="center")

    score_df = analytics.get("top20_best_score", pd.DataFrame())
    if not score_df.empty:
        display_cols = ["застройщик", "название_жк", "район_адрес", "комнат",
                        "площадь_м2", "цена_полная_тг", "цена_за_м2_тг",
                        "срок_сдачи", "класс_жилья", "условия_покупки", "score"]
        score_display = score_df[[c for c in display_cols if c in score_df.columns]].copy()

        # Format headers
        for ci, col_name in enumerate(score_display.columns, start=1):
            write_header(ws_sum, 2, ci, col_name)

        # Fill rows with alternating colors
        fill_even = PatternFill(start_color="DEEAF1", end_color="DEEAF1", fill_type="solid")
        fill_odd  = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        fill_top3 = PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid")

        price_cols_set = {"цена_полная_тг", "цена_за_м2_тг"}
        for ri, (_, row_data) in enumerate(score_display.iterrows(), start=3):
            for ci, (col_name, val) in enumerate(zip(score_display.columns, row_data), start=1):
                cell = ws_sum.cell(row=ri, column=ci)
                if col_name in price_cols_set and isinstance(val, (int, float)) and not pd.isna(val):
                    cell.value = int(val)
                    cell.number_format = '#,##0 [$₸]'
                elif col_name == "score" and val is not None and not pd.isna(val):
                    cell.value = round(float(val), 3)
                else:
                    cell.value = val if (val is not None and not (isinstance(val, float) and pd.isna(val))) else ""
                cell.fill = fill_top3 if ri <= 5 else (fill_even if ri % 2 == 0 else fill_odd)

        for ci, col_name in enumerate(score_display.columns, start=1):
            max_len = max(len(str(col_name)), score_display.iloc[:, ci-1].astype(str).str.len().max())
            ws_sum.column_dimensions[get_column_letter(ci)].width = min(max_len + 2, 35)

    wb.save(xlsx_path)
    logger.info(f"Charts and summary sheet added to: {xlsx_path}")


def _print_summary(df: pd.DataFrame, analytics: dict) -> None:
    print("\n" + "="*70)
    print("РЕЗУЛЬТАТЫ АНАЛИЗА НОВОСТРОЕК АСТАНЫ")
    print("="*70)
    print(f"Всего квартир: {len(df)}")
    print(f"С ценой: {int(df['цена_полная_тг'].notna().sum())}")
    print(f"ЖК: {df['название_жк'].nunique()}, Застройщиков: {df['застройщик'].nunique()}")

    print("\n--- ТОП-5 самых дешёвых (полная цена) ---")
    top5 = analytics.get("top20_cheap_total", pd.DataFrame()).head(5)
    if not top5.empty:
        for _, r in top5.iterrows():
            p = r.get("цена_полная_тг", 0)
            price_str = f"{p/1_000_000:.2f} млн ₸" if p else "—"
            print(f"  {r.get('название_жк','?')} | {r.get('комнат','?')}к | "
                  f"{r.get('площадь_м2','?')} м² | {price_str} | {r.get('источник','?')}")

    print("\n--- ТОП-5 по Score (комплексная оценка) ---")
    top5s = analytics.get("top20_best_score", pd.DataFrame()).head(5)
    if not top5s.empty:
        for _, r in top5s.iterrows():
            p = r.get("цена_за_м2_тг", 0)
            pm2_str = f"{int(p):,}₸/м²".replace(",", " ") if p else "—"
            print(f"  {r.get('название_жк','?')} | {r.get('комнат','?')}к | "
                  f"{pm2_str} | score={r.get('score',0):.3f} | {r.get('срок_сдачи','?')}")

    print("\n--- Файлы сохранены ---")
    print(f"  CSV:   data/processed/apartments_astana.csv")
    print(f"  Excel: data/processed/apartments_astana.xlsx")
    print(f"  JSON:  data/processed/apartments_astana.json")
    print(f"  Отчёт: reports/report.md")
    print("="*70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Astana New Apartments Scraper")
    parser.add_argument("--demo", action="store_true", help="Use demo data (no network)")
    parser.add_argument("--source", type=str, default=None, help="Filter by source name")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info(f"{'='*60}")
    logger.info(f"Astana Apartments Scraper started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Mode: {'DEMO' if args.demo else 'LIVE'}")

    if args.demo:
        apartments, scraping_log = load_demo_data()
    else:
        apartments, scraping_log = run_scrapers(source_filter=args.source)

    process_and_save(apartments, scraping_log)
    logger.info("Done.")


if __name__ == "__main__":
    main()
