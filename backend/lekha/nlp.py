"""Classical NLP on SYNTHETIC template-generated dispute text: TF-IDF + logistic regression,
NMF topic modelling and per-class keywords. No pretrained / gated models."""
from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from .textgen import CATEGORIES


def train(tickets: pd.DataFrame, seed: int = 42, model_path: str | None = None) -> dict:
    X_tr, X_te, y_tr, y_te = train_test_split(tickets["DESCRIPTION"], tickets["CATEGORY"], test_size=0.25, random_state=seed,
                                              stratify=tickets["CATEGORY"])
    pipe = Pipeline([("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
                     ("lr", LogisticRegression(max_iter=2000, C=5.0))]).fit(X_tr, y_tr)
    pred = pipe.predict(X_te)
    rep = classification_report(y_te, pred, labels=CATEGORIES, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_te, pred, labels=CATEGORIES)
    majority = float((y_te == y_tr.mode()[0]).mean())

    # keywords per class from LR coefficients
    names = np.array(pipe.named_steps["tfidf"].get_feature_names_out())
    coef = pipe.named_steps["lr"].coef_
    keywords = {c: names[np.argsort(coef[i])[::-1][:8]].tolist() for i, c in enumerate(pipe.named_steps["lr"].classes_)}

    # unsupervised topics (ignores labels) - do they recover the categories?
    tv = TfidfVectorizer(stop_words="english", min_df=3, max_df=0.5)
    M = tv.fit_transform(tickets["DESCRIPTION"])
    nmf = NMF(n_components=len(CATEGORIES), random_state=seed, init="nndsvda", max_iter=400).fit(M)
    vocab = np.array(tv.get_feature_names_out())
    topics = [{"topic": i, "top_terms": vocab[np.argsort(row)[::-1][:8]].tolist()} for i, row in enumerate(nmf.components_)]
    dom = nmf.transform(M).argmax(axis=1)
    purity = float(pd.crosstab(dom, tickets["CATEGORY"]).max(axis=1).sum() / len(tickets))

    if model_path:
        joblib.dump(pipe, model_path)
    return {
        "synthetic": True, "n_train": int(len(X_tr)), "n_test": int(len(X_te)), "accuracy": float(rep["accuracy"]),
        "macro_f1": float(rep["macro avg"]["f1-score"]), "majority_class_baseline_accuracy": majority,
        "per_class": [{"class": c, "precision": rep[c]["precision"], "recall": rep[c]["recall"], "f1": rep[c]["f1-score"],
                       "support": int(rep[c]["support"])} for c in CATEGORIES],
        "confusion_matrix": {"labels": CATEGORIES, "matrix": cm.tolist()},
        "keywords": keywords, "topics": topics, "topic_purity_vs_labels": purity,
        "note": "Text is template-generated with typos/filler/mixed-signal sentences and 4% label noise, so scores are optimistic "
                "compared with real free-text disputes.",
    }


def classify(model_path: str, text: str) -> dict:
    pipe = joblib.load(model_path)
    proba = pipe.predict_proba([text])[0]
    order = np.argsort(proba)[::-1]
    classes = pipe.named_steps["lr"].classes_
    return {"label": str(classes[order[0]]), "confidence": float(proba[order[0]]),
            "scores": [{"label": str(classes[i]), "probability": float(proba[i])} for i in order]}
