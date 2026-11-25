# HIPAA Privacy Rule: the 2026 final rule as a version

Phase 57. Every number on this page is read from `grc.db` (tables `regulation_paragraphs`, `regulation_paragraph_diff`, `master_mappings`); `tools/count_truth.py` does not cover it, so regenerate it with the build when the data moves.

## The rule

| | |
|---|---|
| Document | HHS OCR final rule, FR doc 2026-23429, 91 FR 74848, RIN 0945-AA00 |
| Published / effective / compliance | 2026-11-19 / 2027-01-19 / 2027-07-19 |
| Amends | 45 CFR 160.103 (business associate) and Subpart E: 164.501, .502, .506, .512, .514, .520, .524 (rewritten), .525 (new), .532 |
| Does not amend | Subpart C, the Security Rule (164.302-164.318) |
| eCFR | not yet codified; the eCFR applies an amendment on its effective date |
| HIPAA Security Rule final rule | a separate rulemaking (RIN 0945-AA22): still only the 2025 proposed rule |

**Only the amendatory instructions change the text.** The preamble (section IV) also discusses a minimum-necessary exception for care coordination (its topic D) and disclosures for substance use disorder, serious mental illness and emergencies (topic F); no instruction amends 164.502(b), 164.510 or 164.512(j), so neither version's text differs there. Instructions 1 and 3 replace the two authority citations, 2 amends 160.103, and 4 to 12 amend Subpart E (register below).

## How the database holds it

- **Two labels, never merged:** `HIPAA Privacy Rule` is Subpart E as in force (eCFR, 2026-11-18); `HIPAA Privacy Rule (2026 Final Rule)` is Subpart E as amended. They sit side by side the way NIST SP 800-171 r2 and r3 do.
- **`regulation_paragraphs`:** both texts paragraph by paragraph (1,040 in force, 1,094 amended). The amended text is computed: the in-force text with the rule's numbered amendatory instructions applied in order (`cross-mapping/engine/cfr_versions.py`).
- **`regulation_paragraph_diff`:** one row per paragraph with its status and the instruction that touched it. Paragraphs are matched by identity, never by citation string: the rule removes 164.520(c)(2)(ii) and gives that number to the old (c)(2)(iii).
- **`master_mappings`:** `HIPAA Privacy Rule (2026 Final Rule)` has 5,869 rows, each a copy of an in-force row whose provision text is unchanged, at the amended paragraph id. Provenance `carried_transitive_unified` or `carried_consensus`, same tier as the source row; consensus votes are not copied, so carried consensus rows read `asserted_by_source`. No row pairs the two versions.
- **Query:** `python3 cross-mapping/engine/dbz_query.py cfr-version 164.520(c)(2)(ii)` (one provision in both versions), `cfr-version --summary`, `--section 164.524`, `--status changed`.

## What changed, section by section (paragraphs)

| Section | unchanged | renumbered, unchanged | changed | unchanged under a changed lead-in | held back | removed | dropped from the rewritten section | added |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 164.501 | 44 | 0 | 10 | 2 | 0 | 0 | 0 | 6 |
| 164.502 | 92 | 2 | 11 | 0 | 0 | 0 | 0 | 2 |
| 164.506 | 11 | 0 | 2 | 0 | 0 | 0 | 0 | 1 |
| 164.512 | 182 | 0 | 9 | 3 | 0 | 0 | 0 | 3 |
| 164.514 | 122 | 0 | 3 | 0 | 0 | 0 | 0 | 1 |
| 164.520 | 58 | 3 | 19 | 0 | 1 | 2 | 0 | 2 |
| 164.524 | 1 | 0 | 35 | 10 | 0 | 0 | 6 | 42 |
| 164.525 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 |
| 164.532 | 11 | 0 | 9 | 0 | 0 | 0 | 0 | 0 |
| **all** | **913** | **5** | **98** | **15** | **1** | **2** | **6** | **62** |

Sections with no change: 164.500, 164.504, 164.508, 164.509, 164.510, 164.522, 164.526, 164.528, 164.530, 164.534, 164.535.

## What happens to the existing mappings

The in-force label has 6,460 master rows over 579 cited paragraphs. **5,869 (90.9%) carry.** The rest stay blank until a source maps the amended text.

