# 📊 Dataset Analysis Report — `bus_occupancy.csv`
### Smart Public Transport Occupancy and Emission Monitoring System
**Analyzed on:** 03 November 2026 | **File size:** ~159 KB | **Status:** ✅ Read-Only (No modifications made)

---

## 1. 📁 Dataset Overview

| Property | Value |
|---|---|
| **File** | `data/bus_occupancy.csv` |
| **Total Rows** | 2,002 |
| **Total Columns** | 14 |
| **Date Range** | 01 Oct 2026 → 28 Oct 2026 (27 days) |
| **Total Unique Buses** | 20 (KA-BUS-001 to KA-BUS-020) |
| **Total Routes** | 4 (R047, R101, R205, R330) |
| **Stops per Route** | 11 (uniform across all routes) |
| **Total Trips** | 182 |
| **Records per Trip** | Always exactly 11 (one per stop) |

---

## 2. 🏷️ Column Names and Data Types

| # | Column Name | Data Type | Simple Explanation |
|---|---|---|---|
| 1 | `trip_id` | Integer | Unique ID for each bus journey (1 to 182) |
| 2 | `timestamp` | Text (datetime string) | Date and time of the bus at each stop (e.g., `2026-10-24 10:41:00`) |
| 3 | `bus_id` | Text | Bus registration identifier (e.g., `KA-BUS-004`) |
| 4 | `route_id` | Text | Route the bus is running on (e.g., `R101`) |
| 5 | `stop_id` | Text | Specific stop on the route (e.g., `R101-S03`) |
| 6 | `boarding` | Integer | Number of passengers who **got on** at this stop |
| 7 | `alighting` | Integer | Number of passengers who **got off** at this stop |
| 8 | `current_occupancy` | Integer | Total passengers **currently inside** the bus at this stop |
| 9 | `bus_capacity` | Integer | Maximum seats the bus can hold (always **60**) |
| 10 | `previous_occupancy` | Integer | Passenger count from the **previous stop** |
| 11 | `peak_hour` | Integer | `1` = Peak time (rush hour), `0` = Off-peak time |
| 12 | `day_type` | Text | `weekday` or `weekend` |
| 13 | `fuel_consumption` | Decimal | Fuel used at this stop segment (in litres, range: 0.20–0.44) |
| 14 | `future_occupancy` | Integer | Predicted/actual passenger count at the **next stop** |

> [!NOTE]
> The `timestamp` column is stored as a **text string**, not a proper datetime type. It will need to be converted to datetime format when used in any module for time-based analysis or sorting.

---

## 3. 🔍 Missing Values and Duplicate Records

### Missing Values
| Check | Result |
|---|---|
| **Columns with missing (NaN) values** | ✅ **Zero** — No missing values in any column |
| **Total missing cells** | **0 out of 28,028** |

**What this means:** The dataset is 100% complete. No row has blank or empty fields.

### Duplicate Records
| Check | Result |
|---|---|
| **Fully duplicate rows** | ✅ **Zero** — No duplicates found |

**What this means:** Every row is unique. There is no repeated data entry.

> [!TIP]
> Even though there are no missing values now, future real-time sensor data (GPS, cameras, IR sensors) will likely have gaps. The pipeline should be built to handle missing values gracefully.

---

## 4. ✅ Occupancy Calculation Accuracy

The formula for occupancy is:

```
current_occupancy = previous_occupancy + boarding - alighting
```

| Check | Result |
|---|---|
| Rows where formula is **incorrect** | ✅ **0 out of 2,002** |
| Rows with **negative** occupancy | ✅ **0** |
| Rows where occupancy **exceeds** bus capacity (60) | ✅ **0** |
| Rows where `alighting > previous_occupancy` (impossible) | ✅ **0** |

**What this means:** The occupancy arithmetic is **100% accurate** across all 2,002 records. The boarding and alighting counts are logically consistent — no passenger count ever goes negative, and no bus is ever over-filled beyond its 60-seat capacity.

---

## 5. 🚌 Bus Capacity and Passenger Occupancy

### Capacity
- Every single bus has a **fixed capacity of 60 seats**.
- The `bus_capacity` column has only **one unique value: 60** — no variation whatsoever.

### Passenger Boarding & Alighting
| Metric | Boarding | Alighting |
|---|---|---|
| Minimum per stop | 0 | 0 |
| Maximum per stop | 13 | 5 |
| Average per stop | ~3.7 | ~1.4 |

### Occupancy Distribution (How full are buses typically?)
| Occupancy Range | Number of Stop-Records | % of Total |
|---|---|---|
| 0 – 25% full (0–15 passengers) | 921 | **46%** |
| 25 – 50% full (16–30 passengers) | 600 | **30%** |
| 50 – 75% full (31–45 passengers) | 297 | **15%** |
| 75 – 100% full (46–60 passengers) | 184 | **9%** |
| **Completely full (60/60)** | **54** | **~3%** |

