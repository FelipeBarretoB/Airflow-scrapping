CREATE TABLE IF NOT EXISTS regulations(
    id SERIAL PRIMARY KEY,
    created_at TEXT,
    update_at TIMESTAMP,
    is_active BOOLEAN,
    title TEXT,
    gtype TEXT,
    entity TEXT,
    external_link TEXT,
    rtype_id INTEGER,
    summary TEXT,
    classification_id INTEGER
);

CREATE TABLE IF NOT EXISTS regulations_component(
    id SERIAL PRIMARY KEY,
    regulations_id INTEGER,
    components_id INTEGER,
    FOREIGN KEY (regulations_id) REFERENCES regulations(id)
);