| Cited paragraph is | paragraphs | HITRUST-bridged rows | consensus rows | carried |
|---|---:|---:|---:|---|
| unchanged | 506 | 5,767 | 78 | yes |
| renumbered, unchanged | 2 | 24 | 0 | yes |
| changed | 42 | 319 | 15 | no |
| unchanged under a changed lead-in | 13 | 72 | 0 | no |
| held back | 1 | 12 | 0 | no |
| removed | 1 | 26 | 0 | no |
| dropped from the rewritten section | 6 | 65 | 0 | no |
| not in the in-force text | 8 | 82 | 0 | no |

**Same wording at a new number, not carried.** No instruction moves these paragraphs, so the carry rule leaves their rows blank; a reviewer can confirm the move: 164.502(a)(2)(ii) → 164.502(a)(2)(iii) (8 rows); 164.524(b)(2) → 164.524(d)(5)(ii) (0 rows); 164.524(c)(2)(iii)(A) → 164.524(c)(2)(iv)(A)(1) (7 rows).

## Every change, by amendatory instruction

Paragraphs whose own wording changed, and every added, removed or held-back paragraph (a parent that changed only through its sub-paragraphs is not repeated). Wording is shortened to the part that differs. Full text: `dbz_query.py cfr-version <id>`.


**Instruction 4**

- `164.501[Health care operations](1)` changed: «…health or reducing health care costs, protocol development, case management and care coordination, contacting of health care providers and patients with information about treatment alternatives; and related functions…» → «…health or reducing health care costs; protocol development; case management and care coordination; contacting of health care providers and patients with information about treatment alternatives; and related functions…»
- `164.501[Health care operations](2)` changed: «…accreditation, certification, licensing, or credentialing activities;…» → «…accreditation, certification, licensing, or credentialing activities.…»
- `164.501[Health care operations](3)` changed: «…§ 164.514(g) are met, if applicable;…» → «…§ 164.514(g) are met, if applicable.…»
- `164.501[Health care operations](4)` changed: «…and abuse detection and compliance programs;…» → «…and abuse detection and compliance programs.…»
- `164.501[Health care operations](5)` changed: «…methods of payment or coverage policies; and…» → «…methods of payment or coverage policies.…»
- `164.501[Health care operations](6)` changed: «…entity, including, but not limited to:…» → «…entity, including, but not limited to, any of the following:…»
- `164.501[Health care operations](6)(i)` changed: «…with the requirements of this subchapter;…» → «…with the requirements of this subchapter.…»
- `164.501[Health care operations](6)(ii)` unchanged under a changed lead-in: lead-in changed: 164.501[Health care operations](6)
- `164.501[Health care operations](6)(iii)` changed: «…Resolution of internal grievances;…» → «…Resolution of internal grievances.…»
- `164.501[Health care operations](6)(iv)` changed: «…due diligence related to such activity; and…» → «…due diligence related to such activity.…»
- `164.501[Health care operations](6)(v)` unchanged under a changed lead-in: lead-in changed: 164.501[Health care operations](6)
- `164.501[Electronic health record]` added: «Electronic health record Electronic health record means an electronic record of health-related information on an individual that is created, gathered, managed, and consulted by authorized health care clinicians and staff.…»
- `164.501[Personal health application]` added: «Personal health application Personal health application means an electronic application used by an individual to access health information about that individual, which can be drawn from multiple sources, provided that…»
- `164.501[Personal health application](1)` added: «Such information is managed, shared, and controlled by or primarily for the individual.…»
- `164.501[Personal health application](2)` added: «Such information is not managed, shared, or controlled in any of the following manners:…»
- `164.501[Personal health application](2)(i)` added: «By or primarily for a covered entity.…»
- `164.501[Personal health application](2)(ii)` added: «Primarily for another person.…»

**Instruction 5**

