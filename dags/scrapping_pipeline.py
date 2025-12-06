from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.exceptions import AirflowSkipException
from datetime import datetime
import os
from modules.extraccion import start_extraction
from modules.validacion import validate_scrape_data
from modules.escritura import start_insertion


default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2025, 12, 4),
    'retries': 1
}

with DAG(
    dag_id='extraer_normativas_pipeline',
    default_args=default_args,
    schedule_interval='@daily',
    catchup=False
) as dag:
    
    # El escenario que vamos a probar
    # Se puede ajustar desde el archivo .env
    test_event = {
        'num_pages_to_scrape': int(os.environ.get('NUM_PAGES_TO_SCRAPE', 5)), # Número de páginas a scrapear
        'force_scrape': os.environ.get('FORCE_SCRAPE', 'False').lower() in ('true', '1', 't') # Si queremos saltar la verificación de nuevo contenido
    }

    # Configurar el modo verbose desde variable de entorno
    verbose = os.environ.get('VERBOSE', 'False').lower() in ('true', '1', 't')

    # Primera tarea: Extracción
    def extract(**kwargs):
        #Se llama a la función de extracción con el evento de prueba
        # Esta funcion esta definida en src/modules/extraccion.py
        # Retorna un diccionario con los datos extraidos y metadatos
        page_data = start_extraction(test_event, verbose=verbose)
        # Se guardan los datos extraidos en XCom para la siguiente tarea
        kwargs['ti'].xcom_push(key='page_data', value=page_data)

        print("Restulado de la extracción:")
        # Muestra los resultados de la extracción
        print(page_data)

        # Manejo de errores
        if page_data is None:
            raise Exception("Error en la extracción de datos.")
        
        # Avisos sobre extracción parcial
        if page_data['statusCode'] == 206:
            print("Extracción parcial de las páginas.")

        # Manejo de errores graves
        if page_data.get('success') is False:
            raise(page_data)

    # Segunda tarea: Validación de datos extraídos
    def validate(**kwargs):

        # Se obtienen los datos extraidos de la tarea anterior
        ti = kwargs['ti']
        page_data = ti.xcom_pull(key='page_data', task_ids='extract_task')

        # Se verifica que los datos existan
        if not page_data:
            print("Error al conseguir los datos de la extracción.")
            raise Exception("Error al conseguir los datos de la extracción.")

        # Verificamos si hay datos que requieran validación
        if not page_data['continue']:
            print("No se requiere validación, se detiene el pipeline.")
            # Si no lo hay, mandamos un skip, que se salta esta tarea y la siguiente 
            raise AirflowSkipException("No se requiere validación.")
        
        # Se llama a la función de validación con los datos extraídos
        # Esta función está definida en src/modules/validacion.py
        valid_data = validate_scrape_data(page_data["all_normas_data"], verbose=verbose)

        # Se guardan los datos validados en XCom para la siguiente tarea
        ti.xcom_push(key='valid_data', value=valid_data)
        print("Resultado de la validación:")
        print(valid_data)

    # Tercera tarea: Inserción de datos validados
    def insert(**kwargs):
        ti = kwargs['ti']
        # Se obtienen los datos validados de la tarea anterior
        valid_data = ti.xcom_pull(key='valid_data', task_ids='validate_task')

        # Se obtienen los datos extraidos de la tarea de extracción
        page_data = ti.xcom_pull(key='page_data', task_ids='extract_task')

        # Verificamos que los datos validados existan
        if not valid_data:
            print("Error al conseguir los datos validados.")
            raise Exception("Error al conseguir los datos validados.")

        # Verificamos si hay datos que requieran inserción
        if not valid_data['continue']:
            print("No se requiere inserción, se detiene el pipeline.")
            raise AirflowSkipException("No se requiere inserción.")
        
        # Se llama a la función de inserción con los datos validados
        # Esta función está definida en src/modules/escritura.py
        result = start_insertion(valid_data['valid_data'], page_data["start_page"], page_data["end_page"],force_scrape=test_event['force_scrape'] ,verbose=verbose)
        print("Resultado de la inserción:")
        print(result)

        # Manejo de errores
        if not result.get('success'):
            raise Exception(result)

    # Definición de las tareas del DAG:
    extract_task = PythonOperator(
        task_id='extract_task',
        python_callable=extract,
        provide_context=True
    )

    validate_task = PythonOperator(
        task_id='validate_task',
        python_callable=validate,
        provide_context=True
    )

    insert_task = PythonOperator(
        task_id='insert_task',
        python_callable=insert,
        provide_context=True
    )

    # Definición del flujo de tareas
    extract_task >> validate_task >> insert_task