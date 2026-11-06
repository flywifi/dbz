# GRC Source Inventory

Authoritative source registry for the GRC cross-mapping engine. Last updated: 2026-06-30.

All `human_review_required: true`. Never fabricate control IDs or crosswalk relationships.

---

## US Federal Standards (NIST)

| Framework | Version | URL | Format | Freshness | Loader |
|---|---|---|---|---|---|
| NIST SP 800-53 Rev 5.1.1 | Rev 5.1.1 | `https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json` | OSCAL JSON | GitHub Releases Atom | `oscal_diff.py` |
| NIST SP 800-53B Baselines | Rev 5 | `https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/baselines/` | OSCAL JSON | GitHub Releases | `oscal_diff.py` |
| NIST SP 800-171 Rev 3 | Rev 3 final | `https://csrc.nist.gov/pubs/sp/800/171/r3/final` | OSCAL JSON + PDF | csrc.nist.gov | `spine_loader.load_171r3_projection` (CPRT) |
| NIST SP 800-172 Rev 3 | Rev 3 (May 2026) | `https://csrc.nist.gov/pubs/sp/800/172/r3/final` | OSCAL JSON + PDF | csrc.nist.gov | `spine_loader.load_172r3_projection` (CPRT) |
| NIST CSF 2.0 | 2.0 | `https://csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all` | JSON (CPRT) | Real-time | `generate_controls_csf20.py` |
| NIST AI RMF | 1.0 | `https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf` | PDF | NIST news RSS | manual |
| NIST AI 600-1 (GenAI) | 1.0 | `https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf` | PDF | NIST news RSS | manual |
| NIST Privacy Framework | 1.0 | `https://www.nist.gov/system/files/documents/2020/01/16/NIST-Privacy-Framework-V1.0-Core.xlsx` | XLSX | Static | planned |
| NIST ATT&CK↔800-53 Mapping | v13/Rev5 | `https://www.nist.gov/system/files/documents/2023/09/12/SP800-53_ATT%26CK_v13_v1.xlsx` — **404 since at least 2026-11-05**; superseded by the CTID mapping (MITRE section) | XLSX | — | retired (phase 51) |

---

## US Federal Agencies

### CISA

| Resource | URL | Format | Freshness | Loader |
|---|---|---|---|---|
| KEV Catalog JSON | `https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json` | JSON | Daily | `kev_loader.py` |
| KEV GitHub mirror (preferred) | `https://github.com/cisagov/kev-data` | JSON/CSV | Daily | `kev_loader.py` |
| CPGs 2.0 Matrix XLSX | `https://www.cisa.gov/resources-tools/resources/complete-cpgs-matrixspreadsheet` | XLSX | Version-based | planned |
| CSAF Advisory Feed | `https://github.com/cisagov/CSAF` | CSAF JSON (OASIS) | Per-advisory | poll_landing |
| ScubaGear (M365 baselines) | `https://github.com/cisagov/ScubaGear` | PowerShell/JSON | github_release | poll_landing |
| ScubaGoggles (GWS baselines) | `https://github.com/cisagov/ScubaGoggles` | Python/JSON | github_release | poll_landing |
| Zero Trust Maturity Model v2 | `https://www.cisa.gov/sites/default/files/2023-04/zero_trust_maturity_model_v2_508.pdf` | PDF | Static | reference |

> **Note:** CISA RSS feeds DEPRECATED May 12, 2025. Use GitHub mirrors and `poll_landing` instead.

### DISA / DoD

| Resource | URL | Format | Freshness | Loader |
|---|---|---|---|---|
| CCI Trackr API (3,551 CCIs) | `https://cyber.trackr.live/cci` | REST JSON | Continuous | `cci_trackr_loader.py` |
| DISA CCI List XML | `https://public.cyber.mil/stigs/cci-downloads/` | XML | Quarterly | manual |
| STIG Library | `https://public.cyber.mil/stigs/compilations/` | XML | Quarterly | poll_landing |
| CMMC Assessment Guide | `https://dodcio.defense.gov/CMMC/Documentation/` | PDF | Version-based | reference |
| DoD ZT Discovery Guide v2 | `https://media.defense.gov/2024/Jul/25/2003510911/-1/-1/1/DOD_ZT_DISCOVERY_GUIDE_V2.PDF` | PDF | Static | reference |
| DoD ZT Phase One Guide v2 | `https://media.defense.gov/2024/Jul/25/2003510908/-1/-1/1/DOD_ZT_PHASE_ONE_GUIDE_V2.PDF` | PDF | Static | reference |
| DoD ZT Phase Two Guide v2 | `https://media.defense.gov/2024/Jul/25/2003510909/-1/-1/1/DOD_ZT_PHASE_TWO_GUIDE_V2.PDF` | PDF | Static | reference |
| JSIG (Joint SAP Impl. Guide) | `https://www.dni.gov/index.php/who-we-are/organizations/ic-cio/ic-cio-related-menus/ic-cio-related-links/ic-technical-specifications-and-implementation-guides` | PDF | Version-based | reference |
| ICD 503 (IC IT Security) | Same DNI page as JSIG | PDF | Version-based | reference |

### FedRAMP

| Resource | URL | Format | Freshness | Loader |
|---|---|---|---|---|
| FedRAMP Rev5 LOW baseline | `https://raw.githubusercontent.com/GSA/fedramp-automation/master/dist/content/rev5/baselines/json/FedRAMP_rev5_LOW-baseline_profile.json` | OSCAL JSON | GitHub Releases Atom | `oscal_diff.py` |
| FedRAMP Rev5 MODERATE baseline | `https://raw.githubusercontent.com/GSA/fedramp-automation/master/dist/content/rev5/baselines/json/FedRAMP_rev5_MODERATE-baseline_profile.json` | OSCAL JSON | GitHub Releases Atom | `oscal_diff.py` |
| FedRAMP Rev5 HIGH baseline | `https://raw.githubusercontent.com/GSA/fedramp-automation/master/dist/content/rev5/baselines/json/FedRAMP_rev5_HIGH-baseline_profile.json` | OSCAL JSON | GitHub Releases Atom | `oscal_diff.py` |
| FedRAMP 20x KSI | `https://www.fedramp.gov/docs/20x/phase1/key-security-indicators/` | HTML/PDF | fedramp.gov/feed.xml | poll_landing |

---

## US Regulatory (eCFR API)

All CFR parts accessible via `https://www.ecfr.gov/api/versioner/v1/`. Loaded by `ecfr_loader.py`.

| Framework | CFR Citation | eCFR URL | NIST Families | Freshness |
|---|---|---|---|---|
| HIPAA Security Rule | 45 CFR 164 Subpart C | `https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-C` | AU, AC, IA, SC, SI | Daily diff |
| HIPAA Breach Notification | 45 CFR 164 Subpart D | `https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-D` | IR, AU | Daily diff |
| GLBA Safeguards Rule | 16 CFR Part 314 | `https://www.ecfr.gov/current/title-16/chapter-I/subchapter-C/part-314` | AC, IA, SC, IR, CM | Daily diff |
| FDA Electronic Records | 21 CFR Part 11 | `https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11` | AU, IA, SC | Daily diff |
| FDA Quality System / QMSR | 21 CFR Part 820 | `https://www.ecfr.gov/current/title-21/chapter-II/part-820` | CM, SA, RA | Daily diff |
| NRC Nuclear Cybersecurity | 10 CFR 73.54 | `https://www.ecfr.gov/current/title-10/chapter-I/part-73/section-73.54` | AC, AU, IR, SC | Daily diff |
| SAMHSA Substance Use | 42 CFR Part 2 | `https://www.ecfr.gov/current/title-42/chapter-I/subchapter-A/part-2` | AC, AU | Daily diff |
| ONC HIT Certification | 45 CFR Part 170 | `https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-D/part-170` | AC, AU, SC | Daily diff |
| ONC Information Blocking | 45 CFR Part 171 | `https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-D/part-171` | AC, AU | Daily diff |
| SEC Cyber Disclosure Rules | 17 CFR Parts 229/240 | `https://www.ecfr.gov/current/title-17/chapter-II/part-229` | IR, AU | Daily diff |
| FCC CPNI / Breach Rule | 47 CFR Part 64 Subpart U | `https://www.ecfr.gov/current/title-47/chapter-I/subchapter-B/part-64/subpart-U` | SC, IR, AU | Daily diff |

