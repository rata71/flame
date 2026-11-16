#!/usr/bin/env python3
"""
Script para consultar el índice NDVI desde la API REST pública de NASA ORNL DAAC MODIS (MOD13Q1).
Incluye reintentos automáticos y tiempo de espera ampliado para evitar errores de ReadTimeout.

Requisitos:
    pip install requests

Uso por línea de comandos:
    python consultar_ndvi_modis.py -33.3017 -66.3378 2024-02-15
"""

import sys
import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def crear_sesion_con_reintentos(reintentos=3, backoff_factor=2.0):
    """Crea una sesión HTTP con reintentos automáticos ante demoras o fallos temporales."""
    sesion = requests.Session()
    estrategia_reintento = Retry(
        total=reintentos,
        read=reintentos,
        connect=reintentos,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adaptador = HTTPAdapter(max_retries=estrategia_reintento)
    sesion.mount("https://", adaptador)
    sesion.mount("http://", adaptador)
    return sesion


def obtener_ndvi_modis(lat: float, lon: float, fecha_str: str, ventana_dias: int = 16, timeout: int = 90):
    """
    Obtiene el NDVI de MODIS (MOD13Q1 - 250m) para una coordenada y fecha específica.

    Args:
        lat (float): Latitud en grados decimales (ej. -33.3017).
        lon (float): Longitud en grados decimales (ej. -66.3378).
        fecha_str (str): Fecha en formato YYYY-MM-DD (ej. '2024-02-15').
        ventana_dias (int): Días hacia atrás y adelante para buscar el compuesto más cercano.
        timeout (int): Tiempo máximo de espera en segundos (por defecto 90s).

    Returns:
        list[dict]: Lista con las mediciones encontradas y el NDVI escalado.
    """
    try:
        fecha = datetime.datetime.strptime(fecha_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError("El formato de fecha debe ser YYYY-MM-DD (ejemplo: 2024-02-15).")

    inicio = fecha - datetime.timedelta(days=ventana_dias)
    fin = fecha + datetime.timedelta(days=ventana_dias)

    start_julian = f"A{inicio.year}{inicio.timetuple().tm_yday:03d}"
    end_julian = f"A{fin.year}{fin.timetuple().tm_yday:03d}"

    url = "https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset"
    params = {
        "latitude": lat,
        "longitude": lon,
        "band": "250m_16_days_NDVI",
        "startDate": start_julian,
        "endDate": end_julian,
        "kmAboveBelow": 0,
        "kmLeftRight": 0
    }

    sesion = crear_sesion_con_reintentos()

    try:
        respuesta = sesion.get(url, params=params, timeout=timeout)
        respuesta.raise_for_status()
        datos = respuesta.json()
    except requests.exceptions.ReadTimeout:
        raise RuntimeError(
            f"El servidor de NASA ORNL DAAC tardó más de {timeout} segundos en responder. "
            "Suele ocurrir cuando el servidor extrae datos en tiempo real bajo alta demanda. "
            "Intenta nuevamente en unos minutos o aumenta el parámetro timeout."
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Error al consultar la API de NASA MODIS: {e}")

    resultados = []
    for item in datos.get("subset", []):
        fecha_dato = item.get("calendar_date")
        valores = item.get("data", [])

        if valores and valores[0] != -3000:
            valor_crudo = valores[0]
            ndvi_real = round(valor_crudo * 0.0001, 4)
            diferencia_dias = abs((datetime.datetime.strptime(fecha_dato, "%Y-%m-%d") - fecha).days)
            resultados.append({
                "fecha_compuesta": fecha_dato,
                "fecha_modis": item.get("modis_date"),
                "ndvi": ndvi_real,
                "diferencia_dias": diferencia_dias
            })

    resultados.sort(key=lambda x: x["diferencia_dias"])
    return resultados


if __name__ == "__main__":
    if len(sys.argv) == 4:
        lat_in = float(sys.argv[1])
        lon_in = float(sys.argv[2])
        fecha_in = sys.argv[3]
    else:
        lat_in = -33.3017
        lon_in = -66.3378
        fecha_in = "2024-02-15"
        print(f"Usando valores de ejemplo -> Lat: {lat_in}, Lon: {lon_in}, Fecha: {fecha_in}\n")

    print("Consultando servidor de NASA MODIS (puede demorar entre 15 y 60 segundos)...")
    try:
        registros = obtener_ndvi_modis(lat_in, lon_in, fecha_in)
        if not registros:
            print("No se encontraron datos válidos de NDVI para esa coordenada y fecha (posible cuerpo de agua o sin cobertura).")
        else:
            print(f"Resultados encontrados (ordenados por cercanía a {fecha_in}):\n")
            for r in registros:
                print(f"- Fecha compuesta: {r['fecha_compuesta']} ({r['fecha_modis']}) | NDVI: {r['ndvi']} (a {r['diferencia_dias']} días)")
    except Exception as err:
        print(f"Error: {err}")
