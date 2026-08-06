-- TaxBriefing PostgreSQL schema draft v1.0
-- Review before production. UUID generation assumes pgcrypto.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE authority_grade AS ENUM ('A','B','C','D');
CREATE TYPE legal_status AS ENUM ('DISCUSSION','BILL_PROPOSED','PREANNOUNCED','GOV_ANNOUNCED','ASSEMBLY_PASSED','PROMULGATED','EFFECTIVE','SUSPENDED','ABOLISHED','UNKNOWN');
CREATE TYPE workflow_status AS ENUM ('DETECTED','UNVERIFIED','SOURCE_CONFIRMED','ANALYZED','REVIEW_PENDING','APPROVED','SCHEDULED','PUBLISHED','MONITORING','CORRECTED','SUPERSEDED','ARCHIVED');
CREATE TYPE risk_level AS ENUM ('LOW','MEDIUM','HIGH','CRITICAL');
CREATE TYPE review_decision AS ENUM ('APPROVE','APPROVE_WITH_EDIT','REJECT');
CREATE TYPE delivery_status AS ENUM ('PENDING','QUEUED','SENT','DELIVERED','FAILED','BOUNCED','CANCELED');

CREATE TABLE tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  slug text NOT NULL UNIQUE,
  status text NOT NULL DEFAULT 'ACTIVE',
  settings jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenants(id),
  email text NOT NULL,
  phone text,
  display_name text,
  role text NOT NULL DEFAULT 'SUBSCRIBER',
  status text NOT NULL DEFAULT 'ACTIVE',
  password_hash text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id,email)
);

CREATE TABLE sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  display_name text NOT NULL,
  organization_code text,
  canonical_domain text NOT NULL,
  authority authority_grade NOT NULL,
  collector_type text NOT NULL,
  schedule_cron text,
  rate_limit_per_min integer,
  terms_url text,
  copyright_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
  adapter_name text,
  adapter_version text,
  status text NOT NULL DEFAULT 'ACTIVE',
  last_success_at timestamptz,
  failure_streak integer NOT NULL DEFAULT 0,
  settings jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE source_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL REFERENCES sources(id),
  run_type text NOT NULL,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  status text NOT NULL,
  discovered_count integer NOT NULL DEFAULT 0,
  new_count integer NOT NULL DEFAULT 0,
  changed_count integer NOT NULL DEFAULT 0,
  error_count integer NOT NULL DEFAULT 0,
  error_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  trace_id text
);

CREATE TABLE raw_contents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL REFERENCES sources(id),
  source_item_id text,
  canonical_url text NOT NULL,
  title text NOT NULL,
  publisher text NOT NULL,
  published_at timestamptz,
  first_collected_at timestamptz NOT NULL DEFAULT now(),
  last_checked_at timestamptz NOT NULL DEFAULT now(),
  current_version_id uuid,
  status text NOT NULL DEFAULT 'ACTIVE',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (source_id, canonical_url)
);

CREATE TABLE raw_content_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  raw_content_id uuid NOT NULL REFERENCES raw_contents(id) ON DELETE CASCADE,
  version_no integer NOT NULL,
  content_hash char(64) NOT NULL,
  raw_html text,
  normalized_text text NOT NULL,
  http_etag text,
  http_last_modified text,
  parser_version text NOT NULL,
  collected_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (raw_content_id,version_no),
  UNIQUE (raw_content_id,content_hash)
);
ALTER TABLE raw_contents ADD CONSTRAINT raw_current_version_fk FOREIGN KEY (current_version_id) REFERENCES raw_content_versions(id);

CREATE TABLE attachments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  raw_content_version_id uuid NOT NULL REFERENCES raw_content_versions(id) ON DELETE CASCADE,
  filename text NOT NULL,
  mime_type text,
  byte_size bigint,
  content_hash char(64) NOT NULL,
  object_key text NOT NULL,
  extraction_status text NOT NULL DEFAULT 'PENDING',
  extracted_text text,
  malware_scan_status text NOT NULL DEFAULT 'PENDING',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (raw_content_version_id,content_hash)
);

