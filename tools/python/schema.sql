PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS extension_dependencies;
DROP TABLE IF EXISTS profile_extensions;
DROP TABLE IF EXISTS extension_requirements;
DROP TABLE IF EXISTS extension_versions;
DROP TABLE IF EXISTS instructions;
DROP TABLE IF EXISTS profiles;
DROP TABLE IF EXISTS extensions;

CREATE TABLE extensions (
	extension_id INTEGER PRIMARY KEY,
	name TEXT NOT NULL UNIQUE,
	type TEXT,
	long_name TEXT,
	description TEXT,
	source_path TEXT NOT NULL UNIQUE
);

CREATE TABLE profiles (
	profile_id INTEGER PRIMARY KEY,
	name TEXT NOT NULL UNIQUE,
	kind TEXT NOT NULL,
	long_name TEXT,
	mode TEXT,
	base INTEGER,
	source_path TEXT NOT NULL UNIQUE
);

CREATE TABLE extension_versions (
	extension_version_id INTEGER PRIMARY KEY,
	extension_id INTEGER NOT NULL REFERENCES extensions(extension_id) ON DELETE CASCADE,
	version TEXT NOT NULL,
	state TEXT,
	ratification_date TEXT,
	UNIQUE(extension_id, version)
);

CREATE TABLE extension_requirements (
	extension_requirement_id INTEGER PRIMARY KEY,
	extension_id INTEGER NOT NULL REFERENCES extensions(extension_id) ON DELETE CASCADE,
	requirement_path TEXT NOT NULL,
	requirement_kind TEXT NOT NULL,
	required_name TEXT,
	operator TEXT,
	value TEXT,
	UNIQUE(extension_id, requirement_path, required_name, operator, value)
);

CREATE TABLE extension_dependencies (
	extension_id INTEGER NOT NULL REFERENCES extensions(extension_id) ON DELETE CASCADE,
	depends_on_extension_id INTEGER NOT NULL REFERENCES extensions(extension_id) ON DELETE CASCADE,
	requirement_id INTEGER NOT NULL REFERENCES extension_requirements(extension_requirement_id) ON DELETE CASCADE,
	PRIMARY KEY(extension_id, depends_on_extension_id)
);

CREATE TABLE instructions (
	instruction_id INTEGER PRIMARY KEY,
	name TEXT NOT NULL UNIQUE,
	extension_id INTEGER REFERENCES extensions(extension_id) ON DELETE SET NULL,
	long_name TEXT,
	assembly TEXT,
	description TEXT,
	encoding_match TEXT,
	source_path TEXT NOT NULL UNIQUE
);

CREATE TABLE profile_extensions (
	profile_id INTEGER NOT NULL REFERENCES profiles(profile_id) ON DELETE CASCADE,
	extension_name TEXT NOT NULL,
	extension_id INTEGER REFERENCES extensions(extension_id) ON DELETE SET NULL,
	presence TEXT,
	version_constraint TEXT,
	note TEXT,
	PRIMARY KEY(profile_id, extension_name)
);

CREATE INDEX idx_extension_versions_extension ON extension_versions(extension_id);
CREATE INDEX idx_extension_requirements_extension ON extension_requirements(extension_id);
CREATE INDEX idx_extension_dependencies_dependency ON extension_dependencies(depends_on_extension_id);
CREATE INDEX idx_instructions_extension ON instructions(extension_id);
CREATE INDEX idx_profile_extensions_extension ON profile_extensions(extension_id);
