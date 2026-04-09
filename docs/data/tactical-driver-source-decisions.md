# Tactical Driver Source Decisions

Date: 2026-04-08

This note records the source decision for each tactical driver that was still missing from the backend foundation before this slice.

## Current coverage status

- Live and approved in this repository:
  - `broad_usd_index`
  - `commodity_terms_of_trade`
- Approved internal batch source now wired in this repository:
  - `cds_brazil_5y`
- Tactical signal endpoint status:
  - `GET /v1/client/tactical-signal` is available only after the manual CDS file is ingested and the curated tactical signal snapshot is built.

## `cds_brazil_5y`

- Proposed source:
  - approved internal manual CSV file drop for Brazil 5Y sovereign CDS
- Source type:
  - approved internal
- Why it is acceptable or not acceptable:
  - acceptable because governance for this slice explicitly approves a manual internal batch file drop
  - acceptable only as a file-based internal upload path, not as a scraped or unofficial proxy
  - not acceptable to describe as a live source, API source, or automated vendor feed
- Update cadence:
  - manual batch, whenever a new approved internal file is dropped
- Approved for production ingestion:
  - yes, for `manual_batch` mode only in this repository
- Required credentials/config:
  - none
- Exact series identifier or endpoint if available:
  - file path:
    - `data/raw/cds/BRGV5YUSAC=R_2026-04-07.csv`
  - source symbol in file name:
    - `BRGV5YUSAC=R`
  - expected columns:
    - `Date`, `Price`, `Open`, `High`, `Low`, `Change %`
  - canonical value field:
    - `Price`

## `broad_usd_index`

- Proposed source:
  - Federal Reserve Board H.10 Data Download Program daily indexes package
- Source type:
  - primary public
- Why it is acceptable or not acceptable:
  - acceptable because it is published directly by the Board of Governors of the Federal Reserve System on a `.gov` domain
  - it is not FRED or ALFRED; it is the Federal Reserve Board’s own H.10 release path
- Update cadence:
  - business daily with the H.10 release cycle
- Approved for production ingestion:
  - yes
- Exact series identifier or endpoint if available:
  - preformatted package endpoint:
    - `https://www.federalreserve.gov/datadownload/Output.aspx?rel=H10&series=122e3bcb627e8e53f1bf72a1a09cfb81&lastobs=10&from=&to=&filetype=csv&label=include&layout=seriescolumn&type=package`
  - exact broad-dollar column identifier in the package:
    - `JRXWTFB_N.B`
  - package description:
    - `H.10 Statistical Release - Daily Indexes`

## `commodity_terms_of_trade`

- Proposed source:
  - Banco Central do Brasil SGS `IC-Br` in US dollars
- Source type:
  - official public
- Why it is acceptable or not acceptable:
  - acceptable because it is published by Banco Central do Brasil through the official SGS API
  - this slice uses the commodity branch of the existing `commodity_terms_of_trade` driver slot, not an invented fallback series
  - the chosen production path is the overall `IC-Br` in US dollars, which is a public official commodity driver already aligned with the repo’s BCB-first sourcing rule
- Update cadence:
  - monthly
- Approved for production ingestion:
  - yes
- Exact series identifier or endpoint if available:
  - SGS series code:
    - `29042`
  - API endpoint template:
    - `https://api.bcb.gov.br/dados/serie/bcdata.sgs.29042/dados`
  - series description:
    - `Commodity Index - Brazil (IC-Br) in US Dollars`
