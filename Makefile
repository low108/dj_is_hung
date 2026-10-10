# Run each target in its own terminal: make emulator, make api, make web
PROJECT ?= demo-dj-is-hung
API_PORT ?= 8001

.PHONY: install emulator api web test

install:
	uv sync
	cd web && npm install

emulator:
	npx -y firebase-tools@14 emulators:start --only firestore --project $(PROJECT)

api:
	FIRESTORE_EMULATOR_HOST=localhost:8080 GOOGLE_CLOUD_PROJECT=$(PROJECT) uv run uvicorn api.main:app --reload --port $(API_PORT)

web:
	cd web && npm run dev

test:
	uv run pytest -q
