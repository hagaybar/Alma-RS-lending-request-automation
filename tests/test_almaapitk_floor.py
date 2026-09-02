"""Guards on the almaapitk floor — why `>=0.5.1` and not lower.

A version pin is a claim about behaviour, and a claim nothing checks drifts.
These tests fail if the installed almaapitk stops providing what the pin exists
for, so a floor lowered by accident is caught offline rather than in production.

Fully offline: the PubMed HTTP call is stubbed with canned XML. No network.
"""
from types import SimpleNamespace

import pytest

from almaapitk.utils import citation_metadata
from almaapitk.utils.citation_metadata import get_pubmed_metadata

from rs_requests.metadata import fetch_citation_metadata


# A PubMed record whose issue spans two months, so PubMed cannot express the
# date in <Year> and emits <MedlineDate> instead. Shape copied from the real
# response that broke production on 2026-09-02 (AlmaAPITK #214); the PMID here
# is synthetic.
_MEDLINE_DATE_ONLY_XML = b"""<?xml version="1.0"?>
<PubmedArticleSet><PubmedArticle><MedlineCitation>
  <Article>
    <Journal>
      <ISSN IssnType="Electronic">1555-824X</ISSN>
      <JournalIssue><Volume>38</Volume><Issue>1</Issue>
        <PubDate><MedlineDate>2023 Jan-Feb 01</MedlineDate></PubDate>
      </JournalIssue>
      <Title>Some Journal of Medical Quality</Title>
    </Journal>
    <ArticleTitle>An Article With An Irregular Cover Date.</ArticleTitle>
    <Pagination><MedlinePgn>23-28</MedlinePgn></Pagination>
    <AuthorList><Author><LastName>Doe</LastName><Initials>J</Initials></Author></AuthorList>
    <ArticleDate DateType="Electronic"><Year>2022</Year><Month>11</Month><Day>15</Day></ArticleDate>
  </Article>
</MedlineCitation></PubmedArticle></PubmedArticleSet>"""


@pytest.fixture
def canned_pubmed(monkeypatch):
    """Stub PubMed's efetch with the MedlineDate-only record above."""
    def _get(*args, **kwargs):
        return SimpleNamespace(content=_MEDLINE_DATE_ONLY_XML,
                               raise_for_status=lambda: None)

    monkeypatch.setattr(citation_metadata.requests, "get", _get)


def test_installed_almaapitk_recovers_the_year_from_medline_date(canned_pubmed):
    """The reason the floor is >=0.5.1 (AlmaAPITK #214).

    Below 0.5.1 the year is read only from PubDate/Year, so this record yields
    year='' — and the borrowing builder then skips the request, because Alma
    rejects an article citation with no year (401930).
    """
    assert get_pubmed_metadata("00000000")["year"] == "2023"


def test_year_reaches_this_repo_normalised_metadata(canned_pubmed):
    """The value has to survive our own normalisation layer, not just theirs."""
    meta = fetch_citation_metadata("00000000", "pmid")

    assert meta["year"] == "2023"
    assert meta["title"] == "An Article With An Irregular Cover Date."
    assert meta["journal"] == "Some Journal of Medical Quality"


def test_borrowing_builder_accepts_a_medline_date_record(canned_pubmed):
    """End to end: the trio check that skipped the production file now passes."""
    from rs_requests.borrowing import BorrowingRequestBuilder

    processor = SimpleNamespace(borrowing_config={})
    meta = fetch_citation_metadata("00000000", "pmid")

    built = BorrowingRequestBuilder(processor).build(
        {"requestor": "SHEB", "file_token": "1756800000",
         "filename": "r.tsv", "order_number": ""},
        meta,
    )

    assert built.payload["year"] == "2023"
