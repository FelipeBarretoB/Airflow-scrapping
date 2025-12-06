.PHONY: reset-airflow init-airflow up-airflow down-airflow start

down-airflow:
	docker-compose down --volumes

# pequeño cabio aca, ya no borra el contenido de dags, entonces se puede iniciar
# y reiniciar el airflow sin perder los dags cargados
reset-airflow: down-airflow
	sudo chown -R $$(id -u):$$(id -g) logs dags plugins || true
	rm -rf logs/* plugins/*
	mkdir -p logs dags plugins
	chmod 777 logs dags plugins

init-airflow:
	docker-compose run --rm webserver airflow db init
	docker-compose run --rm webserver \
	  airflow users create \
	    --username admin --password admin \
	    --firstname Admin --lastname User \
	    --role Admin --email admin@example.com

up-airflow:
	docker-compose up -d

start: reset-airflow init-airflow up-airflow
