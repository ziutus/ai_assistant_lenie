from library import text_transcript


def test_split_text_and_time_none():
    result = text_transcript.split_text_and_time(None)
    assert result == {}


def test_split_text_and_time_empty():
    result = text_transcript.split_text_and_time('')
    assert result == {}


def test_split_text_and_time_no_match():
    result = text_transcript.split_text_and_time('random string')
    assert result == {}


def test_split_text_and_time_single_match():
    result = text_transcript.split_text_and_time('text 12:30')
    assert result == {'text': 'text', 'czas': '12:30'}


def test_split_text_and_time_single_match_2():
    result = text_transcript.split_text_and_time('12:30 - text')
    assert result == {'text': 'text', 'czas': '12:30'}


def test_split_text_and_time_single_match_3():
    result = text_transcript.split_text_and_time('12:30:00 - text')
    assert result == {'text': 'text', 'czas': '12:30:00'}
