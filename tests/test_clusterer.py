"""Tests for HDBSCAN clustering, TF-IDF labeling, and content score derivation."""

from __future__ import annotations

import numpy as np
import pytest

from icloud_cleanup.models import Tier


# --- Helper: create well-separated clusters in low dimensions ---

def make_clustered_embeddings(
    n_per_cluster: int = 50,
    n_clusters: int = 3,
    dim: int = 10,
    separation: float = 10.0,
    seed: int = 42,
) -> np.ndarray:
    """Create synthetic embeddings with well-separated clusters.

    Returns (n_per_cluster * n_clusters, dim) array.
    """
    rng = np.random.RandomState(seed)
    clusters = []
    for i in range(n_clusters):
        center = np.zeros(dim)
        center[i % dim] = separation * (i + 1)
        points = rng.randn(n_per_cluster, dim) * 0.5 + center
        # L2-normalize for cosine metric
        norms = np.linalg.norm(points, axis=1, keepdims=True)
        points = points / norms
        clusters.append(points)
    return np.vstack(clusters)


# --- Tests for cluster_embeddings ---

class TestClusterEmbeddings:
    """Tests for HDBSCAN clustering function."""

    def test_returns_array_same_length_as_input(self):
        from icloud_cleanup.clusterer import cluster_embeddings

        embeddings = make_clustered_embeddings(n_per_cluster=60, n_clusters=3)
        labels = cluster_embeddings(embeddings, min_cluster_size=20, min_samples=5)

        assert isinstance(labels, np.ndarray)
        assert len(labels) == len(embeddings)

    def test_labels_contain_noise_and_cluster_ids(self):
        from icloud_cleanup.clusterer import cluster_embeddings

        embeddings = make_clustered_embeddings(n_per_cluster=60, n_clusters=3)
        labels = cluster_embeddings(embeddings, min_cluster_size=20, min_samples=5)

        unique_labels = set(labels)
        # Should have at least 2 distinct cluster IDs (excluding noise)
        cluster_ids = unique_labels - {-1}
        assert len(cluster_ids) >= 2

    def test_handles_very_few_points(self):
        """When there are fewer points than min_cluster_size, all become noise."""
        from icloud_cleanup.clusterer import cluster_embeddings

        rng = np.random.RandomState(42)
        small = rng.randn(5, 10).astype(np.float32)
        norms = np.linalg.norm(small, axis=1, keepdims=True)
        small = small / norms
        labels = cluster_embeddings(small, min_cluster_size=100, min_samples=20)

        assert len(labels) == 5
        # All should be noise since we have 5 points but min_cluster_size=100
        assert all(l == -1 for l in labels)

    def test_labels_are_integers(self):
        from icloud_cleanup.clusterer import cluster_embeddings

        embeddings = make_clustered_embeddings(n_per_cluster=60, n_clusters=3)
        labels = cluster_embeddings(embeddings, min_cluster_size=20, min_samples=5)

        assert labels.dtype in (np.int32, np.int64, np.intp)


# --- Tests for label_clusters ---

class TestLabelClusters:
    """Tests for TF-IDF cluster labeling."""

    def test_returns_dict_mapping_cluster_id_to_terms(self):
        from icloud_cleanup.clusterer import label_clusters

        texts = [
            "shipping tracking delivery fedex",
            "shipping order delivery package",
            "shipping fedex tracking update",
            "meeting calendar invite schedule",
            "meeting agenda conference call",
            "meeting schedule zoom invite",
        ]
        labels = np.array([0, 0, 0, 1, 1, 1])

        result = label_clusters(texts, labels, top_n=3)

        assert isinstance(result, dict)
        assert 0 in result
        assert 1 in result
        assert len(result[0]) == 3
        assert len(result[1]) == 3

    def test_skips_noise_cluster(self):
        from icloud_cleanup.clusterer import label_clusters

        texts = ["noise email", "shipping tracking", "shipping delivery"]
        labels = np.array([-1, 0, 0])

        result = label_clusters(texts, labels, top_n=3)

        assert -1 not in result
        assert 0 in result

    def test_single_cluster_edge_case(self):
        from icloud_cleanup.clusterer import label_clusters

        texts = [
            "python programming code",
            "python code development",
            "programming python script",
        ]
        labels = np.array([0, 0, 0])

        result = label_clusters(texts, labels, top_n=3)

        assert 0 in result
        assert len(result) == 1
        assert "python" in result[0]

    def test_distinct_vocabulary_per_cluster(self):
        from icloud_cleanup.clusterer import label_clusters

        texts = [
            "shipping delivery package fedex tracking",
            "shipping delivery order fedex package",
            "shipping tracking delivery package fedex",
            "invoice payment receipt billing total",
            "invoice billing payment receipt due",
            "payment invoice billing receipt total",
        ]
        labels = np.array([0, 0, 0, 1, 1, 1])

        result = label_clusters(texts, labels, top_n=5)

        cluster_0_terms = set(result[0])
        cluster_1_terms = set(result[1])
        # Clusters should have mostly different vocabulary
        assert "shipping" in cluster_0_terms or "delivery" in cluster_0_terms
        assert "invoice" in cluster_1_terms or "payment" in cluster_1_terms

    def test_returns_up_to_top_n_terms(self):
        from icloud_cleanup.clusterer import label_clusters

        texts = ["word"] * 5
        labels = np.array([0, 0, 0, 0, 0])

        result = label_clusters(texts, labels, top_n=10)

        # Only 1 unique term available, so result has <= top_n terms
        assert len(result[0]) <= 10


