import pandas as pd
import requests
from io import StringIO
import time

# Configuración de pandas para imprimir TODAS las filas y TODAS las columnas sin recortar
pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

MAP_KEY = "cf115e26cdb5e9ae15e5685db23d0ba6"
AREA = "-67.5,-36.0,-63.5,-31.8"
FECHA = "2019-10-04"
DIAS = 5

INSTRUMENTOS = [
    "MODIS_SP",
    "VIIRS_SNPP_SP",
    "VIIRS_NOAA20_SP"
]

def es_confianza_valida(valor):
    if pd.isna(valor):
        return False
    val_str = str(valor).strip().lower()
    
    # Si es letra "l" (low), ignorar el registro
    if val_str == 'l':
        return False
        
    # Si es un número, validar que sea >= 45
    try:
        num = float(val_str)
        return num >= 45
    except ValueError:
        # Si es otra letra (ej. 'n' o 'h'), se conserva el registro
        return True

dataframes = []

for inst in INSTRUMENTOS:
    # url = f"https://nasa.gov{MAP_KEY}/{inst}/{AREA}/{DIAS}/{FECHA}"
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{inst}/{AREA}/{DIAS}/2019-10-04"
    resp = requests.get(url)
    
    if resp.status_code == 200 and "latitude" in resp.text:
        df_temp = pd.read_csv(StringIO(resp.text))
        if not df_temp.empty:
            # 1. Filtrar registros según la validación de 'confidence'
            if "confidence" in df_temp.columns:
                df_temp = df_temp[df_temp["confidence"].apply(es_confianza_valida)].copy()
            
            # Verificar que sigan quedando registros después del filtro
            if not df_temp.empty:
                # 2. Mover 'bright_ti4' -> 'brightness' si trae información
                if "bright_ti4" in df_temp.columns:
                    if "brightness" in df_temp.columns:
                        df_temp["brightness"] = df_temp["bright_ti4"].combine_first(df_temp["brightness"])
                    else:
                        df_temp["brightness"] = df_temp["bright_ti4"]
                    df_temp.drop(columns=["bright_ti4"], inplace=True)

                # 3. Mover 'bright_ti5' -> 'bright_t31' si trae información
                if "bright_ti5" in df_temp.columns:
                    if "bright_t31" in df_temp.columns:
                        df_temp["bright_t31"] = df_temp["bright_ti5"].combine_first(df_temp["bright_t31"])
                    else:
                        df_temp["bright_t31"] = df_temp["bright_ti5"]
                    df_temp.drop(columns=["bright_ti5"], inplace=True)

                # Insertar el nombre del instrumento en la POSICIÓN 0
                df_temp.insert(0, "fuente_instrumento", inst)
                dataframes.append(df_temp)
            
    time.sleep(1)

if dataframes:
    df_total = pd.concat(dataframes, ignore_index=True)
    
    # Reordenar columnas dejando 'fuente_instrumento' primero y el resto de los datos a continuación
    columnas_ordenadas = ["fuente_instrumento"] + [col for col in df_total.columns if col != "fuente_instrumento"]
    df_total = df_total[columnas_ordenadas]
    
    # Imprimir el detalle completo de CADA foco en consola
    print(f"=== DETALLE DE LOS {len(df_total)} FOCOS VÁLIDOS DETECTADOS EL {FECHA} ===\n")
    print(df_total.to_string(index=False))
    
    # Guardar el CSV con este mismo orden de columnas
    nombre_archivo = f"detalle_focos_{FECHA}.csv"
    df_total.to_csv(nombre_archivo, index=False)
    print(f"\nArchivo guardado con el detalle completo en: {nombre_archivo}")
else:
    print(f"No se encontraron focos válidos para el {FECHA}.")