---

## Federal Register Monitoring

Monitored via `fr_watcher.py` using `https://www.federalregister.gov/api/v1/documents.json`.

| Agency | Slug | Topics |
|---|---|---|
| CISA | `cybersecurity-and-infrastructure-security-agency` | cybersecurity, incident reporting |
| HHS | `department-of-health-and-human-services` | HIPAA, health IT |
| FTC | `federal-trade-commission` | GLBA, data breach, privacy |
| SEC | `securities-and-exchange-commission` | cyber disclosure, investor protection |
| DoD | `department-of-defense` | CMMC, DFARS, cyber |
| FCC | `federal-communications-commission` | CPNI, data breach |
| FDIC | `federal-deposit-insurance-corporation` | IT examination |
| OCC | `office-of-the-comptroller-of-the-currency` | bank technology |
| Federal Reserve | `federal-reserve-system` | supervisory guidance |
| Treasury/FinCEN | `financial-crimes-enforcement-network` | AML, BSA |
| NRC | `nuclear-regulatory-commission` | cybersecurity rule |

---

## SEC EDGAR

| Resource | URL | Format | Freshness | Loader |
|---|---|---|---|---|
| 8-K Item 1.05 Full-Text Search | `https://efts.sec.gov/LATEST/search-index` | REST JSON | Real-time | `edgar_loader.py` |
| Submissions API (per-company) | `https://data.sec.gov/submissions/CIK{10digits}.json` | REST JSON | Real-time | `edgar_loader.py` |
| 8-K Atom feed | `https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&dateb=&owner=include&count=40&search_text=&output=atom` | Atom | Real-time | `fr_watcher.py` |

Rule effective: Dec 15, 2023 (SEC rule 33-11216). Default start_date in `edgar_loader.py`.

---

## NVD / CVE

| Resource | URL | Format | Rate Limit | Loader |
|---|---|---|---|---|
| NVD CVE API 2.0 | `https://services.nvd.nist.gov/rest/json/cves/2.0` | REST JSON | 5 req/30s (no key); 50 req/30s (key) | `nvd_api_loader.py` |

> **Note:** NVD v1.x JSON gz feeds deprecated. This loader uses API 2.0 with date-range incremental pulls. Set `NVD_API_KEY` env var for higher rate limit.

---

## MITRE

| Framework | URL | Format | Freshness | Loader |
|---|---|---|---|---|
| ATT&CK Enterprise (TAXII 2.1) | `https://attack-taxii.mitre.org/api/v21/` collection `x-mitre-collection--1f5f1533-f617-4ca8-9ab4-6a02367fa019` (paged at 100; an unpaged query gets a 502) | STIX 2.1 via TAXII | weekly version check (Thursday slot) | `attack_stix_loader.py` (default source since phase 51; `--stix-url` takes a single bundle as an override) |
| CTID Mappings Explorer — NIST 800-53 rev5 ↔ ATT&CK 16.1 (enterprise) | `https://ctid.mitre.org/mappings/data/nist_800_53/attack-16.1/nist_800_53-rev5/enterprise/nist_800_53-rev5_attack-16.1-enterprise_json.json` | JSON | pinned per ATT&CK version (`last_update` 04/16/2025) | `attack_stix_loader.py` (direct `mitigates` rows only) |
| D3FEND | `https://d3fend.mitre.org/ontologies/d3fend.json` | JSON-LD | github_release | planned |
| CAPEC XML | `https://capec.mitre.org/data/xml/capec_latest.xml` | XML | Annual | poll_landing |
| CWE XML | `https://cwe.mitre.org/data/xml/cwec_latest.xml.zip` | XML | Annual | poll_landing |

---

## Security Frameworks

| Framework | Version | URL | Format | Loader |
|---|---|---|---|---|
| HITRUST CSF | v11.5.0 | Paywalled (licensed) | XLSX (64-col hub) | `generate_controls_hitrust.py` |
| CSA CCM | v4.1 | `https://github.com/cloudsecurityalliance/cloud-controls-matrix` | YAML/JSON/XLSX | existing CCM loader |
| CMMC 2.0 | 2.0 | `https://www.acq.osd.mil/asda/dpc/cp/cyber/cmmc.html` | PDF | manual |
| OWASP Top 10 | 2021 (2025 TBD) | `https://github.com/OWASP/Top10/releases` | Markdown/JSON | planned |
| OWASP ASVS | v5.0.0 (May 2025) | `https://github.com/OWASP/ASVS/releases` | XLSX/JSON | planned |
| CIS Controls | v8.1 | `https://www.cisecurity.org/controls/cis-controls-list` | XLSX (free reg) | planned |
| FIPS 140-3 (CMVP) | Current | `https://csrc.nist.gov/projects/cryptographic-module-validation-program` | HTML/JSON | reference |

---

## US Financial Regulators

| Agency / Rule | URL | Format | Freshness | Notes |
|---|---|---|---|---|
| NY DFS 23 NYCRR Part 500 | `https://www.dfs.ny.gov/system/files/documents/2024/08/Cyber-WD-Part500-Requirement-Checklist.pdf` | PDF | Version-based | Checklist XLSX; 2023 amendments |
| FFIEC IT Handbook (IS Booklet) | `https://ithandbook.ffiec.gov/media/resources/6/IT_Information-Security.pdf` | PDF | Version-based | Replaces retired FFIEC CAT |
| FFIEC CAT | `https://www.ffiec.gov/cyberassessmenttool.htm` | XLSX | **RETIRED Aug 31, 2025** | Historical reference only |
| Federal Reserve SR 24-7 | `https://www.federalreserve.gov/supervisionreg/srletters/sr2407.htm` | HTML | Static | Confirms FFIEC CAT sunset |
| Federal Reserve SR 24-24 | `https://www.federalreserve.gov/supervisionreg/srletters/sr2424.htm` | HTML | Static | Cybersecurity supervision update |
| OCC Bulletin 2023-22 | `https://www.occ.treas.gov/news-issuances/bulletins/2023/bulletin-2023-22.html` | HTML | Static | Cybersecurity Supervision Work Program |
| FDIC FIL-58-2024 | `https://www.fdic.gov/news/financial-institution-letters/2024/fil24058.html` | HTML | Static | Technology-related guidance |
| FINRA Small Firm Checklist | `https://www.finra.org/sites/default/files/smallfirm_cybersecurity_checklist.xlsx` | XLSX | Annual | Machine-readable |
| FinCEN Advisories | `https://www.fincen.gov/resources/advisories` | HTML/PDF | poll_landing | AML/BSA cyber advisories |
| PCAOB AS 2201 (SOX ITGC) | `https://pcaobus.org/Oversight/Standards/Auditing-Standards/Details/AS2201` | HTML/PDF | Version-based | Effective Dec 15, 2026 update |
| CIRCIA (6 USC 681b) | `https://www.federalregister.gov/...` | Federal Register | FR API | Final rule target: May 2026 |
| NERC CIP Standards | `https://www.nerc.com/pa/Stand/Pages/CIPStandards.aspx` | PDF/XLSX | Quarterly | XLSX crosswalk: `nerc-cip-to-nist-csf.xlsx` |
| NERC CIP↔NIST CSF Crosswalk | `https://www.nerc.com/globalassets/programs/compliance/nist-csf-v1.1-to-nerc-cip-final.xlsx` | XLSX | Static | Direct XLSX download |

---

## US Criminal / Civil Statutes

Monitoring via `poll_landing` on `uscode.house.gov`. No machine-readable API; web scraping required.

