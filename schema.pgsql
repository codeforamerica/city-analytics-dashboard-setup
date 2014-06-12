DROP TABLE connections;

CREATE TABLE connections
(
    email_address   TEXT,
    profile_name    TEXT,
    website_url     TEXT,

    connected_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