CREATE TABLE policy_clusters (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_title text NOT NULL,
  topic_key text,
  status text NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE policy_cluster_items (
  policy_cluster_id uuid REFERENCES policy_clusters(id) ON DELETE CASCADE,
  raw_content_id uuid REFERENCES raw_contents(id) ON DELETE CASCADE,
  relation_type text NOT NULL DEFAULT 'RELATED',
  confidence numeric(5,4),
  PRIMARY KEY (policy_cluster_id,raw_content_id)
);

CREATE TABLE tax_contents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenants(id),
  policy_cluster_id uuid REFERENCES policy_clusters(id),
  workflow workflow_status NOT NULL DEFAULT 'DETECTED',
  legal legal_status NOT NULL DEFAULT 'UNKNOWN',
  risk risk_level NOT NULL DEFAULT 'MEDIUM',
  title text NOT NULL,
  one_line_summary text,
  announcement_date date,
  promulgation_date date,
  effective_date date,
  application_start date,
  application_end date,
  source_confidence smallint NOT NULL DEFAULT 0 CHECK (source_confidence BETWEEN 0 AND 100),
  current_version_id uuid,
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE content_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tax_content_id uuid NOT NULL REFERENCES tax_contents(id) ON DELETE CASCADE,
  version_no integer NOT NULL,
  body jsonb NOT NULL,
  rendered_html text,
  change_note text,
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tax_content_id,version_no)
);
ALTER TABLE tax_contents ADD CONSTRAINT content_current_version_fk FOREIGN KEY (current_version_id) REFERENCES content_versions(id);

CREATE TABLE content_sources (
  tax_content_id uuid NOT NULL REFERENCES tax_contents(id) ON DELETE CASCADE,
  raw_content_version_id uuid NOT NULL REFERENCES raw_content_versions(id),
  role text NOT NULL CHECK (role IN ('PRIMARY','SECONDARY','REFERENCE')),
  verified_by uuid REFERENCES users(id),
  verified_at timestamptz,
  PRIMARY KEY (tax_content_id,raw_content_version_id)
);

CREATE TABLE content_evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tax_content_id uuid NOT NULL REFERENCES tax_contents(id) ON DELETE CASCADE,
  content_version_id uuid REFERENCES content_versions(id),
  field_name text NOT NULL,
  raw_content_version_id uuid NOT NULL REFERENCES raw_content_versions(id),
  locator text NOT NULL,
  support_type text NOT NULL CHECK (support_type IN ('DIRECT','INFERRED','CONFLICT')),
  note text
);