| Statute | USC Citation | URL | NIST Relevance |
|---|---|---|---|
| CFAA | 18 USC §1030 | `https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title18-section1030` | IR, AC |
| ECPA | 18 USC §2510 | `https://uscode.house.gov/view.xhtml?path=%2Fprelim%40title18%2Fpart1%2Fchapter119` | SC, AU |
| DTSA | 18 USC §1836 | `https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title18-section1836` | SA, SC |
| Economic Espionage Act | 18 USC §§1831–1839 | `https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title18-section1831` | SA, SC |
| Wire Fraud | 18 USC §1343 | `https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title18-section1343` | IR |
| Identity Theft | 18 USC §1028A | `https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title18-section1028a` | IA, IR |
| CIRCIA | 6 USC §681b | `https://uscode.house.gov/view.xhtml?req=granuleid%3AUSC-prelim-title6-section681b` | IR |

---

## US State Privacy Laws

| Law | Authority | Landing URL | Freshness |
|---|---|---|---|
| Colorado Privacy Act (CPA) | coag.gov | `https://coag.gov/resources/data-protection-laws/` | poll_landing |
| Virginia CDPA | lis.virginia.gov | `https://lis.virginia.gov/cgi-bin/legp604.exe?212+sum+HB2307` | poll_landing |
| Texas TDPSA | capitol.texas.gov | `https://capitol.texas.gov/tlodocs/88R/billtext/html/HB04/index.htm` | poll_landing |
| NY SHIELD Act | ag.ny.gov | `https://ag.ny.gov/resources/individuals/data-security/shielding-new-yorkers` | poll_landing |
| Illinois BIPA | ilga.gov | `https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=3004&ChapterID=57` | poll_landing |
| Washington My Health My Data | app.leg.wa.gov | `https://app.leg.wa.gov/billsummary?BillNumber=1155&Year=2023` | poll_landing |
| Massachusetts 201 CMR 17.00 | mass.gov | `https://www.mass.gov/regulations/201-CMR-17-standards-for-the-protection-of-personal-information` | poll_landing |

---

## HHS / Healthcare

| Resource | URL | Format | Notes |
|---|---|---|---|
| HIPAA Audit Protocol | `https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/audit/protocol/index.html` | HTML/XLSX | Audit procedures → HIPAA safeguard mapping |
| HIPAA↔NIST CSF Crosswalk | `https://www.nist.gov/system/files/documents/2025/03/17/nist-csf-to-hipaa-security-rule-crosswalk-02-22-2016-final.pdf` | PDF | HIPAA→NIST CSF→800-53 mapping |
| NIST SP 800-66 Rev 2 | `https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-66r2.pdf` | PDF | NIST impl guide for HIPAA Security Rule. **On disk since Phase 19**: CPRT export + OLIR element graphs (manifest ids `cprt-sp800-66r2-export` / `cprt-sp800-66r2-olir-graphs`) — the HIPAA→800-53 r5.1.1 mapping (279 pairs) is the `direct_800_66` spine projection |
| HHS 405(d) HICP | `https://405d.hhs.gov/cornerstone/hicp` | PDF/HTML | Top 5 cyber threats for healthcare |
| CMS ARS 5.1 | `https://security.cms.gov/policy-guidance/cms-acceptable-risk-safeguards-ars` | PDF/HTML | CMS-tailored NIST 800-53 Rev 5 baseline |
| ONC HTI-1 Final Rule | `https://healthit.gov/regulations/hti-rules/hti-1-final-rule/` | HTML/PDF | Algorithm transparency, USCDI v3 |
| FDA Medical Device Cyber (premarket) | `https://www.fda.gov/media/178134/download` | PDF | Section 524B: SBOM, vuln disclosure |
| openFDA Device API | `https://open.fda.gov/apis/device/` | REST JSON | Device registrations, adverse events |

---

## EU / UK / International

| Framework | Version | URL | Format | Loader |
|---|---|---|---|---|
| EU GDPR | 2016/679 | `https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng` (CELEX: 32016R0679) | HTML/XML | `eurlex_loader.py` |
| NIS2 Directive | 2022/2555 | `https://eur-lex.europa.eu/eli/dir/2022/2555/oj/eng` (CELEX: 32022L2555) | HTML/XML | `eurlex_loader.py` |
| DORA | 2022/2554 | `https://eur-lex.europa.eu/eli/reg/2022/2554/oj/eng` (CELEX: 32022R2554) | HTML/XML | `eurlex_loader.py` |
| EU AI Act | 2024/1689 | `https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng` (CELEX: 32024R1689) | HTML/XML | `eurlex_loader.py` |
| EUR-Lex Cellar SPARQL | — | `https://publications.europa.eu/webapi/rdf/sparql` | SPARQL/RDF | reference |
| UK DPA 2018 / UK GDPR | 2018 | `https://www.legislation.gov.uk/ukpga/2018/12/data.xml` | XML | poll_landing |
| ENISA ECSF | Current | `https://enisaeu.github.io/ECSF/` | JSON | poll_landing |
| ISO/IEC 27001:2022 | 2022 | `https://www.iso.org/standard/82875.html` | PDF (paywalled) | HITRUST bridge |
| ISO/IEC 27002:2022 | 2022 | `https://www.iso.org/standard/75652.html` | PDF (paywalled) | HITRUST bridge |
| ISO/IEC 42001:2023 (AI) | 2023 | `https://www.iso.org/standard/81230.html` | PDF (paywalled) | reference |
| ISO/IEC 27701:2019 (Privacy) | 2019 | `https://www.iso.org/standard/71670.html` | PDF (paywalled) | reference |
| PCI DSS | v4.0.1 | `https://www.pcisecuritystandards.org/document_library/` | PDF/XLSX (free reg) | reference |
| UK NCSC CAF | Current | `https://www.ncsc.gov.uk/collection/cyber-assessment-framework` | HTML | poll_landing |

---

## Asia-Pacific

| Framework | Authority | URL | Format | Freshness |
|---|---|---|---|---|
| Singapore MAS TRM 2021 | MAS | `https://www.mas.gov.sg/-/media/MAS/Regulations-and-Financial-Stability/Regulatory-and-Supervisory-Framework/Risk-Management/TRM-Guidelines-18-January-2021.pdf` | PDF | poll_landing |
| Australia APRA CPS 234 | APRA | `https://www.apra.gov.au/sites/default/files/cps_234_july_2019_for_public_release_0.pdf` | PDF | poll_landing |
| ASD Essential Eight | cyber.gov.au | `https://www.cyber.gov.au/resources-business-and-government/essential-cyber-security/essential-eight` | HTML | poll_landing |
| ASD ISM | cyber.gov.au | `https://www.cyber.gov.au/resources-business-and-government/essential-cyber-security/ism` | XLSX | Annual |
| Canada PIPEDA | priv.gc.ca | `https://laws-lois.justice.gc.ca/eng/acts/P-8.6/` | HTML/XML | poll_landing |
| Canada Bill C-27 (CPPA) | parl.ca | `https://www.parl.ca/legisinfo/en/bill/44-1/c-27` | HTML | In progress |
| India DPDP Act 2023 | meity.gov.in | `https://www.meity.gov.in/data-protection-framework` | PDF | poll_landing |

---

## FCC / Telecom

| Resource | URL | Format | Notes |
|---|---|---|---|
| FCC Data Breach Notification Rule (2024) | `https://www.federalregister.gov/documents/2024/02/12/2024-01667` | FR JSON | 7-day FBI/USSS + 30-day customer |
| 47 CFR Part 64 Subpart U (CPNI) | `https://www.ecfr.gov/current/title-47/chapter-I/subchapter-B/part-64/subpart-U` | eCFR API | CPNI safeguards §64.2010 + breach §64.2011 |
| FCC ECFS Proceedings API | `https://www.fcc.gov/ecfs/public-api-docs.html` | REST JSON | Query rulemaking comments |
| FCC RSS Feeds | `https://www.fcc.gov/news-events/rss-feeds-and-email-updates-fcc` | RSS/XML | Daily Digest + category feeds |

---

## RSS / Atom Feed Seeds

For use with `announcement_monitor.py`:

