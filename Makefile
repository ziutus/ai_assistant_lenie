CONTAINER_NAME=lenie


# Add the following 'help' target to your Makefile
# And add help text after each target name starting with '\#\#'

default:	help

help:           ## Show this help.
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##//'

# Everything below is an example

build:          ## Builds docker containers
	docker compose build

dev:            ## Runs backend and frontend
	docker compose up -d

down:            ## Stops and removes containers
	docker compose down -v
