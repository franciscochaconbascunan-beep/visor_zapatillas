"""
Consolida los crudos de las tres tiendas (data/raw_*.json) en:
  - data/consolidado.csv          (base homologada, lista para Excel)
  - docs/data/productos.json      (lo que consume el visor web)

Columnas de la base consolidada (en el orden pedido + extras):
  Precio | Talla | Valor | Modelo | Link | Fecha_publicacion | Tienda
  + Marca | Descuento_% | Tiene_44.5/45 | Vendedor | SKU | Imagen | Disponible
  + Fecha_actualizacion
  + Precio_min_historico | Fecha_min_historico | Precio_anterior | Variacion_$
  + Es_minimo_historico | Dias_seguimiento | Modelo_clave

Persistencia entre corridas:
  - data/first_seen.json        -> primera fecha vista (proxy de "fecha de publicación")
  - data/historial_precios.json -> serie {fecha, valor} por producto, para ver la
    evolución del precio en el tiempo. Se construye HACIA ADELANTE (desde hoy).

Uso:  python consolidate.py
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scrapers"))
import common  # noqa: E402

DATA_DIR = ROOT / "data"
DOCS_DATA = ROOT / "docs" / "data"
DOCS_DATA.mkdir(parents=True, exist_ok=True)

STORES = ["falabella", "ripley", "paris"]
FIRST_SEEN_PATH = DATA_DIR / "first_seen.json"
HIST_PATH = DATA_DIR / "historial_precios.json"
HIST_MAX = 60  # máximo de puntos de historial que se guardan por producto

CSV_COLUMNS = [
    "Precio", "Talla", "Valor", "Modelo", "Link", "Fecha_publicacion", "Tienda",
    "Marca", "Descuento_%", "Tiene_44.5/45", "Vendedor", "SKU", "Imagen",
    "Disponible", "Fecha_actualizacion",
    "Precio_min_historico", "Fecha_min_historico", "Precio_anterior",
    "Variacion_$", "Es_minimo_historico", "Dias_seguimiento", "Modelo_clave",
]


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return default
    return default


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


def update_history(entries: list[dict], valor, today: str) -> list[dict]:
    """Agrega hoy a la serie solo si el precio cambió respecto al último punto."""
    if valor is None:
        return entries
    if not entries or entries[-1]["v"] != valor:
        entries = entries + [{"f": today, "v": valor}]
    return entries[-HIST_MAX:]


def derive_history_fields(entries: list[dict], valor, today: str) -> dict:
    valores = [e["v"] for e in entries]
    if not valores:
        return {
            "precio_min_hist": valor, "fecha_min_hist": today,
            "precio_max_hist": valor, "precio_anterior": None,
            "variacion": None, "es_minimo_historico": False,
            "historial_suficiente": False, "dias_seguimiento": 0,
            "historial": [],
        }
    pmin = min(valores)
    fecha_min = entries[valores.index(pmin)]["f"]
    precio_anterior = valores[-2] if len(valores) >= 2 else None
    variacion = (valor - precio_anterior) if (valor is not None and precio_anterior is not None) else None
    suficiente = len(valores) >= 2
    try:
        dias = (date.fromisoformat(today) - date.fromisoformat(entries[0]["f"])).days
    except Exception:  # noqa: BLE001
        dias = 0
    return {
        "precio_min_hist": pmin,
        "fecha_min_hist": fecha_min,
        "precio_max_hist": max(valores),
        "precio_anterior": precio_anterior,
        "variacion": variacion,
        "es_minimo_historico": bool(valor is not None and suficiente and valor <= pmin),
        "historial_suficiente": suficiente,
        "dias_seguimiento": dias,
        "historial": entries,
    }


def main() -> int:
    print("== Consolidando ==")
    raw = load_raw()
    if not raw:
        print("  No hay datos crudos. Corre primero los scrapers.")
        return 1

    first_seen = load_json(FIRST_SEEN_PATH, {})
    historial = load_json(HIST_PATH, {})
    today = date.today().isoformat()
    now_iso = datetime.now().isoformat(timespec="seconds")

    consolidated: dict[str, dict] = {}
    descartados_marca = 0
    for r in raw:
        if not common.brand_allowed(r.get("marca", ""), r.get("modelo", "")):
            descartados_marca += 1
            continue  # fuera del filtro de marcas (Adidas/Nike)
        key = f"{r['tienda']}|{r['sku']}"
        if key in consolidated:
            continue  # dedup global por tienda+sku
        if key not in first_seen:
            first_seen[key] = today

        valor = r.get("precio_oferta")
        historial[key] = update_history(historial.get(key, []), valor, today)
        hist_fields = derive_history_fields(historial[key], valor, today)

        tallas = r.get("tallas_disponibles") or []
        producto = {
            **r,
            "talla": ", ".join(tallas) if tallas else "s/info",
            "fecha_publicacion": first_seen[key],
            "fecha_actualizacion": now_iso,
            "modelo_clave": common.modelo_clave(r.get("marca", ""), r.get("modelo", "")),
            **hist_fields,
        }
        consolidated[key] = producto

    productos = list(consolidated.values())
    # Orden por defecto: talla confirmada, luego mínimo histórico, luego mayor descuento.
    productos.sort(key=lambda p: (
        not p["tiene_44_5_45"], not p["es_minimo_historico"], -(p.get("descuento_pct") or 0)
    ))

    # ---- CSV consolidado ----
    csv_path = DATA_DIR / "consolidado.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for p in productos:
            w.writerow([
                p.get("precio_normal", ""), p.get("talla", ""), p.get("precio_oferta", ""),
                p.get("modelo", ""), p.get("link", ""), p.get("fecha_publicacion", ""),
                p.get("tienda", ""), p.get("marca", ""), p.get("descuento_pct", ""),
                "Si" if p.get("tiene_44_5_45") else "No", p.get("vendedor", ""),
                p.get("sku", ""), p.get("imagen", ""), "Si" if p.get("disponible") else "No",
                p.get("fecha_actualizacion", ""),
                p.get("precio_min_hist", ""), p.get("fecha_min_hist", ""),
                p.get("precio_anterior", "") if p.get("precio_anterior") is not None else "",
                p.get("variacion", "") if p.get("variacion") is not None else "",
                "Si" if p.get("es_minimo_historico") else "No",
                p.get("dias_seguimiento", 0), p.get("modelo_clave", "") or "",
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
        "en_minimo_historico": sum(1 for p in productos if p["es_minimo_historico"]),
        "por_tienda": por_tienda,
        "marcas_filtro": sorted(common.BRAND_ALLOW),
        "productos": productos,
    }
    json_path = DOCS_DATA / "productos.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"  JSON -> {json_path.relative_to(ROOT)}")

    FIRST_SEEN_PATH.write_text(json.dumps(first_seen, ensure_ascii=False, indent=2), encoding="utf-8")
    HIST_PATH.write_text(json.dumps(historial, ensure_ascii=False), encoding="utf-8")

    if common.BRAND_ALLOW:
        print(f"  Filtro de marcas {sorted(common.BRAND_ALLOW)}: {descartados_marca} descartados")
    print(f"  Total: {len(productos)} | talla 44.5/45: {payload['con_talla_44_5_45']}"
          f" | en mínimo histórico: {payload['en_minimo_historico']}")
    print(f"  Historial: {len(historial)} productos siguiendo precio")
    print(f"  Por tienda: {por_tienda}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
