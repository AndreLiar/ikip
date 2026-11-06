# IKIP — Candidate Data Sources (Appendix)

_Supporting appendix to `brief.md`, `prd.md` (Epic 2 / FR1–FR2) and `architecture.md`. Catalog of candidate ingestion sources for the knowledge base and evaluation corpus._

---

## How to read this document

IKIP is a **vertical, industrial documentation-intelligence platform**. Therefore:

- **Primary (in-scope) corpus** = Category 1 (Industrial products & technical manuals). These feed the P0 MVP knowledge base.
- **Secondary (reference / future-vertical / evaluation) sources** = Categories 2–9. They are retained because (a) they informed the broader RAG-mastery plan, (b) several are strong *evaluation* and *version-aware-retrieval* corpora (regulations change, documents have effective dates), and (c) they map to future verticals (insurance, banking, finance, public-sector). They are **not** part of the initial industrial production scope.

> ⚠️ **Licensing gate (NFR / Story 6.5).** Not every source below permits bulk download or commercial reuse. Before any source is ingested, its **license, API availability, robots/ToS and access restrictions must be verified** and its provenance recorded per `document.rights` in the data model. Links carry no tracking parameters. Start with a bounded, licensed set of ~100–500 documents across a few equipment families (see `brief.md` → MVP Scope).

---

## Category 1 — Industrial products & technical manuals  ⭐ PRIMARY / in-scope (P0)

| # | Source | URL |
|---|--------|-----|
| 1 | Siemens — Technical Documentation | https://www.siemens.com/fr-fr/support/documentation-downloads/ |
| 2 | Schneider Electric — Download Center | https://www.se.com/ww/en/download/ |
| 3 | ManualLib — Manuals Library | https://www.manuallib.com/ |
| 4 | Metrology Manuals — Measurement Equipment | https://www.metrologymanuals.com/ |
| 5 | Requip Market — Industrial Equipment Manuals | https://requipmarket.com/manuals |

**Use in IKIP:** equipment manuals, specs, maintenance procedures, troubleshooting guides, parts catalogs. These exercise the full pipeline — native PDF + scanned PDF, tables, equipment model/revision identification, version supersession, citations.

---

## Category 2 — Insurance  (secondary / future vertical)

| # | Source | URL |
|---|--------|-----|
| 6 | EIOPA — European Insurance Authority | https://www.eiopa.europa.eu/ |
| 7 | EIOPA — Registers, Lists & Databases | https://www.eiopa.europa.eu/tools-and-data/registers-lists-and-databases_en |
| 8 | ACPR — French Banking & Insurance Regulator | https://acpr.banque-france.fr/ |
| 9 | ACPR — REGAFI Register & API | https://acpr.banque-france.fr/en/node/34354 |
| 10 | NAIC — Insurance Financial Data Repository | https://content.naic.org/insurance-topics/financial-data-repository |
| 11 | Insurance Information Institute — Research & Statistics | https://www.iii.org/ |

## Category 3 — Government & Public Administration  (secondary; strong version-aware/eval corpus)

| # | Source | URL |
|---|--------|-----|
| 12 | data.gouv.fr — French Open Government Data | https://www.data.gouv.fr/ |
| 13 | EUR-Lex — European Union Law | https://eur-lex.europa.eu/ |
| 14 | Légifrance — French Laws and Regulations | https://www.legifrance.gouv.fr/ |
| 15 | World Bank — Open Data | https://data.worldbank.org/ |
| 16 | World Bank — Documents & Reports | https://documents.worldbank.org/ |
| 17 | United Nations — Digital Library | https://digitallibrary.un.org/ |
| 18 | data.europa.eu — European Open Data Portal | https://data.europa.eu/ |
| 19 | INSEE — French Official Statistics | https://www.insee.fr/ |

## Category 4 — Finance & Financial Markets  (secondary / future vertical)

| # | Source | URL |
|---|--------|-----|
| 20 | Banque de France — Webstat | https://webstat.banque-france.fr/ |
| 21 | IMF — International Monetary Fund Data | https://data.imf.org/ |
| 22 | ECB — European Central Bank Data Portal | https://data.ecb.europa.eu/ |
| 23 | AMF — French Financial Markets Authority | https://www.amf-france.org/ |

## Category 5 — Education & Research  (secondary)

