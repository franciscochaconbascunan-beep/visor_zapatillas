"""
Consolida los crudos de las tres tiendas (data/raw_*.json) en:
  - data/consolidado.csv          (base homologada, lista para Excel)
  - docs/data/productos.json      (lo que consume el visor web)

Columnas de la base consolidada (en el orden pedido + extras relevantes):
  Precio | Talla | Valor | Modelo | Link | Fecha_publicacion | Tienda
  + Marca | Descuento_% | Tiene_44.5/45 | Vendedor | SKU | Imagen | Disponible | Fecha_actualizacion

"Fecha_publicacion" es un proxy: la PRIMERA fecha en que detectamos el producto
(persistida en data/first_seen.json), porque el retail no expone fecha real de aviso.

Uso:  python consolidate.py
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DOCS_DATA = ROOT / "docs" / "data"
DOCS_DATA.mkdir(parents=True, exist_ok=True)

STORES = ["falabella", "ripley", "paris"]
FIRST_SEEN_PATH = DATA_DIR / "first_seen.json"

CSV_COLUMNS = [
    "Precio", "Talla", "Valor", "Modelo", "Link", "Fecha_publicacion", "Tienda",
    "Marca", "Descuento_%", "Tiene_44.5/45", "Vendedor", "SKU", "Imagen",
    "Disponible", "Fecha_actualizacion",
]


def load_raw() -> list[dict]:
    records: list[dict] = []
    for store in STORES:
        path = DATA_DIR / f"raw_{store}.json"
        if not path.exists():
            print(f"  aviso: {path.name} no existe, se omite.")
            continue
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"  aviso: no pude leer {path.name}: {exc}")
            continue
        print(f"  {store}: {len(items)} productos")
        records.extend(items)
    return records


def load_first_seen() -> dict:
    if FIRST_SEEN_PATH.exists():
        try:
            return json.loads(FIRST_SEEN_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def main() -> int:
    print("== Consolidando ==")
    raw = load_raw()
    if not raw:
        print("  No hay datos crudos. Corre primero los scrapers.")
        return 1

    first_seen = load_first_seen()
    today = date.today().isoformat()
    now_iso = datetime.now().isoformat(timespec="seconds")

    consolidated: dict[str, dict] = {}
    for r in raw:
        key = f"{r['tienda']}|{r['sku']}"
        if key in consolidated:
            continue  # dedup global por tienda+sku
        if key not in first_seen:
            first_seen[key] = today
        tallas = r.get("tallas_disponibles") or []
        talla_str = ", ".join(tallas) if tallas else "s/info"
        producto = {
            **r,
            "talla": talla_str,
            "fecha_publicacion": first_seen[key],
            "fecha_actualizacion": now_iso,
        }
        consolidated[key] = producto

    productos = list(consolidated.values())
    # Orden por defecto: primero los que confirman talla, luego mayor descuento.
    productos.sort(key=lambda p: (not p["tiene_44_5_45"], -(p.get("descuento_pct") or 0)))

    # ---- CSV consolidado ----
    csv_path = DATA_DIR / "consolidado.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for p in productos:
            w.writerow([
                p.get("precio_normal", ""),
                p.get("talla", ""),
                p.get("precio_oferta", ""),
                p.get("modelo", ""),
                p.get("link", ""),
                p.get("fecha_publicacion", ""),
                p.get("tienda", ""),
                p.get("marca", ""),
                p.get("descuento_pct", ""),
                "Si" if p.get("tiene_44_5_45") else "No",
                p.get("vendedor", ""),
                p.get("sku", ""),
                p.get("imagen", ""),
                "Si" if p.get("disponible") else "No",
                p.get("fecha_actualizacion", ""),
            ])
    print(f"  CSV -> {csv_path.relative_to(ROOT)} ({len(productos)} filas)")

    # ---- JSON para el visor ----
    por_tienda: dict[str, int] = {}
    for p in productos:
        por_tienda[p["tienda"]] = por_tienda.get(p["tienda"], 0) + 1
    payload = {
        "generado": now_iso,
        "total": len(productos),
        "con_talla_44_5_45": sum(1 for p in productos if p["tiene_44_5_45"]),
        "por_tienda": por_tienda,
        "productos": productos,
    }
    json_path = DOCS_DATA / "productos.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"  JSON -> {json_path.relative_to(ROOT)}")

    FIRST_SEEN_PATH.write_text(json.dumps(first_seen, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  Total consolidado: {len(productos)} | con talla 44.5/45: {payload['con_talla_44_5_45']}")
    print(f"  Por tienda: {por_tienda}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