```
https://www.nist.gov/news-events/cybersecurity/rss
https://csrc.nist.gov/publications/drafts-open-for-comment.xml
https://www.federalregister.gov/api/v1/documents.rss?agencies[]=cybersecurity-and-infrastructure-security-agency
https://www.federalregister.gov/api/v1/documents.rss?agencies[]=securities-and-exchange-commission
https://www.federalregister.gov/api/v1/documents.rss?agencies[]=department-of-health-and-human-services
https://www.federalregister.gov/api/v1/documents.rss?agencies[]=federal-trade-commission
https://www.fedramp.gov/feed.xml
https://www.hhs.gov/rss/hipaa-news.xml
https://blog.pcisecuritystandards.org/rss.xml
https://www.ncsc.gov.uk/feeds/all
https://www.enisa.europa.eu/media/rss
https://www.edpb.europa.eu/feed/news_en
https://eur-lex.europa.eu/RSSXSL/sfeed_EULAW.xml
https://www.mas.gov.sg/rss/publications
https://www.apra.gov.au/rss.xml
https://www.nerc.com/pa/Stand/Pages/rss.aspx
https://www.pcaobus.org/rss/standards
https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&dateb=&owner=include&count=40&search_text=&output=atom
https://www.fcc.gov/news-events/rss-feeds-and-email-updates-fcc
https://www.occ.treas.gov/news-issuances/news-releases/rss.xml
https://www.fdic.gov/news/press-releases/rss.xml
https://www.federalreserve.gov/feeds/press_all.xml
```

> **Note:** CISA RSS feeds (`https://www.cisa.gov/sites/default/files/feeds/alerts.xml`) DEPRECATED May 12, 2025. Do not use.

---

## Version Corrections Applied (2026-06-30)

| Framework | Old Version | New Version | Note |
|---|---|---|---|
| HITRUST CSF | v11.4.0 | v11.5.0 | Adds CMMC 2.0, DORA, ISO 29151, CMS ARS v5.1 mappings |
| CSA CCM | v4.0.12 | v4.1 | Updated on GitHub (cloudsecurityalliance/cloud-controls-matrix) |
| OWASP ASVS | v4.0.3 | v5.0.0 | Released May 2025 |
| FFIEC CAT | active | **retired** | SUNSET Aug 31, 2025; use FFIEC IT Handbook instead |
| NSM-8 | active | **retired** | RESCINDED June 2026; superseded by NSPM-12 |
| CISA RSS feeds | active | **deprecated** | DEPRECATED May 12, 2025; use GitHub mirrors / poll_landing |
| NVD CVE feeds | v1.x JSON gz | **API 2.0** | v1.x deprecated; use `https://services.nvd.nist.gov/rest/json/cves/2.0` |
| DoD Zero Trust | — | ZIG v2 (Jan 2026) | Discovery, Phase One, Phase Two PDFs at media.defense.gov |

---

## Loaders Reference

| Script | Path | Source(s) | Output |
|---|---|---|---|
| `kev_loader.py` | `engine/` | CISA KEV JSON | `canonical-sources/known_exploited_vulnerabilities.json` |
| `cci_trackr_loader.py` | `nist-catalog/ingestion/` | CCI Trackr API | `canonical-sources/disa-cci-trackr.json` |
| `ecfr_loader.py` | `engine/` | eCFR REST API | `canonical-sources/cfr/{title}-cfr-{part}.json` |
| `fr_watcher.py` | `engine/` | Federal Register API | `canonical-sources/announcements_feed.json` |
| `attack_stix_loader.py` | `engine/` | MITRE ATT&CK TAXII 2.1 + CTID NIST 800-53 rev5 mapping | `canonical-sources/mitre-attack-techniques.json` |
| `eurlex_loader.py` | `engine/` | EUR-Lex ELI HTML | `canonical-sources/eurlex/{reg_id}-articles.json` |
| `nvd_api_loader.py` | `engine/` | NVD CVE API 2.0 | `canonical-sources/nvd-cve-{date}.json` |
| `edgar_loader.py` | `engine/` | SEC EDGAR Search API | `canonical-sources/edgar-8k-cyber.json` |
| `build_db.py` | `engine/` | All of the above | `cross-mapping/output/grc.db` |
| `cprt_traverser.py` | `engine/` | NIST CPRT API | `canonical-sources/cprt_gap_report.json` |
| `olir_crawler.py` | `engine/` | NIST CPRT OLIR API | `canonical-sources/olirs/` + source_manifest.json update |
| `pdf_structure_extractor.py` | `engine/` | Local PDF files | `canonical-sources/fips/{pub_id}-structured.json` |

---

## NIST Normative References

Publications normatively referenced in NIST SP 800-53 Rev 5.2.0 OSCAL catalog text (found in
control discussion fields), not yet fully ingested. Grouped by ingestion tier.

### Tier A: Monitor-Only (feed_registry entries added 2026-06-30)

These publications are cited by name or subject in 800-53 control discussions but their
content is policy/guidance-level, not control-ID-structured. Version monitoring is sufficient;
no ingestion loader required.

| Publication | Controls That Cite It | Version Signal | feed_registry ID |
|---|---|---|---|
| **SP 800-37 Rev 2** (RMF) | PM-7, CA-6, CA-7 | csrc.nist.gov publication date | `nist-sp-800-37` |
| **SP 800-63-3** (Digital Identity) | IA-8, IA-9, MA-4 | csrc.nist.gov publication date | `nist-sp-800-63` |
| **SP 800-63A Rev 3** (Enrollment) | IA-8(1) PIV proofing | csrc.nist.gov publication date | `nist-sp-800-63a` |
| **SP 800-63B Rev 3** (Authentication) | IA-2 MFA, IA-5 authenticators | csrc.nist.gov publication date | `nist-sp-800-63b` |
| **SP 800-56A Rev 3** (Key Agreement) | SC-12, SC-12(3) | csrc.nist.gov publication date | `nist-sp-800-56a` |
| **SP 800-57 Pt 1 Rev 5** (Key Mgmt) | SC-12, SC-12(1) | csrc.nist.gov publication date | `nist-sp-800-57pt1` |
| **SP 800-160 Vol 2 Rev 1** (Cyber Resiliency) | PL-8, SA-17 | csrc.nist.gov publication date | `nist-sp-800-160-2` |
| **SP 800-166** (Derived PIV) | IA-8(2) derived PIV | csrc.nist.gov publication date | `nist-sp-800-166` |
| **SP 800-189** (BGP Route Filtering) | SI-18, SC-5 | csrc.nist.gov publication date | `nist-sp-800-189` |
| **SP 800-213A** (IoT Federal Profile) | IR-9, AC-20 | csrc.nist.gov publication date | `nist-sp-800-213a` |
| **FIPS 140-3** (CMVP) | SC-13, IA-7, SC-8(1), SC-28(1) | csrc.nist.gov publication date | `fips-140-3` |
| **FIPS 199** (Categorization) | RA-2 (foundational) | csrc.nist.gov publication date | `fips-199` |
| **FIPS 200** (Min Requirements) | Underpins all baselines | csrc.nist.gov publication date | `fips-200` |
| **FIPS 201-3** (PIV) | IA-2(12), IA-5(2), IA-8(1)-(4) | csrc.nist.gov publication date | `fips-201-3` |
| **NIST IR 8477** (STRM Methodology) | OLIRs / crosswalk methodology | csrc.nist.gov publication date | `nist-ir-8477` |
| **ISO/IEC 15408** (Common Criteria) | SA-17, SA-11 (NIAP) | niap-ccevs.org product list | `iso-15408` |

### CCI Provenance for Normative References