> [!NOTE]
> Almost half the records (46%) show buses less than a quarter full. This suggests buses are **underutilized** during many trips, which is a key insight for route optimization.

### Peak vs Off-Peak Breakdown
| Condition | Records |
|---|---|
| Weekday + Peak Hour | 784 |
| Weekday + Off-Peak | 657 |
| Weekend + Peak Hour | 228 |
| Weekend + Off-Peak | 333 |

---

## 6. 🔮 `future_occupancy` Column Analysis

This column stores the **passenger count expected at the next stop** — making it the key column for next-stop occupancy prediction (the ML prediction target).

| Check | Result |
|---|---|
| **Range** | 0 to 60 (within valid bounds) |
| **Average value** | ~22.5 passengers |
| **Exceeds bus capacity** | ✅ **0 rows** |
| **Matches actual next-stop occupancy** | ✅ **1,820 / 1,820 non-terminal rows** (100% match) |
| **Rows where value = 0** | 3 rows (see below) |

### The 3 Rows with `future_occupancy = 0`
| trip_id | stop_id | current_occupancy | boarding | alighting | future_occupancy |
|---|---|---|---|---|---|
| 75 | R047-S02 | 1 | 1 | 0 | 0 |
| 125 | R047-S01 | 1 | 1 | 0 | 0 |
| 125 | R047-S02 | 0 | 0 | 1 | 0 |

**What this means:** These 3 records predict 0 passengers at the next stop, even when the bus currently has passengers. These are **minor anomalies** — they could represent trips that were cut short or data edge cases. Since they are only 3 out of 2,002 records (0.15%), they are **not a concern for model training** but should be flagged.

> [!IMPORTANT]
> The `future_occupancy` column is **perfectly valid** as the target label (Y variable) for the occupancy prediction ML model. It is derived from actual observed data — not guessed values.

---

## 7. 🔗 Which Project Modules Can Use This Dataset

### ✅ Module 1: Real-Time Occupancy Dashboard
**Uses:** `bus_id`, `route_id`, `stop_id`, `timestamp`, `current_occupancy`, `bus_capacity`, `boarding`, `alighting`

Shows live bus occupancy per stop on a map or dashboard. Can compute **occupancy percentage** (`current_occupancy / bus_capacity × 100`) in real time.

---

### ✅ Module 2: Passenger Occupancy Prediction (ML)
**Uses:** `previous_occupancy`, `boarding`, `alighting`, `peak_hour`, `day_type`, `current_occupancy`, `fuel_consumption`, `future_occupancy` (as the prediction target)

The `future_occupancy` column directly serves as the **label** for training a model that predicts how many passengers will be on the bus at the next stop.

---

### ✅ Module 3: Emission / Fuel Consumption Analysis
**Uses:** `fuel_consumption`, `current_occupancy`, `bus_capacity`, `route_id`, `peak_hour`, `day_type`

Can analyse how fuel usage varies with bus load. Buses with more passengers but using less fuel per passenger = more efficient. This supports emission reporting.

---

### ✅ Module 4: Route and Schedule Optimization
**Uses:** `route_id`, `stop_id`, `trip_id`, `timestamp`, `current_occupancy`, `day_type`, `peak_hour`

Identifies which routes are chronically underutilized vs overloaded. Supports decisions like adding more trips, adjusting stop order, or redeploying buses.

---

### ✅ Module 5: Alert System (Overcrowding Warning)
**Uses:** `current_occupancy`, `bus_capacity`, `future_occupancy`, `stop_id`, `route_id`

Generates alerts when `current_occupancy` or `future_occupancy` approaches or reaches `bus_capacity` (60). Passengers can be warned in advance using the predicted next-stop count.

---

### ✅ Module 6: Historical Trend Analysis & Reports
**Uses:** All columns, grouped by `day_type`, `peak_hour`, `route_id`, `bus_id`, `timestamp`

Can generate weekly/monthly reports on average load per route, busiest stops, peak time patterns, and emission trends.

---

## 8. 📋 Additional Supporting Data Needed

The current `bus_occupancy.csv` is a solid foundation, but other system modules will require their own dedicated datasets. Here is what is needed and why:

---

### 🛰️ GPS / Location Data
**Needed for:** Live bus tracking, map display, ETA calculation

| Column Needed | Purpose |
|---|---|
| `bus_id` | Link to this dataset |
| `latitude`, `longitude` | Exact bus position |
| `speed_kmph` | Speed at that moment |
| `heading_degrees` | Direction of travel |
| `gps_timestamp` | When position was recorded |
| `nearest_stop_id` | Which stop the bus is approaching |

