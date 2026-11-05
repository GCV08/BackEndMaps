from enum import Enum
from typing import Optional
import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
import requests
from google import genai
from google.genai import types

# Inicializar la aplicación de FastAPI
app = FastAPI(
    title="API de Movilidad Urbana Inclusiva",
    description="Backend optimizado con enums estrictos y gestión limpia de archivos multimedia.",
    version="3.2.0"
)

# Configuración de tus API Keys
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Inicializar el cliente de Gemini UNA SOLA VEZ
gemini_client = genai.Client(api_key=GEMINI_API_KEY)


# Definir un Enum para que los modos sean fijos y seguros (evita errores de dedo)
class ModoAccesibilidad(str, Enum):
    VISUAL = "visual"      # Usuario ciego (prioridad audio)
    AUDITIVO = "auditivo"  # Usuario sordo (prioridad cámara)


@app.get("/")
def home():
    return {
        "estado": "activo",
        "mensaje": "Backend operando correctamente con Enums y limpieza de archivos."
    }


# =====================================================================
# 1. ENDPOINT DE RUTAS (Puros datos geográficos)
# =====================================================================
@app.get("/ruta-accesible")
def obtener_ruta_accesible(origen: str, destino: str):
    try:
        url_maps = "https://routes.googleapis.com/directions/v2:computeRoutes"
        
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": "routes.legs.steps.navigationInstruction,routes.legs.steps.distanceMeters,routes.legs.steps.startLocation,routes.legs.steps.endLocation,routes.polyline.encodedPolyline"
        }
        
        payload = {
            "origin": {"address": origen},
            "destination": {"address": destino},
            "travelMode": "WALK",
            "computeAlternativeRoutes": False,
            "languageCode": "es"
        }
        
        response_maps = requests.post(url_maps, json=payload, headers=headers)
        data_maps = response_maps.json()
        
        if "routes" not in data_maps or not data_maps["routes"]:
            error_detalle = data_maps.get("error", {}).get("message", "No se encontró una ruta o verifica los lugares.")
            raise HTTPException(
                status_code=400, 
                detail=f"Error en Google Routes API: {error_detalle}"
            )

        ruta_principal = data_maps['routes'][0]
        pasos_raw = ruta_principal['legs'][0]['steps']
        poly_codificada = ruta_principal.get('polyline', {}).get('encodedPolyline', '')

        pasos_con_coordenadas = []
        
        for paso in pasos_raw:
            nav_inst = paso.get("navigationInstruction", {})
            instr = nav_inst.get("instructions", "Avanzar por el tramo indicado.")
            
            start_loc = paso.get("startLocation", {}).get("latLng", {})
            end_loc = paso.get("endLocation", {}).get("latLng", {})
            
            pasos_con_coordenadas.append({
                "instruccion": instr,
                "distancia_metros": paso.get("distanceMeters", 0),
                "coordenada_inicio": {"lat": start_loc.get("latitude"), "lng": start_loc.get("longitude")},
                "coordenada_fin": {"lat": end_loc.get("latitude"), "lng": end_loc.get("longitude")}
            })
            
        return {
            "estatus": "exito",
            "origen": origen,
            "destino": destino,
            "polylines_global": poly_codificada,
            "detalle_pasos": pasos_con_coordenadas
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno al procesar la ruta: {str(e)}")


# =====================================================================
# 2. ENDPOINT INTELIGENTE EN TIEMPO REAL (Con Enum y Limpieza)
# =====================================================================
@app.post("/monitorear-en-ruta")
async def monitorear_en_ruta(
    modo_accesibilidad: ModoAccesibilidad = Form(...),  # <- Aquí entra el Enum desplegable
    imagen: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None)
):
    try:
        contenido_multimodal = []
        
        # Usamos .value para obtener el texto plano ("visual" o "auditivo")
        if modo_accesibilidad == ModoAccesibilidad.VISUAL:
            instruccion_perfil = (
                "El usuario es una persona con discapacidad visual (ciego/a). "
                "Tu prioridad es analizar el AUDIO ambiental recibido en busca de sonidos de peligro "
                "(claxons cercanos, motores acelerando de repente, sirenas o vehículos aproximándose)."
            )
        else:
            instruccion_perfil = (
                "El usuario es una persona con discapacidad auditiva (sordo/a). "
                "Tu prioridad es analizar la IMAGEN de la cámara en busca de obstáculos físicos, "
                "baches, obras, semáforos o vehículos cruzando el camino que debe evitar."
            )
            
        prompt = f"""
        Actúa como el sistema de alerta inteligente para movilidad urbana inclusiva.
        {instruccion_perfil}
        Da una respuesta extremadamente breve, directa y de alta urgencia (ideal para que la app móvil la convierta en voz o vibración táctil de inmediato).
        """
        contenido_multimodal.append(prompt)

        # Leer y procesar imagen si existe
        if imagen:
            img_bytes = await imagen.read()
            contenido_multimodal.append(
                types.Part.from_bytes(data=img_bytes, mime_type=imagen.content_type or "image/jpeg")
            )

        # Leer y procesar audio si existe
        if audio:
            audio_bytes = await audio.read()
            contenido_multimodal.append(
                types.Part.from_bytes(data=audio_bytes, mime_type=audio.content_type or "audio/mp3")
            )

        # Consumir Gemini
        response = gemini_client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=contenido_multimodal,
        )

        return {
            "estatus": "exito",
            "modo_accesibilidad": modo_accesibilidad.value,
            "alerta_inteligente": response.text
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el monitoreo inteligente: {str(e)}")
    
    finally:
        # Bloque de limpieza: Asegura que los archivos temporales se cierren al terminar la petición
        if imagen:
            await imagen.close()
        if audio:
            await audio.close()