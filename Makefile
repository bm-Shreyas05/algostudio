.PHONY: dev api web check test bench demo clean

api:
	cd backend && python -m uvicorn algostudio.api.app:app --port 8000 --reload

web:
	cd frontend && npm run dev

# The two load-bearing invariants. If either fails, everything built on the
# event stream is describing a program the user did not write.
check:
	cd backend && python tools/check_semantics.py
	cd backend && python tools/check_timetravel.py

test:
	cd backend && python -m pytest -q

fixtures:
	cd backend && python tools/make_fixtures.py && python tools/make_algorithms.py

runtime-image:
	docker build -f backend/Dockerfile.runtime -t algostudio-runtime:latest backend

clean:
	rm -rf var/executions/* frontend/dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
