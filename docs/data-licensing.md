# Data Licensing Audit for OpenCell

**Last Updated:** 2024  
**Purpose:** Document redistribution terms, licensing restrictions, and data handling requirements for all external data sources used in OpenCell.

---

## Executive Summary

OpenCell integrates data from multiple public databases and repositories. Each source has different licensing terms and redistribution policies. This document establishes clear guidelines for data handling to ensure legal compliance and reproducibility.

**Key Principle:** Data must be obtained programmatically at runtime when redistribution is restricted. Data with permissive licenses can be committed to the repository with proper attribution.

---

## Data Sources

### 1. KEGG (Kyoto Encyclopedia of Genes and Genomes)

**URL:** https://rest.kegg.jp/  
**License Type:** Free for academic use  
**Commercial Use:** Requires separate license  

| Property | Details |
|----------|---------|
| **Data Redistribution** | ❌ NO bulk data redistribution allowed |
| | ✅ Individual query results permitted for use in research/academic projects |
| **Repository Commit** | Fetch-script only (never commit raw data) |
| **API Access** | REST API |
| **Rate Limits** | 3 requests/second (strictly enforced) |
| **Attribution** | Must cite: "KEGG is freely available at https://www.kegg.jp/" and cite the KEGG paper: Kanehisa & Goto (2000) |

**Details:**
- KEGG provides metabolic pathway data, gene annotations, and enzyme information
- The REST API allows querying specific entries (genes, pathways, reactions, compounds)
- Direct downloads of flat files are restricted and prohibited for redistribution
- Each query result (e.g., individual pathway or gene record) can be used in research outputs
- For OpenCell, queries must be performed at runtime; results can be cached locally but not committed to repository

**Compliance Approach:**
- Implement fetch-scripts that query KEGG API on-demand
- Cache query results locally with version metadata (timestamp, query parameters)
- Store cache in `.gitignore` location or use `fetch-scripts/` directory
- Document exact KEGG API queries used for reproducibility

---

### 2. BRENDA (Braunschweig Enzyme Database)

**URL:** https://www.brenda-enzymes.org/  
**License Type:** Free for academic use (requires registration)  
**Commercial Use:** Restricted  

| Property | Details |
|----------|---------|
| **Data Redistribution** | ❌ NO redistribution allowed |
| **Repository Commit** | Fetch-script only (never commit raw data) |
| **API Access** | SOAP API (requires authentication) |
| **Rate Limits** | Not publicly specified; use reasonable polling (UNVERIFIED — check before relying on this) |
| **Attribution** | Must cite BRENDA and include link to https://www.brenda-enzymes.org/ |

**Details:**
- BRENDA contains enzyme kinetic data, substrate specificities, and organism information
- Requires free registration; access credentials must not be committed to repository
- SOAP API available but may have limitations on bulk data download
- Raw data files cannot be redistributed
- Individual enzyme records can be queried and used in research

**Compliance Approach:**
- Create fetch-scripts that authenticate and query BRENDA SOAP API
- Store BRENDA credentials in environment variables or configuration files (never in git)
- Cache query results in `.gitignore` location with metadata
- Document API endpoints and queries used for full reproducibility
- Consider reaching out to BRENDA maintainers for bulk access if needed for large-scale simulations

---

### 3. BioCyc (Biochemical Cycles Database)

**URL:** https://biocyc.org/  
**License Type:** Subscription (~$100-150/year) or institutional access  
**Free Tier:** Limited access to MetaCyc subset  

| Property | Details |
|----------|---------|
| **Data Redistribution** | ❌ Restrictive licensing; bulk redistribution not permitted |
| **Repository Commit** | Fetch-script only (for subscription access) |
| | ✅ MetaCyc subset may be redistributable (UNVERIFIED — verify license) |
| **API Access** | REST/HTTP API (requires credentials for full access) |
| **Rate Limits** | Not publicly specified; assume reasonable limits (UNVERIFIED) |
| **Attribution** | Required; specific format on BioCyc website |

