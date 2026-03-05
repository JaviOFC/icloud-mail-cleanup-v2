"""HDBSCAN clustering with TF-IDF labeling and content score derivation.

Clusters email embeddings into semantic groups, auto-labels them with
top TF-IDF terms, and derives content scores from cluster tier composition.
"""

from __future__ import annotations

import logging
from collections import Counter

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer

from icloud_cleanup.models import Tier

log = logging.getLogger(__name__)

# Tiers considered "keep" for composition analysis
_KEEP_TIERS = {Tier.KEEP_ACTIVE, Tier.KEEP_HISTORICAL}


def cluster_embeddings(
    embeddings: np.ndarray,
    min_cluster_size: int = 25,
    min_samples: int = 10,
) -> np.ndarray:
    """Cluster embedding vectors using HDBSCAN with cosine metric.

    Args:
        embeddings: (N, dim) array of L2-normalized embeddings.
        min_cluster_size: Minimum points to form a cluster.
        min_samples: Core distance parameter (controls noise sensitivity).

    Returns:
        (N,) integer array of cluster labels (-1 = noise).
    """
    # HDBSCAN requires min_samples <= n_samples; if too few points, all are noise
    n_samples_available = embeddings.shape[0]
    if n_samples_available < max(min_cluster_size, min_samples):
        log.info("Too few points (%d) for clustering -- all marked as noise", n_samples_available)
        return np.full(n_samples_available, -1, dtype=np.intp)

    clusterer = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="cosine",
        cluster_selection_method="eom",
    )
    labels = clusterer.fit_predict(embeddings)

    n_clusters = len(set(labels) - {-1})
    noise_count = int(np.sum(labels == -1))
    noise_frac = noise_count / len(labels) if len(labels) > 0 else 0.0

    log.info("HDBSCAN: %d clusters, %d noise points (%.1f%%)", n_clusters, noise_count, noise_frac * 100)
    if noise_frac > 0.5:
        log.warning("High noise fraction (%.1f%%) -- consider lowering min_cluster_size", noise_frac * 100)

    return labels


def label_clusters(
    texts: list[str],
    labels: np.ndarray,
    top_n: int = 5,
) -> dict[int, list[str]]:
    """Extract top TF-IDF terms per cluster as human-readable labels.

    Args:
        texts: Original texts corresponding to each embedding.
        labels: Cluster assignment for each text (-1 = noise).
        top_n: Number of top terms to extract per cluster.

    Returns:
        {cluster_id: [term1, term2, ...]} for non-noise clusters.
    """
    cluster_ids = sorted(set(labels) - {-1})
    cluster_labels: dict[int, list[str]] = {}

    for cid in cluster_ids:
        mask = labels == cid
        cluster_texts = [t for t, m in zip(texts, mask) if m]

        vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=1000,
            max_df=0.9,
        )
        try:
            tfidf = vectorizer.fit_transform(cluster_texts)
        except ValueError:
            # All terms pruned (identical docs or all terms exceed max_df)
            cluster_labels[cid] = []
            continue
        feature_names = vectorizer.get_feature_names_out()
        mean_tfidf = tfidf.mean(axis=0).A1
        top_indices = mean_tfidf.argsort()[::-1][:top_n]
        cluster_labels[cid] = [feature_names[i] for i in top_indices]

    return cluster_labels


def derive_content_scores(
    labels: np.ndarray,
    existing_tiers: list[Tier],
) -> dict[int, float]:
    """Derive content scores from cluster tier composition.

    For each cluster, count members by Phase 1 tier:
    - Keep-dominated (>60% Keep): score = 0.8
    - Trash-dominated (>60% Trash): score = 0.2
    - Mixed or small: score = 0.5
    - Noise points (-1): score = 0.5 (neutral)

    Args:
        labels: Cluster assignment per point.
        existing_tiers: Phase 1 tier for each point.

    Returns:
        {point_index: content_score} for all points.
    """
    # Pre-compute cluster composition scores
    cluster_ids = set(labels) - {-1}
    cluster_score: dict[int, float] = {}

    for cid in cluster_ids:
        mask = labels == cid
        member_tiers = [t for t, m in zip(existing_tiers, mask) if m]
        total = len(member_tiers)
        if total == 0:
            cluster_score[cid] = 0.5
            continue

        keep_count = sum(1 for t in member_tiers if t in _KEEP_TIERS)
        trash_count = sum(1 for t in member_tiers if t == Tier.TRASH)

        keep_frac = keep_count / total
        trash_frac = trash_count / total

        if keep_frac > 0.6:
            cluster_score[cid] = 0.8
        elif trash_frac > 0.6:
            cluster_score[cid] = 0.2
        else:
            cluster_score[cid] = 0.5

    # Assign scores to all points
    scores: dict[int, float] = {}
    for idx, label in enumerate(labels):
        if label == -1:
            scores[idx] = 0.5
        else:
            scores[idx] = cluster_score[label]

    return scores
