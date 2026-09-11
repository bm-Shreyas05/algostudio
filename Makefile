.PHONY: api web build check audit test fixtures runtime-image api-image preflight gc up down clean

api:
	cd backend && python -m uvicorn algostudio.api.app:app --port 8000 --reload

web:
	cd frontend && npm run dev

# Build the SPA into frontend/dist, which api/app.py then serves from the same
# origin as the API -- one process runs the whole thing.
build:
	cd frontend && npm ci && npm run build

# The two load-bearing invariants. If either fails, everything built on the
# event stream is describing a program the user did not write.
check:
	cd backend && python tools/check_semantics.py
	cd backend && python tools/check_timetravel.py

# Every algorithm's visualization, not just its exit status.
audit:
	cd backend && python tools/audit_views.py

test:
	cd backend && python -m pytest tests -q

fixtures:
	cd backend && python tools/make_fixtures.py && python tools/make_algorithms.py

# ---- deployment -----------------------------------------------------------
# Is this configuration safe to expose? Exits non-zero if not.
preflight:
	cd backend && python tools/preflight.py

runtime-image:
	docker build -f backend/Dockerfile.runtime -t algostudio-runtime:latest backend

api-image:
	docker build -f backend/Dockerfile.api -t algostudio-api:latest .

# The deployable stack: API + built SPA in one container. Needs a .env
# (start from .env.example) and the runtime image for the sandbox.
up: runtime-image
	docker compose -f docker-compose.prod.yml up -d --build

down:
	docker compose -f docker-compose.prod.yml down

# Delete recordings past ALGOSTUDIO_RETENTION_DAYS.
gc:
	cd backend && python tools/gc.py

clean:
	rm -rf var/executions/* frontend/dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
