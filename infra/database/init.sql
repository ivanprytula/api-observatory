-- PostgreSQL database initialization script for data-pipeline-async
-- This script runs automatically when the PostgreSQL container starts
-- (mounted to /docker-entrypoint-initdb.d/)

-- Create optional extensions only when they are available in the image.
-- This keeps initialization portable across postgres/postgis variants.
DO $$
BEGIN
	IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'postgis') THEN
		CREATE EXTENSION IF NOT EXISTS postgis;
	ELSE
		RAISE NOTICE 'Extension postgis is not available; skipping';
	END IF;

	IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
		CREATE EXTENSION IF NOT EXISTS vector;
	ELSE
		RAISE NOTICE 'Extension vector is not available; skipping';
	END IF;

	IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'pgcrypto') THEN
		CREATE EXTENSION IF NOT EXISTS pgcrypto;
	ELSE
		RAISE NOTICE 'Extension pgcrypto is not available; skipping';
	END IF;

	IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'uuid-ossp') THEN
		CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
	ELSE
		RAISE NOTICE 'Extension uuid-ossp is not available; skipping';
	END IF;
END
$$;

-- Runtime database parameters are managed via postgresql.conf.
-- Keep this init script focused on extension/bootstrap DDL only.
