"""
Utilidades compartidas por los tres scrapers (Falabella, Ripley, Paris).

Cada scraper produce una lista de "registros normalizados" con el MISMO esquema,
para que consolidate.py solo tenga que unirlos. El esquema es:

    {
      "tienda":            str,        # "Falabella" | "Ripley" | "Paris"
      "modelo":            str,        # nombre del producto
      "marca":             str,
      "precio_normal":     int | None, # Precio (lista / tachado), en CLP
      "precio_oferta":     int | None, # Valor (lo que pagas hoy), en CLP
      "descuento_pct":     int | None,
      "link":              str,        # URL directa al aviso
      "sku":               str,        # id único dentro de la tienda
      "imagen":            str,        # URL de miniatura
      "vendedor":          str,        # tienda propia vs marketplace/tercero
      "tallas_disponibles":list[str],  # tallas con stock (solo si la fuente lo entrega)
      "tiene_44_5_45":     bool,       # True si 44.5 o 45 está confirmada con stock
      "disponible":        bool,
    }
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Rutas del proyecto
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# Tallas objetivo del usuario. Se normalizan comas -> puntos antes de comparar.
TARGET_SIZES = {"44.5", "45"}

# Encabezados "de navegador real" para reducir bloqueos anti-bot.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(DEFAULT_HEADERS)
    return s


def fetch(session: requests.Session, url: str, *, retries: int = 3, timeout: int = 30) -> str:
    """GET con reintentos y backoff. Devuelve el texto o lanza la última excepción."""
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=timeout)
            r.raise_for_status()
            return r.text
        except Exception as exc:  # noqa: BLE001
            last = exc
            wait = 2 * attempt
            print(f"    [retry {attempt}/{retries}] {url} -> {exc} (espera {wait}s)")
            time.sleep(wait)
    raise last  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Helpers de parsing
# ---------------------------------------------------------------------------
def parse_price(value) -> int | None:
    """Convierte '$ 26.990', '26.990', 24990, ['26.990'] -> 26990 (int CLP)."""
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
        if value is None:
            return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None


def norm_size(raw: str) -> str:
    """Normaliza una talla: '44,5' -> '44.5', '45.0' -> '45', '  45 ' -> '45'."""
    s = str(raw).strip().replace(",", ".")
    if s.endswith(".0"):
        s = s[:-2]
    return s


def has_target_size(sizes) -> bool:
    return any(norm_size(s) in TARGET_SIZES for s in (sizes or []))


def discount_pct(normal: int | None, oferta: int | None) -> int | None:
    if normal and oferta and normal > 0 and oferta < normal:
        return round((normal - oferta) / normal * 100)
    return None


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text


def make_record(
    *,
    tienda: str,
    modelo: str,
    marca: str = "",
    precio_normal: int | None = None,
    precio_oferta: int | None = None,
    link: str = "",
    sku: str = "",
    imagen: str = "",
    vendedor: str = "",
    tallas_disponibles=None,
    disponible: bool = True,
) -> dict:
    tallas = [norm_size(t) for t in (tallas_disponibles or [])]
    # Si no hay precio de oferta, el "valor" = precio normal (y viceversa).
    if precio_oferta is None:
        precio_oferta = precio_normal
    if precio_normal is None:
        precio_normal = precio_oferta
    return {
        "tienda": tienda,
        "modelo": (modelo or "").strip(),
        "marca": (marca or "").strip(),
        "precio_normal": precio_normal,
        "precio_oferta": precio_oferta,
        "descuento_pct": discount_pct(precio_normal, precio_oferta),
        "link": link,
        "sku": str(sku),
        "imagen": imagen,
        "vendedor": (vendedor or tienda).strip(),
        "tallas_disponibles": tallas,
        "tiene_44_5_45": has_target_size(tallas),
        "disponible": disponible,
    }


def save_raw(store_key: str, records: list[dict]) -> Path:
    path = DATA_DIR / f"raw_{store_key}.json"
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {len(records)} productos guardados en {path.relative_to(ROOT)}")
    return path
