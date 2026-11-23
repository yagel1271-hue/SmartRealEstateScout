from app.services.text_parser import parse_listing_text


def test_full_hebrew_ad():
    t = ("דירה למכירה בפתח תקווה, רחוב אחד העם 61, מרכז העיר. 3 חדרים, 66 מ\"ר, קומה 3 מתוך 4, "
         "מעלית, חניה, ממ\"ד. מחיר 1,690,000 ₪ https://www.yad2.co.il/realestate/item/center-and-sharon/xnkus569")
    p = parse_listing_text(t)
    assert p.source_code == "yad2" and p.external_id == "xnkus569"
    assert p.asking_price == 1_690_000
    assert (p.rooms, p.sqm, p.floor, p.building_floors) == (3, 66, 3, 4)
    assert p.street == "אחד העם" and p.house_number == "61"
    assert p.city == "פתח תקווה"
    assert p.elevator and p.parking and p.mamad
    assert p.neighborhood == "מרכז העיר"


def test_million_notation_and_half_rooms():
    p = parse_listing_text("3.5 חדרים 85 מטר קומה קרקע 1.65 מיליון כפר גנים ב", default_city="פתח תקווה")
    assert p.asking_price == 1_650_000
    assert p.rooms == 3.5 and p.sqm == 85 and p.floor == 0
    assert p.neighborhood == "כפר גנים ב"
    assert p.source_code == "telegram" and p.external_id.startswith("t-")


def test_phone_number_is_not_price():
    p = parse_listing_text("לפרטים 052-1234567 או 0521234567, 4 חדרים")
    assert p.asking_price is None


def test_negative_features_and_renovation_and_rent():
    p = parse_listing_text("ללא מעלית, אין חניה, דרושה שיפוץ - דרוש שיפוץ. מושכרת ב 5,200 ₪, מחיר 1,450,000")
    assert p.elevator is False and p.parking is False
    assert p.condition == "needs_renovation"
    assert p.known_rent == 5200
    assert p.asking_price == 1_450_000


def test_madlan_link():
    p = parse_listing_text("https://www.madlan.co.il/listings/AbC123xyz 2 חדרים")
    assert p.source_code == "madlan" and p.external_id == "AbC123xyz"


def test_same_text_same_id():
    a = parse_listing_text("3 חדרים 70 מ\"ר 1,500,000")
    b = parse_listing_text("3 חדרים 70 מ\"ר 1,500,000")
    assert a.external_id == b.external_id