**Details:**
- BioCyc provides pathway databases (EcoCyc, MetaCyc, etc.)
- Subscription provides access to proprietary pathway data
- MetaCyc is the only open-access subset within BioCyc
- Data files have restrictive licenses that prohibit redistribution
- API-based access is preferred over flat file downloads

**Compliance Approach:**
- Use fetch-scripts to query BioCyc API at runtime
- If using MetaCyc (free tier), verify open license and consider whether redistribution is permitted
- Store subscription credentials in environment variables; never commit
- Cache query results with version information and timestamp
- Document which BioCyc database version was used (e.g., MetaCyc v28.5)
- UNVERIFIED: Confirm with BioCyc team whether your intended use case permits caching

---

### 4. UniProt (Universal Protein Resource)

**URL:** https://www.uniprot.org/  
**License Type:** CC BY 4.0 (Creative Commons Attribution 4.0 International)  
**Commercial Use:** ✅ Permitted with attribution  

| Property | Details |
|----------|---------|
| **Data Redistribution** | ✅ YES, with attribution |
| **Repository Commit** | ✅ YES (with license and attribution) |
| **API Access** | REST API; flat file downloads available |
| **Rate Limits** | 1 request/second recommended; see https://www.uniprot.org/help/api_idmapping |
| **Attribution** | Cite UniProt paper and include CC BY 4.0 license notice |

**Details:**
- UniProt provides protein sequences, annotations, and functional information
- Completely open and freely accessible
- CC BY 4.0 license permits redistribution, adaptation, and commercial use with attribution
- Both FASTA and XML formats available
- Flat files can be downloaded and committed to repository if properly attributed

**Compliance Approach:**
- Can download and commit UniProt data to repository
- Include `LICENSE` file or header noting CC BY 4.0 license
- Add attribution in data files or documentation
- Document which UniProt release version was used (e.g., UniProt Release 2024_02)
- Include standard citation: "The UniProt Consortium. UniProt: the Universal Protein Knowledgebase in 2021. Nucleic Acids Res. 2021;49:D480–D489"
- Store version metadata for reproducibility

---

### 5. GenBank/NCBI (National Center for Biotechnology Information)

**URL:** https://www.ncbi.nlm.nih.gov/genbank/  
**License Type:** Public Domain (US government work)  
**Commercial Use:** ✅ Permitted  

| Property | Details |
|----------|---------|
| **Data Redistribution** | ✅ YES, unrestricted |
| **Repository Commit** | ✅ YES |
| **API Access** | NCBI E-utilities REST API; Entrez Direct CLI tool |
| **Rate Limits** | 3 requests/second without API key; 10 requests/second with API key |
| **Attribution** | Optional but recommended; cite NCBI and specific GenBank record IDs |

**Details:**
- GenBank contains DNA, RNA, and protein sequences
- Public domain—no restrictions on use or redistribution
- NCBI provides comprehensive APIs for programmatic access
- E-utilities allows querying sequences, references, and metadata
- Flat files available for download

**Compliance Approach:**
- Can download and commit GenBank data to repository
- Recommended: Include GenBank record IDs and accession numbers for traceability
- Document which GenBank release was used and timestamp of download
- Use API key to increase rate limits (sign up free at NCBI)
- Store query results with metadata for reproducibility
- Include GenBank record IDs in simulations for data provenance

---

### 6. Karr 2012 Parameters (E. coli Whole-Cell Model)

**URL:** Published on GitHub (original repository)  
**License Type:** MIT License  
**Original Publication:** Karr et al., 2012 in *Cell*  

| Property | Details |
|----------|---------|
| **Data Redistribution** | ✅ YES, under MIT license |
| **Repository Commit** | ✅ YES |
| **API Access** | GitHub repository; direct download |
| **Rate Limits** | None |
| **Attribution** | Must cite Karr et al. (2012) paper and original repository |

