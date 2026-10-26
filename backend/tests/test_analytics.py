import numpy as np

from lekha import anomaly, forecast, nlp, regression, simulation
from lekha.tables import AS_OF, incomplete_orders


def test_regression_metrics_and_signs(built):
    r = regression.run(built["t"])
    coefs = {c["term"]: c for c in r["ols"]["coefficients"]}
    assert coefs["dispute"]["coef"] > 4 and coefs["dispute"]["p_value"] < 0.001  # disputes slow payment (built into the generator)
    assert coefs["terms"]["coef"] > 0 and coefs["log_amount"]["coef"] > 0
    assert r["ols"]["r2"] > 0.5
    h = r["holdout"]
    assert h["ols"]["mae"] < h["baseline_train_mean"]["mae"]  # beats predicting the mean
    assert h["gbm"]["mae"] <= h["baseline_terms"]["mae"] * 1.05
    late = [b for b in r["holdout_breakdown"] if b["region"] == "APAC" and b["period"].startswith("2025-07")]
    assert late and late[0]["ols_bias"] < -2  # documented non-generalisation after the regime change


def test_forecast_backtest_reports_every_model(built):
    s = forecast.weekly_series(built["t"])["demand_units"]
    bt = forecast.backtest(s)
    assert {m["model"] for m in bt["models"]} == set(forecast.MODELS)
    assert bt["folds"] >= 3
    assert all(0 < m["wape"] < 1.5 for m in bt["models"])
    assert [m["wape"] for m in bt["models"]] == sorted(m["wape"] for m in bt["models"])
    fut = forecast.future(s, "naive", 13)
    assert len(fut) == 13 and (fut["forecast"] >= 0).all()


def test_wape_mape_math():
    y, f = np.array([100.0, 200.0]), np.array([110.0, 180.0])
    assert abs(forecast.wape(y, f) - 30 / 300) < 1e-12
    assert abs(forecast.mape(y, f) - 0.1) < 1e-12


def test_simulation_is_seeded_and_converges(built):
    t = built["t"]
    a = simulation.cash_collection(t, AS_OF, runs=800, seed=3)
    b = simulation.cash_collection(t, AS_OF, runs=800, seed=3)
    c = simulation.cash_collection(t, AS_OF, runs=800, seed=4)
    assert a["total_cash_in"] == b["total_cash_in"]
    assert a["total_cash_in"]["mean"] != c["total_cash_in"]["mean"]
    tc = a["total_cash_in"]
    assert tc["p5"] <= tc["p50"] <= tc["p95"] <= a["open_ar"]
    assert a["convergence"][-1]["runs"] == 500 or a["convergence"][-1]["runs"] <= 800
    big = simulation.cash_collection(t, AS_OF, runs=3000, seed=3)
    assert abs(big["total_cash_in"]["mean"] - tc["mean"]) < 0.02 * a["open_ar"]  # means agree across run counts
    assert big["convergence"][-1]["std_error"] < big["convergence"][0]["std_error"]


def test_safety_stock_simulation(built):
    s = simulation.safety_stock(built["t"], AS_OF, n_materials=3, runs=4000, seed=5)
    assert s == simulation.safety_stock(built["t"], AS_OF, n_materials=3, runs=4000, seed=5) and len(s["materials"]) >= 1
    for m in s["materials"]:
        assert m["safety_stock_simulated"] > 0 and m["safety_stock_analytic"] > 0
        assert 0 < m["stockout_prob_at_analytic_rop"] < 0.3
        assert m["convergence"][-1]["std_error"] < m["convergence"][0]["std_error"]


def test_nlp_metrics(built):
    r = nlp.train(built["t"]["TICKETS"])
    assert r["accuracy"] > r["majority_class_baseline_accuracy"] + 0.3
    assert r["macro_f1"] > 0.6 and len(r["per_class"]) == 7
    cm = np.array(r["confusion_matrix"]["matrix"])
    assert cm.sum() == r["n_test"] and cm.shape == (7, 7)
    assert all(0 <= c["f1"] <= 1 for c in r["per_class"])


def test_anomaly_recall(built):
    tr = built["truth"]["TRUTH_ANOMALY"]
    inv = anomaly.detect_invoices(built["t"], set(tr[tr.KIND == "invoice"].KEY), skip_orders=incomplete_orders(built["stg"], built["q"]))
    assert inv["injected_in_clean_data"] > 0
    assert inv["evaluation"]["flagged"]["recall"] >= 0.8
    assert inv["evaluation"]["flag_match"]["recall"] > inv["evaluation"]["flag_z"]["recall"]  # amount-only z-score is weak (honest)
    pay = anomaly.detect_payments(built["t"], set(tr[tr.KIND == "payment"].KEY))
    assert pay["evaluation"]["flag_rule"]["recall"] >= 0.95
