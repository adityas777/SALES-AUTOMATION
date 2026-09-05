from src.dedup.fuzzy_dedup import compute_dedup_hash, is_probable_duplicate, normalize_phone


def test_same_phone_different_formats_hash_identically():
    h1 = compute_dedup_hash("Rhythm Dance Academy", "Civil Lines, Durg", "+91 99999 00001")
    h2 = compute_dedup_hash("Rhythm Dance Academy Pvt Ltd", "Somewhere Else", "09999900001")
    assert h1 == h2


def test_different_phone_hashes_differ():
    h1 = compute_dedup_hash("A", "Addr", "+919999900001")
    h2 = compute_dedup_hash("A", "Addr", "+919999900002")
    assert h1 != h2


def test_normalize_phone_strips_country_code_and_leading_zero():
    assert normalize_phone("+91 99999 00001") == "9999900001"
    assert normalize_phone("09999900001") == "9999900001"


def test_fuzzy_duplicate_requires_same_city():
    assert not is_probable_duplicate("Rhythm Dance Academy", "Durg", "Rhythm Dance Academy", "Raipur")


def test_fuzzy_duplicate_detects_near_identical_names_same_city():
    assert is_probable_duplicate("Rhythm Dance Academy", "Durg", "Rhythm Dance Academy", "Durg")
