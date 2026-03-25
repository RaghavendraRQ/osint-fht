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

## Project Structure

```
osint-fr-ht/
├── config.py                          # All config: API keys, URLs, timeouts, paths
├── run.py                             # Application entrypoint (argparse, uvicorn)
├── requirements.txt                   # Python dependencies
├── Dockerfile                         # Multi-stage build (Python 3.11-slim)
├── docker-compose.yml                 # 3 services: neo4j, tor, osint-app
├── check_setup.py                     # Pre-flight environment checker
│
├── src/
│   ├── osint/
│   │   ├── __init__.py                # Exports OSINTManager
│   │   └── osint_manager.py           # Central orchestrator for all handlers
│   │
│   ├── api_handlers/
│   │   ├── __init__.py                # Re-exports all handler classes
│   │   ├── base_handler.py            # Abstract base: rate limiting, retries, aiohttp
│   │   ├── numverify.py               # Phone validation via NumVerify
│   │   ├── truecaller.py              # Caller ID via TrueCaller
│   │   ├── hunter.py                  # Email intelligence via Hunter.io
│   │   ├── sherlock.py                # Username search via Sherlock CLI
│   │   ├── maigret.py                 # Username search via Maigret CLI
│   │   ├── blackbird.py               # Username/email search via Blackbird CLI
│   │   ├── spiderfoot.py              # Automated scanning via SpiderFoot API
│   │   └── ahmia_handler.py           # Dark web search + Tor scraping + risk scoring
│   │
│   ├── utils/
│   │   ├── phone_validator.py         # phonenumbers-based validation
│   │   ├── entity_resolver.py         # Dedup, normalize, confidence scoring
│   │   └── neo4j_handler.py           # Graph DB: CRUD + analytics queries
│   │
│   ├── visualization/
│   │   ├── __init__.py
│   │   └── graph_generator.py         # NetworkX graph data builder
│   │
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── periodic_scanner.py        # APScheduler-based periodic re-scanning
│   │
│   └── web/
│       ├── main.py                    # FastAPI app: routes, SSE, graph API
│       ├── static/style.css
│       └── templates/
│           ├── index.html             # Search form + API status dashboard
│           ├── results.html           # Full results + graph analytics + timeline
│           └── history.html           # Past search history
│
└── data/
    ├── results/                       # JSON result files per investigation
    └── neo4j/                         # Neo4j data and logs (Docker volume)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11, FastAPI, Uvicorn, asyncio, aiohttp |
| **Dark Web** | Ahmia search engine, Tor SOCKS5 proxy (`aiohttp-socks`), BeautifulSoup |
| **Graph Database** | Neo4j 5.12 with APOC and Graph Data Science plugins |
| **Frontend** | Jinja2, TailwindCSS, Plotly.js (graphs + timeline), GSAP, Three.js |
| **Scheduling** | APScheduler (AsyncIOScheduler) |
| **Containerization** | Docker, Docker Compose (3-service stack) |
| **Phone Validation** | `phonenumbers` library |
| **CLI Tools** | Sherlock, Maigret, Blackbird (subprocess wrappers) |

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

### Quick Start (Docker — recommended)

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

### Local Development (without Docker)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start Neo4j separately (or use Docker just for Neo4j + Tor)
docker-compose up neo4j tor -d

# 3. Set environment variables
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password
export TOR_PROXY_HOST=localhost
export TOR_PROXY_PORT=9050

# 4. Run the application
python run.py --host 0.0.0.0 --port 8000 --reload
```

### Verify Setup

```bash
python check_setup.py
```

This checks: Python version, required packages, API key configuration, CLI tool availability (Sherlock, Maigret, Blackbird), Neo4j connectivity, Tor proxy connectivity.

---

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

## Running the Application

