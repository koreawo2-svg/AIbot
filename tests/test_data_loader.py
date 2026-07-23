from autotrader.data_loader import load_close_series


def write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_auto_detect_ohlcv(tmp_path):
    path = write(tmp_path, "a.csv",
                 "Date,Open,High,Low,Close,Volume\n"
                 "2024-01-02,100,110,90,105,1000\n"
                 "2024-01-03,105,120,100,115,1200\n")
    dates, closes = load_close_series(path)
    assert closes == [105.0, 115.0]
    assert dates == ["2024-01-02", "2024-01-03"]


def test_korean_columns_and_commas(tmp_path):
    path = write(tmp_path, "k.csv",
                 "날짜,종가,거래량\n"
                 "2024-01-02,\"72,000\",1000\n"
                 "2024-01-03,\"71,500\",900\n")
    dates, closes = load_close_series(path)
    assert closes == [72000.0, 71500.0]


def test_sorts_by_date_ascending(tmp_path):
    path = write(tmp_path, "s.csv",
                 "Date,Close\n"
                 "2024-01-05,130\n"
                 "2024-01-02,100\n"
                 "2024-01-03,110\n")
    dates, closes = load_close_series(path)
    assert dates == ["2024-01-02", "2024-01-03", "2024-01-05"]
    assert closes == [100.0, 110.0, 130.0]


def test_skips_blank_and_bad_rows(tmp_path):
    path = write(tmp_path, "b.csv",
                 "Date,Close\n"
                 "2024-01-02,100\n"
                 "2024-01-03,\n"
                 "2024-01-04,N/A\n"
                 "2024-01-05,120\n")
    _, closes = load_close_series(path)
    assert closes == [100.0, 120.0]


def test_explicit_price_col(tmp_path):
    path = write(tmp_path, "e.csv",
                 "d,px\n2024-01-02,10\n2024-01-03,11\n")
    _, closes = load_close_series(path, date_col="d", price_col="px")
    assert closes == [10.0, 11.0]