**Details:**
- Contains parameterization for *E. coli* whole-cell model from seminal 2012 study
- MIT license permits redistribution, modification, and commercial use
- Parameters include metabolic, proteomic, and transcriptomic data
- Originally used in systems biology research
- Source repository is actively maintained

**Compliance Approach:**
- Can commit Karr 2012 data to OpenCell repository
- Include MIT license header or reference in relevant files
- Document the exact version/commit SHA of Karr 2012 repository used
- Add citation to Karr et al., 2012 paper in README or data documentation
- Citation format: "Karr, J. R., et al. (2012). A whole-cell computational model predicts phenotype from genotype. *Cell*, 150(2), 389-401."
- Include GitHub repository link for reference

---

### 7. PySCeS Models (Python Simulator of Cellular Systems)

**URL:** https://github.com/PySCeS/pysces  
**License Type:** BSD 3-Clause License  
**Project Status:** Active (UNVERIFIED — verify current status)  

| Property | Details |
|----------|---------|
| **Data Redistribution** | ✅ YES, under BSD license |
| **Repository Commit** | ✅ YES |
| **API Access** | GitHub repository; Python module |
| **Rate Limits** | None |
| **Attribution** | Must cite PySCeS project and include BSD license |

**Details:**
- PySCeS is a Python-based systems biology modeling tool
- Contains pre-built metabolic models (MDL format)
- BSD 3-Clause license permits redistribution with attribution
- Models are community-contributed and peer-reviewed
- Actively used in computational biology research

**Compliance Approach:**
- Can commit PySCeS models to OpenCell repository
- Include BSD 3-Clause license in relevant files
- Document the exact version of PySCeS used and model names
- Cite original model publications if available
- Add reference to https://github.com/PySCeS/pysces
- Include model metadata (source, organism, last updated date)

---

## Compliance Rules

### Rule 1: Fetch-Scripts for Restricted Data
**Applies to:** KEGG, BRENDA, BioCyc (proprietary subset)

- **Never commit raw data** from these sources to the repository
- **Create fetch-scripts** that download data at runtime
- Scripts must be idempotent (safe to run multiple times)
- Cache downloaded data in `fetch-scripts/cache/` or `.gitignore`-listed directories
- Document rate limits and implement appropriate delays
- Include error handling for API failures or network issues

**Example structure:**
```
fetch-scripts/
├── fetch_kegg.py
├── fetch_brenda.py
├── fetch_biocyc.py
├── cache/
│   ├── .gitignore
│   └── (cached data goes here)
└── config/
    └── fetch_config.yml
```

### Rule 2: Permitted Redistribution with Attribution
**Applies to:** UniProt, GenBank, Karr 2012, PySCeS

- **Can commit data** to the repository (with proper documentation)
- **Must include license information** in committed files or license directory
- **Must cite sources** in README or data documentation
- Include version/release information for reproducibility
- Document download date and source URLs
- Use standard license headers in code files

**Example license header:**
```
# Data source: UniProt (https://www.uniprot.org/)
# License: CC BY 4.0
# Release: 2024_02
# Downloaded: 2024-01-15
# Citation: The UniProt Consortium. UniProt: the Universal Protein Knowledgebase...
```

### Rule 3: Content Hashing for Data Versioning
**Applies to:** All data sources

- Compute SHA-256 hash of all data artifacts (downloaded or committed)
- Store hash in metadata file or database
- Use hashes to verify data integrity and track changes
- Document hash value alongside version/timestamp
- Include hashes in simulation logs for full reproducibility

**Example metadata format:**
```json
{
  "data_source": "UniProt",
  "release": "2024_02",
  "download_date": "2024-01-15",
  "file": "uniprot_reviewed.fasta",
  "sha256": "a1b2c3d4e5f6...",
  "url": "https://www.uniprot.org/uniprotkb?compressed=true&format=fasta&query=*",
  "license": "CC BY 4.0"
}
```

### Rule 4: Database Version Documentation
**Applies to:** All data sources

