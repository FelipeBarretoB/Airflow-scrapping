import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
from modules.escritura import DatabaseManager
from modules.validacion import is_valid_created_at


# Constantes para el scraping
ENTITY_VALUE = 'Agencia Nacional de Infraestructura'
FIXED_CLASSIFICATION_ID = 13
URL_BASE = "https://www.ani.gov.co/informacion-de-la-ani/normatividad?field_tipos_de_normas__tid=12&title=&body_value=&field_fecha__value%5Bvalue%5D%5Byear%5D="

# Clasificaciones de documentos
CLASSIFICATION_KEYWORDS = {
    'resolución': 15,
    'resolucion': 15,
    'decreto': 14,
}

DEFAULT_RTYPE_ID = 14

def normalize_datetime(dt):
    """
    Normaliza un datetime para quitar información de timezone.
    """
    if dt is None:
        return None
    
    # Si es un datetime con timezone, convertir a naive
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    
    return dt

def clean_quotes(text):
    if not text:
        return text
    quotes_map = {
        '\u201C': '', '\u2018': '', '\u2019': '', '\u00AB': '', '\u00BB': '',
        '\u201E': '', '\u201A': '', '\u2039': '', '\u203A': '', '"': '',
        "'": '', '´': '', '`': '', '′': '', '″': '',
    }
    cleaned_text = text
    for quote_char, replacement in quotes_map.items():
        cleaned_text = cleaned_text.replace(quote_char, replacement)
    quotes_pattern = r'["\'\u201C\u201D\u2018\u2019\u00AB\u00BB\u201E\u201A\u2039\u203A\u2032\u2033]'
    cleaned_text = re.sub(quotes_pattern, '', cleaned_text)
    cleaned_text = cleaned_text.strip()
    cleaned_text = ' '.join(cleaned_text.split())
    return cleaned_text

def extract_summary(row, norma_data):
    """
    Extrae el resumen/descripción de una fila
    """
    summary_cell = row.find('td', class_='views-field views-field-body')
    if summary_cell:
        raw_summary = summary_cell.get_text(strip=True)
        cleaned_summary = clean_quotes(raw_summary)
        formatted_summary = cleaned_summary.capitalize()
        norma_data['summary'] = formatted_summary
    else:
        norma_data['summary'] = None

def get_rtype_id(title):
    """
    Obtiene el rtype_id basado en el título del documento.
    """
    title_lower = title.lower()
    
    for keyword, rtype_id in CLASSIFICATION_KEYWORDS.items():
        if keyword in title_lower:
            return rtype_id
    
    return DEFAULT_RTYPE_ID


def extract_title_and_link(row, norma_data, verbose, row_num):
    """
    Extrae título y enlace de una fila
    
    Returns:
        bool: True si se extrajo correctamente, False si debe saltarse
    """
    title_cell = row.find('td', class_='views-field views-field-title')
    if not title_cell:
        if verbose:
            print(f"No se encontró celda de título en la fila {row_num}. Saltando.")
        return False
    
    title_link = title_cell.find('a')
    if not title_link:
        if verbose:
            print(f"No se encontró enlace en la fila {row_num}. Saltando.")
        return False
    
    # Procesar título
    raw_title = title_link.get_text(strip=True)
    cleaned_title = clean_quotes(raw_title)
    
    norma_data['title'] = cleaned_title
    
    # Procesar enlace
    external_link = title_link.get('href')
    if external_link and not external_link.startswith('http'):
        external_link = 'https://www.ani.gov.co' + external_link
    
    norma_data['external_link'] = external_link
    norma_data['gtype'] = 'link' if external_link else None

    
    return True

