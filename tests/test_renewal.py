from app.analysis.analyzer import _renewal_bucket, renewal_for
from app.collectors.urban_renewal import name_tokens, store_records
from app.database.models import Listing, Property

RECORDS = [
    {"ShemMitcham": "זבוטינסקי 19", "Maslul": "מיסוי", "Status": "תכנית מאושרת\xa0-\xa0\xa0אחרי\xa0רישוי",
     "MisparTochnit": "410-0478206", "YachadKayam": "36", "YachadTosafti": "96",
     "KishurLatar": "https://mavat.iplan.gov.il/SV4/1/4000540481/310"},
    {"ShemMitcham": "מתחם 3 רמת ורבר", "Maslul": "", "Status": "תכנון סטטוטורי", "MisparTochnit": "410-1133313",
     "YachadKayam": "102", "YachadTosafti": "337", "KishurLatar": ""},
    {"ShemMitcham": "בר כוכבא - סטרומה - גולנדהירש", "Status": "תכנון ראשוני"},
]


def _listing(session, street=None, neighborhood=None):
    p = Property(city="פתח תקווה", street=street, neighborhood=neighborhood)
    l = Listing(property=p, source_id=1, external_id=f"x{street}{neighborhood}")
    session.add(l)
    session.flush()
    return l


def test_tokens():
    assert "בר כוכבא" in name_tokens("בר כוכבא - סטרומה - גולנדהירש")
    assert "זבוטינסקי" in name_tokens("זבוטינסקי 19")


def test_street_match_keeps_official_status(session):
    store_records(session, "פתח תקווה", RECORDS)
    ren = renewal_for(session, _listing(session, street="רחוב זבוטינסקי"))
    assert ren["match"] == "street"
    assert ren["official_status"] == "תכנית מאושרת - אחרי רישוי"
    assert _renewal_bucket(ren) == "approved"


def test_initial_planning_is_not_approved(session):
    store_records(session, "פתח תקווה", RECORDS)
    ren = renewal_for(session, _listing(session, street="סטרומה"))
    assert _renewal_bucket(ren) == "initial"


def test_area_match_and_no_match(session):
    store_records(session, "פתח תקווה", RECORDS)
    assert _renewal_bucket(renewal_for(session, _listing(session, street="הרצל", neighborhood="רמת ורבר"))) == "planning_area"
    assert _renewal_bucket(renewal_for(session, _listing(session, street="הרצל"))) == "none"
