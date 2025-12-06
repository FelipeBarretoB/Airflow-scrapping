# Refactorización de Scraping a Airflow DAG

¡Hola!

Este proyecto está basado en código ya existente. El propósito fue reescribir una función de scraping originalmente implementada como AWS Lambda y migrarla a un DAG de Airflow. La idea principal fue mantener la mayor cantidad de funcionalidad original intacta, pero separar las partes del proceso en diferentes tareas/módulos y agregar funciones para la validación de datos y el manejo de variables de entorno de forma más amigable.

---

## ¿Cómo lanzar el proyecto?

1. **Ubicación:**  
   Asegúrate de estar en la misma carpeta que el archivo `Makefile`.

2. **Inicialización rápida:**  
   Para iniciar el proyecto desde cero, ejecuta:

   ```bash
   make start
   ```
Este comando borra el contenedor de Airflow si ya existe, lo reinicia y lo levanta.  
También puedes usar los siguientes comandos por separado:

- `make reset-airflow` – Borra y reinicia el entorno de Airflow.
- `make init-airflow` – Inicializa la base de datos y crea el usuario admin.
- `make up-airflow` – Levanta los servicios de Airflow.
- `make down-airflow` – Apaga los servicios de Airflow.

3. **Acceso a Airflow:**  
   Una vez Airflow esté arriba, accede a la interfaz visual en [http://localhost:8080](http://localhost:8080).  
   Usa las credenciales que se encuentran en el archivo `.env` para ingresar.  
   Ten paciencia, el DAG puede tardar unos minutos en aparecer (en mi caso, hasta 5 minutos).

4. **Ejecución del DAG:**  
   Cuando el DAG esté disponible, puedes ejecutarlo desde la interfaz web.  
   Accede al proceso y revisa los logs si tienes algún problema.

---

## Tips y configuración

- **Variables de entorno:**  
  Todas las variables de entorno se manejan en el archivo `.env`.  
  Puedes cambiar contraseñas y nombres de servicios según tus necesidades.

- **Scraping:**  
  En `.env` también puedes configurar la cantidad de páginas a revisar (`NUM_PAGES_TO_SCRAPE`), forzar el scraping (`FORCE_SCRAPE`) y activar el modo verbose para obtener logs adicionales (`VERBOSE`).

- **Configuración de la base de datos y validación:**  
  En la carpeta `configs` encontrarás:
  - El archivo `DDL.sql` con el esquema de la base de datos (las dos tablas usadas en el ejercicio).
  - El archivo de reglas de validación (`reglas_de_validacion.yaml`), donde puedes modificar los criterios de validación de los campos durante el scraping.

---

## Notas finales

- El proyecto está modularizado en extracción, validación y escritura.
- El DAG de Airflow orquesta el proceso completo.
- Los logs muestran totales extraídos, descartes por validación y filas insertadas.
- La lógica de idempotencia evita duplicados en la base de datos.

---