def extract_creation_date(row, norma_data, verbose, row_num):
    """
    Extrae la fecha de creación de una fila
    
    Returns:
        bool: True si se extrajo correctamente, False si debe saltarse
    """
    fecha_cell = row.find('td', class_='views-field views-field-field-fecha--1')
    if fecha_cell:
        fecha_span = fecha_cell.find('span', class_='date-display-single')
        if fecha_span:
            created_at_raw = fecha_span.get('content', fecha_span.get_text(strip=True))
            # Procesar diferentes formatos de fecha
            if 'T' in created_at_raw:
                norma_data['created_at'] = created_at_raw.split('T')[0]
            elif '/' in created_at_raw:
                try:
                    day, month, year = created_at_raw.split('/')
                    norma_data['created_at'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                except:
                    norma_data['created_at'] = created_at_raw
            else:
                norma_data['created_at'] = created_at_raw
        else:
            norma_data['created_at'] = fecha_cell.get_text(strip=True)
    else:
        norma_data['created_at'] = None
    
    return True

def scrape_page(page_num, verbose=False):
    """
    Scrapea una página específica de ANI
    
    Args:
        page_num (int): Número de página a scrapear
        verbose (bool): Si mostrar logs detallados
    
    Returns:
        list: Lista de diccionarios con los datos extraídos
    """
    # Construir URL de la página
    if page_num == 0:
        page_url = URL_BASE
    else:
        page_url = f"{URL_BASE}&page={page_num}"
    
    if verbose:
        print(f"Scrapeando página {page_num}: {page_url}")
    
    try:
        # Realizar solicitud HTTP
        response = requests.get(page_url, timeout=15)
        response.raise_for_status()
        
        # Parsear HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        tbody = soup.find('tbody')
        
        if not tbody:
            if verbose:
                print(f"No se encontró tabla en página {page_num}")
            return []
        
        rows = tbody.find_all('tr')
        if verbose:
            print(f"Encontradas {len(rows)} filas en página {page_num}")
        
        # Procesar filas
        page_data = []
        for i, row in enumerate(rows, 1):
            try:
                # Estructura base del registro
                norma_data = {
                    'created_at': None,
                    'update_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'is_active': True,
                    'title': None,
                    'gtype': None,
                    'entity': ENTITY_VALUE,
                    'external_link': None,
                    'rtype_id': None,
                    'summary': None,
                    'classification_id': FIXED_CLASSIFICATION_ID,
                }
                
                # Extraer datos
                if not extract_title_and_link(row, norma_data, verbose, i):
                    continue
                
                extract_summary(row, norma_data)
                
                if not extract_creation_date(row, norma_data, verbose, i):
                    continue
                
                # Establecer rtype_id basado en título
                norma_data['rtype_id'] = get_rtype_id(norma_data['title'])
                
                page_data.append(norma_data)
                
            except Exception as e:
                if verbose:
                    print(f"Error procesando fila {i} en página {page_num}: {str(e)}")
                continue
        
        return page_data, f"Página {page_num} procesada exitosamente"
        
    except requests.RequestException as e:
        print(f"Error HTTP en página {page_num}: {e}")
        return [], "Error HTTP en la página"
    except Exception as e:
        print(f"Error procesando página {page_num}: {e}")
        return [], "Error procesando la página"
    
# Esta es la funcion que vamos a llamar en el airflow
def check_for_new_content(num_pages_to_check=3):
    """
    Verifica si hay contenido nuevo en las primeras páginas.
    Puede retornar un estado de salida JSON
    O puede retornar all_normas_data para procesamiento posterior.
    """
    print(f"Verificando contenido nuevo en las primeras {num_pages_to_check} páginas...")
    
    try:
        # Conectar a la base de datos para obtener la fecha más reciente
        db_manager = DatabaseManager()
        if not db_manager.connect():
            print("Error conectando a la base de datos para verificación")
            return True  # En caso de error, proceder con el scraping
        
        # Obtener la fecha de creación más reciente en la base de datos
        # Esta consulta SQL originalmente llamaba a la tabla dapper_regulations_regulations, sin embargo todas otras consultas llamaban a regulations,
        # Dado que no me queda del todo claro que es la tabla dapper_regulations_regulations y no tengo suficiente informacion para determinar si es un JOIN o una vista,
        # Voy a seguir llamando a la talbla regulations directamente.
        # Una pequeña observación, a final de cuentas created_at se inserta como string, así que creo que el MAX puede llegar a causar problemas. 
        query = "SELECT MAX(created_at) FROM regulations WHERE entity = %s"
        result = db_manager.execute_query(query, (ENTITY_VALUE,))
        
        latest_db_date = None
        if result and result[0][0]:
            latest_db_date = result[0][0]
            
            # Normalizar fecha de la base de datos
            if isinstance(latest_db_date, str):
                try:
                    latest_db_date = datetime.strptime(latest_db_date, '%Y-%m-%d %H:%M:%S')
                except:
                    try:
                        latest_db_date = datetime.strptime(latest_db_date.split()[0], '%Y-%m-%d')
                    except:
                        latest_db_date = None
            
            # Normalizar datetime (quitar timezone info)
            latest_db_date = normalize_datetime(latest_db_date)
        
        db_manager.close()
        
        print(f"Fecha más reciente en BD: {latest_db_date}")
        
        # Verificar las primeras páginas en busca de contenido más reciente
        for page_num in range(num_pages_to_check):
            try:
                page_data = scrape_page(page_num, verbose=False)
                
                for record in page_data:
                    created_at_val = record.get('created_at')
                    
                    if created_at_val and is_valid_created_at(created_at_val):
                        web_date = None
                        try:
                            web_date = datetime.strptime(created_at_val, '%Y-%m-%d %H:%M:%S')
                        except:
                            try:
                                web_date = datetime.strptime(created_at_val.split()[0], '%Y-%m-%d')
                            except:
                                continue
                        
                        # Normalizar fecha web (quitar timezone info)
                        web_date = normalize_datetime(web_date)
                        
                        # Si encontramos contenido más reciente que el de la base de datos
                        if not latest_db_date or web_date > latest_db_date:
                            print(f"Nuevo contenido detectado - Fecha web: {web_date}, Fecha BD: {latest_db_date}")
                            return True
                
            except Exception as e:
                print(f"Error verificando página {page_num}: {e}")
                continue
        
        print("No se detectó contenido nuevo")
        return False
        
    except Exception as e:
        print(f"Error en verificación de contenido nuevo: {e}")
        return True  # En caso de error, proceder con el scraping

def start_extraction(event, verbose=False):
     # Obtener parámetros del evento
    num_pages_to_scrape = event.get('num_pages_to_scrape', 9) if event else 9
    force_scrape = event.get('force_scrape', False) if event else False

    print(f"Iniciando scraping de ANI - Páginas a procesar: {num_pages_to_scrape}")
        
    # Verificar si hay contenido nuevo (a menos que se fuerce el scraping)
    if not force_scrape:
        has_new_content = check_for_new_content(min(3, num_pages_to_scrape))
        if not has_new_content:
            return {
                "statusCode": 200,
                "message": "No se detectó contenido nuevo. Scraping omitido.",
                "records_scraped": 0,
                "records_inserted": 0,
                "content_check": "no_new_content",
                "success": True,
                "continue": False
            }
        
    # Procesar las páginas más recientes (0 a num_pages_to_scrape-1)
    start_page = 0
    end_page = num_pages_to_scrape - 1
        
    print(f"Procesando páginas más recientes desde {start_page} hasta {end_page}")
        
    # Proceso principal de scraping
    all_normas_data = []
    page_messages = []
    for page_num in range(start_page, end_page + 1):
        print(f"Procesando página {page_num}...")
        page_data, page_message = scrape_page(page_num, verbose=verbose)
        page_messages.append(page_message)
        if verbose:
            print(page_message)
        all_normas_data.extend(page_data)
            
        # Indicador de progreso cada 3 páginas
        if (page_num + 1) % 3 == 0:
            print(f"Procesadas {page_num + 1}/{num_pages_to_scrape} páginas. Encontrados {len(all_normas_data)} registros.")

    #Verificar si no fueron errores de http, es decir si la pagina esta caida o no
    if any("Error" in msg for msg in page_messages):
        
        # Si todas las páginas tuvieron error, retornar error crítico
        error_pages = [msg for msg in page_messages if "Error" in msg]
        if len(error_pages) == len(page_messages):
            return {
                'statusCode': 500,
                'message': 'Error crítico: error al procesar todas las paginas solicitadas.',
                'records_scraped': 0,
                'records_inserted': 0,
                'pages_processed': f"{start_page}-{end_page}",
                'success': False,
                "continue": False,
                "errors": error_pages
            }

        # Si solo algunas páginas tuvieron error, retornar aviso parcial
        return {
            'statusCode': 206,
            'message': 'Errores ocurrieron durante el scraping de las páginas.',
            'records_scraped': len(all_normas_data),
            'records_inserted': 0,
            'pages_processed': f"{start_page}-{end_page}",
            'success': False,
            "continue": True,
            "errors": error_pages
        }

    if not all_normas_data:
        return {
            'statusCode': 200,
            'message': 'No se encontraron datos válidos durante el scraping',
            'records_scraped': 0,
            'records_inserted': 0,
            'pages_processed': f"{start_page}-{end_page}",
            'success': True,
            "continue": False
        }
    
    print(f"Scraping incial completado. Total registros encontrados: {len(all_normas_data)}")
    return {
        "statusCode": 200,
        "success": True,
        "message": "El scraping inicial se completo con exito",
        "start_page": start_page,
        "end_page": end_page,
        "continue": True,
        "all_normas_data": all_normas_data
    }
