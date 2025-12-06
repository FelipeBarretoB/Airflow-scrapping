import psycopg2
import pandas as pd
import os


ENTITY_VALUE = 'Agencia Nacional de Infraestructura'

#  Clase para manejar la conexión a la base de datos y realizar operaciones de inserción de datos.
class DatabaseManager:
    # TODO añadir verbose a todo xd 
    def __init__(self, verbose=False):
        self.connection = None
        self.cursor = None
        self.verbose = verbose

    def create_table(self):
        try:
            with open('configs/DDL.sql', 'r', encoding='utf-8') as file:
                ddl_statements = file.read()

            # Como se crean dos tablas, se separan y ejecutan individualmente
            # Porque sino el execute pone problema 
            for statement in ddl_statements.split(';'):
                query = statement.strip()
                if query:
                    if self.verbose:
                        print(f"Ejecutando DDL: {query[:50]}...")
                    self.cursor.execute(query)
            
            self.connection.commit()
            if self.verbose:
                print("Se crearon las tablas existentes en el config/DDL.sql")
            return True
        except Exception as e:
            print(f"Error al crear la tabla: {e}")
            raise False

    def connect(self, verbose=False):
        self.verbose = verbose
        try:
            
            self.connection = psycopg2.connect(
                dbname= os.environ.get('POSTGRES_DB', 'airflow'),
                user= os.environ.get('POSTGRES_USER', 'airflow'),
                password= os.environ.get('POSTGRES_PASSWORD', 'airflow'),
                host= os.environ.get('POSTGRES_HOST', 'postgres'),
                port= os.environ.get('POSTGRES_PORT', '5432')
            )
            self.cursor = self.connection.cursor()
            success = self.create_table()
            if not success:
                return False, "Error al crear tablas necesarias"
            return True, "Conexión a la base de datos exitosa"
        except Exception as e:
            print(f"Database connection error: {e}")
            return False, f"Error al conectar a la base de datos {str(e)}"

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()

    def execute_query(self, query, params=None):
        if not self.cursor:
            raise Exception("Database not connected")
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    def bulk_insert(self, df, table_name):
        if not self.connection or not self.cursor:
            raise Exception("Database not connected")
        
        try:
            df = df.astype(object).where(pd.notnull(df), None)
            columns_for_sql = ", ".join([f'"{col}"' for col in df.columns])
            placeholders = ", ".join(["%s"] * len(df.columns))
            
            insert_query = f"INSERT INTO {table_name} ({columns_for_sql}) VALUES ({placeholders})"
            records_to_insert = [tuple(x) for x in df.values]
            
            self.cursor.executemany(insert_query, records_to_insert)
            self.connection.commit()
            return len(df)
        except Exception as e:
            self.connection.rollback()
            raise Exception(f"Error inserting into {table_name}: {str(e)}")

def insert_regulations_component(db_manager, new_ids, verbose=False):
    """
    Inserta los componentes de las regulaciones.
    """
    if not new_ids:
        return 0, "No new regulation IDs provided"

    try:
        id_rows = pd.DataFrame(new_ids, columns=['regulations_id'])
        id_rows['components_id'] = 7
        if verbose:
            print(f"Insertando {len(id_rows)} componentes de regulaciones")
        inserted_count = db_manager.bulk_insert(id_rows, 'regulations_component')
        return inserted_count, f"Se insertaron correctamente {inserted_count} componentes de regulaciones"
        
    except Exception as e:
        return 0, f"Error al insertar componentes de regulaciones: {str(e)}"


