from replay_parser.fetch import code_to_filename, code_to_s3_url

def test_code_to_filename_simple():
    assert code_to_filename("ABC-DEF") == "ABC-DEF.json.gz"

def test_code_to_filename_special_chars():
    assert code_to_filename("++A4h-1QDmB") == "++A4h-1QDmB.json.gz"

def test_code_to_s3_url_encodes_plus():
    url = code_to_s3_url("a+b")
    assert "%2B" in url

def test_code_to_s3_url_encodes_at():
    url = code_to_s3_url("a@b")
    assert "%40" in url

def test_code_to_s3_url_base():
    url = code_to_s3_url("simple")
    assert url.startswith("http://saved-games-alpha.s3-website-us-east-1.amazonaws.com/")
    assert url.endswith(".json.gz")
