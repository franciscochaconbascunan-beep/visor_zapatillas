"""
Scraper de Falabella Chile.

Estrategia: la página de búsqueda es una app Next.js que embebe TODO el catálogo
de resultados en <script id="__NEXT_DATA__">. Ese JSON trae, por producto:
  props.pageProps.results[] = {
     productId, displayName, url, brand, sellerName,
     prices:[{crossed:bool, price:["26.990"]}...],   # crossed=True -> normal, False -> oferta
     variants:[{type:"COLOR", options:[{sizes:[{value:"44.5", available:True}]}]}],
     discountBadge:{label:"-70%"}
  }

Ventaja clave: Falabella entrega las TALLAS con su disponibilidad dentro del
propio listado, por lo que podemos confirmar stock de 44.5/45 sin requests extra.

Uso:  python scrapers/falabella.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SEARCH_URL = "https://www.falabella.com/falabella-cl/search?Ntt=zapatillas+hombre&page={page}"
MAX_PAGES = 5
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _find_results(node):
    """Busca recursivamente la lista de productos (clave 'results')."""
    if isinstance(node, dict):
        r = node.get("results")
        if isinstance(r, list) and r and isinstance(r[0], dict) and "productId" in r[0]:
            return r
        for v in node.values():
            found = _find_results(v)
            if found:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find_results(v)
            if found:
                return found
    return None


def _prices(prod: dict):
    """Devuelve (precio_normal, precio_oferta) en CLP."""
    normal = oferta = None
    for p in prod.get("prices", []):
        val = common.parse_price(p.get("price"))
        if val is None:
            continue
        if p.get("crossed"):
            normal = val if normal is None else min(normal, val)
        else:
            oferta = val if oferta is None else min(oferta, val)
    return normal, oferta


def _sizes_disponibles(prod: dict) -> list[str]:
    tallas = []
    for variant in prod.get("variants", []):
        if variant.get("type") != "COLOR":
            continue
        for opt in variant.get("options", []):
            for size in opt.get("sizes", []):
                if size.get("available") and size.get("value"):
                    tallas.append(str(size["value"]))
    return sorted(set(tallas), key=lambda x: float(common.norm_size(x)) if common.norm_size(x).replace(".", "").isdigit() else 0)


def parse_page(html: str) -> list[dict]:
    m = NEXT_DATA_RE.search(html)
    if not m:
        return []
    data = json.loads(m.group(1))
    results = _find_results(data) or []
    records = []
    for prod in results:
        normal, oferta = _prices(prod)
        tallas = _sizes_disponibles(prod)
        media = prod.get("mediaUrls") or []
        imagen = media[0] if media else ""
        records.append(
            common.make_record(
                tienda="Falabella",
                modelo=prod.get("displayName", ""),
                marca=prod.get("brand", ""),
                precio_normal=normal,
                precio_oferta=oferta,
                link=prod.get("url", ""),
                sku=prod.get("productId", ""),
                imagen=imagen,
                vendedor=prod.get("sellerName") or "Falabella",
                tallas_disponibles=tallas,
                disponible=True,
            )
        )
    return records


def scrape() -> list[dict]:
    session = common.make_session()
    all_records: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        url = SEARCH_URL.format(page=page)
        print(f"  Falabella página {page} ...")
        try:
            html = common.fetch(session, url)
        except Exception as exc:  # noqa: BLE001
            print(f"    error página {page}: {exc}")
            break
        recs = parse_page(html)
        if not recs:
            print("    sin resultados; fin de la paginación.")
            break
        for r in recs:
            all_records[r["sku"]] = r  # dedup por productId
    return list(all_records.values())


def main() -> int:
    print("== Falabella ==")
    try:
        records = scrape()
    except Exception as exc:  # noqa: BLE001
        print(f"  FALLO Falabella: {exc}")
        records = []
    common.save_raw("falabella", records)
    con_talla = sum(1 for r in records if r["tiene_44_5_45"])
    print(f"  {len(records)} productos ({con_talla} con talla 44.5/45 confirmada)")
    return 0 if records else 1


if __name__ == "__main__":
    raise SystemExit(main())
