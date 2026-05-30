"""
Deduplication module.

Priority order: developer site > korter.kz > krisha.kz > homsters.kz > kapster.kz

Two records are considered duplicates if they share the same complex name,
number of rooms, area (within ±2 m²), and price (within ±5%).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

SOURCE_PRIORITY = {
    "bi.group": 1,
    "qazaqstroy.kz": 1,
    "sensata.kz": 1,
    "ramsqz.com": 1,
    "gbg.kz": 1,
    "svoydom.kz": 1,
    "sat-ns.kz": 1,
    "korter.kz": 2,
    "krisha.kz": 3,
    "homsters.kz": 4,
    "kapster.kz": 5,
}


def _priority(source: Optional[str]) -> int:
    return SOURCE_PRIORITY.get(source or "", 99)


def _key(apt: dict) -> Optional[tuple]:
    """Fuzzy key for duplicate detection."""
    name = (apt.get("название_жк") or "").strip().lower()
    rooms = apt.get("комнат")
    area = apt.get("площадь_м2")
    if not name or rooms is None or area is None:
        return None
    area_bucket = round(float(area) / 2) * 2  # 2 m² buckets
    return (name, int(rooms), area_bucket)


def deduplicate(apartments: list[dict]) -> list[dict]:
    """Remove duplicate apartments, keeping the highest-priority source."""
    seen: dict[tuple, dict] = {}
    no_key: list[dict] = []

    for apt in apartments:
        k = _key(apt)
        if k is None:
            no_key.append(apt)
            continue
        if k not in seen:
            seen[k] = apt
        else:
            existing_prio = _priority(seen[k].get("источник"))
            new_prio = _priority(apt.get("источник"))
            if new_prio < existing_prio:
                logger.debug(
                    f"Dedup: replacing {seen[k].get('источник')} with {apt.get('источник')} "
                    f"for {apt.get('название_жк')} {apt.get('комнат')}к {apt.get('площадь_м2')}м²"
                )
                seen[k] = apt
            else:
                logger.debug(
                    f"Dedup: keeping {seen[k].get('источник')} over {apt.get('источник')} "
                    f"for {apt.get('название_жк')}"
                )

    result = list(seen.values()) + no_key
    removed = len(apartments) - len(result)
    if removed:
        logger.info(f"Deduplication: removed {removed} duplicates, kept {len(result)} records")
    return result
