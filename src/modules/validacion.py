import re
import yaml
from datetime import datetime

rule_file_path = 'configs/reglas_de_validacion.yaml'

# Quise crear otro porque cuando se busca nuevo contenido tambien se valida el created at
# Creo que seria raro hacer tipo validar si hay contenido en extraer luego ir a este modulo de validar
# Para luego volver a extraer para volver a validar, creo que seria mejor crear esta funcion
# importarla en extraccion.py y usarla ahi directamente solo cuando se busca contenido nuevo
def is_valid_created_at(created_at_value):
    rules = load_validation_rules()
    rules = rules['fields'].get('created_at')
    if not created_at_value:
        return False
    expected_type = rules.get('type')
    correct_type = False
    for type in expected_type:
        if isinstance(created_at_value, eval(type)):
            correct_type = True
            break
    return correct_type

def load_validation_rules():
    with open(rule_file_path, 'r', encoding='utf-8') as file:
        rules = yaml.safe_load(file)
    return rules 

def validate_scrape_data(page_data, verbose=False):
    valid_data = []
    count_skipped = 0
    validation_rules = load_validation_rules()
    for norma_data in page_data:
        is_valid = True

        for field, rules in validation_rules['fields'].items():
            value = norma_data.get(field)

            # Validar obligatoriedad
            if rules.get('required') and not value:
                if verbose:
                    if field == "external_link":
                        print(f"Saltando norma '{norma_data.get('title', 'N/A')}' por no tener enlace externo válido.")
                    else:
                        print(f"Saltando norma '{norma_data.get('title', 'N/A')}' porque el campo obligatorio '{field}' está vacío.")
                is_valid = False
                break  # Descartar toda la fila
            
            # Validar tipo de dato
            expected_type = rules.get('type')
            type_valid = False
            for check_type in expected_type:
                if check_type and value is not None:
                    try:
                        if not isinstance(value, eval(check_type)):
                            if rules.get('required'):
                                is_valid = False
                            else:
                                norma_data[field] = None
                        else:
                            type_valid = True
                            is_valid = True
                            break  # Tipo válido, salir del loop
                    except NameError:
                        if verbose:
                            print(f"Tipo '{check_type}' no reconocido en las reglas de validación.")
            if not type_valid and value is not None and verbose:
                if rules.get('required'):
                    print(f"Campo obligatorio:'{field}', tiene tipo inválido en norma '{norma_data.get('title', 'N/A')}': {value} (Tipo esperado: {expected_type}).")
                else:
                    print(f"Campo opcional:'{field}', tiene tipo inválido en norma '{norma_data.get('title', 'N/A')}': {value} (Tipo esperado: {expected_type}). Se establecerá como None.")

            regex_pattern = rules.get('regex')
            regex_pattern_matched = True
            if regex_pattern and value is not None:
                if not re.match(regex_pattern, str(value)):
                    if rules.get('required'):
                        is_valid = False
                        regex_pattern_matched = False
                    else:
                        regex_pattern_matched = False
                        norma_data[field] = None
            
            if not regex_pattern_matched and verbose:
                if rules.get('required'):
                    print(f"Campo obligatorio:'{field}', no cumple con el patrón regex en norma '{norma_data.get('title', 'N/A')}': {value}. Patrón esperado: {regex_pattern}.")
                else:
                    print(f"Campo opcional:'{field}', no cumple con el patrón regex en norma '{norma_data.get('title', 'N/A')}': {value}. Patrón esperado: {regex_pattern}. Se establecerá como None.")
            
        if is_valid:
            valid_data.append(norma_data)
        else:
            if verbose:
                print(f"Norma '{norma_data.get('title', 'N/A')}' saltada durante la validación.")
            count_skipped += 1
    
    print(f"Total de normas saltadas durante la validación: {count_skipped}")
    print(f"Total de normas válidas después de la validación: {len(valid_data)}")

    if len(valid_data) == 0:
        return {
            'statusCode': 200,
            'message': 'No se encontraron datos válidos en el scraping.',         
            'success': True,
            "continue": False
        }

    return {
        'statusCode': 200,
        'message': 'Validación completada con éxito.',         
        'success': True,
        "continue": True,
        "valid_data": valid_data
    }