CREATE TABLE ai_analyses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tax_content_id uuid REFERENCES tax_contents(id),
  policy_cluster_id uuid REFERENCES policy_clusters(id),
  prompt_template_id text NOT NULL,
  prompt_version text NOT NULL,
  schema_version text NOT NULL,
  model_provider text NOT NULL,
  model_name text NOT NULL,
  input_hash char(64) NOT NULL,
  output_json jsonb,
  validation_result jsonb NOT NULL DEFAULT '{}'::jsonb,
  token_usage jsonb NOT NULL DEFAULT '{}'::jsonb,
  cost_amount numeric(12,6),
  latency_ms integer,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE reviews (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tax_content_id uuid NOT NULL REFERENCES tax_contents(id) ON DELETE CASCADE,
  content_version_id uuid NOT NULL REFERENCES content_versions(id),
  reviewer_id uuid NOT NULL REFERENCES users(id),
  decision review_decision NOT NULL,
  review_note text,
  checked_source_version_ids uuid[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE corrections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tax_content_id uuid NOT NULL REFERENCES tax_contents(id),
  original_content_version_id uuid NOT NULL REFERENCES content_versions(id),
  corrected_content_version_id uuid NOT NULL REFERENCES content_versions(id),
  reason_code text NOT NULL,
  reason_detail text NOT NULL,
  severity risk_level NOT NULL,
  impact_filter jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'DRAFT',
  approved_by uuid REFERENCES users(id),
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tags (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tag_type text NOT NULL,
  code text NOT NULL,
  label text NOT NULL,
  parent_id uuid REFERENCES tags(id),
  status text NOT NULL DEFAULT 'ACTIVE',
  UNIQUE(tag_type,code)
);
CREATE TABLE content_tags (
  tax_content_id uuid REFERENCES tax_contents(id) ON DELETE CASCADE,
  tag_id uuid REFERENCES tags(id),
  source text NOT NULL DEFAULT 'MANUAL',
  confidence numeric(5,4),
  PRIMARY KEY (tax_content_id,tag_id)
);

CREATE TABLE business_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  business_type text NOT NULL,
  tax_type text,
  industry_codes text[] NOT NULL DEFAULT '{}',
  region_codes text[] NOT NULL DEFAULT '{}',
  employee_band text,
  revenue_band text,
  interest_topics text[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE consents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  consent_type text NOT NULL,
  channel text,
  granted boolean NOT NULL,
  document_version text NOT NULL,
  granted_at timestamptz NOT NULL,
  revoked_at timestamptz,
  source text,
  UNIQUE(user_id,consent_type,channel,granted_at)
);

CREATE TABLE campaigns (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenants(id),
  campaign_type text NOT NULL,
  name text NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT',
  audience_filter jsonb NOT NULL,
  channels text[] NOT NULL,
  scheduled_at timestamptz,
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE campaign_contents (
  campaign_id uuid REFERENCES campaigns(id) ON DELETE CASCADE,
  content_version_id uuid REFERENCES content_versions(id),
  sort_order integer NOT NULL DEFAULT 0,
  PRIMARY KEY(campaign_id,content_version_id)
);
CREATE TABLE campaign_recipients (
  campaign_id uuid REFERENCES campaigns(id) ON DELETE CASCADE,
  user_id uuid REFERENCES users(id),
  match_score integer,
  match_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  excluded_reason text,
  PRIMARY KEY(campaign_id,user_id)
);
CREATE TABLE deliveries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id uuid NOT NULL REFERENCES campaigns(id),
  user_id uuid NOT NULL REFERENCES users(id),
  channel text NOT NULL,
  provider text NOT NULL,
  idempotency_key text NOT NULL UNIQUE,
  provider_message_id text,
  status delivery_status NOT NULL DEFAULT 'PENDING',
  message_snapshot jsonb NOT NULL,
  attempted_at timestamptz,
  delivered_at timestamptz,
  error_code text,
  error_detail text
);

CREATE TABLE engagement_events (
  id bigserial PRIMARY KEY,
  tenant_id uuid REFERENCES tenants(id),
  user_id uuid REFERENCES users(id),
  delivery_id uuid REFERENCES deliveries(id),
  tax_content_id uuid REFERENCES tax_contents(id),
  event_type text NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE consultation_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenants(id),
  user_id uuid NOT NULL REFERENCES users(id),
  tax_content_id uuid REFERENCES tax_contents(id),
  message text,
  status text NOT NULL DEFAULT 'NEW',
  assigned_to uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_logs (
  id bigserial PRIMARY KEY,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor_user_id uuid REFERENCES users(id),
  tenant_id uuid REFERENCES tenants(id),
  action text NOT NULL,
  object_type text NOT NULL,
  object_id text NOT NULL,
  before_data jsonb,
  after_data jsonb,
  reason text,
  ip_hash text,
  trace_id text
);

CREATE INDEX idx_raw_contents_published ON raw_contents(published_at DESC);
CREATE INDEX idx_raw_versions_hash ON raw_content_versions(content_hash);
CREATE INDEX idx_tax_contents_status ON tax_contents(workflow,legal,risk);
CREATE INDEX idx_tax_contents_dates ON tax_contents(effective_date,application_end);
CREATE INDEX idx_content_evidence_content ON content_evidence(tax_content_id,field_name);
CREATE INDEX idx_deliveries_campaign_status ON deliveries(campaign_id,status);
CREATE INDEX idx_engagement_content_time ON engagement_events(tax_content_id,occurred_at DESC);
CREATE INDEX idx_audit_object ON audit_logs(object_type,object_id,occurred_at DESC);