- **Every simulation run** must document which version of each data source was used
- Include version information in:
  - Simulation metadata/logs
  - Output files or results documentation
  - Configuration files or setup scripts
- Use timestamps and/or release numbers for identification
- Enable reproducibility by specifying exact versions

**Example simulation metadata:**
```yaml
simulation_id: sim_20240115_001
timestamp: 2024-01-15T14:30:00Z
data_sources:
  kegg:
    version: "latest as of 2024-01-15"
    api_hash: "sha256:..."
    query_params: {"org": "eco", "dbtype": "pathway"}
  uniprot:
    release: "2024_02"
    file_hash: "sha256:..."
  genbank:
    download_date: "2024-01-15"
    file_hash: "sha256:..."
  karr_2012:
    repository_sha: "abc123def456..."
    url: "https://github.com/..."
  pysces:
    version: "0.9.11"
    models_used: ["ecoli.mdl"]
```

---

## Implementation Checklist

- [ ] **KEGG:** Create fetch script with 3 req/s rate limiting
- [ ] **BRENDA:** Set up authentication; store credentials in environment variables
- [ ] **BioCyc:** Verify license for MetaCyc vs. proprietary data; create appropriate fetch-script
- [ ] **UniProt:** Document CC BY 4.0 license in repository; include current release version
- [ ] **GenBank:** Set up NCBI API key for higher rate limits
- [ ] **Karr 2012:** Link to original repository; include MIT license header
- [ ] **PySCeS:** Document BSD license; link to project repository
- [ ] **Hashing:** Implement SHA-256 hashing for all data artifacts
- [ ] **Versioning:** Create metadata storage for database versions per simulation
- [ ] **Testing:** Verify fetch-scripts work without errors
- [ ] **Documentation:** Update README with data source information and attribution

---

## Unverified Details

The following items marked as **UNVERIFIED** require confirmation before relying on them in production:

1. **BRENDA rate limits:** Official rate limit documentation not found; verify with BRENDA team
2. **BioCyc rate limits:** Official rate limit documentation not found; verify with BioCyc support
3. **BioCyc MetaCyc license:** Verify whether MetaCyc subset redistribution is permitted under their license
4. **PySCeS project status:** Confirm project is actively maintained and appropriate for use
5. **Institutional access policies:** Check whether OpenCell's institution has BioCyc or other subscriptions

---

## References

### Official Links

- **KEGG:** https://www.kegg.jp/ | API: https://rest.kegg.jp/
- **BRENDA:** https://www.brenda-enzymes.org/
- **BioCyc:** https://biocyc.org/
- **UniProt:** https://www.uniprot.org/ | License: https://creativecommons.org/licenses/by/4.0/
- **GenBank:** https://www.ncbi.nlm.nih.gov/genbank/
- **Karr 2012:** https://github.com/ (original repository)
- **PySCeS:** https://github.com/PySCeS/pysces

### Key Citations

- Kanehisa, M., & Goto, S. (2000). KEGG: Kyoto Encyclopedia of Genes and Genomes. *Nucleic Acids Research*, 28(1), 27-30.
- Karr, J. R., et al. (2012). A whole-cell computational model predicts phenotype from genotype. *Cell*, 150(2), 389-401.
- The UniProt Consortium. (2021). UniProt: the Universal Protein Knowledgebase in 2021. *Nucleic Acids Research*, 49(D1), D480–D489.

---

## Questions & Contact

For questions about compliance, licensing, or data handling:

- **KEGG:** See https://www.kegg.jp/kegg/legal.html
- **BRENDA:** Contact support@brenda-enzymes.org
- **BioCyc:** Contact inquiries@biocyc.org
- **UniProt:** See https://www.uniprot.org/help
- **NCBI:** See https://www.ncbi.nlm.nih.gov/home/about/policies/

---

**Document Status:** Draft — Requires legal review and stakeholder approval  
**Last Reviewed:** [Update when reviewed]  
**Next Review:** [Schedule for Q2 2024]