| # | Source | URL |
|---|--------|-----|
| 24 | UNESCO — Education Data Browser | https://databrowser.uis.unesco.org/ |
| 25 | UNESCO — Bulk Education Data Downloads | https://databrowser.uis.unesco.org/resources/bulk |
| 26 | ERIC — Education Research Database | https://eric.ed.gov/ |
| 27 | French Ministry of Education — Open Data | https://data.education.gouv.fr/ |
| 28 | Eurydice — European Education Systems | https://eurydice.eacea.ec.europa.eu/ |

## Category 6 — Private Lending & Consumer Credit  (secondary / future vertical)

| # | Source | URL |
|---|--------|-----|
| 29 | CFPB — Data & Research | https://www.consumerfinance.gov/data-research/ |
| 30 | CFPB — Consumer Complaints Database | https://www.consumerfinance.gov/data-research/consumer-complaints/ |
| 31 | CFPB — Consumer Credit Trends | https://www.consumerfinance.gov/data-research/consumer-credit-trends/ |
| 32 | CFPB — Small Business Lending | https://www.consumerfinance.gov/data-research/small-business-lending/ |
| 33 | FCA — Financial Conduct Authority Handbook | https://www.handbook.fca.org.uk/ |
| 34 | UK Government — Consumer Credit Law | https://www.gov.uk/offering-credit-consumers-law |

## Category 7 — Banking & Financial Regulation  (secondary / future vertical)

| # | Source | URL |
|---|--------|-----|
| 35 | BIS — Basel Framework | https://www.bis.org/baselframework/ |
| 36 | EBA — European Banking Authority | https://www.eba.europa.eu/ |
| 37 | EBA — Publications & Regulatory Reports | https://www.eba.europa.eu/publications-and-media |
| 38 | FFIEC — Central Data Repository | https://cdr.ffiec.gov/public/ |
| 39 | FDIC — Bank Data Downloads & API | https://www.fdic.gov/bank-data-guide/data-downloads |

## Category 8 — IT, Software & Enterprise Product Documentation  (secondary; useful technical-docs corpus)

| # | Source | URL |
|---|--------|-----|
| 40 | Microsoft Learn — Product Documentation | https://learn.microsoft.com/ |
| 41 | Kubernetes — Official Documentation | https://kubernetes.io/docs/ |
| 42 | AWS — Documentation | https://docs.aws.amazon.com/ |
| 43 | GitHub — Documentation | https://docs.github.com/ |
| 44 | Red Hat — Product Documentation | https://docs.redhat.com/ |
| 45 | Odoo — ERP Documentation | https://www.odoo.com/documentation/ |
| 46 | SAP — Help Portal | https://help.sap.com/ |
| 47 | Salesforce — Help | https://help.salesforce.com/ |
| 48 | Atlassian — Product Support | https://support.atlassian.com/ |

## Category 9 — Cybersecurity, Privacy & Open Resources  (secondary; governance reference)

| # | Source | URL |
|---|--------|-----|
| 49 | CNIL — Data Protection & GDPR | https://www.cnil.fr/ |
| 50 | ANSSI — Cybersecurity Documentation | https://cyber.gouv.fr/ |
| 51 | Wikimedia Commons — Open Media Library | https://commons.wikimedia.org/ |

---

## Recommended evaluation / benchmark datasets (not ingestion sources)

For measurable retrieval quality (Epic 5) rather than production content:

| Dataset | Purpose | URL |
|---------|---------|-----|
| DocVQA | Document visual QA (scanned PDFs, tables, forms) | https://site.docvqa.org/datasets/docvqa |
| BEIR | Diverse retrieval benchmark | https://github.com/beir-cellar/beir |
| RAGBench | RAG evaluation dataset | https://huggingface.co/datasets/rungalileo/ragbench |
| IBM RAGWorkbench | Multi-dataset/metric evaluation framework | https://github.com/IBM/RagWorkbench |
| SEC EDGAR + XBRL APIs | Document + structured-data retrieval (future finance vertical) | https://www.sec.gov/search-filings |

---

## Summary

- **51 unique candidate sources** across 9 categories + 5 evaluation datasets.
- **In-scope for MVP:** Category 1 (5 industrial sources) → bounded licensed starter corpus.
- **All other categories:** reference / future-vertical / evaluation only; each requires an explicit license + provenance check (Story 6.5) before ingestion.