def insert_new_records(db_manager, df, entity, verbose=False):
    """
    Inserta nuevos registros en la base de datos evitando duplicados.
    Optimizada para velocidad y precisión.
    """
    regulations_table_name = 'regulations'
    
    try:
        # 1. OBTENER REGISTROS EXISTENTES INCLUYENDO EXTERNAL_LINK
        query = """
            SELECT title, created_at, entity, COALESCE(external_link, '') as external_link 
            FROM {} 
            WHERE entity = %s
        """.format(regulations_table_name)
        
        existing_records = db_manager.execute_query(query, (entity,))
        
        if not existing_records:
            db_df = pd.DataFrame(columns=['title', 'created_at', 'entity', 'external_link'])
            if verbose:
                print(f"No se encontraron registros existentes en BD para {entity}")
        else:
            db_df = pd.DataFrame(existing_records, columns=['title', 'created_at', 'entity', 'external_link'])
            if verbose:
                print(f"Registros existentes en BD para {entity}: {len(db_df)}")
        
        # 2. PREPARAR DATAFRAME DE LA ENTIDAD
        entity_df = df[df['entity'] == entity].copy()
        
        if entity_df.empty:
            return 0, f"No records found for entity {entity}"
        
        print(f"Registros a procesar para {entity}: {len(entity_df)}")
        
        # 3. NORMALIZAR DATOS PARA COMPARACIÓN CONSISTENTE
        # Normalizar created_at a string
        if not db_df.empty:
            db_df['created_at'] = db_df['created_at'].astype(str)
            db_df['external_link'] = db_df['external_link'].fillna('').astype(str)
            db_df['title'] = db_df['title'].astype(str).str.strip()
        
        entity_df['created_at'] = entity_df['created_at'].astype(str)
        entity_df['external_link'] = entity_df['external_link'].fillna('').astype(str)
        entity_df['title'] = entity_df['title'].astype(str).str.strip()
        
        # 4. IDENTIFICAR DUPLICADOS DE MANERA OPTIMIZADA
        print("=== INICIANDO VALIDACIÓN DE DUPLICADOS OPTIMIZADA ===")
        
        if db_df.empty:
            # Si no hay registros existentes, todos son nuevos
            new_records = entity_df.copy()
            duplicates_found = 0
            print("No hay registros existentes, todos son nuevos")
        else:
            # Crear claves únicas para comparación super rápida
            entity_df['unique_key'] = (
                entity_df['title'] + '|' + 
                entity_df['created_at'] + '|' + 
                entity_df['external_link']
            )
            
            db_df['unique_key'] = (
                db_df['title'] + '|' + 
                db_df['created_at'] + '|' + 
                db_df['external_link']
            )
            
            # Usar set para comparación O(1) - súper rápido
            existing_keys = set(db_df['unique_key'])
            entity_df['is_duplicate'] = entity_df['unique_key'].isin(existing_keys)
            
            new_records = entity_df[~entity_df['is_duplicate']].copy()
            duplicates_found = len(entity_df) - len(new_records)
            
            # Log para debugging
            if duplicates_found > 0:
                print(f"Duplicados encontrados: {duplicates_found}")
                duplicate_records = entity_df[entity_df['is_duplicate']]
                print("Ejemplos de duplicados:")
                for idx, row in duplicate_records.head(3).iterrows():
                    print(f"  - {row['title'][:50]}... | {row['created_at']}")
        
        # 5. REMOVER DUPLICADOS INTERNOS DEL DATAFRAME
        print(f"Antes de remover duplicados internos: {len(new_records)}")
        new_records = new_records.drop_duplicates(
            subset=['title', 'created_at', 'external_link'], 
            keep='first'
        )
        internal_duplicates = len(entity_df) - duplicates_found - len(new_records)
        if internal_duplicates > 0:
            print(f"Duplicados internos removidos: {internal_duplicates}")
        
        print(f"Después de remover duplicados internos: {len(new_records)}")
        print(f"=== DUPLICADOS IDENTIFICADOS: {duplicates_found + internal_duplicates} ===")
        
        if new_records.empty:
            return 0, f"No se encontraron nuevos registros para {entity} después de la validación de duplicados."
        
        # 6. LIMPIAR DATAFRAME ANTES DE INSERTAR
        # Remover columnas auxiliares
        columns_to_drop = ['unique_key', 'is_duplicate']
        for col in columns_to_drop:
            if col in new_records.columns:
                new_records = new_records.drop(columns=[col])
        
        print(f"Registros finales a insertar: {len(new_records)}")
        
        # 7. INSERTAR NUEVOS REGISTROS
        try:
            print(f"=== INSERTANDO {len(new_records)} REGISTROS ===")
            
            total_rows_processed = db_manager.bulk_insert(new_records, regulations_table_name)
            
            if total_rows_processed == 0:
                return 0, f"No se insertaron registros para la entidad {entity}"
            
            print(f"Registros insertados exitosamente: {total_rows_processed}")
            
        except Exception as insert_error:
            print(f"Error en inserción: {insert_error}")
            # Si es error de duplicados, algunos se escaparon
            if "duplicate" in str(insert_error).lower() or "unique" in str(insert_error).lower():
                if verbose:
                    print("Error de duplicados detectado - algunos registros ya existían")
                return 0, f"Algunos registros para la entidad {entity} eran duplicados y fueron omitidos"
            else:
                raise insert_error
        
        # 8. OBTENER IDS DE REGISTROS INSERTADOS - MÉTODO OPTIMIZADO
        print("=== OBTENIENDO IDS DE REGISTROS INSERTADOS ===")
        
        # Método simple y eficiente - obtener los últimos N IDs
        new_ids_query = f"""
            SELECT id FROM {regulations_table_name}
            WHERE entity = %s 
            ORDER BY id DESC
            LIMIT %s
        """
        
        new_ids_result = db_manager.execute_query(
            new_ids_query, 
            (entity, total_rows_processed)
        )
        new_ids = [row[0] for row in new_ids_result]
        
        print(f"IDs obtenidos: {len(new_ids)}")
        
        # 9. INSERTAR COMPONENTES DE REGULACIÓN
        inserted_count_comp = 0
        component_message = ""
        
        if new_ids:
            try:
                inserted_count_comp, component_message = insert_regulations_component(db_manager, new_ids, verbose=verbose)
                print(f"Componentes: {component_message}")
            except Exception as comp_error:
                if verbose:
                    print(f"Error insertando componentes: {comp_error}")
                component_message = f"Error insertando componentes: {str(comp_error)}"
        
        # 10. MENSAJE FINAL CON ESTADÍSTICAS DETALLADAS
        total_duplicates = duplicates_found + internal_duplicates
        stats = (
            f"Procesados: {len(entity_df)} | "
            f"Existentes: {len(db_df)} | "
            f"Duplicados saltados: {total_duplicates} | "
            f"Nuevos registros: {total_rows_processed} | "
            f"Total insertado a regulations_component: {inserted_count_comp}"
        )
        
        message = f"Entidad {entity}: {stats}. {component_message}"
        print(f"=== RESULTADO FINAL ===")
        print(message)
        print("=" * 50)
        
        return total_rows_processed, message
        
    except Exception as e:
        if hasattr(db_manager, 'connection') and db_manager.connection:
            db_manager.connection.rollback()
        error_msg = f"Error processing entity {entity}: {str(e)}"
        print(f"ERROR CRÍTICO: {error_msg}")
        import traceback
        print(traceback.format_exc())
        return 0, error_msg

