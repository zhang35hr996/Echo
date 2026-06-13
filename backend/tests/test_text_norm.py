from echo.text_norm import normalize_title, normalize_artist


def test_strips_feat_and_brackets_and_lowercases():
    assert normalize_title("Yesterday (Remastered 2009) [Official Video]") == "yesterday"
    assert normalize_title("Shape of You feat. XYZ") == "shape of you"


def test_collapses_whitespace_and_symbols():
    assert normalize_title("  Hello   World!! ") == "hello world"


def test_artist_drops_topic_suffix():
    assert normalize_artist("The Beatles - Topic") == "the beatles"
    assert normalize_artist("Adele ") == "adele"