- `164.502(a)(2)` changed: «…required to disclose protected health information:…» → «…required to disclose protected health information in each of the following circumstances:…»
- `164.502(a)(2)(i)` changed: «…when requested under, and required by § 164.524 or § 164.528; and…» → «…when requested under, and required by, § 164.524 or § 164.528.…»
- `164.502(a)(2)(ii)` changed: «…When required by the Secretary under subpart C of part 160 of this subchapter to investigate or determine the covered entity's compliance with this subchapter.…» → «…To a person designated by the individual, when requested under, and required by, § 164.524.…»
- `164.502(a)(4)(ii)` changed: «…To the covered entity, individual, or individual's designee, as necessary to satisfy a covered entity's obligations under § 164.524(c)(2)(ii) and (3)(ii) with respect to an individual's request for…» → «…To the covered entity or, when specified in the written contract or other written arrangement with a business associate required by § 164.502(e)(2), to the individual or the…»
- `164.502(a)(5)(ii)(B)(2)(vii)` → `164.502(a)(5)(ii)(B)(2)(viii)` renumbered, unchanged
- `164.502(a)(5)(ii)(B)(2)(viii)` → `164.502(a)(5)(ii)(B)(2)(ix)` renumbered, unchanged
- `164.502(a)(2)(iii)` added: «When required by the Secretary under subpart C of part 160 of this subchapter to investigate or determine the covered entity's compliance with this subchapter.…»
- `164.502(a)(5)(ii)(B)(2)(vii)` added: «To a person designated by an individual, when requested under § 164.524;…»

**Instruction 6**

- `164.506(c)(6)` added: «A covered entity may disclose an individual's protected health information to a social services agency, community-based organization, home and community based services provider, or similar third party that provides health…»

**Instruction 7**

