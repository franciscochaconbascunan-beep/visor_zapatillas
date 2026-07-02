"""
Scraper de Paris Chile (paris.cl).

Paris usa Next.js App Router con streaming RSC (self.__next_f), sin __NEXT_DATA__.
La vía MÁS ESTABLE es el bloque JSON-LD schema.org (ItemList) que viene embebido
(escapado) dentro del stream. Por cada producto trae:
  { "@type":"Product", "name", "url", "image", "sku",
    "brand":{"name"}, "offers":{"price", "priceCurrency", "availability", "url"} }

Limitaciones: el JSON-LD entrega solo UN precio (el de venta -> "Valor"); no trae
precio normal tachado ni tallas. Por eso en Paris Precio = Valor y talla queda s/info.

Plan B (documentado, no activo): si el JSON-LD desaparece, usar Playwright headless.

Uso:  python scrapers/paris.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

CATEGORY_URL = "https://www.paris.cl/zapatos/zapatillas/?page={page}"
# El JSON-LD SSR de Paris solo renderiza la primera página (~30 productos) y la
# paginación no cambia el SSR. Por eso 1 página. Para cobertura total haría falta
# el Plan B con Playwright (ver README).
MAX_PAGES = 1


def _unescape_rsc(html: str) -> str:
    """Deshace el escape del stream RSC para exponer el JSON-LD legible."""
    return html.replace('\\"', '"').replace("\\/", "/")


def _extract_itemlist(text: str) -> list[dict]:
    """Extrae los elementos de la primera ItemList JSON-LD encontrada."""
    anchor = text.find('"@type":"ItemList"')
    if anchor == -1:
        return []
    key = text.find('"itemListElement"', anchor)
    if key == -1:
        return []
    start = text.find("[", key)
    if start == -1:
        return []
    # Captura balanceada del arreglo [ ... ]
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                chunk = text[start : i + 1]
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    return []
    return []


def parse_page(html: str) -> list[dict]:
    text = _unescape_rsc(html)
    elements = _extract_itemlist(text)
    records = []
    for el in elements:
        item = el.get("item", el) if isinstance(el, dict) else {}
        if not isinstance(item, dict):
            continue
        offers = item.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        brand = item.get("brand") or {}
        marca = brand.get("name", "") if isinstance(brand, dict) else str(brand)
        precio = common.parse_price(offers.get("price"))
        avail = str(offers.get("availability", "")).lower()
        records.append(
            common.make_record(
                tienda="Paris",
                modelo=item.get("name", ""),
                marca=marca,
                precio_normal=None,      # JSON-LD no entrega precio normal
                precio_oferta=precio,
                link=item.get("url") or offers.get("url", ""),
                sku=item.get("sku", ""),
                imagen=item.get("image", ""),
                vendedor="Paris",
                tallas_disponibles=[],
                disponible=("instock" in avail) or ("outofstock" not in avail),
            )
        )
    return records


def scrape() -> list[dict]:
    session = common.make_session()
    all_records: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        url = CATEGORY_URL.format(page=page)
        print(f"  Paris página {page} ...")
        try:
            html = common.fetch(session, url)
        except Exception as exc:  # noqa: BLE001
            print(f"    error página {page}: {exc}")
            break
        recs = parse_page(html)
        if not recs:
            print("    sin resultados; fin de la paginación.")
            break
        new = 0
        for r in recs:
            key = r["sku"] or r["link"]
            if key not in all_records:
                new += 1
            all_records[key] = r
        if new == 0:
            print("    página sin productos nuevos; fin.")
            break
    return list(all_records.values())


def main() -> int:
    print("== Paris ==")
    try:
        records = scrape()
    except Exception as exc:  # noqa: BLE001
        print(f"  FALLO Paris: {exc}")
        records = []
    common.save_raw("paris", records)
    print(f"  {len(records)} productos")
    return 0 if records else 1


if __name__ == "__main__":
    raise SystemExit(main())
