import os
import time
from datetime import datetime, timedelta
import pystac_client
import rasterio
from pyproj import Transformer

os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
os.environ["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".tif"

def obtener_ndvi_punto(lat: float, lon: float, fecha_objetivo: str, margen_dias: int = 15):
    inicio = time.time()

    # Armamos la URL pieza por pieza para evitar cualquier alteración al copiar
    partes = ["https://", "earth-search", ".aws.", "element84", ".com/v1"]
    url_api = "".join(partes)
    
    catalog = pystac_client.Client.open(url_api)

    fecha_dt = datetime.strptime(fecha_objetivo, "%Y-%m-%d")
    fecha_inicio = (fecha_dt - timedelta(days=margen_dias)).strftime("%Y-%m-%d")
    fecha_fin = (fecha_dt + timedelta(days=margen_dias)).strftime("%Y-%m-%d")

    search = catalog.search(
        collections=["sentinel-2-l2a"],
        intersects={"type": "Point", "coordinates": [lon, lat]},
        datetime=f"{fecha_inicio}/{fecha_fin}",
        query={"eo:cloud_cover": {"lt": 20}},
    )

    items = list(search.items())
    if not items:
        return {"error": "No se encontraron imágenes sin nubes en ese rango de fechas."}

    items.sort(key=lambda item: abs((item.datetime.replace(tzinfo=None) - fecha_dt).total_seconds()))
    mejor_escena = next(iter(items))

    url_b04 = mejor_escena.assets["red"].href
    url_b08 = mejor_escena.assets["nir"].href

    def leer_valor_pixel(url_cog, lat, lon):
        with rasterio.open(url_cog) as src:
            transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            x, y = transformer.transform(lon, lat)
            muestra = next(src.sample([(x, y)]))
            return float(muestra.item())

    rojo = leer_valor_pixel(url_b04, lat, lon)
    nir = leer_valor_pixel(url_b08, lat, lon)

    ndvi = 0.0 if (nir + rojo) == 0 else (nir - rojo) / (nir + rojo)
    tiempo_total = round(time.time() - inicio, 3)

    return {
        "ndvi": round(ndvi, 4),
        "fecha_escena": mejor_escena.datetime.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "nubosidad_escena_%": mejor_escena.properties.get("eo:cloud_cover"),
        "escena_id": mejor_escena.id,
        "tiempo_respuesta_seg": tiempo_total
    }

if __name__ == "__main__":
    print("Consultando AWS Earth Search...")
    resultado = obtener_ndvi_punto(
        lat=-33.675, 
        lon=-65.462, 
        fecha_objetivo="2026-11-10",
        margen_dias=15
    )
    print(resultado)