def start_insertion(all_normas_data, start_page, end_page, force_scrape, verbose=False):
    # Crear DataFrame
        df_normas = pd.DataFrame(all_normas_data)
        print(f"Total de registros extraídos: {len(df_normas)}")
        
        # Operaciones de base de datos
        db_manager = DatabaseManager()
        connection_result, connection_message = db_manager.connect(verbose=verbose)
        if not connection_result:
            if verbose:
                print(f"Error de conexión a la base de datos: {connection_message}")
            return {
                'statusCode': 500,
                'message': connection_message,
                'success': False
            }
        
        try:
            # Insertar nuevos registros
            inserted_count, status_message = insert_new_records(db_manager, df_normas, ENTITY_VALUE, verbose=verbose)
            
            if "error" in status_message.lower():
                return {
                    'statusCode': 500,
                    'message': status_message,
                    'records_scraped': len(df_normas),
                    'records_inserted': inserted_count,
                    'pages_processed': f"{start_page}-{end_page}",
                    'content_check': 'new_content_found' if not force_scrape else 'forced_scrape',
                    'success': False
                }

            response = {
                'statusCode': 200,
                'message': status_message,
                'records_scraped': len(df_normas),
                'records_inserted': inserted_count,
                'pages_processed': f"{start_page}-{end_page}",
                'content_check': 'new_content_found' if not force_scrape else 'forced_scrape',
                'success': True
                }
            
            print(f"Operación completada: {status_message}")
            return response
            
        finally:
            db_manager.close()