```bash
# Production (via Docker)
docker-compose up -d

# Development
python run.py --host 0.0.0.0 --port 8000 --reload --debug

# Check API status
curl http://localhost:8000/api/status
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web UI — search form with API status dashboard |
| `POST` | `/search` | Run full OSINT investigation (JSON response) |
| `POST` | `/search/stream` | SSE stream of investigation progress |
| `GET` | `/results/{phone}` | Results dashboard for a phone number |
| `GET` | `/download/{phone}` | Download results as JSON |
| `GET` | `/history` | Search history page |
| `GET` | `/api/status` | API health status for all integrations |
| `GET` | `/api/graph/connections/{phone}` | Connected phone numbers (2-hop) |
| `GET` | `/api/graph/clusters` | Community detection (Louvain) |
| `GET` | `/api/graph/high-risk` | Entities with multiple high-risk dark web mentions |
| `GET` | `/api/graph/centrality` | Betweenness centrality (top 20 facilitators) |
| `GET` | `/api/graph/network/{phone}` | Full subgraph for visualization |
| `GET` | `/api/graph/timeline/{phone}` | Temporal activity timeline |
| `GET` | `/api/graph/movement/{phone}` | Geographic movement pattern detection |

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

### Case 3: Backpage.com Network (USA, seized 2018)

**Background:** Backpage.com was the largest online marketplace for sex ads in the US before it was seized by the DOJ in 2018. Analysis of Backpage data revealed that many traffickers used the same phone numbers across hundreds of ads in different cities, the same email to manage multiple accounts, and the same usernames on linked platforms.

**How this tool would help:**
- Input any phone number from historical Backpage ad data (publicly available via court records)
- Sherlock/Maigret would find the same username active on social media, dating sites, and other ad platforms
- The cross-entity matching in Ahmia would find the same phone + email combination appearing on dark web forums that mirror old Backpage content
- Temporal tracking would show the same phone appearing in different cities over weeks — a strong indicator of circuit trafficking

**Test data pattern:** Single phone number appearing in ads across 5+ cities within 30 days, same email managing accounts on 3+ platforms, username variations following a pattern (`sweetie_ny`, `sweetie_la`, `sweetie_chi`).

**Public references:**
- US Department of Justice: "Backpage.com and Affiliated Websites" case documents
- Senate Permanent Subcommittee on Investigations: "Backpage.com's Knowing Facilitation of Online Sex Trafficking" report

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

### Case 5: Sunitha Krishnan / Prajwala Foundation Cases (India)

**Background:** Prajwala Foundation, led by Sunitha Krishnan, has worked extensively on rescuing trafficking victims in India, particularly from Kamathipura (Mumbai), Sonagachi (Kolkata), and GB Road (Delhi). Their documented cases show traffickers using specific phone networks and online recruitment through job portals and social media.

**How this tool would help:**
- India-specific keywords in the risk scorer (`kamathipura`, `sonagachi`, `gb road`, `devadasi`, `jogini`) would boost risk scores for dark web results mentioning these locations
- Phone numbers from known trafficking hotspots could be investigated to map the recruiter-to-destination network
- Neo4j graph analytics would reveal whether isolated cases are actually connected through shared infrastructure

**Public references:**
- Prajwala Foundation case documentation (prajwalaindia.com)
- UNODC reports on trafficking in South Asia

---

### How to Use These Cases for Testing

1. **Do NOT use real victim phone numbers.** Use only publicly known trafficker/organizational phone numbers from court records, or create synthetic test data following the patterns described above.

2. **Synthetic test workflow:**
   ```
   # Create a set of test phone numbers that simulate a trafficking network
   # Phone A (recruiter): connected to emails on job-portal domains
   # Phone B (transporter): same email domain, different cities in dark web mentions
   # Phone C (handler): shares username pattern with A and B

   # Run investigation on each
   POST /search {"phone_number": "+91XXXXXXXXXX", "include_darkweb": true}

   # After all three are in Neo4j, check graph analytics:
   GET /api/graph/clusters          # Should group A, B, C together
   GET /api/graph/centrality        # Recruiter phone should have highest centrality
   GET /api/graph/connections/+91A  # Should show B and C as connected
   ```

3. **Enable periodic scanning** to simulate monitoring:
   ```env
   SCHEDULER_ENABLED=true
   SCHEDULER_INTERVAL_HOURS=1   # hourly for testing
   ```

---

## Limitations & Ethics

- **Legal compliance:** Only use this tool for lawful investigations. Dark web scraping must comply with your jurisdiction's laws.
- **False positives:** Keyword matching (even weighted) will produce false positives. The risk score is an indicator, not proof.
- **Ahmia limitations:** Ahmia indexes only a fraction of .onion sites. Many trafficking operations use private/invite-only hidden services not indexed by any search engine.
- **Tor scraping:** .onion sites may be offline, slow, or block scrapers. The scrape success rate varies.
- **API rate limits:** Free tiers of NumVerify and Hunter.io have monthly quotas. TrueCaller may rate-limit aggressive querying.
- **Neo4j GDS:** Community detection and centrality require sufficient graph data. Single investigations with few entities will not produce meaningful analytics — the value increases as more phone numbers are investigated and the graph grows.
- **This tool does not replace human judgment.** All findings should be verified by trained investigators before any action is taken.

---

## License

This project is developed for academic and research purposes as part of a college project on AI-enhanced OSINT for human trafficking investigation.
