# Local Home Assistant with this integration and a Prusa Connect demo server.
# See README.md next to this file.

# Where the Prusa Connect source comes from. By default it is cloned into
# ./prusa-connect; point PRUSA_CONNECT_SRC at a checkout of your own to build that.
PRUSA_CONNECT_REPO ?= https://github.com/prusa3d/prusa-connect.git
PRUSA_CONNECT_REF ?= main
PRUSA_CONNECT_SRC ?= $(CURDIR)/prusa-connect
export PRUSA_CONNECT_SRC

CONNECT_PORT ?= 8090
CONNECT_PASSWORD ?= prusa-demo
RELEASES_PORT ?= 8091
export CONNECT_PORT CONNECT_PASSWORD RELEASES_PORT

ROOT := $(abspath $(CURDIR)/..)
PYTHON ?= python3
COMPOSE := docker compose -f $(CURDIR)/compose.yaml

.PHONY: help up down restart logs status setup publish printers printers-stop source update-source vendor clean

help: ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-14s %s\n", $$1, $$2}'

up: source vendor ## build and start both; Home Assistant starts fresh, the integration not set up
	@mkdir -p ha-config
	$(COMPOSE) up -d --build --wait connect releases
	@test -f ha-config/configuration.yaml || \
		sed "s|DEV_PUBLIC_KEY|$$($(COMPOSE) exec -T releases cat /data/public.key)|" configuration.yaml \
		> ha-config/configuration.yaml
	$(COMPOSE) up -d --wait homeassistant
	@echo
	@echo "  Home Assistant  http://localhost:8123   (first run: create the account)"
	@echo "  Prusa Connect   http://localhost:$(CONNECT_PORT)   demo / $(CONNECT_PASSWORD)   (an external server)"
	@echo "  Releases        http://localhost:$(RELEASES_PORT)   for the server Home Assistant runs itself"
	@echo
	@echo "  Add Prusa Connect in Home Assistant: run the server inside it (port 8080), or connect to"
	@echo "  the demo (it is also discovered). make setup connects to the demo for you."

down: ## stop both servers, keeping their data
	$(COMPOSE) down

restart: vendor ## reload the integration after a code change (restarts Home Assistant)
	$(COMPOSE) restart homeassistant

logs: ## follow both servers' logs
	$(COMPOSE) logs -f

status: ## show the containers
	$(COMPOSE) ps

setup: ## create the Home Assistant account and add the integration by pairing, skipping what is done
	@$(PYTHON) setup.py

publish: ## publish another development release for the embedded server, VERSION=0.0.1-alpha.2
	@test -n "$(VERSION)" || { echo "make publish VERSION=0.0.1-alpha.2"; exit 1; }
	$(COMPOSE) exec -T releases sh -c 'echo "$(VERSION)" >> /data/versions; cat /data/versions'

PRINTERS_URL ?= http://localhost:8080
MODEL ?= MK4S
COUNT ?= 1

printers: ## connect simulated printers to a server: MODEL=MK4S COUNT=1 PRINTERS_URL=http://localhost:8080
	$(COMPOSE) --profile printers build printers
	$(COMPOSE) run -d --rm --name prusa-connect-ha-dev-printers-$$(echo $(MODEL) | tr 'A-Z.' 'a-z-')-$$(date +%s) \
		printers -url $(PRINTERS_URL) -model $(MODEL) -count $(COUNT) -serial SIM$(MODEL)- -cameras=false -v
	@echo "  $(COUNT) x $(MODEL) dial $(PRINTERS_URL). If the server holds new printers at the door, approve"
	@echo "  them in Prusa Connect; make printers-logs shows their registration codes."

printers-logs: ## follow the simulated printers' logs
	docker ps -q --filter name=prusa-connect-ha-dev-printers- | xargs -n1 docker logs --tail 20

printers-stop: ## stop every simulated printer
	-docker ps -q --filter name=prusa-connect-ha-dev-printers- | xargs docker rm -f

source: ## clone the Prusa Connect source when PRUSA_CONNECT_SRC has none
	@if [ ! -f "$(PRUSA_CONNECT_SRC)/go.mod" ]; then \
		if [ "$(PRUSA_CONNECT_SRC)" != "$(CURDIR)/prusa-connect" ]; then \
			echo "PRUSA_CONNECT_SRC=$(PRUSA_CONNECT_SRC) is not a Prusa Connect checkout"; exit 1; \
		fi; \
		git clone --depth 1 --branch $(PRUSA_CONNECT_REF) $(PRUSA_CONNECT_REPO) "$(PRUSA_CONNECT_SRC)" || { \
			echo "Cloning $(PRUSA_CONNECT_REPO) failed. Over SSH: make up PRUSA_CONNECT_REPO=git@github.com:prusa3d/prusa-connect.git"; \
			exit 1; }; \
	fi

update-source: ## move the cloned Prusa Connect source to the head of PRUSA_CONNECT_REF
	git -C "$(CURDIR)/prusa-connect" fetch --depth 1 origin $(PRUSA_CONNECT_REF)
	git -C "$(CURDIR)/prusa-connect" checkout --detach FETCH_HEAD

vendor: ## copy lib/ into the integration, as the release does
	@cd $(ROOT) && $(PYTHON) scripts/vendor_lib.py sync

clean: printers-stop ## remove the containers and all their data (Home Assistant config, demo database)
	$(COMPOSE) down -v
	rm -rf ha-config
