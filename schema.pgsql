DROP TABLE connections;
DROP TABLE tarballs;

CREATE TABLE connections
(
    id              SERIAL PRIMARY KEY,
    
    email_address   TEXT,
    profile_name    TEXT,
    website_url     TEXT,

    connected_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE tarballs
(
    id          INT REFERENCES connections(id),
    contents    BYTEA,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
