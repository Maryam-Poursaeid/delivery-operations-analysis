# Data Dictionary — `synthetic_delivery_data_raw.csv.gz`

Synthetic last-mile delivery operations dataset in **raw source-system schema** (as exported by an operational system, before renaming/cleaning). One row = one order event. ~170,000 rows, 3 cities, 19 consecutive days (Gregorian dates `2025-06-01` to `2025-06-19`).

> The cleaning notebook (`notebooks/01_data_cleaning.ipynb`) renames these columns to analysis-friendly names (shown in the last column).

| Raw column | Type | Description | Renamed to |
|---|---|---|---|
| `Date` | string | Order date (Gregorian, ISO `YYYY-MM-DD`) | `Order_Date` |
| `OrderID` | int | Unique synthetic order identifier (5,000,000–5,800,000) | — |
| `Final_Status` | string | `Delivered`, `DeliveredWithDelay`, `Canceled`, `Returned`; ~1% missing (late status sync) | — |
| `StoreID` | int | Synthetic store/vendor identifier (~5,000 stores, power-law volume) | — |
| `City` | string | `Istanbul`, `Ankara`, `Izmir` (≈ 57 / 37 / 6 %) | — |
| `DriverID` | int | Synthetic courier identifier (100–999, 900 drivers, skewed activity) | — |
| `ConfirmationHour` | int | Hour the order was confirmed (0–23); bimodal lunch/dinner demand | `Order_Hour` |
| `CancelHour` | string | Hour of cancellation; `**` placeholder for non-canceled orders | `Cancel_Hour` |
| `FirstAssignDu` | int | Minutes until first driver assignment (zero-inflated, long tail) | — |
| `LastAssignDU` | int | Minutes until final driver assignment; redundant with `Queue_DU` (dropped in cleaning) | *(dropped)* |
| `Diff_AssignTime_Minutes` | int | Extra queue time from re-assignments (`LastAssignDU` − `FirstAssignDu`) | — |
| `Queue_DU` | int | Total dispatch queue time (minutes) | `Dispatch_Wait_Time` |
| `SourceArrival_DU` | float | Courier travel time to vendor (minutes); contains a few **negative values** (logging glitches) | `Travel_To_Vendor_Time` |
| `PickUp_DU` | float | Wait at vendor while the order is prepared (minutes); 100% missing for canceled orders | `At_Vendor_Prep_Time` |
| `DestinationArrival_DU` | float | Delivery leg to customer (minutes); contains "teleportation" rows | `Transit_To_Customer_Time` |
| `Operation_DU` | float | End-to-end cycle time = queue + travel + prep + transit; missing for canceled orders | `Total_Cycle_Time` |
| `DistanceVendorToCustomer` | int | Vendor → customer distance (meters) | `Distance_V2C` |
| `DistanceBikerToVendor` | float | Courier base → vendor distance (meters); ~31% missing | `Distance_B2V` |

## Intentional data-quality artifacts

Injected on purpose so the cleaning notebook has realistic work to do:

1. **Exact duplicate rows** (60 double-logged events).
2. **Negative `SourceArrival_DU`** (~0.15% of completed orders) — logging glitches.
3. **Teleportation rows** (~0.08%) — `DestinationArrival_DU` ≈ 1 min with 12–20 km distances (speed > 200 km/h).
4. **Impossible cycle times on `Delivered` rows** — ~0.2% close in < 2 minutes, ~0.1% stay open 3–8 hours (app-side closure bugs); the labeler flags these as `Anomaly`.
5. **Missing `Final_Status`** (~1%) — late status synchronization; reconstructed from `CancelHour` and stage-time evidence.
6. **Status-dependent missingness** — canceled orders have no prep/transit/total times.
7. **`**` placeholders** in `CancelHour` for non-canceled orders (must not be parsed as numeric).