**Why it's missing:** The current dataset uses stop-level snapshots, not continuous GPS coordinates. You cannot draw a live moving bus on a map with only stop-level data.

---

### 🗓️ Bus Schedule Data
**Needed for:** On-time performance, delay alerts, schedule adherence

| Column Needed | Purpose |
|---|---|
| `route_id` | Link to this dataset |
| `stop_id` | Which stop |
| `scheduled_arrival` | When the bus *should* arrive |
| `actual_arrival` | When it *actually* arrived |
| `delay_minutes` | How late or early |
| `trip_id` | Link to this dataset |

**Why it's missing:** The current dataset has `timestamp` (when data was recorded), but there is no "scheduled time" to compare against. You cannot compute delays without a schedule reference.

---

### 📷 Camera / Computer Vision Data
**Needed for:** Automated passenger counting validation, crowd density images

| Column Needed | Purpose |
|---|---|
| `bus_id` | Link to this dataset |
| `camera_id` | Which camera (front/rear) |
| `image_path` or `frame_id` | Reference to the captured image |
| `detected_boarding` | Passengers detected entering |
| `detected_alighting` | Passengers detected exiting |
| `confidence_score` | How sure the model is |
| `timestamp` | When the frame was captured |

**Why it's missing:** The current dataset's `boarding` and `alighting` values are assumed correct, but in a real system a camera would generate raw counts that need to be validated against the dataset.

---

### 🔴 IR (Infrared) Sensor Data
**Needed for:** Low-cost passenger counting at stops or bus doors

| Column Needed | Purpose |
|---|---|
| `sensor_id` | Which sensor device |
| `bus_id` | Link to this dataset |
| `stop_id` | At which stop |
| `timestamp` | When triggered |
| `direction` | `IN` or `OUT` (boarding vs alighting) |
| `raw_count` | Number of pulses/detections |
| `sensor_status` | `OK`, `FAULT`, `OFFLINE` |

**Why it's missing:** IR sensors produce raw pulse data that needs to be aggregated into boarding/alighting counts. This raw feed is separate from the already-processed counts in this dataset.

---

### 🌫️ Emission / Air Quality Data
**Needed for:** CO₂ and pollutant monitoring, emission compliance reporting

| Column Needed | Purpose |
|---|---|
| `bus_id` | Link to this dataset |
| `timestamp` | When reading was taken |
| `co2_ppm` | Carbon dioxide level |
| `nox_ppm` | Nitrogen oxide level |
| `pm2_5` | Particulate matter (fine dust) |
| `engine_rpm` | Engine load |
| `exhaust_temp_c` | Exhaust temperature |
| `fuel_type` | Diesel, CNG, Electric, Hybrid |
| `odometer_km` | Total distance travelled |

**Why it's missing:** The current `fuel_consumption` column (0.20–0.44 L per stop) is a **proxy** for emissions, not a real emission reading. Actual CO₂/NOx sensors produce separate, more detailed readings.

---

## 9. 🔑 Summary — Key Findings

| # | Finding | Status |
|---|---|---|
| 1 | Dataset has **2,002 rows and 14 columns** | ✅ Clean |
| 2 | **Zero missing values** across all columns | ✅ Excellent |
| 3 | **Zero duplicate records** | ✅ Excellent |
| 4 | Occupancy formula is **100% accurate** in all rows | ✅ Perfect |
| 5 | Bus capacity is uniformly **60 seats** (no variation) | ℹ️ Fixed value |
| 6 | **46% of records** show buses less than 25% full | ⚠️ Underutilization insight |
| 7 | Only **54 records** (3%) show fully loaded buses | ℹ️ Rare event |
| 8 | `future_occupancy` is **100% accurate** for all non-terminal stops | ✅ Valid ML target |
| 9 | **3 anomalous rows** with `future_occupancy = 0` (0.15% of data) | ⚠️ Minor edge case |
| 10 | `timestamp` is stored as **text**, not datetime | ⚠️ Needs conversion in code |
| 11 | Dataset covers **4 routes**, **20 buses**, **182 trips**, **27 days** | ✅ Good coverage |
| 12 | **5 additional datasets** are needed for full system functionality | 🔧 To be created later |

---

## 10. ✅ Approval Checkpoint

> [!IMPORTANT]
> **This report is complete. The original `bus_occupancy.csv` has NOT been modified.**
>
> **Awaiting your approval before proceeding to the next step.**
>
> Suggested next steps (pending your approval):
> - Create supporting datasets (GPS, Schedule, Camera, IR Sensor, Emission)
> - Begin data preprocessing and feature engineering pipeline
> - Train the occupancy prediction ML model

---
*Report generated by Antigravity AI | Smart Public Transport and Emission Monitoring System*

