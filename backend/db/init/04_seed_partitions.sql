-- Pre-create the initial set of daily partitions at container startup so the
-- database is immediately writable (otherwise every insert would land in
-- events_default until someone runs `make partitions`).
SELECT create_daily_partitions();
