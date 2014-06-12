DROP TABLE connections;
DROP TABLE tarballs;

CREATE TABLE connections
(
    email_address   TEXT,
    profile_name    TEXT,
    website_url     TEXT,

    connected_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE tarballs
(
    id          SERIAL PRIMARY KEY,
    contents    BYTEA,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
