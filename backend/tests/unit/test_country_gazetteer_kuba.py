"""Kuba matches country forms without matching Kubernetes or cups."""

import pytest

pytest.importorskip("unidecode")

from library.country_gazetteer import count_country_mentions, detect_countries  # noqa: E402


@pytest.mark.parametrize("text", [
    "kubernetes", "Kubernetes", "kubernetesa", "kubectl get pods", "kubelet", "kubek", "kubki",
    "kubka", "kubeconfig", "kubestronaut", "kubeadm", "kube-proxy",
    "Kubę",  # Documented loss: folded accusative kube also means the Kubernetes shorthand.
])
def test_non_country_words_do_not_count_as_kuba(text):
    counts = {c.name_pl: count for c, count in count_country_mentions(text)}
    assert counts.get("Kuba", 0) == 0


@pytest.mark.parametrize("text", [
    "Kuba", "na Kubie", "wyspy Kuby", "z Kubą", "kubańskiego", "Kubańczyków", "kubańskie cygara",
])
def test_country_forms_count_as_kuba(text):
    counts = {c.name_pl: count for c, count in count_country_mentions(text)}
    assert counts.get("Kuba", 0) >= 1


def test_repeated_kubernetes_does_not_detect_kuba():
    assert "Kuba" not in [c.name_pl for c in detect_countries("kubernetes " * 6)]