# --- Tests for derive_content_scores ---

class TestDeriveContentScores:
    """Tests for content score derivation from cluster tier composition."""

    def test_trash_dominated_cluster_gets_low_score(self):
        from icloud_cleanup.clusterer import derive_content_scores

        labels = np.array([0, 0, 0, 0, 0])
        tiers = [Tier.TRASH, Tier.TRASH, Tier.TRASH, Tier.TRASH, Tier.REVIEW]

        scores = derive_content_scores(labels, tiers)

        for idx in range(5):
            assert scores[idx] == pytest.approx(0.2)

    def test_keep_dominated_cluster_gets_high_score(self):
        from icloud_cleanup.clusterer import derive_content_scores

        labels = np.array([0, 0, 0, 0, 0])
        tiers = [
            Tier.KEEP_ACTIVE, Tier.KEEP_ACTIVE, Tier.KEEP_ACTIVE,
            Tier.KEEP_HISTORICAL, Tier.REVIEW,
        ]

        scores = derive_content_scores(labels, tiers)

        for idx in range(5):
            assert scores[idx] == pytest.approx(0.8)

    def test_mixed_cluster_gets_mid_score(self):
        from icloud_cleanup.clusterer import derive_content_scores

        labels = np.array([0, 0, 0, 0])
        tiers = [Tier.TRASH, Tier.KEEP_ACTIVE, Tier.REVIEW, Tier.REVIEW]

        scores = derive_content_scores(labels, tiers)

        for idx in range(4):
            assert scores[idx] == pytest.approx(0.5)

    def test_noise_points_get_mid_score(self):
        from icloud_cleanup.clusterer import derive_content_scores

        labels = np.array([-1, -1, 0, 0, 0])
        tiers = [
            Tier.REVIEW, Tier.TRASH,
            Tier.KEEP_ACTIVE, Tier.KEEP_ACTIVE, Tier.KEEP_ACTIVE,
        ]

        scores = derive_content_scores(labels, tiers)

        # Noise points should be 0.5 regardless of their tier
        assert scores[0] == pytest.approx(0.5)
        assert scores[1] == pytest.approx(0.5)
        # Cluster 0 points are keep-dominated
        assert scores[2] == pytest.approx(0.8)

    def test_returns_dict_mapping_index_to_float(self):
        from icloud_cleanup.clusterer import derive_content_scores

        labels = np.array([0, 1, -1])
        tiers = [Tier.TRASH, Tier.KEEP_ACTIVE, Tier.REVIEW]

        scores = derive_content_scores(labels, tiers)

        assert isinstance(scores, dict)
        assert len(scores) == 3
        for idx, score in scores.items():
            assert isinstance(idx, int)
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0

    def test_all_noise_returns_all_mid_scores(self):
        from icloud_cleanup.clusterer import derive_content_scores

        labels = np.array([-1, -1, -1])
        tiers = [Tier.TRASH, Tier.KEEP_ACTIVE, Tier.REVIEW]

        scores = derive_content_scores(labels, tiers)

        for score in scores.values():
            assert score == pytest.approx(0.5)

    def test_multiple_clusters_with_different_compositions(self):
        from icloud_cleanup.clusterer import derive_content_scores

        labels = np.array([0, 0, 0, 1, 1, 1])
        tiers = [
            # Cluster 0: all trash
            Tier.TRASH, Tier.TRASH, Tier.TRASH,
            # Cluster 1: all keep
            Tier.KEEP_ACTIVE, Tier.KEEP_HISTORICAL, Tier.KEEP_ACTIVE,
        ]

        scores = derive_content_scores(labels, tiers)

        # Cluster 0 members should get low score
        assert scores[0] == pytest.approx(0.2)
        assert scores[1] == pytest.approx(0.2)
        assert scores[2] == pytest.approx(0.2)
        # Cluster 1 members should get high score
        assert scores[3] == pytest.approx(0.8)
        assert scores[4] == pytest.approx(0.8)
        assert scores[5] == pytest.approx(0.8)