| Publication | Primary CCI Tier | Key CCIs | Notes |
|---|---|---|---|
| FIPS 201-3 (PIV) | **Confirmed-Direct** | CCI-001948, CCI-000203, CCI-001768/769 | Highest-confidence; "PIV credentials" and "FICAM" named in CCI text |
| SP 800-63B (Auth) | **Confirmed-Subject** | CCI-000765/766 (MFA), CCI-000185–216 (authenticators) | "Multifactor authentication" and "authenticator" language; CCI-001764 names SP 800-63 |
| FIPS 140-3 (CMVP) | **Confirmed-Subject** | CCI-002450–002453 (SC-13), CCI-000803/804 (IA-7) | "FIPS-validated cryptography" language; FIPS 140-2→3 transition is Implied-Bridge |
| SP 800-57 Pt1 (Key Mgmt) | **Confirmed-Subject** | CCI-002449 (SC-12) | "Key establishment and key management" subject match |
| SP 800-37 (RMF) | **Implied-Bridge** | CCI-000076–079 (CA-6), CCI-000174–178 (CA-7) | "Authorization to operate" / "continuous monitoring" language; pub not named |
| SP 800-160 Vol 2 | **Implied-Bridge** | CCI-001771/772 (PL-8), CCI-002218–224 (SA-17) | "Security architecture" heuristic; 800-160 Vol 1 is primary citation |
| FIPS 199/200 | **Not-Applicable** | None | Policy/categorization level; no control-implementation CCIs |
| ISO/IEC 15408 | **Implied-Heuristic** | CCI-002218–224 (SA-17) | "Developer security architecture" → CC EAL chain; not named in CCI text |

### Tier B: Planned Loaders (not yet implemented)

| Publication | Format | Proposed Loader | DB Table | Notes |
|---|---|---|---|---|
| SP 800-63B (CPRT JSON) | NIST CPRT API | `generate_controls_800_63b.py` | `nist_800_63b_requirements` | AAL-level requirements; `cci_provenance` field per row |
| FIPS 140-3 CMVP list | CSV (NIST CMVP) | `fips_cmvp_loader.py` | `fips_140_validations` | Module-level: vendor, level, algorithms; queryable via `dbz_query.py sc13 --fips-level 3` |
| NIAP Product List | HTML (niap-ccevs.org) | `niap_loader.py` | `niap_validated_products` | PP/EAL claims; cross-reference to SA-17 CCIs |

---

## Automated Update Pipeline

**Since phase 51 the scheduled cadence is `canonical-sources/fetch_schedule.json`, which is
authoritative over this table.** A row not in it runs by hand. Procedure: runbook § Weekly rotation.

| Layer | Script | Trigger | Sources |
|---|---|---|---|
| Weekly (Wednesday, PR) | `kev_loader.py` | `weekly-refresh.yml` | CISA KEV JSON (primary or GitHub mirror) |
| Weekly (Wednesday, report only) | `nvd_api_loader.py --days 7 --dry-run` | `weekly-refresh.yml` → digest | NVD CVE API 2.0 (incremental by `lastModified`) |
| Daily | `edgar_loader.py` | Cron / manual | SEC EDGAR 8-K Item 1.05 (incremental by filed date) |
| Weekly (Monday, inside the drift check) | `announcement_monitor.py --dry-run` | `standards-watch.yml` | All RSS/Atom feeds in feed_registry |
| Weekly (Monday build step, governed since phase 51) | `oscal_diff.py --oscal-cache … --dry-run` | `standards-watch.yml` | usnistgov/oscal-content GitHub (`--check-remote` stays manual) |
| Not scheduled (phase 51: `/api/olir/finalized` 404) | `olir_crawler.py --auto-download` | manual | NIST CPRT OLIR catalog |
| Weekly (Tuesday, PR; phase 52) | `eurlex_loader.py` | `weekly-refresh.yml` | Publications Office Cellar (XHTML by CELEX; EUR-Lex HTML answers automated clients with a bot challenge) |
| Weekly (Tuesday, PR: 45 CFR 164 subpart C, 32 CFR 170) | `ecfr_loader.py --title … --part …` | `weekly-refresh.yml` | eCFR versioner API |
| Weekly (Thursday, phase 51) | `attack_stix_loader.py` when `remote_attack_version()` differs | `weekly-refresh.yml` | MITRE ATT&CK TAXII 2.1 |
| Not scheduled (phase 51: `/api/catalog/pubs/page` 404) | `cprt_traverser.py` | Manual | NIST CPRT publications API |
| On-demand | `pdf_structure_extractor.py` | Manual | Local PDF files |
| Weekly (Thursday, PR when DISA publishes a newer quarter) | `stig_harvest.py --auto-library` | `weekly-refresh.yml` | DISA SRG-STIG Library |
| Quarterly | `stig_harvest.py --check/--refresh-stale/--full` | Manual | DISA SRG-STIG Library + cyber.trackr.live |
| On CCI-list release | `cci_harvest.py --acasehs / --trackr --enrich` | Manual | acasehs republication + cyber.trackr.live/api/cci |
| After any loader | `build_db.py` | Manual | All canonical-sources/ |

## CSA CCM v4.1 / AICM v1.1 / CSA repos evaluation (Phase 24)

Exhaustive traversal of the CSA v4.1 bundle set + 5 CSA GitHub repos established that **CCM v4.1
cross-framework mappings do not exist yet** — CSA's own v4.1 "Scope Applicability (Mappings)" sheet
reads "This dataset is not available yet" and the OSCAL mappings are empty. The v4.1 catalog/CAIQ is
published; our committed **v4.0.13** mappings remain the latest that exist (not a gap). Recorded as an
anticipated update (`au-csa-ccm`) so the mappings are watched-for. Evaluated / not applicable:
- **AICM v1.1** — 270-control AI Controls Matrix mapping only to EU AI Act / ISO 42001:2023 / BSI AI C4
  (off the 800-53 spine). Registered watch-only (`csa-aicm-v1.1`); not a projection source.
- **SecurityControlsCatalog** — CSA's controls-as-STIX-2.1 (the intended future home of CCM/AICM
  mappings), "early-stage, initial content being prepared." Registered watch-only
  (`csa-controls-catalog-stix`); becomes the real v4.1 mappings source once populated.
- **SecID / SecID-Client-SDK** — a security-knowledge *referencing* registry + SDK (not mappings).
- **cti** — Cloud Threat Intelligence (CAVEaT/STIX) — threat intel, not control mappings.
- **csa-plugins-official** — Claude Code plugins (tooling).

## CCI dictionary + corroboration (Phase 22)

The full DISA CCI dictionary (**5,137** CCIs with definitions + status) loads from the committed
`U_CCI_List.xml` (v2025-01-23); legacy Rev-3-only CCIs are recovered to base r5 controls, and a
`cci_mapping_corroboration` layer cross-witnesses every CCI↔800-53 edge across the DISA bridge,
the acasehs r4/r5 republications, trackr `rmf`, and STIG usage. acasehs/trackr are derived
republications (enrichment/corroboration only, never primary). Full model: `docs/cci-enrichment.md`.

---

## STIG application layer (Phase 21)

The goal is **CCI application evidence** — which DISA CCIs each STIG rule exercises — not a
complete STIG catalog. `tools/stig_harvest.py` distills the DISA SRG-STIG Library compilation
(the ~360MB zip is fetched at harvest time and **never committed**) into two committed
artifacts under `canonical-sources/source_data/stig/`: `stig_cci_map.json.gz` (rule→CCI) and
`stig_catalog.json` (the 1,079-title trackr delta ledger + per-benchmark harvest provenance).
The October-2026 refresh (phase 50) holds 407 benchmarks / 20,842 rules / 539 distinct CCIs: the
library's 387 plus 20 STIGs DISA dropped, kept and flagged `not_in_current_library` (April 2026,
the first harvest: 383 / 19,667, 97.6% resolved in `cci_bridge`).

Uploaded research-file dispositions:

| File | Verdict |
|---|---|
| Adobe Acrobat STIG CSV (stigviewer export) | **Format note, not a source** — stigviewer's CSV export carries no CCI column (verified); DISA XCCDF / trackr are the CCI-bearing sources. |
| MS Windows Security Baseline zip (Microsoft SCT) | **Reference-only, not committed** — Microsoft Security Compliance Toolkit baseline, not a DISA CCI source. |
| `acasehs/STIG-Control-CCI`, `cognis-digital/stigsentry`, stigviewer.com | **Watch-only** (`stig-community-refs` feed) — announcement monitoring only, never loader inputs (precedence: DISA compilation > trackr mirror > community aggregations). |

## Phase 25 — full source audit + two-tier broadening

