from library.cited_publications import extract_cited_publications


def test_extracts_distinct_pubmed_pmc_and_doi_citations():
    text = """Źródła:
National Library of Medicine, https://pmc.ncbi.nlm.nih.gov/articles/PMC8431537/
National Library of Medicine, https://pubmed.ncbi.nlm.nih.gov/30485934/
National Library of Medicine, https://pubmed.ncbi.nlm.nih.gov/21188562/
Badanie DOI: 10.1000/ABC.123
"""
    rows = extract_cited_publications(text)
    assert [(r["identifier_type"], r["identifier"]) for r in rows] == [
        ("pmcid", "PMC8431537"),
        ("pmid", "30485934"),
        ("pmid", "21188562"),
        ("doi", "10.1000/abc.123"),
    ]
