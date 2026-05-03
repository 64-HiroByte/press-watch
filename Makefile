ENV_FILE := .env
COMPOSE_FILE := infra/compose.yml
DOCKER_COMPOSE := docker compose --env-file $(ENV_FILE) -f $(COMPOSE_FILE)

.PHONY: compose-up compose-up-build compose-down

compose-up:
	$(DOCKER_COMPOSE) up

compose-up-build:
	$(DOCKER_COMPOSE) up --build

compose-down:
	$(DOCKER_COMPOSE) down