The canonical-source universe was re-audited end to end (see `docs/source-audit-phase25.md`).
Feeds now carry `tier` (mappable | reference) + `jurisdiction`; 20 net-new tiered feeds were
added (NIST corpus, US federal/defense, US Code/CFR/FR APIs, US sector, standards bodies, EU,
UK/Commonwealth, APAC/MEA/LATAM). Broken feed URLs were repointed; the deprecated `mitre/cti`
STIX source moved to `mitre-attack/attack-stix-data`; the 26 landing-less `poll_landing` feeds
were fixed; metadata contradictions reconciled. Seven Tier-2 control catalogues (CJIS, IRS
1075, BSI C5, CMS ARS, ITSG-33, ISMAP, NCA ECC) are registered under
`source_manifest.json → staged_reference_sources` (staged, no fabricated file/sha). The
`olir_hub_edges` table adds CIS 8.1 / OWASP LLM Top 10 / SSDF v1.1 → 800-53 composed through
the CSF 2.0 hub (two OLIR refs per edge, contained off the matrix). Broken/gated endpoints
(OLIR bulk API, FedRAMP OSCAL, CPRT nudp REST) are indexed with path-discovery notes, not
claimed as ingestable.

## Phase 26 — FedRAMP Consolidated Rules 2026 (the modernized program)

The complete canonical dataset (`FedRAMP/rules` → `fedramp-consolidated-rules.json`,
v2026.07.06.01), its JSON schema, all 11 certification-data reporting schemas (2026-06-24 set),
and the whole `FedRAMP/2026-markdown` narrative corpus (291 files) are committed verbatim under
`canonical-sources/source_data/fedramp/` — see `docs/fedramp-modernization.md` for the model.
This is an audit-framework revision on top of the unchanged 800-53 r5 spine (the ISO 2013→2022
pattern): FedRAMP r5 keeps its matrix seat; the KSI confirmation layer (46 indicators, 373
FedRAMP-published KSI→800-53 edges, 95.2% inside the Moderate baseline) is a contained
query-surface tier. GSA/fedramp-automation is archived (2025-07-01); FedRAMP/docs is legacy;
the living sources are FedRAMP/rules + fedramp.gov/2026/ + fedramp.gov/schemas/.

## GitHub seed-source triage (Phase 48, 2026-10-19) — recorded, nothing added

Twenty-one user-supplied GitHub repositories were triaged against the registries at
`0012f0d` (own grep) and against the GitHub API (live/archived status and last-push dates,
as reported by the triaging workstation; not re-fetched here). **Decision: record only.** No
source was added, pinned, or crawled; a future phase may promote a row, and must start by
re-verifying it.

**Already referenced by dbz (4):** `FedRAMP/rules` (pinned consolidated-rules dataset),
`FedRAMP/2026-markdown` (vendored narrative corpus), `usnistgov/oscal-content` and
`usnistgov/OSCAL` (OSCAL cache + format watch). The triage also listed `FedRAMP/2026`,
`FedRAMP/schemas`, `usnistgov/800-63-4-Implementation-Resources` and `usnistgov/800-63-3` as
"in use"; **they are not** — `FedRAMP/2026` appears only inside a vendored markdown file and
the other three nowhere (the 800-63 material arrives via NIST CPRT exports, not those repos).
A refresh of the four real pins is ordinary `standards_refresh.py` work, not a new source.

**New and relevant, ranked (none adopted):**

| # | Repository | What it is | Would fit | Reported size / last push |
|---|---|---|---|---|
| 1 | `FedRAMP/marketplace-fedramp-gov-data` | public FedRAMP Marketplace data: authorized CSPs, impact levels, agencies, status | a `kev_loader`-pattern loader + `dbz_query.py` surface; answers "is this vendor FedRAMP authorized" | ~22 MB / 2026-10-19 |
| 2 | `usnistgov/macos_security` | macOS Security Compliance Project; per-rule YAML mapped to 800-53 r5, 800-171, CIS, DISA STIG, CMMC | a STIG-like technical-control catalog beside the `stig_*` / CCI tables | ~29 MB YAML / 2026-10-14 |
| 3 | `usnistgov/800-63-Public-Comments` | SP 800-63-4 comment dispositions | `anticipated_updates` signal for the 800-63 feeds | ~49 MB / 2026-10-06 |
| 4 | `usnistgov/800-217` | PIV credentials with federation | IA-family depth | ~3 MB / 2026-10-06 |
| 5 | `usnistgov/liboscal-java`, `usnistgov/metaschema` | OSCAL tooling | only if dbz validates or emits OSCAL | 2026-10-19 |
| 6 | `FedRAMP/JSONViewer` | JS viewer for the CR26 JSON (UI, not data) | low value | 2026-10-13 |
| 7 | `usnistgov/swid-tools`, `usnistgov/dioptra` | SWID tags; AI test platform | marginal (SR / CM-8; AI RMF angle); dioptra is ~261 MB | 2026-10-19 |

**Not GRC-related, skipped:** `usnistgov/fipy`, `usnistgov/AusteniteCalculator`,
`usnistgov/open-notebook`, `usnistgov/pyproject2conda`.

## NIST feed directory + National Checklist Program crawl (Phase 49, 2026-11-04)

Two user-supplied seeds crawled recursively: NIST's feed directory
(`www.nist.gov/coo/nist-rss-feeds`, updated 2026-07-01) and an NCP checklist page
(`ncp.nist.gov/checklist/953`, the DISA Microsoft Office 365 ProPlus STIG). Every relevance
figure below was measured against the live feeds with `announcement_monitor`'s own fetch and
keyword matcher, 180-day window.

**NIST feed directory: 30 feeds listed** (news, events, 24 topics, 4 blogs). Directory feeds
all have the form `/rss.xml`; the bare `/rss` paths return 404.

| Outcome | Feeds | Evidence |
|---|---|---|
| Already in the registry, carrying the signal | Cybersecurity Insights blog, Information Technology topic | 32 and 24 GRC-relevant items of 40 |
| **Repaired** (dead bare path → `/rss.xml`) | news (nist-ai-rmf), events (nist-sp-800-56a, nist-sp-800-57pt1; events entries given label-derived keywords, since unfiltered they would tag all 24 events) | old paths 404; new paths 200 |
| Not added: no GRC signal | standards, resilience, energy, manufacturing, electronics, Taking Measure blog (0 relevant items each); health, public safety (1 each) | the directory's "Standards" topic covers measurement standards, not security publications |
| Not added to other frameworks: signal already covered | all-news (one item in 180 days not already in the IT feed: a CSF small-business guide); advanced communications (O-RAN security reports also land in the IT feed) | items deduplicated by URL against the two registered feeds |
| Not added to other frameworks: wrong kind | events (webinars and community calls, not publications); Cybersecurity topic (live but empty, 0 items) | — |
| Not crawled: not GRC | bioscience, buildings and construction, chemistry, environment, fire, forensic science, materials, mathematics, metrology, nanotechnology, neutron research, performance excellence, physics, transportation; Blogrige; Manufacturing Innovation blog | — |

**National Checklist Program: added as feed `nist-ncp`.** The repository and checklist pages
are a JavaScript app; a scripted fetch gets a 2,250-byte shell whose `Last-Modified` is the app
build date, so they cannot be monitored. NCP's **data feeds** can: `checklist-0.1-feed.xml.gz`
(all checklists, 918 entries) and `checklist-0.1-feed-modified.xml.gz` (recent changes), each with
a `.meta` sidecar (`lastModifiedDate`, sizes, SHA-256 of the uncompressed feed; the downloaded
feed matched its published SHA-256). The registry polls the `.meta` file. Coverage at crawl:
DISA 447 checklists, CIS Benchmarks 322, CISA SCuBA 18, NIST macOS Security Compliance Project
14, USGCB 9; FINAL 512, ARCHIVED 405; 71 modified since 2026-08-01. The data-feeds page also
lists NIST's CCE v5 configuration-identifier downloads (combined file dated 2025-12-09), recorded
on the same entry, not as a separate feed.

