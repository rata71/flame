import argparse
import math
import os
import sys
from datetime import datetime, timedelta
import pandas as pd
import pystac_client
import rasterio
import requests
from pyproj import Transformer

# Optimizaciones de lectura remota para COG (Cloud Optimized GeoTIFF)
os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
os.environ["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".tif"


# ==============================================================================
# ECUACIONES OFICIALES DEL SISTEMA CANADIENSE FWI (VAN WAGNER, 1987)
# ==============================================================================
def calcular_ffmc(temp, rh, wind, rain, ffmc_prev):
    mo = 147.2 * (101.0 - ffmc_prev) / (59.5 + ffmc_prev)
    if rain > 0.5:
        rf = rain - 0.5
        if mo <= 150.0:
            mr = (
                mo
                + 42.5
                * rf
                * math.exp(-100.0 / (251.0 - mo))
                * (1.0 - math.exp(-6.93 / rf))
            )
        else:
            mr = (
                mo
                + 42.5
                * rf
                * math.exp(-100.0 / (251.0 - mo))
                * (1.0 - math.exp(-6.93 / rf))
                + 0.0015 * ((mo - 150.0) ** 2) * math.sqrt(rf)
            )
        mo = min(250.0, mr)

    ed = (
        0.942 * (rh ** 0.679)
        + 11.0 * math.exp((rh - 100.0) / 10.0)
        + 0.18 * (21.1 - temp) * (1.0 - math.exp(-0.115 * rh))
    )
    if mo > ed:
        ko = 0.424 * (1.0 - (rh / 100.0) ** 1.7) + 0.0694 * math.sqrt(wind) * (
            1.0 - (rh / 100.0) ** 8
        )
        kd = ko * 0.581 * math.exp(0.0365 * temp)
        m = ed + (mo - ed) * (10.0 ** (-kd))
    else:
        ew = (
            0.618 * (rh ** 0.753)
            + 10.0 * math.exp((rh - 100.0) / 10.0)
            + 0.18 * (21.1 - temp) * (1.0 - math.exp(-0.115 * rh))
        )
        if mo < ew:
            kl = 0.424 * (1.0 - ((100.0 - rh) / 100.0) ** 1.7) + 0.0694 * math.sqrt(
                wind
            ) * (1.0 - ((100.0 - rh) / 100.0) ** 8)
            kw = kl * 0.581 * math.exp(0.0365 * temp)
            m = ew - (ew - mo) * (10.0 ** (-kw))
        else:
            m = mo

    ffmc = 59.5 * (250.0 - m) / (147.2 + m)
    return max(0.0, min(101.0, ffmc))


def calcular_dmc(temp, rh, rain, dmc_prev, mes, lat):
    le_norte = [6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0]
    le_sur = [12.4, 10.9, 9.4, 8.0, 7.0, 6.0, 6.5, 7.5, 9.0, 12.8, 13.9, 13.9]
    le = le_sur[mes - 1] if lat < 0 else le_norte[mes - 1]

    if rain > 1.5:
        re = 0.92 * rain - 1.27
        mo = 20.0 + math.exp(5.6348 - dmc_prev / 43.43)
        if dmc_prev <= 33.0:
            b = 100.0 / (0.5 + 0.3 * dmc_prev)
        elif dmc_prev <= 65.0:
            b = 14.0 - 1.3 * math.log(dmc_prev)
        else:
            b = 6.2 * math.log(dmc_prev) - 17.2
        mr = mo + 1000.0 * re / (48.77 + b * re)
        pr = 244.72 - 43.43 * math.log(mr - 20.0)
        dmc_prev = max(0.0, pr)

    t_eff = max(-1.1, temp)
    k = 1.894 * (t_eff + 1.1) * (100.0 - rh) * le * 1e-6
    return max(0.0, dmc_prev + 100.0 * k)


def calcular_dc(temp, rain, dc_prev, mes, lat):
    lf_norte = [-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6]
    lf_sur = [6.4, 5.0, 2.4, 0.4, -1.6, -1.6, -1.6, -1.6, -1.6, 0.9, 3.8, 5.8]
    lf = lf_sur[mes - 1] if lat < 0 else lf_norte[mes - 1]

    if rain > 2.8:
        rd = 0.83 * rain - 1.27
        qo = 800.0 * math.exp(-dc_prev / 400.0)
        qr = qo + 3.937 * rd
        dr = 400.0 * math.log(800.0 / qr)
        dc_prev = max(0.0, dr)

    t_eff = max(-2.8, temp)
    v = max(0.0, 0.36 * (t_eff + 2.8) + lf)
    return max(0.0, dc_prev + 0.5 * v)


def calcular_isi(ffmc, wind):
    m = 147.2 * (101.0 - ffmc) / (59.5 + ffmc)
    f_wind = math.exp(0.05039 * wind)
    f_ffmc = 91.9 * math.exp(-0.1386 * m) * (1.0 + (m ** 5.31) / 4.93e7)
    return 0.208 * f_wind * f_ffmc


def calcular_bui(dmc, dc):
    if dmc == 0 and dc == 0:
        return 0.0
    if dmc <= 0.4 * dc:
        u = 0.8 * dmc * dc / (dmc + 0.4 * dc)
    else:
        u = dmc - (1.0 - 0.8 * dc / (dmc + 0.4 * dc)) * (
            0.92 + (0.0114 * dmc) ** 1.7
        )
    return max(0.0, u)


def calcular_fwi(isi, bui):
    if bui <= 80.0:
        f_d = 0.626 * (bui ** 0.809) + 2.0
    else:
        f_d = 1000.0 / (25.0 + 108.64 * math.exp(-0.023 * bui))

    b = 0.1 * isi * f_d
    if b > 1.0:
        s = math.exp(2.72 * ((0.434 * math.log(b)) ** 0.647))
    else:
        s = b
    return s


# ==============================================================================
# EXTRACCIÓN RÁPIDA DE NDVI EN LOTE CON CACHÉ POR ESCENA
# ==============================================================================
def leer_valor_pixel(url_cog, lat, lon):
    with rasterio.open(url_cog) as src:
        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        x, y = transformer.transform(lon, lat)
        muestra = next(src.sample([(x, y)]))
        return float(muestra.item())


def obtener_ndvi_serie(fechas_utc, lat, lon, margen_dias=15, max_nubes=20):
    """
    Realiza una sola búsqueda STAC para todo el rango y cachea los valores NDVI
    de cada escena satelital para evitar lecturas repetidas.
    """
    if len(fechas_utc) == 0:
        return {}

    partes = ["https://", "earth-search", ".aws.", "element84", ".com/v1"]
    url_api = "".join(partes)
    catalog = pystac_client.Client.open(url_api)

    min_fecha = min(fechas_utc).tz_localize(None) - timedelta(days=margen_dias)
    max_fecha = max(fechas_utc).tz_localize(None) + timedelta(days=margen_dias)

    search = catalog.search(
        collections=["sentinel-2-l2a"],
        intersects={"type": "Point", "coordinates": [lon, lat]},
        datetime=f"{min_fecha.strftime('%Y-%m-%d')}/{max_fecha.strftime('%Y-%m-%d')}",
        query={"eo:cloud_cover": {"lt": max_nubes}},
    )

    items = list(search.items())
    resultados_por_fecha = {}
    cache_escenas = {}  # Guarda {item.id: (ndvi, nubosidad)}

    for fecha_ts in fechas_utc:
        fecha_naive = fecha_ts.tz_localize(None)
        if not items:
            resultados_por_fecha[fecha_ts] = (None, None)
            continue

        # Buscar la escena más cercana dentro del margen permitido
        mejor_item = min(
            items,
            key=lambda it: abs((it.datetime.replace(tzinfo=None) - fecha_naive).total_seconds()),
        )
        diff_dias = abs((mejor_item.datetime.replace(tzinfo=None) - fecha_naive).total_seconds()) / 86400.0

        if diff_dias > margen_dias:
            resultados_por_fecha[fecha_ts] = (None, None)
            continue

        # Si ya calculamos esta escena satelital, reutilizar desde caché (0 ms)
        if mejor_item.id not in cache_escenas:
            url_b04 = mejor_item.assets["red"].href
            url_b08 = mejor_item.assets["nir"].href

            rojo = leer_valor_pixel(url_b04, lat, lon)
            nir = leer_valor_pixel(url_b08, lat, lon)

            ndvi = 0.0 if (nir + rojo) == 0 else (nir - rojo) / (nir + rojo)
            nubosidad = mejor_item.properties.get("eo:cloud_cover")
            cache_escenas[mejor_item.id] = (
                round(ndvi, 4),
                round(float(nubosidad), 2) if nubosidad is not None else None,
            )

        resultados_por_fecha[fecha_ts] = cache_escenas[mejor_item.id]

    return resultados_por_fecha


# ==============================================================================
# CONSULTA Y PROCESAMIENTO EN FORMATO CSV CON DECIMALES CON COMA
# ==============================================================================
def obtener_datos_rango_fwi(
    fecha_inicio_str, fecha_fin_str, lat, lon, user, password, spinup_days=30, margen_ndvi_dias=15
):
    # 12:00:00 hora de Argentina (UTC-3) corresponde exactamente a 15:00:00 UTC
    dt_inicio_objetivo = datetime.strptime(
        f"{fecha_inicio_str} 15:00:00", "%Y-%m-%d %H:%M:%S"
    )
    dt_fin_objetivo = datetime.strptime(
        f"{fecha_fin_str} 15:00:00", "%Y-%m-%d %H:%M:%S"
    )

    if dt_fin_objetivo < dt_inicio_objetivo:
        raise ValueError("La fecha_fin no puede ser anterior a fecha_inicio.")

    # Retroceder días de estabilización desde la fecha inicial del rango
    dt_inicio_consulta = dt_inicio_objetivo - timedelta(days=spinup_days)

    rango_tiempo = (
        f"{dt_inicio_consulta.strftime('%Y-%m-%dT%H:%M:%SZ')}--"
        f"{dt_fin_objetivo.strftime('%Y-%m-%dT%H:%M:%SZ')}:P1D"
    )

    parametros = [
        "forest_fire_warning:idx",
        "fosberg_fire_weather_index:idx",
        "drought_index:idx",
        "t_2m:C",
        "relative_humidity_2m:p",
        "wind_speed_10m:kmh",
        "precip_24h:mm",
    ]
    url = f"https://api.meteomatics.com/{rango_tiempo}/{','.join(parametros)}/{lat},{lon}/json"

    respuesta = requests.get(url, auth=(user, password), timeout=30)
    if respuesta.status_code != 200:
        raise Exception(
            f"Error en API ({respuesta.status_code}): {respuesta.text}"
        )

    registros = {}
    for item in respuesta.json()["data"]:
        param = item["parameter"]
        for coord in item["coordinates"]:
            for entry in coord["dates"]:
                fecha = entry["date"]
                if fecha not in registros:
                    registros[fecha] = {"validdate": fecha}
                registros[fecha][param] = entry["value"]

    df = pd.DataFrame(list(registros.values()))
    df["validdate_utc"] = pd.to_datetime(df["validdate"])
    df = df.sort_values("validdate_utc").reset_index(drop=True)

    # Cálculo secuencial de índices FWI desde el inicio del spin-up
    ffmc_val, dmc_val, dc_val = 85.0, 6.0, 15.0
    ffmc_list, dmc_list, dc_list, isi_list, bui_list, fwi_list = (
        [],
        [],
        [],
        [],
        [],
        [],
    )

    for _, row in df.iterrows():
        t = row["t_2m:C"]
        rh = row["relative_humidity_2m:p"]
        w = row["wind_speed_10m:kmh"]
        p = row["precip_24h:mm"]
        mes = row["validdate_utc"].month

        ffmc_val = calcular_ffmc(t, rh, w, p, ffmc_val)
        dmc_val = calcular_dmc(t, rh, p, dmc_val, mes, lat)
        dc_val = calcular_dc(t, p, dc_val, mes, lat)
        isi_val = calcular_isi(ffmc_val, w)
        bui_val = calcular_bui(dmc_val, dc_val)
        fwi_val = calcular_fwi(isi_val, bui_val)

        ffmc_list.append(round(ffmc_val, 2))
        dmc_list.append(round(dmc_val, 2))
        dc_list.append(round(dc_val, 2))
        isi_list.append(round(isi_val, 2))
        bui_list.append(round(bui_val, 2))
        fwi_list.append(round(fwi_val, 2))

    df["FFMC"] = ffmc_list
    df["DMC"] = dmc_list
    df["DC"] = dc_list
    df["ISI"] = isi_list
    df["BUI"] = bui_list
    df["FWI"] = fwi_list

    # Filtrar únicamente el rango de fechas solicitado por el usuario
    df_filtrado = df[
        df["validdate_utc"] >= pd.Timestamp(dt_inicio_objetivo, tz="UTC")
    ].copy()

    # Consultar NDVI y nubosidad en lote para las fechas filtradas
    mapa_ndvi = obtener_ndvi_serie(
        df_filtrado["validdate_utc"].tolist(),
        lat=lat,
        lon=lon,
        margen_dias=margen_ndvi_dias,
    )

    df_filtrado["ndvi"] = df_filtrado["validdate_utc"].map(
        lambda f: mapa_ndvi.get(f, (None, None))[0]
    )
    df_filtrado["nubosidad_escena_%"] = df_filtrado["validdate_utc"].map(
        lambda f: mapa_ndvi.get(f, (None, None))[1]
    )

    # Convertir la fecha a hora local de Argentina (UTC-3)
    df_filtrado["fecha_hora_argentina"] = (
        df_filtrado["validdate_utc"] - pd.Timedelta(hours=3)
    ).dt.strftime("%Y-%m-%d %H:%M:%S")

    # Columna de coordenada
    df_filtrado["coordenada"] = f"{lat},{lon}"

    # Ordenar exactamente las columnas solicitadas incluyendo NDVI y nubosidad
    columnas_finales = [
        "coordenada",
        "fecha_hora_argentina",
        "forest_fire_warning:idx",
        "fosberg_fire_weather_index:idx",
        "drought_index:idx",
        "t_2m:C",
        "relative_humidity_2m:p",
        "wind_speed_10m:kmh",
        "precip_24h:mm",
        "FFMC",
        "DMC",
        "DC",
        "ISI",
        "BUI",
        "FWI",
        "ndvi",
        "nubosidad_escena_%",
    ]

    return df_filtrado[columnas_finales]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Obtiene datos de Meteomatics, calcula FWI y cruza NDVI/nubosidad en formato CSV."
    )
    parser.add_argument(
        "--inicio",
        required=True,
        help="Fecha inicial del rango (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--fin",
        required=True,
        help="Fecha final del rango (YYYY-MM-DD)",
    )
    parser.add_argument("--lat", type=float, required=True, help="Latitud")
    parser.add_argument("--lon", type=float, required=True, help="Longitud")
    parser.add_argument(
        "--margen_ndvi",
        type=int,
        default=15,
        help="Margen máximo de días para buscar imagen satelital cercana (default: 15)",
    )
    args = parser.parse_args()

    try:
        df_csv = obtener_datos_rango_fwi(
            fecha_inicio_str=args.inicio,
            fecha_fin_str=args.fin,
            lat=args.lat,
            lon=args.lon,
            user="hackathon_nasa_space_apps_arenas_antoniogabriel",
            password="85997DuLziV7hR8984Ay",
            margen_ndvi_dias=args.margen_ndvi,
        )

        # Generar salida CSV con punto y coma (;) como delimitador de columnas
        # y coma (,) como separador decimal (estándar Excel/CSV en español)
        csv_texto = df_csv.to_csv(index=False, sep=";", decimal=",")
        print(csv_texto, end="")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
