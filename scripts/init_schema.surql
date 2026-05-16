// ============================================================================
// Project Panopticon - SurrealDB Schema Initialization
// ============================================================================

// Use the panopticon namespace and osint database
USE namespace:panopticon;
USE database:osint;

// ============================================================================
// Entity Tables
// ============================================================================

// Aircraft table
DEFINE TABLE aircraft SCHEMAFULL;

DEFINE FIELD icao_hex ON aircraft TYPE string ASSERT $value != NONE;
DEFINE FIELD callsign ON aircraft TYPE option<string>;
DEFINE FIELD coordinates ON aircraft TYPE geometry<point>;
DEFINE FIELD altitude ON aircraft TYPE option<float>;
DEFINE FIELD velocity ON aircraft TYPE option<float>;
DEFINE FIELD heading ON aircraft TYPE option<float>;
DEFINE FIELD aircraft_type ON aircraft TYPE option<string>;
DEFINE FIELD owner_entity ON aircraft TYPE option<record<entity>>;
DEFINE FIELD last_seen ON aircraft TYPE datetime DEFAULT time::now();
DEFINE FIELD created_at ON aircraft TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at ON aircraft TYPE datetime DEFAULT time::now();

DEFINE INDEX idx_aircraft_coords ON aircraft FIELDS coordinates GEOSPATIAL;
DEFINE INDEX idx_aircraft_icao ON aircraft FIELDS icao_hex;
DEFINE INDEX idx_aircraft_type ON aircraft FIELDS aircraft_type;
DEFINE INDEX idx_aircraft_created ON aircraft FIELDS created_at;

// Event table
DEFINE TABLE event SCHEMAFULL;

DEFINE FIELD title ON event TYPE string;
DEFINE FIELD description ON event TYPE option<string>;
DEFINE FIELD coordinates ON event TYPE geometry<point>;
DEFINE FIELD event_type ON event TYPE string;
DEFINE FIELD severity ON event TYPE option<string>;
DEFINE FIELD source ON event TYPE option<string>;
DEFINE FIELD timestamp ON event TYPE datetime DEFAULT time::now();
DEFINE FIELD embedding ON event TYPE option<array<float>>;
DEFINE FIELD raw_data ON event TYPE option<object>;
DEFINE FIELD created_at ON event TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at ON event TYPE datetime DEFAULT time::now();

DEFINE INDEX idx_event_coords ON event FIELDS coordinates GEOSPATIAL;
DEFINE INDEX idx_event_type ON event FIELDS event_type;
DEFINE INDEX idx_event_severity ON event FIELDS severity;
DEFINE INDEX idx_event_timestamp ON event FIELDS timestamp;
DEFINE INDEX idx_event_vector ON event FIELDS embedding MTREE DIMENSION 1536;

// Entity table (organizations, individuals, etc.)
DEFINE TABLE entity SCHEMAFULL;

DEFINE FIELD name ON entity TYPE string;
DEFINE FIELD entity_type ON entity TYPE string;
DEFINE FIELD aliases ON entity TYPE option<array<string>>;
DEFINE FIELD coordinates ON entity TYPE option<geometry<point>>;
DEFINE FIELD description ON entity TYPE option<string>;
DEFINE FIELD website ON entity TYPE option<string>;
DEFINE FIELD social_media ON entity TYPE option<array<string>>;
DEFINE FIELD created_at ON entity TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at ON entity TYPE datetime DEFAULT time::now();

DEFINE INDEX idx_entity_name ON entity FIELDS name;
DEFINE INDEX idx_entity_type ON entity FIELDS entity_type;
DEFINE INDEX idx_entity_coords ON entity FIELDS coordinates GEOSPATIAL;

// ============================================================================
// Graph Edge Tables
// ============================================================================

// Aircraft belongs to Entity
DEFINE TABLE belongs_to SCHEMAFULL TYPE RELATION IN aircraft OUT entity;

// Entity involved in Event
DEFINE TABLE involved_in SCHEMAFULL TYPE RELATION IN entity OUT event;

// Event related to Event
DEFINE TABLE related_to SCHEMAFULL TYPE RELATION IN event OUT event;

// Event related to Entity
DEFINE TABLE event_entity_rel SCHEMAFULL TYPE RELATION IN event OUT entity;

// Aircraft related to Event
DEFINE TABLE aircraft_event_rel SCHEMAFULL TYPE RELATION IN aircraft OUT event;

// ============================================================================
// Indexes for Performance
// ============================================================================

// Composite indexes for common queries
DEFINE INDEX idx_aircraft_event_time ON aircraft_event_rel FIELDS created_at;
DEFINE INDEX idx_entity_event_time ON event_entity_rel FIELDS timestamp;

// ============================================================================
// Sample Data (Optional - for testing)
// ============================================================================

// Uncomment to create sample data
/*
// Sample aircraft
INSERT INTO aircraft {
  icao_hex: "A1B2C3",
  callsign: "TEST001",
  coordinates: point(31.0, 44.0),
  altitude: 10000,
  velocity: 500,
  heading: 90,
  aircraft_type: "A320",
  owner_entity: (SELECT id FROM entity WHERE name = "Test Airline")
};

// Sample event
INSERT INTO event {
  title: "Test Event",
  description: "A test event for demonstration",
  coordinates: point(31.0, 44.0),
  event_type: "test",
  severity: "low",
  source: "test",
  timestamp: time::now()
};

// Sample entity
INSERT INTO entity {
  name: "Test Airline",
  entity_type: "organization",
  description: "A test airline for demonstration",
  website: "https://test-airline.com"
};
*/

// ============================================================================
// Schema Information
// ============================================================================

// View all tables
SELECT * FROM information.schema;

// View all indexes
SELECT * FROM information.indexes;

// View all relations
SELECT * FROM information.relations;