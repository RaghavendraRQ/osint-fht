# AI-Enhanced OSINT Framework for Human Trafficker Identification Using Phone-Centric Social Graph Analysis

> **Purpose:** Given a phone number (and optionally an email), this framework automatically queries 8 different OSINT sources across the surface web, searches the dark web via Ahmia/Tor, builds a Neo4j graph of all discovered entities, and applies graph analytics (community detection, centrality analysis, temporal tracking) to identify potential human trafficking networks.

---

## Table of Contents

- [How It Works (End-to-End Workflow)](#how-it-works-end-to-end-workflow)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [API Integrations](#api-integrations)
- [Setup & Installation](#setup--installation)
- [Configuration (.env)](#configuration-env)
- [Running the Application](#running-the-application)
- [API Endpoints](#api-endpoints)
- [Graph Analytics Features](#graph-analytics-features)
- [Risk Scoring System](#risk-scoring-system)
- [Periodic Scanning](#periodic-scanning)
- [Testing with Real-World Cases](#testing-with-real-world-cases)
- [Limitations & Ethics](#limitations--ethics)
- [License](#license)

---

## How It Works (End-to-End Workflow)

This is the complete data pipeline from input to output:

```
Step 1: USER INPUT
   User enters a phone number (e.g., +91-XXXXXXXXXX) and optionally an email
   on the web UI at http://localhost:8000

Step 2: PHONE VALIDATION
   phonenumbers library validates format, extracts country code, carrier, line type

Step 3: SURFACE WEB OSINT (parallel)
   The OSINTManager fires all configured API handlers concurrently:
   ┌─ NumVerify ──────→ carrier, country, line type, validity
   ├─ TrueCaller ─────→ registered name, alternate phones, addresses
   ├─ Hunter.io ──────→ email domain search, associated emails
   ├─ Sherlock ───────→ username presence across 300+ sites
   ├─ Maigret ────────→ username OSINT across 2000+ sites
   ├─ Blackbird ──────→ username/email search across platforms
   └─ SpiderFoot ─────→ automated scan for emails, usernames, domains, IPs

Step 4: ENTITY RESOLUTION
   EntityResolver deduplicates and normalizes all discovered entities:
   phones, emails, usernames, social accounts, domains, names
   Each entity gets a confidence score based on how many sources confirmed it

Step 5: DARK WEB SEARCH (if enabled)
   5a. Ahmia clearnet search — queries ahmia.fi for each entity
   5b. Tor .onion scraping — top results (by risk score) are fetched
       through the SOCKS5 Tor proxy for full-page content analysis
   5c. Weighted keyword matching — 30+ trafficking-related keywords
       with severity weights (1.0 critical → 0.2 low) including
       India-specific terms
   5d. Cross-entity matching — flags pages where multiple entities
       from the same investigation appear together (high-confidence link)

Step 6: RISK SCORING
   Composite score (0.0 to 1.0) based on:
   - Dark web mention count (30%)
   - Cross-entity matches (25%)
   - Weighted keyword severity (30%)
   - High-risk indicator density (15%)
   Mapped to levels: MINIMAL → LOW → MEDIUM → HIGH → CRITICAL

Step 7: NEO4J GRAPH STORAGE
   All entities and relationships are persisted to Neo4j:
   - Nodes: Phone, Email, Username, Profile, DarkWebSite, OnionDomain,
            CrossMatch, Carrier, Location, Organization
   - Relationships: HAS_EMAIL, HAS_USERNAME, HAS_PROFILE, MENTIONED_IN,
                    HOSTED_ON, CROSS_REFERENCED, RELATED_PHONE, etc.
   - Temporal data: first_seen, last_seen, mention_count on all
     MENTIONED_IN relationships

Step 8: GRAPH ANALYTICS
   Neo4j Graph Data Science plugin runs:
   - Louvain community detection — finds clusters of connected entities
   - Betweenness centrality — identifies hub/facilitator nodes
   - Connected phones — 2-hop traversal to find related investigations
   - High-risk entity detection — phones with multiple dark web mentions
   - Temporal tracking — timeline of appearances/reappearances

Step 9: RESULTS DISPLAY
   Web dashboard shows:
   - Per-API results in expandable accordion cards
   - Dark web findings with risk banners and keyword highlights
   - Entity relationship network graph (Plotly interactive)
   - Graph Analytics section: Connected Investigations, Risk Clusters,
     Network Role (centrality), High Risk Entities, Activity Timeline
   - Summary statistics: success/failure counts, average confidence
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        User (Browser)                            │
│                     http://localhost:8000                         │
└──────────────────┬───────────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                    FastAPI Web Application                        │
│  Routes: /, /search, /search/stream (SSE), /results/{phone},    │
│          /history, /download/{phone}, /api/status,               │
│          /api/graph/connections, /clusters, /high-risk,          │
│          /centrality, /network, /timeline, /movement             │
└──────────┬──────────────────────────────────┬────────────────────┘
           │                                  │
           ▼                                  ▼
┌─────────────────────┐          ┌─────────────────────────────────┐
│    OSINT Manager     │          │      Neo4j Graph Database       │
│  (Orchestrator)      │          │  Plugins: APOC, Graph Data Sci  │
│                      │          │  Port: 7474 (HTTP), 7687 (Bolt) │
└──┬──┬──┬──┬──┬──┬──┬┘          └─────────────────────────────────┘
   │  │  │  │  │  │  │
   │  │  │  │  │  │  └─── SpiderFoot API (self-hosted)
   │  │  │  │  │  └────── Blackbird CLI
   │  │  │  │  └───────── Maigret CLI
   │  │  │  └──────────── Sherlock CLI
   │  │  └─────────────── Hunter.io API
   │  └────────────────── TrueCaller API
   └───────────────────── NumVerify API
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Entity Resolver                              │
│  Normalize, deduplicate, assign confidence scores                │
└──────────┬──────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Dark Web Phase                                 │
│  1. Ahmia Search (clearnet) ──→ .onion URLs + snippets           │
│  2. Tor Proxy Scraper ────────→ full .onion page content         │
│     (via SOCKS5 at port 9050)                                    │
│  3. Weighted Risk Scorer ─────→ keyword matching + risk score    │
│  4. Cross-Entity Matcher ─────→ multi-entity page detection      │
└──────────┬──────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Graph Analytics Engine                          │
│  - Community Detection (Louvain)                                 │
│  - Centrality Analysis (Betweenness)                             │
│  - Temporal Tracking (first_seen / mention_count)                │
│  - Cross-Entity Matching                                         │
│  - Movement Pattern Detection                                    │
└─────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│              Results Dashboard + JSON Export                      │
│  Interactive network graph, risk banners, timeline charts,       │
│  connected investigations, cluster view, downloadable JSON       │
└─────────────────────────────────────────────────────────────────┘
           │
           ▼  (optional, runs on schedule)
┌─────────────────────────────────────────────────────────────────┐
│                   Periodic Scanner                                │
│  APScheduler re-scans all previously investigated phones         │
│  every N hours, compares new results, updates Neo4j              │
└─────────────────────────────────────────────────────────────────┘
```

---


## API Integrations

| # | Service | What It Provides | Auth |
|---|---------|-----------------|------|
| 1 | **NumVerify** | Phone validation, carrier, country, line type | API key |
| 2 | **TrueCaller** | Caller name, alternate numbers, addresses | API key via `truecallerpy` |
| 3 | **Hunter.io** | Email domain search, email finder, verification | API key via `pyhunter` |
| 4 | **Sherlock** | Username presence across 300+ websites | None (CLI tool) |
| 5 | **Maigret** | Username OSINT across 2000+ websites | None (CLI tool) |
| 6 | **Blackbird** | Username and email search across platforms | None (CLI tool) |
| 7 | **SpiderFoot** | Automated scans: emails, IPs, domains, usernames | Self-hosted API |
| 8 | **Ahmia + Tor** | Dark web search + .onion page scraping | None (Tor proxy required) |

---

## Setup & Installation

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Git

### Quick Start (Docker)

```bash
# 1. Clone the repository
git clone <repo-url>
cd osint-fr-ht

# 2. Create .env file with your API keys
cp .env.example .env
# Edit .env and fill in: NUMVERIFY_API_KEY, TRUECALLER_API_KEY, HUNTER_API_KEY

# 3. Start all services (Neo4j + Tor + App)
docker-compose up --build -d

# 4. Wait for Neo4j to become healthy (~30s), then open:
#    http://localhost:8000       — Web UI
#    http://localhost:7474       — Neo4j Browser
```

## Configuration (.env)

```env
# Required API Keys
NUMVERIFY_API_KEY=your_numverify_key
TRUECALLER_API_KEY=your_truecaller_key
HUNTER_API_KEY=your_hunter_key

# Optional: SpiderFoot (if self-hosted)
SPIDERFOOT_API_URL=http://127.0.0.1:5001
SPIDERFOOT_API_KEY=

# Neo4j (defaults match docker-compose.yml)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# Tor Proxy (defaults match docker-compose.yml)
TOR_PROXY_HOST=localhost
TOR_PROXY_PORT=9050

# Periodic Scanner (optional)
SCHEDULER_ENABLED=false
SCHEDULER_INTERVAL_HOURS=6
```

---

## Graph Analytics Features

The Neo4j Graph Data Science plugin powers four analytics capabilities:

### Community Detection (Louvain)
Identifies clusters of entities that are densely connected. If two phone numbers share multiple dark web site mentions, emails, or usernames, they are grouped into the same community — indicating they may belong to the same trafficking network.

### Betweenness Centrality
Measures how often a node sits on the shortest path between other nodes. High centrality = likely a facilitator or hub in the network (e.g., a recruiter phone that connects multiple victims to multiple dark web sites).

### Temporal Tracking
Every `MENTIONED_IN` relationship records `first_seen`, `last_seen`, and `mention_count`. This enables:
- Detecting new appearances on the dark web
- Tracking frequency of re-occurrence
- Identifying temporal patterns (e.g., periodic posting)

### Connected Investigations
2-hop graph traversal from a phone number through shared entities to find other phone numbers that share dark web presence, emails, or usernames — linking separate investigations.

---

## Risk Scoring System

The dark web risk score is a weighted composite:

| Factor | Weight | Calculation |
|--------|--------|-------------|
| Dark web mention count | 30% | `min(count * 0.06, 0.30)` |
| Cross-entity matches | 25% | `min(count * 0.125, 0.25)` |
| Weighted keyword severity | 30% | `min(sum_of_weights * 0.03, 0.30)` |
| High-risk indicator density | 15% | `min(count * 0.05, 0.15)` |

**Keyword tiers:**

| Tier | Weight | Examples |
|------|--------|---------|
| Critical | 1.0 | trafficking, underage, child exploitation, forced labor, sex trafficking |
| High | 0.7 | smuggling, slave, passport confiscation, visa fraud, organ trade |
| Medium | 0.4 | escort, brothel, recruitment agency, red light |
| Low | 0.2 | massage, services, agency, travel |
| India-specific | 0.4–0.7 | devadasi, jogini, kamathipura, sonagachi, gb road |

**Risk levels:** MINIMAL (< 0.1) → LOW (0.1–0.3) → MEDIUM (0.3–0.5) → HIGH (0.5–0.7) → CRITICAL (≥ 0.7)

---

## Periodic Scanning

When `SCHEDULER_ENABLED=true`, an APScheduler job runs every `SCHEDULER_INTERVAL_HOURS` hours:

1. Loads all previously investigated phone numbers from `data/results/`
2. Re-runs the full OSINT pipeline (including dark web search) for each
3. Saves new results to disk
4. Updates the Neo4j graph (temporal tracking increments `mention_count`)
5. New dark web appearances are flagged via changed `first_seen`/`last_seen` timestamps

---

## Testing with Real-World Cases

The following are **publicly documented** human trafficking cases from law enforcement records, news reports, and NGO publications. They are provided to illustrate the kind of data patterns this tool is designed to detect. **All information below is already in the public domain.**

### Case 1: Operation Cross Country (FBI, USA — recurring annually)

**Background:** The FBI's Operation Cross Country is an annual nationwide operation targeting sex trafficking networks. In 2023 (Operation Cross Country XVI), 59 child victims were identified and 103 suspects arrested across multiple US states.

**How this tool would help:**
- Phone numbers posted in online escort advertisements are the primary entry point
- Sherlock/Maigret would discover usernames reused across multiple escort sites
- Ahmia dark web search would find .onion mirrors of these advertisements
- Neo4j community detection would cluster phones sharing the same ad posting patterns
- Centrality analysis would identify the "manager" phones connecting multiple victims

**Test data pattern:** Multiple phone numbers posting similar escort ads across different cities, sharing the same email or username root (e.g., `manager_chicago`, `manager_detroit`).

**Public references:**
- FBI press release: "Operation Cross Country" (fbi.gov)
- National Center for Missing & Exploited Children reports

---

### Case 2: Telangana Trafficking Ring (India, 2022–2023)

**Background:** Hyderabad police dismantled a trafficking ring operating across Telangana and Andhra Pradesh that used WhatsApp groups and social media to recruit young women under false job promises. The ring used rotating phone numbers registered under fake identities and posted on both surface web job portals and dark web forums.

**How this tool would help:**
- Input the known phone numbers used by the ring
- NumVerify/TrueCaller would reveal carrier patterns (same carrier, same region)
- Hunter.io would trace associated email domains used for fake job postings
- Ahmia search with India-specific keywords (`placement agency`, `manpower agency`) would surface dark web postings
- Neo4j graph would reveal the phone number network — the recruiter, transporter, and handler roles would emerge as distinct centrality tiers

**Test data pattern:** 3-5 phone numbers all registered with the same carrier in Hyderabad, linked to emails on the same domain, with dark web presence mentioning `recruitment`, `placement agency`, and specific city names.

**Public references:**
- Hyderabad Cyber Crime Police press releases (2022–2023)
- Telangana State Anti-Human Trafficking Unit reports

---

### Case 4: Polaris Project — Trafficking Hotline Data Patterns (USA)

**Background:** The Polaris Project operates the US National Human Trafficking Hotline. Their annual reports document common patterns: traffickers use prepaid/burner phones, rotate numbers every 2-4 weeks, share numbers across victim-posted ads, and maintain a "digital footprint" that connects to dark web forums.

**How this tool would help:**
- Periodic scanner (Phase 5) would detect when a phone number disappears from one dark web site and reappears on another — matching the burner phone rotation pattern
- Community detection would group burner phones that share the same email or username infrastructure
- Movement pattern detection (via dark web snippet geographic analysis) would show a phone's digital presence moving between cities

**Test data pattern:** Phone number A active for 2 weeks, then goes silent. Phone number B appears with the same email and similar usernames — the Neo4j graph would link A and B through shared entities.

**Public references:**
- Polaris Project: "Typology of Modern Slavery" report
- National Human Trafficking Hotline annual reports (polarisproject.org)


---

## Limitations & Ethics

- **Legal compliance:** Only use this tool for lawful investigations. Dark web scraping must comply with your jurisdiction's laws.
- **False positives:** Keyword matching (even weighted) will produce false positives. The risk score is an indicator, not proof.
- **Ahmia limitations:** Ahmia indexes only a fraction of .onion sites. Many trafficking operations use private/invite-only hidden services not indexed by any search engine.
- **Tor scraping:** .onion sites may be offline, slow, or block scrapers. The scrape success rate varies.
- **API rate limits:** Free tiers of NumVerify and Hunter.io have monthly quotas. TrueCaller may rate-limit aggressive querying.
- **Neo4j GDS:** Community detection and centrality require sufficient graph data. Single investigations with few entities will not produce meaningful analytics — the value increases as more phone numbers are investigated and the graph grows.
- **This tool does not replace human judgment.** All findings should be verified by trained investigators before any action is taken.