- `164.512(d)(3)` changed: «…Joint activities or investigations. Nothwithstanding…» → «…Joint activities or investigations. Notwithstanding…»
- `164.512(k)(1)` changed: «…Military…» → «…Uniformed Services…»
- `164.512(k)(1)(i)` changed: «…Armed Forces personnel. A covered entity may use and disclose the protected health information of individuals who are Armed Forces personnel for activities deemed necessary by appropriate military…» → «…Uniformed Services personnel. A covered entity may use and disclose the protected health information of individuals who are Uniformed Services personnel for activities deemed necessary by appropriate command…»
- `164.512(k)(1)(i)(A)` changed: «…Appropriate military command authorities; and…» → «…Appropriate command authorities.…»
- `164.512(k)(1)(i)(B)` unchanged under a changed lead-in: lead-in changed: 164.512(k)(1), 164.512(k)(1)(i)
- `164.512(k)(1)(ii)` changed: «…Separation or discharge from military service. A covered entity that is a component of the Departments of Defense or Homeland Security may disclose to the Department of Veterans…» → «…Separation or discharge from Uniformed Service. A covered entity that is a component of the Departments of Defense, Homeland Security, Commerce, or Health and Human Services may disclose…»
- `164.512(k)(1)(iii)` unchanged under a changed lead-in: lead-in changed: 164.512(k)(1)
- `164.512(k)(1)(iv)` unchanged under a changed lead-in: lead-in changed: 164.512(k)(1)
- `164.512(k)(2)` changed: «…National Security Act (50 U.S.C. 401,…» → «…National Security Act (50 U.S.C. 3001,…»
- `164.512(m)` added: «Standard: Disclosures to Telecommunications Relay Services.…»
- `164.512(m)(1)` added: «A covered entity may disclose protected health information to a Telecommunications Relay Service Communications Assistant, as defined at 47 CFR 64.601(a)(12), as necessary to conduct covered functions.…»
- `164.512(m)(2)` added: «Notwithstanding § 164.502(a)(3), a business associate may disclose protected health information to a Telecommunications Relay Service Communications Assistant, as defined at 47 CFR 64.601(a)(12), as necessary to conduct covered functions…»

**Instruction 8**

- `164.514(h)(2)(v)` added: «Exercise of individual rights. A covered entity may not impose unreasonable verification measures on an individual that would impede the individual from exercising a right under this part. An unreasonable…»

**Instruction 9**

- `164.520(a)(1)` changed: «…as provided by paragraph (a)(3) or (4)…» → «…as provided by paragraph (a)(3)…»
- `164.520(a)(4)` removed: «Exception for inmates. An inmate does not have a right to notice under this section, and the requirements of this section do not apply to a correctional institution that is…»
- `164.520(b)(1)(i)` changed: «…header or otherwise prominently displayed: "THIS NOTICE DESCRIBES HOW MEDICAL INFORMATION ABOUT YOU MAY BE USED AND DISCLOSED AND HOW YOU CAN GET ACCESS TO THIS INFORMATION. PLEASE…» → «…header or otherwise prominently displayed: NOTICE OF PRIVACY PRACTICES OF [NAME OF COVERED ENTITY, AFFILIATED COVERED ENTITIES, OR ORGANIZED HEALTH CARE ARRANGEMENT, AS APPLICABLE] THIS NOTICE DESCRIBES: HOW…»
- `164.520(b)(1)(iii)(B)` changed: «…protected health information to the sponsor of the plan;…» → «…protected health information to the plan sponsor;…»
- `164.520(b)(1)(iv)(C)` changed: «…The right to inspect and copy protected health information…» → «…The right of access to inspect and obtain a copy of protected health information at limited cost or, in some cases, free of charge; and the right of…»
- `164.520(b)(1)(iv)(E)` changed: «…as provided by § 164.528; and…» → «…as provided by § 164.528;…»
- `164.520(b)(1)(iv)(F)` changed: «…from the covered entity upon request.…» → «…from the covered entity upon request; and…»
- `164.520(b)(1)(vii)` changed: «…The notice must contain the name, or title, and telephone number of a person or office to contact for further information…» → «…The notice must contain the name or title, telephone number, and email address for a designated person or office responsible for providing further information and answering questions about…»
- `164.520(c)(2)(ii)` removed: «Except in an emergency treatment situation, make a good faith effort to obtain a written acknowledgment of receipt of the notice provided in accordance with paragraph (c)(2)(i) of this section,…»
- `164.520(c)(2)(iii)` → `164.520(c)(2)(ii)` renumbered, unchanged
- `164.520(c)(2)(iii)(A)` → `164.520(c)(2)(ii)(A)` renumbered, unchanged
- `164.520(c)(2)(iii)(B)` → `164.520(c)(2)(ii)(B)` renumbered, unchanged
- `164.520(c)(2)(iv)` → `164.520(c)(2)(iii)` held back: FR reprint without an instruction differs at 164.520(c)(2)(iii)
- `164.520(c)(3)(iii)` changed: «…individual's first request for service. The requirements in paragraph (c)(2)(ii) of this section apply to electronic notice.…» → «…individual's first request for service.…»
- `164.520(e)` changed: «…notices issued by the covered entity and, if applicable, any written acknowledgments of receipt of the notice or documentation of good faith efforts to obtain such written acknowledgment,…» → «…notices issued by the covered entity.…»
- `164.520(b)(1)(iv)(G)` added: «The right to discuss the notice with a designated contact person or office identified by the covered entity pursuant to § 164.520(b)(1)(vii).…»
- `164.520(b)(2)(iii)` added: «A covered entity may provide in its notice information about how an individual who seeks to direct a copy of protected health information to another person, when the request does…»

**Instruction 10**

- `164.524` changed: «……» → «……»
- `164.524(a)(1)` changed: «…Except as otherwise provided in paragraph (a)(2) or (a)(3) of this section, an individual has a right of access to inspect and obtain a copy of protected health…» → «…Except as otherwise provided in paragraphs (a)(2) or (3) of this section, an individual has a right of access to inspect and obtain a copy of protected health…»
- `164.524(a)(1)(i)` changed: «…Psychotherapy notes; and…» → «…Psychotherapy notes.…»
- `164.524(a)(1)(ii)` unchanged under a changed lead-in: lead-in changed: 164.524(a)(1)
- `164.524(a)(2)` changed: «…an opportunity for review, in the following circumstances.…» → «…an opportunity for review, in any of the following circumstances:…»
- `164.524(a)(2)(i)` unchanged under a changed lead-in: lead-in changed: 164.524(a)(2)
- `164.524(a)(2)(ii)` unchanged under a changed lead-in: lead-in changed: 164.524(a)(2)
- `164.524(a)(2)(iii)` unchanged under a changed lead-in: lead-in changed: 164.524(a)(2)
- `164.524(a)(2)(iv)` unchanged under a changed lead-in: lead-in changed: 164.524(a)(2)
- `164.524(a)(2)(v)` unchanged under a changed lead-in: lead-in changed: 164.524(a)(2)
- `164.524(a)(3)` changed: «…entity may deny an individual access, provided that the individual is given a right to have such denials reviewed, as required by paragraph (a)(4) of this section, in…» → «…entity may deny an individual access provided that the individual is given a right to have such denials reviewed, as required by paragraph (e)(4) of this section, in…»
- `164.524(a)(3)(i)` changed: «…of the individual or another person;…» → «…of the individual or another person.…»
- `164.524(a)(3)(ii)` changed: «…substantial harm to such other person; or…» → «…substantial harm to such other person.…»
- `164.524(a)(3)(iii)` unchanged under a changed lead-in: lead-in changed: 164.524(a)(3)
- `164.524(a)(4)` changed: «…the reviewing official under paragraph (d)(4)…» → «…the reviewing official under paragraph (e)(4)…»
- `164.524(b)` changed: «…Requests for access and timely action…» → «…Requests for access and timely action--…»
- `164.524(b)(1)` changed: «…Individual's request for access. The covered entity must permit an individual to request access to inspect or to obtain a copy of the protected health information about the…» → «…Individual's request for access.…»
- `164.524(b)(2)(i)` changed: «…on a request for access no later than 30 days after receipt of the request as follows.…» → «…on a request for access as soon as practicable, but no later than 15 calendar days after receipt of the request, and the following conditions must be met:…»
- `164.524(b)(2)(i)(A)` unchanged under a changed lead-in: lead-in changed: 164.524(b)(2)(i)
- `164.524(b)(2)(i)(B)` changed: «…denial, in accordance with paragraph (d)…» → «…denial, in accordance with paragraph (e)(2)…»
- `164.524(b)(2)(ii)` changed: «…by no more than 30…» → «…by no more than 30 calendar…»
- `164.524(b)(2)(ii)(A)` unchanged under a changed lead-in: lead-in changed: 164.524(b)(2)(ii)
- `164.524(b)(2)(ii)(B)` unchanged under a changed lead-in: lead-in changed: 164.524(b)(2)(ii)
- `164.524(c)(1)` changed: «…provide the access requested by individuals, including inspection or obtaining a copy, or both, of the protected health information about them…» → «…provide the access requested by an individual, including inspection or obtaining a copy, or both, of the protected health information about the individual…»
- `164.524(c)(2)(i)` changed: «…The covered entity must provide the…» → «…The covered entity must provide an…»
- `164.524(c)(2)(iii)` changed: «…The covered entity may provide the individual with a summary of the protected health information requested, in lieu of providing access to the protected health information or may…» → «…Where another federal or state law applicable to the covered entity requires the provision of access in a particular electronic form and format, the protected health information is…»
- `164.524(c)(2)(iii)(A)` dropped from the rewritten section: «The individual agrees in advance to such a summary or explanation; and…»
- `164.524(c)(2)(iii)(B)` dropped from the rewritten section: «The individual agrees in advance to the fees imposed, if any, by the covered entity for such summary or explanation.…»
- `164.524(c)(3)` changed: «…Time and manner of access.…» → «…Time and manner of access. The covered entity must provide the access as requested by an individual in a timely manner as required by paragraph (b)(2) of this…»
- `164.524(c)(3)(i)` dropped from the rewritten section: «The covered entity must provide the access as requested by the individual in a timely manner as required by paragraph (b)(2) of this section, including arranging with the individual for…»
- `164.524(c)(3)(ii)` dropped from the rewritten section: «If an individual's request for access directs the covered entity to transmit the copy of protected health information directly to another person designated by the individual, the covered entity must…»
- `164.524(c)(4)` changed: «…Fees. If the individual requests a copy of the protected health information or agrees to a summary or explanation of such information, the covered entity may impose a…» → «…Fees.…»
- `164.524(c)(4)(i)` changed: «…Labor for copying the protected health information requested by the individual, whether in paper or electronic form;…» → «…If an individual requests a copy of the protected health information or agrees to a summary or explanation of such information, the covered entity may impose a reasonable,…»
- `164.524(c)(4)(ii)` changed: «…Supplies for creating the paper copy or electronic media if the individual requests that the electronic copy be provided on portable media;…» → «…A covered entity may not impose a fee in either of the following circumstances:…»
- `164.524(c)(4)(iii)` dropped from the rewritten section: «Postage, when the individual has requested the copy, or the summary or explanation, be mailed; and…»
- `164.524(c)(4)(iv)` dropped from the rewritten section: «Preparing an explanation or summary of the protected health information, if agreed to by the individual as required by paragraph (c)(2)(iii) of this section.…»
- `164.524(d)` changed: «…Implementation specifications: Denial of access. If the covered entity denies access, in whole or in part, to protected health information, the covered entity must comply with the following…» → «…Standard: Directing an electronic copy of certain protected health information to a person designated by the individual…»
- `164.524(d)(1)` changed: «…Making other information accessible. The covered entity must, to the extent possible, give the individual access to any other protected health information requested, after excluding the protected health…» → «…Right of access to direct. Subject to the limitations of paragraph (a)(1) of this section, and except as otherwise provided in paragraphs (d)(2) and (3) of this section,…»
- `164.524(d)(2)` changed: «…Denial. The covered entity must provide a timely, written denial to the individual, in accordance with paragraph (b)(2) of this section. The denial must be in plain language…» → «…Unreviewable grounds for denial. A covered entity may deny an individual's request to exercise the right of access to direct a covered entity to transmit an electronic copy…»
- `164.524(d)(2)(i)` changed: «…The basis for the denial;…» → «…The protected health information is excepted from the right of access to direct by paragraph (d)(1) of this section.…»
- `164.524(d)(2)(ii)` changed: «…If applicable, a statement of the individual's review rights under paragraph (a)(4) of this section, including a description of how the individual may exercise such review rights; and…» → «…A covered entity that is a correctional institution or a covered health care provider acting under the direction of the correctional institution may deny, in whole or in…»
- `164.524(d)(2)(iii)` changed: «…A description of how the individual may complain to the covered entity pursuant to the complaint procedures in § 164.530(d) or to the Secretary pursuant to the procedures…» → «…An individual's ability to exercise of the right of access to direct may be temporarily suspended by a covered entity in the course of research that includes treatment…»
- `164.524(d)(3)` changed: «…Other responsibility. If the covered entity does not maintain the protected health information that is the subject of the individual's request for access, and the covered entity knows…» → «…Reviewable grounds for denial of a request to exercise the right of access to direct. A covered entity may deny an individual's request to exercise the right of…»
- `164.524(d)(4)` changed: «…Review of denial requested. If the individual has requested a review of a denial under paragraph (a)(4) of this section, the covered entity must designate a licensed health…» → «…Implementation specification: Summary or explanation prepared by covered entity.…»
- `164.524(e)` changed: «…Implementation specification: Documentation. A covered entity must document the following and retain the documentation as required by § 164.530(j):…» → «…Implementation specifications: Denial of access. If a covered entity denies an individual's right of access, in whole or in part, to protected health information pursuant to paragraph (a)…»
- `164.524(e)(1)` changed: «…The designated record sets that are subject to access by individuals; and…» → «…Making other information accessible. The covered entity must, to the extent possible, give the individual, or a person designated by the individual, access to any other protected health…»
- `164.524(e)(2)` changed: «…The titles of the persons or offices responsible for receiving and processing requests for access by individuals.…» → «…Denial. The covered entity must provide a timely, written denial to the individual. The denial must be in plain language and contain all of the following:…»
- `164.524(b)(1)(i)` added: «The covered entity must permit an individual to request access to inspect or to obtain a copy of the protected health information about the individual that is maintained in a…»
- `164.524(b)(1)(ii)` added: «The covered entity may require individuals to make requests for access in writing, provided that it informs individuals of such a requirement. For purposes of this paragraph, in writing means…»
- `164.524(b)(1)(iii)` added: «The covered entity may not impose measures on individuals making requests for access that impede an individual from obtaining access when there is a measure for making such requests that…»
- `164.524(b)(2)(iii)` added: «Where another federal or state law requires a covered entity to provide an individual with access to the protected health information requested in less than 15 calendar days, that shorter…»
- `164.524(c)(2)(iv)` added: «…»
- `164.524(c)(2)(iv)(A)` added: «The covered entity may provide an individual with a summary of the protected health information requested, in lieu of providing access to the protected health information, or may provide an…»
- `164.524(c)(2)(iv)(A)(1)` added: «The individual agrees in advance to such a summary or explanation; and…»
- `164.524(c)(2)(iv)(A)(2)` added: «The individual agrees in advance to the fees imposed, if any, by the covered entity for such summary or explanation.…»
- `164.524(c)(2)(iv)(B)` added: «The covered entity must inform an individual to whom it offers to provide a summary in lieu of a copy of protected health information that the individual retains the right…»
- `164.524(c)(4)(i)(A)` added: «Labor for copying the protected health information requested by the individual, whether in non-electronic (e.g., paper, film) or electronic form;…»
- `164.524(c)(4)(i)(B)` added: «Supplies for creating a non-electronic copy;…»
- `164.524(c)(4)(i)(C)` added: «Postage, when the individual has requested that a non-electronic copy, or the summary or explanation, be mailed; and…»
- `164.524(c)(4)(i)(D)` added: «Labor of preparing an explanation or summary of the protected health information, if agreed to by the individual as required by paragraph (c)(2)(iv) of this section.…»
- `164.524(c)(4)(ii)(A)` added: «An individual inspects the protected health information about the individual, as described at (a)(1) of this section.…»
- `164.524(c)(4)(ii)(B)` added: «An individual accesses electronic protected health information maintained by or on behalf of the covered entity using an internet-based method, such as a personal health application.…»
- `164.524(d)(2)(iv)` added: «An individual's request to exercise the right of access to direct may be denied if the protected health information is contained in records that are subject to the Privacy Act,…»
- `164.524(d)(2)(v)` added: «An individual's request to exercise the right of access to direct may be denied if the protected health information was obtained from someone other than a health care provider under…»
- `164.524(d)(3)(i)` added: «A licensed health care professional has determined, in the exercise of professional judgment, that the access is reasonably likely to endanger the life or physical safety of the individual or…»
- `164.524(d)(3)(ii)` added: «The protected health information makes reference to another person (unless such other person is a health care provider) and a licensed health care professional has determined, in the exercise of…»
- `164.524(d)(4)(i)` added: «The covered entity may transmit, to a person designated by an individual pursuant to the right of access to direct, a summary of requested protected health information in an electronic…»
- `164.524(d)(4)(i)(A)` added: «The individual agrees in advance to such a summary or explanation.…»
- `164.524(d)(4)(i)(B)` added: «The individual agrees in advance to the fees imposed, if any, by the covered entity for such summary or explanation.…»
- `164.524(d)(4)(ii)` added: «The covered entity must inform an individual with respect to whose protected health information it offers to transmit a summary to a person designated by the individual in lieu of…»
- `164.524(d)(5)` added: «Implementation specification: Requests for access and timely action.…»
- `164.524(d)(5)(i)` added: «Individual's request for access. The covered entity must permit an individual to exercise the right of access to direct where the request is clear, conspicuous, and specific. The covered entity…»
- `164.524(d)(5)(ii)` added: «Timely action by the covered entity.…»
- `164.524(d)(5)(ii)(A)` added: «Except as provided in paragraph (d)(5)(ii)(B) of this section, the covered entity is required to provide an electronic copy requested under paragraph (d)(1) of this section as soon as practicable,…»
- `164.524(d)(5)(ii)(A)(1)` added: «If the covered entity grants the request, in whole or in part, it must inform the individual of the acceptance of the request and provide the access requested, in accordance…»
- `164.524(d)(5)(ii)(A)(2)` added: «If the covered entity denies the individual's request to exercise the right of access to direct, in whole or in part, it must provide the individual with a written denial,…»
- `164.524(d)(5)(ii)(B)` added: «If the covered entity is unable to take an action required by paragraph (d)(5)(ii)(A)(1) or (2) of this section within the time required by paragraph (d)(5)(ii)(A) of this section, as…»
- `164.524(d)(5)(ii)(B)(1)` added: «The covered entity, within the time limit set by paragraph (d)(5)(ii)(A) of this section, as applicable, provides the individual with a written statement of the reasons for the delay and…»
- `164.524(d)(5)(ii)(B)(2)` added: «The covered entity may have only one such extension of time for action on the individual's request to exercise the right of access to direct.…»
- `164.524(d)(5)(ii)(C)` added: «Where another federal or state law requires a covered entity to provide an individual with an electronic copy of the protected health information in an electronic health record in less…»
- `164.524(e)(2)(i)` added: «The basis for the denial.…»
- `164.524(e)(2)(ii)` added: «If applicable, a statement of the individual's right of review under paragraph (e)(4) of this section, including a description of how the individual may exercise such right.…»
- `164.524(e)(2)(iii)` added: «A description of how the individual may complain to the covered entity pursuant to the complaint procedures in § 164.530(d) or to the Secretary pursuant to the procedures in §…»
- `164.524(e)(3)` added: «Other responsibility. If the covered entity (or its business associate on the covered entity's behalf) does not maintain the protected health information that is the subject of the individual's request…»
- `164.524(e)(4)` added: «Right to review of denial. If the individual requests a review of a denial on a ground permitted under paragraphs (a)(3) or (d)(3) of this section, the covered entity must…»
- `164.524(f)` added: «Implementation specification: Documentation. A covered entity must document all of the following and retain the documentation as required by § 164.530(j):…»
- `164.524(f)(1)` added: «The designated record sets that are subject to the right of access under paragraph (a) of this section.…»
- `164.524(f)(2)` added: «The electronic health records that are subject to the right of access to direct under paragraph (d) of this section.…»
- `164.524(f)(3)` added: «The titles of the persons or offices responsible for receiving and processing requests for access made pursuant to paragraphs (a) and (d) of this section.…»

**Instruction 11**

- `164.525` added: «If a covered entity imposes fees for copies of protected health information requested under this subpart, the covered entity must post a fee schedule on its website, if it has…»
- `164.525(a)` added: «All types of access to protected health information available free of charge.…»
- `164.525(b)` added: «Standard fees for all of the following copies, where the covered entity generally charges for such copies:…»
- `164.525(b)(1)` added: «Copies of protected health information provided under § 164.524(a) and § 164.524(d), with respect to all available electronic and non-electronic forms and formats for such copies.…»
- `164.525(b)(2)` added: «Copies of protected health information disclosed pursuant to the individual's valid authorization under § 164.508, with respect to all available forms and formats for such copies.…»

**Instruction 12**

- `164.532(e)(1)` changed: «…documentation and contract requirements of §§…» → «…documentation and contract requirements of § §…»
- `164.532(e)(1)(i)` changed: «…Prior to January 25, 2013,…» → «…Prior to November 19, 2026,…»
- `164.532(e)(1)(ii)` changed: «…not renewed or modified from March 26, 2013, until September 23, 2013.…» → «…not renewed or modified from January 19, 2027, until July 19, 2027.…»
- `164.532(e)(2)(i)` changed: «…or modified on or after September 23, 2013;…» → «…or modified on or after July 19, 2027;…»
- `164.532(e)(2)(ii)` changed: «…September 22, 2014.…» → «…January 18, 2028.…»
- `164.532(e)(3)` changed: «…C of this subchapter and §§…» → «…C of this subchapter and § §…»

## Read before relying on a carried row

- **Identical text is not identical meaning.** 18 carried provisions (231 rows) use the term "health care operations". The rule changes that definition only in punctuation, and the punctuation is the change: semicolons now separate "protocol development; case management and care coordination; contacting of health care providers" into items of their own (the preamble's stated aim, topic C). These provisions carry because their own text is unchanged; the term they use now reads differently.
- **Punctuation-only changes are not automatically editorial.** The definition above is the example; that is why the carry rule treats any change in wording, including punctuation, as a change.
- **The business-associate definition changes for both rules.** From 2027-01-19, 45 CFR 160.103 excludes providers of telecommunications relay services (topic H). The Security Rule applies to business associates (164.302), so it reaches fewer entities; recorded as `chg-hipaa-security-160103-ba-2026`. No Security text or mapping changes.
- **One paragraph is held back.** The rule only redesignates 164.520(c)(2)(iv) as (c)(2)(iii), but its reprint of the paragraph cites (c)(2)(ii) where the redesignated text cites (c)(2)(iii). The eCFR codification decides.
- **8 cited paragraphs are not in today's text** (82 rows, from the HITRUST v11.4 cross-reference). The cause is not established; they do not carry, and check 22 pins them so a new one fails the build.

## When the eCFR codifies the rule

On or after 2027-01-19 run `python3 cross-mapping/engine/cfr_versions.py --verify-ecfr 2027-01-19`. It compares the computed amended text with the eCFR's codified text, paragraph by paragraph, and reports every difference. The horizon record `au-hipaa-privacy-2026` watches for that date. If the eCFR differs, its text wins: pin it as the amended version and rebuild.
