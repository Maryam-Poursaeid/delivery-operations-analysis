"""
Synthetic Delivery Operations Data Generator
============================================
Generates a fully synthetic last-mile delivery operations dataset that mimics
the statistical behavior of a real on-demand delivery platform, WITHOUT using
or exposing any real records. All IDs, dates, and values are artificial.

Design goals:
- Realistic bimodal hourly demand (lunch & dinner peaks)
- Three cities with different volume shares and reliability profiles
- Status mix: Delivered / DeliveredWithDelay / Canceled / Returned
- Internally consistent time components:
    Dispatch_Wait_Time = FirstAssignDu + Diff_AssignTime_Minutes
    Total_Cycle_Time   = Dispatch_Wait + Travel_To_Vendor + Prep + Transit
- Realistic messiness injected on purpose (for the cleaning notebook):
    * missing values with status-dependent patterns
    * a small share of negative / extreme durations (logging glitches)
    * 'teleportation' rows (impossibly high speed)
    * '**' placeholder in Cancel_Hour for non-canceled orders
- One engineered 'anomaly day' with a demand dip (systemic incident)

Usage:
    python generate_synthetic_data.py
Outputs:
    synthetic_delivery_data_raw.csv
"""

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)
N_ORDERS = 170_000

# ---------------------------------------------------------------- calendar --
# 19 consecutive days (Gregorian, ISO format)
DAYS = [f"2025-06-{d:02d}" for d in range(1, 20)]
# Relative daily demand weights; day 3 is an engineered systemic-incident dip,
# day 11 is a promotional spike.
DAY_WEIGHTS = np.array([10.2, 9.1, 6.3, 10.4, 9.0, 8.0, 9.6, 10.3, 9.9, 8.4,
                        11.4, 7.5, 8.9, 9.7, 7.7, 8.7, 9.3, 9.8, 8.6])
DAY_WEIGHTS = DAY_WEIGHTS / DAY_WEIGHTS.sum()

# ------------------------------------------------------------------- hours --
HOURS = np.array([0, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23])
HOUR_WEIGHTS = np.array([0.3, 0.6, 2.7, 3.3, 3.7, 6.1, 15.5, 22.9, 18.3, 11.1,
                         7.3, 6.6, 8.0, 12.7, 19.3, 18.2, 11.3, 5.0])
HOUR_WEIGHTS = HOUR_WEIGHTS / HOUR_WEIGHTS.sum()

# ------------------------------------------------------------------ cities --
CITIES = ["Istanbul", "Ankara", "Izmir"]
CITY_WEIGHTS = [0.57, 0.37, 0.06]
# Per-city status probabilities: [Delivered, DeliveredWithDelay, Canceled, Returned]
CITY_STATUS_P = {
    "Istanbul": [0.645, 0.344, 0.0085, 0.0025],
    "Ankara":   [0.688, 0.308, 0.0035, 0.0005],
    "Izmir":    [0.588, 0.401, 0.0095, 0.0015],
}
STATUSES = ["Delivered", "DeliveredWithDelay", "Canceled", "Returned"]

# --------------------------------------------------------------------- IDs --
N_STORES = 5_000
N_DRIVERS = 900


def lognormal_minutes(median: float, sigma: float, size: int) -> np.ndarray:
    """Sample integer-ish minutes from a lognormal with a given median."""
    return RNG.lognormal(mean=np.log(max(median, 0.1)), sigma=sigma, size=size)