**Finding — the STIG catalog is behind.** NCP lists DISA STIG versions independently of the
trackr API that `stig_harvest.py` uses. Of 96 DISA FINAL checklists whose titles match a
`stig_catalog.json` entry exactly (token-set equality after dropping "STIG"/vendor words; 3
ambiguous titles excluded), **50 carry a newer version/release in NCP**, 44 agree and 2 are
older. Example: Office 365 ProPlus is V3R8 in NCP and V3R5 in our catalog (harvested
2026-07-04). The monthly STIG drift check could not see this because it reported
`check_failed (trackr unreachable)`. Refreshing the STIG layer is a separate, owed step
(`standards_refresh.py --fetch` → `stig_harvest.py --refresh-stale`).

> **CORRECTION (phase 50, 2026-11-04).** "trackr unreachable" was the check's *label*, not its
> cause, and the remedy named above would have failed.
> - **The check could never report drift.** From phase 21 (`e6449ab`, 2026-07-04),
>   `standards_refresh.stage_stig_check` read only the last line of an indented JSON report
>   (always `}`). It also kept only the last 4,000 characters of output. So it said
>   `check_failed` on every run, while trackr answered the CCI check in the same runs.
> - **The true scale was larger.** Measured live: 164 of the then-383 harvested STIGs were stale.
> - **`--refresh-stale` refuses that drift.** It stops above `--max-delta 40`.
> - **What was done:** the check now uses three signals (DISA library quarter, NCP, trackr).
>   The layer was refreshed from the October 2026 library, with the STIGs DISA dropped kept and
>   flagged. See "Phase 50" below.

## Host usage rules + STIG refresh (Phase 50, 2026-11-04)

**Why:** The monthly feed had to carry STIG currency without overloading any source.
Investigating that showed the politeness layer was being bypassed, and that the STIG check
had been blind since July.

**Published usage rules, recorded and enforced.** `canonical-sources/host_policies.json`
holds 12 hosts (11 at 0.15.0; github.com added in 0.15.1). Each records its rule verbatim or "none published", with the check date and
probe. The rules that matter most:
- **NCP:** read `.meta` first; fewer than 200 requests a day.
- **NVD:** 5 requests per rolling 30 s.
- **GitHub:** 60/h unauthenticated, 1,000/h per repository with the workflow token.
- **eCFR:** the full-XML endpoint requires `Accept-Encoding`.

robots.txt follows RFC 9309. Python's blank-line grouping, which silently drops eCFR and
Federal Register Disallow rules, is neutralised. The offline census
(`tools/fetch_census.py --check`, in CI) plans one monthly run at **328 requests to 96 hosts,
none ungoverned**. Before phase 50 it was 423, with 193 ungoverned and two hosts over their
cap. (Corrected by the first CI dispatch, below: GitHub was undercounted. The 0.15.1 upper
bound is 327, api.github.com 38 of 50.)

**What the first governed live run refused** (from the run ledger):
- `texas-tdpsa` polled `capitol.texas.gov/BillLookup/…`, which that host's robots disallows. It
  now polls the codified statute (`statutes.capitol.texas.gov` BC.541, "CHAPTER 541. CONSUMER
  DATA PROTECTION").
- `japan-ismap` polled `www.ismap.go.jp/`, but that robots file reads "Disallow: / Allow: /csm".
  It now polls `/csm`, the portal home with announcements.
- `www.acq.osd.mil`, `www.cnss.gov` and `www.ilga.gov` fail TLS verification from the session
  network, and `www.cyber.gov.au` timed out. Their robots files count as unreachable, which
  means disallow for that run. Their pages fail the same way, so this is not a regression. CI
  runners may differ, and the ledger names the cause.

**STIG layer → DISA October 2026 library.** The library is
`U_SRG-STIG_Library_October_2026.zip`: 375,827,141 B, sha256 `ea581eb2…d1d`, HTTP
Last-Modified 2026-10-26.
- **The library itself:** 387 of the total, carrying 19,386 of its rules (+24 new, 159 version changes).
- **Kept, not deleted:** 20 more that the library no longer carries, flagged
  `not_in_current_library` (schema 3.19), 1,456 rules. DISA's revision history lists most as
  sunset deletions: 09/30/2026 RHEL 8 V2R9, iOS 18 V2R4, Akamai ×2, Exchange Edge ×2; 07/01/2026
  Windows Server 2019 V3R9, Crunchy PostgreSQL V3R2, Palo Alto Y25M04, .NET 4.0, 3PAR, Zebra 13.
  The Exchange 2016/2019 *Mailbox* STIGs have no deletion entry, which is why the flag states
  only the measured fact.
- **Refreshed to DISA's final release:** 5 kept benchmarks (iOS 18 v2r4, Crunchy PostgreSQL
  v3r2, 3PAR 3.2.x v2r2, RHEL 8 v2r9, Windows Server 2019 v3r9).
- **Out-of-cycle releases from trackr:** HP FlexFabric Switch RTR v1r3 and zOS SRRAUDIT TSS
  v7r2. Both sit in date-coded DISA bundles, 25 trackr calls.
- **Result:** **407 benchmarks / 20,842 rules / 539 distinct CCIs.** All three currency signals
  (library, NCP, trackr) read `same`. Two CCIs left the STIG-cited set with revised Windows
  Server 2022 / Apache 2.4 UNIX Site STIGs (CCI-000776, CCI-002506), and two arrived with
  AvePoint Fly Server (CCI-001083, CCI-005155). Net confirmation verdicts over the unchanged
  180,413 pairs: confirmed 23,551 → 23,540.

