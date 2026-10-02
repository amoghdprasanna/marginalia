from marginalia.cursor import RestTracker


def test_rest_updates_only_after_holding_still():
    t = RestTracker((0, 0), now=0.0)
    t.feed(0.1, (300, 300))
    assert t.rest == (0, 0)  # just arrived
    t.feed(0.3, (305, 302))  # small jitter keeps the anchor
    assert t.rest == (0, 0)
    t.feed(0.6, (304, 301))
    assert t.rest == (304, 301)


def test_passing_over_content_does_not_count_as_rest():
    t = RestTracker((0, 0), now=0.0)
    for i in range(1, 20):
        t.feed(i * 0.1, (i * 40, 0))  # steady movement
    assert t.rest == (0, 0)
