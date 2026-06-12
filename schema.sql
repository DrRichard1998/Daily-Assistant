PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY,

  source TEXT NOT NULL,
  input_type TEXT NOT NULL,

  canonical_text TEXT NOT NULL,
  raw_text TEXT,

  extraction_method TEXT NOT NULL,
  extraction_confidence REAL,

  original_retained INTEGER NOT NULL DEFAULT 0,

  language TEXT NOT NULL DEFAULT 'zh',
  timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
  parse_status TEXT NOT NULL,
  parse_confidence REAL,

  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,

  CHECK (input_type IN ('text', 'image', 'audio', 'mixed')),
  CHECK (original_retained IN (0, 1)),
  CHECK (parse_status IN ('parsed', 'needs_review', 'ignored', 'failed'))
);

CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY,

  type TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT,

  status TEXT NOT NULL,
  confidence REAL,

  due_at TEXT,

  start_at TEXT,
  end_at TEXT,
  all_day INTEGER NOT NULL DEFAULT 0,

  project TEXT,
  people TEXT,
  location TEXT,

  created_from_record_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  completed_at TEXT,

  FOREIGN KEY (created_from_record_id) REFERENCES records(id),

  CHECK (type IN ('task', 'event')),
  CHECK (status IN ('active', 'completed', 'cancelled', 'needs_review')),
  CHECK (all_day IN (0, 1))
);

CREATE TABLE IF NOT EXISTS item_relations (
  id TEXT PRIMARY KEY,

  from_item_id TEXT NOT NULL,
  to_item_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  source_record_id TEXT,

  created_at TEXT NOT NULL,

  FOREIGN KEY (from_item_id) REFERENCES items(id),
  FOREIGN KEY (to_item_id) REFERENCES items(id),
  FOREIGN KEY (source_record_id) REFERENCES records(id),

  CHECK (relation_type IN ('prepares_for', 'related_to', 'duplicate_of')),
  CHECK (from_item_id <> to_item_id),
  UNIQUE (from_item_id, to_item_id, relation_type)
);

CREATE TABLE IF NOT EXISTS item_events (
  id TEXT PRIMARY KEY,

  item_id TEXT NOT NULL,
  record_id TEXT NOT NULL,

  action TEXT NOT NULL,
  before_json TEXT,
  after_json TEXT,

  confidence REAL,
  note TEXT,
  created_at TEXT NOT NULL,

  FOREIGN KEY (item_id) REFERENCES items(id),
  FOREIGN KEY (record_id) REFERENCES records(id),

  CHECK (action IN ('create', 'update', 'complete', 'cancel', 'reopen', 'review'))
);

CREATE TABLE IF NOT EXISTS review_queue (
  id TEXT PRIMARY KEY,

  record_id TEXT NOT NULL,
  item_id TEXT,

  reason TEXT NOT NULL,
  question TEXT,
  status TEXT NOT NULL,

  created_at TEXT NOT NULL,
  resolved_at TEXT,

  FOREIGN KEY (record_id) REFERENCES records(id),
  FOREIGN KEY (item_id) REFERENCES items(id),

  CHECK (status IN ('open', 'resolved', 'dismissed'))
);

CREATE INDEX IF NOT EXISTS idx_records_created_at ON records(created_at);
CREATE INDEX IF NOT EXISTS idx_records_parse_status ON records(parse_status);

CREATE INDEX IF NOT EXISTS idx_items_type_status ON items(type, status);
CREATE INDEX IF NOT EXISTS idx_items_due_at ON items(due_at);
CREATE INDEX IF NOT EXISTS idx_items_start_at ON items(start_at);
CREATE INDEX IF NOT EXISTS idx_items_created_from_record_id ON items(created_from_record_id);

CREATE INDEX IF NOT EXISTS idx_item_relations_from ON item_relations(from_item_id);
CREATE INDEX IF NOT EXISTS idx_item_relations_to ON item_relations(to_item_id);

CREATE INDEX IF NOT EXISTS idx_item_events_item_id ON item_events(item_id);
CREATE INDEX IF NOT EXISTS idx_item_events_record_id ON item_events(record_id);

CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_review_queue_record_id ON review_queue(record_id);
