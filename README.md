# 👟 Visor de Zapatillas · Chile

Scraper diario + base consolidada + visor web para comparar **zapatillas de hombre**
(urbanas y deportivas) entre **Falabella, Ripley y Paris**, pensado para encontrar
talla **44.5 / 45**.

**Sitio (una vez activado GitHub Pages):**
👉 https://franciscochaconbascunan-beep.github.io/visor_zapatillas/

---

## ¿Qué hace?

1. **Scrapea** cada tienda con su propio módulo (estructura distinta en cada una).
2. **Consolida** todo en una base homologada (`data/consolidado.csv`) y un JSON para el visor.
3. **Muestra** los productos en una página web con filtros (tienda, marca, precio, talla,
   descuento), vista de tarjetas / tabla / métricas.
4. **Se actualiza solo** cada día vía GitHub Actions.

## Estructura

```
scrapers/
  common.py       Utilidades compartidas + esquema normalizado
  falabella.py    Parsea __NEXT_DATA__ (incluye tallas con stock -> confirma 44.5/45)
  ripley.py       Parsea __NEXT_DATA__ (link vía parentProductID)
  paris.py        Parsea JSON-LD schema.org (ItemList)
consolidate.py    Une las 3 fuentes -> data/consolidado.csv + docs/data/productos.json
docs/             Sitio de GitHub Pages (index.html + data/productos.json)
data/             Crudos por tienda, base consolidada y first_seen.json
.github/workflows/daily.yml   Automatización diaria
```

## Base consolidada — columnas

`Precio` (normal/lista) · `Talla` · `Valor` (precio final que pagas) · `Modelo` ·
`Link` · `Fecha_publicacion` · `Tienda` · `Marca` · `Descuento_%` · `Tiene_44.5/45` ·
`Vendedor` · `SKU` · `Imagen` · `Disponible` · `Fecha_actualizacion`

> **Precio vs Valor:** `Precio` = precio normal tachado; `Valor` = precio de oferta/actual.
> **Fecha_publicacion:** el retail no expone la fecha real del aviso, así que se usa como
> proxy la **primera fecha en que detectamos el producto** (persistida en `data/first_seen.json`).

## Correr localmente

```bash
pip install -r requirements.txt
python scrapers/falabella.py
python scrapers/ripley.py
python scrapers/paris.py
python consolidate.py
python -m http.server 8137 -d docs   # abrir http://localhost:8137/
```

## Activar el sitio (GitHub Pages) — paso único

En GitHub: **Settings → Pages → Source: _Deploy from a branch_ → Branch `main` / carpeta `/docs` → Save**.
En 1-2 minutos el sitio queda publicado en el link de arriba. El workflow diario commitea el
JSON actualizado y el sitio se refresca solo.

## Notas y límites

- **Talla 44.5/45:** solo **Falabella** entrega tallas con stock en el listado, así que la
  confirmación de talla aplica a Falabella. Para Ripley/Paris revisa la talla en el aviso.
- **Paris:** vía JSON-LD trae ~30 productos (solo la primera página que renderiza el servidor).
  Para cobertura total habría que usar el **Plan B con Playwright** (headless + scroll), no
  activado por defecto para no fragilizar GitHub Actions.
- Scrapear retail es frágil: si una tienda cambia su HTML, se ajusta solo su módulo en `scrapers/`.
- Uso personal de comparación de precios.