def main() -> None:
    n = N_ORDERS

    # --- keys -----------------------------------------------------------
    order_date = RNG.choice(DAYS, size=n, p=DAY_WEIGHTS)
    order_hour = RNG.choice(HOURS, size=n, p=HOUR_WEIGHTS)
    city = RNG.choice(CITIES, size=n, p=CITY_WEIGHTS)

    # Store popularity follows a power law (a few high-volume dark stores).
    store_ids_pool = RNG.choice(np.arange(1_000, 90_000), size=N_STORES, replace=False)
    store_pop = RNG.pareto(1.2, N_STORES) + 1
    store_pop = store_pop / store_pop.sum()
    store_id = RNG.choice(store_ids_pool, size=n, p=store_pop)

    # Driver activity is uneven; a small 'elite' pool absorbs more orders.
    driver_ids_pool = np.arange(100, 100 + N_DRIVERS)
    driver_act = RNG.gamma(6.0, 1.0, N_DRIVERS)
    driver_act = driver_act / driver_act.sum()
    driver_id = RNG.choice(driver_ids_pool, size=n, p=driver_act)

    # Unique synthetic order ids (range deliberately different from any real system)
    order_id = RNG.choice(np.arange(5_000_000, 5_800_000), size=n, replace=False)

    # --- status ----------------------------------------------------------
    status = np.empty(n, dtype=object)
    for c in CITIES:
        m = city == c
        status[m] = RNG.choice(STATUSES, size=m.sum(), p=CITY_STATUS_P[c])

    delivered = status == "Delivered"
    delayed = status == "DeliveredWithDelay"
    canceled = status == "Canceled"
    returned = status == "Returned"
    completed = delivered | delayed | returned

    # --- assignment / dispatch queue --------------------------------------
    # FirstAssignDu: time until first driver assignment (many instant, long tail)
    first_assign = np.where(
        RNG.random(n) < 0.45,
        RNG.integers(0, 3, n),
        np.round(lognormal_minutes(3.0, 1.1, n)),
    ).astype(float)

    # Diff_AssignTime: extra queue time from re-assignments (zero-inflated)
    diff_assign = np.where(
        RNG.random(n) < 0.60,
        0,
        np.round(lognormal_minutes(5.0, 1.1, n)),
    ).astype(float)
    # Evening capacity crunch in the largest market: queue inflation between 20-22
    crunch = (city == "Istanbul") & np.isin(order_hour, [20, 21, 22])
    diff_assign[crunch] = np.round(diff_assign[crunch] * 1.4 + 2)
    # Delayed orders systematically waited longer in the queue
    diff_assign[delayed] = np.round(diff_assign[delayed] * 1.3 + 2)

    dispatch_wait = first_assign + diff_assign

    # --- travel & service times -------------------------------------------
    travel_to_vendor = np.round(lognormal_minutes(6.0, 0.65, n))
    prep_time = np.where(
        RNG.random(n) < 0.40,
        RNG.integers(0, 2, n),
        np.round(lognormal_minutes(3.0, 0.9, n)),
    ).astype(float)
    transit = np.round(lognormal_minutes(7.5, 0.62, n))
    transit[delayed] = np.round(transit[delayed] * 1.25)
    transit[returned] = np.round(transit[returned] * 2.2)

    total_cycle = dispatch_wait + travel_to_vendor + prep_time + transit

    # --- distances (meters) ------------------------------------------------
    dist_v2c = np.round(lognormal_minutes(2800, 0.62, n)).astype(float)
    dist_b2v = np.round(lognormal_minutes(2200, 0.60, n)).astype(float)

    # --- cancel hour ---------------------------------------------------------
    cancel_hour = np.full(n, "**", dtype=object)
    ch = np.minimum(order_hour[canceled] + RNG.integers(0, 2, canceled.sum()), 23)
    cancel_hour[canceled] = [f"{int(h):02d}" for h in ch]

    # --- assemble (RAW source-system schema, pre-renaming) --------------------
    # Column names intentionally match a realistic raw operational export;
    # the preprocessing notebook renames them to analysis-friendly names.
    df = pd.DataFrame({
        "Date": order_date,
        "OrderID": order_id,
        "Final_Status": status.copy(),
        "StoreID": store_id,
        "City": city,
        "DriverID": driver_id,
        "ConfirmationHour": order_hour,
        "CancelHour": cancel_hour,
        "FirstAssignDu": first_assign.astype(int),
        "LastAssignDU": dispatch_wait.astype(int),
        "Diff_AssignTime_Minutes": diff_assign.astype(int),
        "Queue_DU": dispatch_wait.astype(int),
        "SourceArrival_DU": travel_to_vendor,
        "PickUp_DU": prep_time,
        "DestinationArrival_DU": transit,
        "Operation_DU": total_cycle,
        "DistanceVendorToCustomer": dist_v2c.astype(int),
        "DistanceBikerToVendor": dist_b2v,
    })

    # --- inject realistic messiness (for the cleaning notebook) --------------
    # 1) Canceled orders never reach the vendor/customer legs
    df.loc[canceled, ["PickUp_DU", "DestinationArrival_DU", "Operation_DU"]] = np.nan
    partial = canceled & (RNG.random(n) < 0.28)
    df.loc[partial, "SourceArrival_DU"] = np.nan

    # 2) Biker-to-vendor distance missing when pickup leg wasn't logged (~30%)
    b2v_missing = completed & (RNG.random(n) < 0.31)
    df.loc[b2v_missing, "DistanceBikerToVendor"] = np.nan

    # 3) Final_Status missing for ~1% of rows (late status sync)
    late_sync = RNG.random(n) < 0.010
    df.loc[late_sync, "Final_Status"] = np.nan

    # 4) Sensor/logging glitches: small share of negative travel times
    glitch = completed & (RNG.random(n) < 0.0015)
    df.loc[glitch, "SourceArrival_DU"] = -RNG.integers(5, 130, glitch.sum()).astype(float)

    # 5) 'Teleportation' rows: absurd speed (distance high, transit ~1 min)
    teleport = completed & (RNG.random(n) < 0.0008)
    df.loc[teleport, "DestinationArrival_DU"] = 1.0
    df.loc[teleport, "DistanceVendorToCustomer"] = RNG.integers(12_000, 20_000, teleport.sum())

    # 6) Random missing values in prep time (~0.5%)
    prep_missing = completed & (RNG.random(n) < 0.005)
    df.loc[prep_missing, "PickUp_DU"] = np.nan

    # 7) Impossible cycle times on 'Delivered' rows (app-side closure bugs):
    #    ~0.2% close in under 2 minutes, ~0.1% stay open for 3-8 hours.
    too_fast = delivered & (RNG.random(n) < 0.002)
    df.loc[too_fast, "Operation_DU"] = RNG.integers(0, 2, too_fast.sum()).astype(float)
    too_slow = delivered & (RNG.random(n) < 0.001)
    df.loc[too_slow, "Operation_DU"] = RNG.integers(181, 480, too_slow.sum()).astype(float)

    # 8) A small batch of exact duplicate rows (double-logged events)
    dup_idx = RNG.choice(df.index, size=60, replace=False)
    df = pd.concat([df, df.loc[dup_idx]], ignore_index=True)
    df = df.sample(frac=1.0, random_state=7).reset_index(drop=True)

    df.to_csv("synthetic_delivery_data_raw.csv", index=False)
    print(f"Wrote synthetic_delivery_data_raw.csv with {len(df):,} rows")
    print(df["Final_Status"].value_counts(dropna=False))


if __name__ == "__main__":
    main()
