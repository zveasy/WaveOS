from waveos.utils import counters, histograms


def test_metrics_singleton_instances() -> None:
    counters_first = counters()
    counters_second = counters()
    histograms_first = histograms()
    histograms_second = histograms()

    assert counters_first is counters_second
    assert histograms_first is histograms_second
