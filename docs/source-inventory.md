# GRC Source Inventory

Authoritative source registry for the GRC cross-mapping engine. Last updated: 2026-06-30.

All `human_review_required: true`. Never fabricate control IDs or crosswalk relationships.

---

## US Federal Standards (NIST)

| Framework | Version | URL | Format | Freshness | Loader |
|---|---|---|---|---|---|
| NIST SP 800-53 Rev 5.1.1 | Rev 5.1.1 | `https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json` | OSCAL JSON | GitHub Releases Atom | `oscal_diff.py` |
| NIST SP 800-53B Baselines | Rev 5 | `https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/baselines/` | OSCAL JSON | GitHub Releases | `oscal_diff.py` |
| NIST SP 800-171 Rev 3 | Rev 3 final | `https://csrc.nist.gov/pubs/sp/800/171/r3/final` | OSCAL JSON + PDF | csrc.nist.gov | `oscal_diff.py` adapter |
| NIST SP 800-172 Rev 3 | Rev 3 (May 2026) | `https://csrc.nist.gov/pubs/sp/800/172/r3/final` | OSCAL JSON + PDF | May 2026 target | pending |
| NIST CSF 2.0 | 2.0 | `https://csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all` | JSON (CPRT) | Real-time | `generate_controls_csf20.py` |
| NIST AI RMF | 1.0 | `https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf` | PDF | NIST news RSS | manual |
| NIST AI 600-1 (GenAI) | 1.0 | `https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf` | PDF | NIST news RSS | manual |
| NIST Privacy Framework | 1.0 | `https://www.nist.gov/system/files/documents/2020/01/16/NIST-Privacy-Framework-V1.0-Core.xlsx` | XLSX | Static | planned |
| NIST ATT&CK↔800-53 Mapping | v13/Rev5 | `https://www.nist.gov/system/files/documents/2023/09/12/SP800-53_ATT%26CK_v13_v1.xlsx` | XLSX | Version-based | `attack_stix_loader.py` |

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
| CMMC Assessment Guide | `https://www.acq.osd.mil/asda/dpc/cp/cyber/cmmc.html` | PDF | Version-based | reference |
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
| ATT&CK Enterprise STIX 2.1 | `https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json` | STIX JSON | GitHub (mitre/cti) | `attack_stix_loader.py` |
| ATT&CK TAXII 2.1 Server | `https://cti-taxii.mitre.org/taxii/` | TAXII/STIX | Real-time | planned |
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
| `kev_loader.py` | `nist-catalog/ingestion/` | CISA KEV JSON | `canonical-sources/known_exploited_vulnerabilities.json` |
| `cci_trackr_loader.py` | `nist-catalog/ingestion/` | CCI Trackr API | `canonical-sources/disa-cci-trackr.json` |
| `ecfr_loader.py` | `engine/` | eCFR REST API | `canonical-sources/cfr/{title}-cfr-{part}.json` |
| `fr_watcher.py` | `engine/` | Federal Register API | `canonical-sources/announcements_feed.json` |
| `attack_stix_loader.py` | `engine/` | MITRE ATT&CK STIX + NIST XLSX | `canonical-sources/mitre-attack-techniques.json` |
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

| Layer | Script | Trigger | Sources |
|---|---|---|---|
| Daily | `kev_loader.py` | Cron / manual | CISA KEV JSON (primary or GitHub mirror) |
| Daily | `nvd_api_loader.py` | Cron / manual | NVD CVE API 2.0 (incremental by `lastModified`) |
| Daily | `edgar_loader.py` | Cron / manual | SEC EDGAR 8-K Item 1.05 (incremental by filed date) |
| Weekly | `announcement_monitor.py` | Cron / manual | All RSS/Atom feeds in feed_registry |
| Weekly | `oscal_diff.py --check-remote` | Cron / manual | usnistgov/oscal-content GitHub |
| Weekly | `olir_crawler.py --auto-download` | Cron / manual | NIST CPRT OLIR catalog |
| Weekly | `eurlex_loader.py --all` | Cron / manual | EUR-Lex ELI endpoints |
| Weekly | `ecfr_loader.py --all-configured-parts` | Cron / manual | eCFR versioner API |
| Weekly | `attack_stix_loader.py --check-version` | Cron / manual | mitre/cti GitHub releases |
| On-demand | `cprt_traverser.py` | Manual | NIST CPRT publications API |
| On-demand | `pdf_structure_extractor.py` | Manual | Local PDF files |
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
The April-2026 library yields 383 benchmarks / 19,667 rules / 539 distinct CCIs (97.6% resolve
in `cci_bridge`).

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
