-- Least-privilege PostgreSQL role separation for production deployment.
-- architecture/TASD-v1.0.md section 9.3/21.3. Run once against the
-- target PostgreSQL 16 instance, as a superuser, before the app's
-- first deploy. Replace the two passwords before running (or better:
-- generate them with `openssl rand -base64 32` and store only in the
-- deployment's secret manager, never in this file or in version control).
--
-- Two roles, two purposes:
--   poc_app_rw   -- what the running application connects as. Can
--                   read/write application data, but cannot alter the
--                   schema (no CREATE/ALTER/DROP TABLE) -- a compromised
--                   app process or an injection bug cannot restructure
--                   or drop the database.
--   poc_migrator -- what `alembic upgrade head` connects as, run only
--                   during deploys, never by the running application.
--                   Owns the schema and can alter it.
--
-- This is the SQL analogue of app/config.py's SecretStr credential
-- handling: least privilege enforced by the database itself, not only
-- by application code discipline.

CREATE ROLE poc_migrator WITH LOGIN PASSWORD 'CHANGE_ME_MIGRATOR_PASSWORD';
CREATE ROLE poc_app_rw WITH LOGIN PASSWORD 'CHANGE_ME_APP_PASSWORD';

CREATE DATABASE poc_workflow OWNER poc_migrator;
\connect poc_workflow

-- poc_migrator: owns the schema, runs migrations (DDL + the initial/
-- subsequent `alembic upgrade head`). The app never connects as this role.
GRANT ALL PRIVILEGES ON SCHEMA public TO poc_migrator;

-- poc_app_rw: DML only (SELECT/INSERT/UPDATE/DELETE) on every table
-- that exists NOW, plus a default-privilege grant so tables created by
-- FUTURE migrations (run as poc_migrator) automatically carry the same
-- grant -- otherwise every new migration would need a manual GRANT
-- statement added here, which is exactly the kind of deploy-time
-- footgun least-privilege setups are supposed to prevent.
GRANT USAGE ON SCHEMA public TO poc_app_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO poc_app_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO poc_app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE poc_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO poc_app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE poc_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO poc_app_rw;

-- Explicitly deny what poc_app_rw must never be able to do, stated
-- here rather than only relied upon by omission -- REVOKE is a no-op
-- if the privilege was never granted, so this is defense in depth,
-- not a correction of the grants above.
REVOKE CREATE ON SCHEMA public FROM poc_app_rw;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

-- DATABASE_URL for the running application (poc_app_rw -- DML only):
--   postgresql+asyncpg://poc_app_rw:<password>@<host>:5432/poc_workflow
-- Migration-only connection string (poc_migrator -- used by `alembic
-- upgrade head` at deploy time ONLY, never set as the app's own
-- DATABASE_URL):
--   postgresql+asyncpg://poc_migrator:<password>@<host>:5432/poc_workflow
