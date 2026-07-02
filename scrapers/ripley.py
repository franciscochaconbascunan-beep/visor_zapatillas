"""
Scraper de Ripley Chile (simple.ripley.cl).

Estrategia: la búsqueda es Next.js con <script id="__NEXT_DATA__"> que embebe la
lista de productos bajo una clave 'products'. Cada producto trae:
  { sku, parentProductID, brand, name, description, primaryImage,
    oldPrice:"$49.990", price:"$24.990", priceNumber:24990, discount:50,
    seller:"RIPLEY", shop:{shopName} }

El link NO viene como campo, pero el HTML incluye <a href="/...-{parentProductID}?...">.
Construimos un mapa parentProductID -> href para obtener la URL real.

Nota: Ripley NO entrega tallas en el listado, así que estos productos quedan sin
confirmación de talla (tiene_44_5_45=False). Coincide con la estrategia mixta.

Uso:  python scrapers/ripley.py
"""
from __future__ import annotations

import html as html_lib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SEARCH_URL = "https://simple.ripley.cl/search/zapatillas%20hombre?page={page}"
BASE = "https://simple.ripley.cl"
MAX_PAGES = 5
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
HREF_RE = re.compile(r'href="(/[^"]*?-(\d{6,})(?:\?[^"]*)?)"')


def _find_products(node):
    if isinstance(node, dict):
        p = node.get("products")
        if isinstance(p, list) and p and isinstance(p[0], dict) and "sku" in p[0]:
            return p
        for v in node.values():
            found = _find_products(v)
            if found:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find_products(v)
            if found:
                return found
    return None


def _href_map(html: str) -> dict[str, str]:
    """parentProductID -> URL absoluta (tomada del primer href que la contenga)."""
    out: dict[str, str] = {}
    for full, pid in HREF_RE.findall(html):
        if pid not in out:
            path = html_lib.unescape(full).split("?")[0]
            out[pid] = BASE + path
    return out


def parse_page(html: str) -> list[dict]:
    m = NEXT_DATA_RE.search(html)
    if not m:
        return []
    data = json.loads(m.group(1))
    products = _find_products(data) or []
    hrefs = _href_map(html)
    records = []
    for prod in products:
        pid = str(prod.get("parentProductID", ""))
        link = hrefs.get(pid) or f"{BASE}/{common.slugify(prod.get('name',''))}-{pid}"
        normal = common.parse_price(prod.get("oldPrice"))
        oferta = common.parse_price(prod.get("priceNumber") or prod.get("price"))
        seller = prod.get("seller") or ""
        shop = (prod.get("shop") or {}).get("shopName") or ""
        vendedor = "Ripley" if seller.upper() == "RIPLEY" else (shop or seller or "Marketplace")
        records.append(
            common.make_record(
                tienda="Ripley",
                modelo=prod.get("name", ""),
                marca=prod.get("brand", ""),
                precio_normal=normal,
                precio_oferta=oferta,
                link=link,
                sku=pid or prod.get("sku", ""),
                imagen=prod.get("primaryImage", ""),
                vendedor=vendedor,
                tallas_disponibles=[],  # no disponibles en el listado
                disponible=True,
            )
        )
    return records


def scrape() -> list[dict]:
    session = common.make_session()
    all_records: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        url = SEARCH_URL.format(page=page)
        print(f"  Ripley página {page} ...")
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
            if r["sku"] not in all_records:
                new += 1
            all_records[r["sku"]] = r
        if new == 0:
            print("    página sin productos nuevos; fin.")
            break
    return list(all_records.values())


def main() -> int:
    print("== Ripley ==")
    try:
        records = scrape()
    except Exception as exc:  # noqa: BLE001
        print(f"  FALLO Ripley: {exc}")
        records = []
    common.save_raw("ripley", records)
    print(f"  {len(records)} productos")
    return 0 if records else 1


if __name__ == "__main__":
    raise SystemExit(main())