**November drift triage** (live tag from the 2026-11-03 scheduled run, plus the issuer's own page):

| Feed | Change | Status |
|---|---|---|
| openapi-spec | → 3.2.1 (10 Sep 2026) | current |
| mitre-attack | → v20.0 (13 Oct 2026) | artifact_stale; ingest owed (ingested in phase 51) |
| mcp-spec | → 2026-07-28 | current |
| oscal-format | → v1.2.3 (6 Aug 2026) | current |
| fedramp | repo repointed GSA/fedramp-automation (archived) → FedRAMP/rules | — |
| cisa-kev | live catalogVersion 2026.11.04 vs committed 2026.07.01 | artifact_stale; `--fetch` owed (refreshed in phase 51) |

- **Re-verified at origin** (7 staleness warnings cleared):
  - `disa-cci`: the live U_CCI_List.xml is byte-identical to the committed one, version
    2025-01-23, despite a 2026-04-28 zip date.
  - `disa-cci-trackr`: enumeration 3,551 matches.
  - `nist-800-53` and `-53b`: CSRC still names Release 5.2.0.
- **Still pending** (no issuer page stated the version): scf (live tag 2026.3), mitre-atlas
  (v2026.10), cisa-scubagear, cisa-csaf, the OWASP feeds, openai-api, and the no-release
  repositories. The tags fallback and the dispatch run decide them.

**The first CI dispatch** (run 41936204283, 2026-11-04, `fetch=false`) proved the pipe from
GitHub's runners:
- **STIG verdict:** `stig_status: current` — library, NCP and trackr all `same` (NCP entry
  digest `c401538de35cfe04`, 96 joined). This is the first live STIG verdict since July.
- **Oracle benchmark:** green on the runner.
- **Fetch ledger:** 272 requests to 96 hosts and 7 refusals.
  - Six refusals came from the four TLS/timeout hosts (`www.acq.osd.mil`, `www.cnss.gov`,
    `www.ilga.gov`: "unable to get local issuer certificate"; `www.cyber.gov.au`: timeout).
    They fail the same way from the runners.
  - The ledger also exposed two **defects, fixed in 0.15.1**:
    1. **Robots precedence (the seventh refusal).** `www.ismap.go.jp/csm` was refused. The stdlib robots parser
       applies the first matching rule, and RFC 9309 §2.2.2 requires the longest
       (`Allow: /csm` beats `Disallow: /`). fetchkit now evaluates robots itself. Re-swept,
       64 registry and seed URLs on 16 hosts with fetched robots files gave exactly one changed
       verdict: this one.
    2. **GitHub counted twice (no refusal).** api.github.com took 54 calls, while the census had said 37.
       No single process passed its 50-call cap, but the run total did.
       The monitor and `standards_refresh` both looked up all 19 release feeds, and the
       census answered with a release, so it never counted the tags fallback. Now the monitor
       skips those feeds in the monthly path. The census models a 404 on every release lookup:
       74 > 50 was red before the skip, and 38 ≤ 50 is green after. The upper-bound plan is
       327 requests.
- **Release rows (live tags):** openapi-spec, mitre-attack, mcp-spec and oscal-format read
  `current` against their pins. Seven rows stay `registry_stale`, none moved without an issuer
  statement:
  - **scf** 2026.3: the SCF download page still names 2026.2.
  - **mitre-atlas** v2026.10: atlas.mitre.org states no version.
  - **cisa-scubagear** v2.0.0 and **openai-api** 2.0.0: the registry carries free text.
  - **owasp-asvs** `latest`, **owasp-top10** `2017-RC2` and **owasp-llm-top10** `2024`: the
    first tags-API entry is not a release of record.
- **Release rows (check_failed):** eight rows have no tag at all.
  - No releases or tags: cisa-csaf, cisa-kev, enisa-ecsf, fedramp (`FedRAMP/rules`) and
    huggingface-hub.
  - The repository itself answers 404: csa-ccm, csa-star-ccm5 and nist-ai-rmf.

  These need a different check strategy or a repo repoint, and both need evidence from
  outside this phase's scope.

**A second CI dispatch** (run 41940244303, on the 0.15.1 fixes, green) confirmed the fixes
from the runners. ISMAP `/csm` was admitted. api.github.com made 28 calls (cap 50) and was
the busiest host. No host exceeded its cap, and the STIG verdict was still `current`.

Its ledger refused two more things:
- **16 `github.com/…/releases.atom` URLs: correct.** GitHub's robots `*` group disallows
  `/*.atom$`, which the stdlib parser could not express. The 18 `announcement_feeds` entries
  that poll those URLs had therefore broken GitHub's rules every month. They are now refused
  and never sent, and the release signal comes from the API. Removing or replacing those
  entries is owed.
- **One law.lis.virginia.gov statute page: a matcher defect, fixed.** A `Crawl-delay` line
  did not end the user-agent run, so `GPTBot: Disallow: /` merged into `*`.

## Weekly rotation, every loader governed, ATT&CK v20, KEV (Phase 51, 2026-11-05)

**Why:** everything that can be automated now runs weekly, spread across four weekdays, and every
change to canonical data arrives as a pull request a human reviews. Before that, every hand-run
loader had to go through the governor, and the ATT&CK layer had to stop guessing.

**Every hand-run loader is governed.** Eleven loaders had their own retry and sleep loops and
bypassed fetchkit: kev, nvd, fr_watcher, ecfr, eurlex, fips_cmvp, olir, cprt, oscal_diff,
attack_stix and horizon_monitor `--check`. Each now calls one helper, `fetchkit.fetch()`. It does
bounded retries on 429/5xx only, never retries a host-rule refusal, and writes a per-run ledger.
Pacing is each host's recorded rule. `host_policies.json` gains `eur-lex.europa.eu` (none
published; 3.0 s, the loader's old delay) and now holds 13 hosts. Measured live dry runs
(2026-11-05, one fresh governor each, 0 refusals):

| Loader | Requests | Result |
|---|---|---|
| kev | www.cisa.gov 1 | catalogVersion 2026.11.04, 1,768 CVEs |
| nvd (7 days) | services.nvd.nist.gov 5 (22 s, NVD's 5-per-30 s window) | 9,676 CVEs |
| fr_watcher (7 days) | www.federalregister.gov 2 | 135 documents |
| ecfr 45 CFR 164 C / 32 CFR 170 | www.ecfr.gov 2 + 2 | 45 CFR 164 differs only in `_as_of_date`; 32 CFR 170 identical |
| eurlex (4 regulations) | eur-lex.europa.eu 4 | **0 articles** (the committed files also hold 0, since 2026-07-02) |
| fips_cmvp | csrc.nist.gov 1 | **0 modules**: CMVP API unavailable |
| olir | csrc.nist.gov 1 | **404** `/api/olir/finalized` |
| cprt (report only) | csrc.nist.gov 2 | **404** `/api/catalog/pubs/page` |

**Correction of record.** 0.15.x said every monthly fetch went through the governor. The
workflow's OSCAL warm-up (`oscal_diff --oscal-cache … --dry-run`: 1 Range probe + 10 windows of
512 KiB for the 5,136,923 B catalog) did not, and the census, which replayed only `--check`, could
not see it. It is governed now, and the census counts it on every building day. Phase 52 then
removed the warm-up: the OSCAL catalog is committed under `canonical-sources/source_data/nist-800-53/`
and the build makes no network request (`build_requests_measured` is empty).

**ATT&CK v20.0, with issuer mappings.**
- **Source.** MITRE's TAXII 2.1 server, Enterprise collection, paged at 100: 11 requests (1 version
  check, 9 attack-pattern pages, 1 collection page). **706 live techniques: 227 + 479
  sub-techniques**, MITRE's stated counts. The committed file had been v19.1 (697), with a session
  `file://` path in its provenance; the new provenance names the issuer endpoint.
- **Mapping.** CTID Mappings Explorer, NIST 800-53 rev5 ↔ ATT&CK 16.1 enterprise (`last_update`
  04/16/2025). The old NIST v13 spreadsheet URL answers 404, which is why every committed mapping
  had been the loader's keyword fallback (22 controls). Only direct `mitigates` rows are used:
  5,314 rows collapse to 5,264 unique technique–control pairs over 470 techniques. Control ids are
  normalised (`AC-02` → `AC-2`); all 109 exist in the catalog.
- **Honest blanks.** 454 of 706 techniques carry controls. **252 are left blank**: no parent
  inheritance and no keyword guess. The 15 CTID ids that v20 deprecated or revoked drop out.
- **Rename notes.** 10 mapped techniques were renamed between 16.1 and v20 (for example T1176
  "Browser Extensions" → "Software Extensions"). Each carries a `nist_mapping_note` for review.
- **Build.** `build_db` now reads the loader's `sub_technique_of`: parent links 0 → 479. The
  `attack-mapper` eval case (T1078 ⊇ {AC-2, IA-2}) passes.
- **Records.** `feed_registry` `mitre-attack` is `current`. `source_manifest` has a new entry
  `mitre-attack-enterprise`, and `framework_changelog` has `chg-mitre-attack-v19.1-to-v20.0` with
  a verbatim provenance block. The phase-50 entry `chg-disa-stig-library-2026-10` gains the
  provenance block it shipped without (a correction of record).
- **Manual `--fetch`.** `standards_refresh --fetch` uses the same TAXII + CTID source as the
  Thursday slot.

**KEV refreshed:** 2026.07.01 (1,631) → 2026.11.04 (**1,768**): 137 added, 0 dropped. Every
committed record changed upstream. CISA added `forensicTriage` and edited ransomware flags and
descriptions, and the build stores the descriptions. The verbatim file is exempt from the
secret scan's email pattern by exact path (`tools/secret_scan.py` `ALLOW_PATHS`). CISA's
mailing-list archive URLs name organisational list addresses, which are public record, and
upstream text is never edited.

**The weekly rotation** (`canonical-sources/fetch_schedule.json`, procedure in the runbook §
Weekly rotation):
- **Monday:** the drift check, weekly instead of monthly.
- **Tuesday:** Federal Register + two eCFR parts.
- **Wednesday:** KEV, plus NVD report-only.
- **Thursday:** ATT&CK and STIG library, each only when the issuer moved, plus horizon report-only.

Planned load (upper bound): 241 / 17 / 17 / 76 requests.

**Not scheduled:** EUR-Lex, FIPS, OLIR and CPRT. Each source returns nothing today (table above).
NIST publishes no machine-readable CMVP listing (csrc.nist.gov, HTML search only), and the
documented CSF 2.0 CPRT export now serves an XLSX. Each repair is its own phase.

**Slot times.** Our own scheduled runs started 3h20m–8h08m after their 06:17 UTC cron (five runs,
July–November). GitHub publishes no quiet hour. A temporary probe workflow measures six candidate
times for 14 days. The slots are pinned from that data at the C8 hand-off (2026-11-19 or later).
