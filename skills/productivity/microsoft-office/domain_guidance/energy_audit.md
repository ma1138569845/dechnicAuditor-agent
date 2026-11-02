# Energy Audit Guidance

Additional guidelines for energy audit workbooks: building energy consumption, equipment inventories, energy balance, benchmarking, audit reporting, carbon accounting, and utility bill analysis.

If any specific rule conflicts with the user's request or a reference/template, prioritize the user's request first, then the reference/template, then these defaults.

## Tab structure & naming

Organize energy audit spreadsheets into clearly separated sheets:

- **Project Info** — unit name, address, audit year, data year, auditor, contact info
- **Buildings** — building list with area, type, construction year, floors, orientation
- **Equipment Inventory** — equipment name, type, quantity, rated power, operating hours, load factor
- **Utility Bills** — monthly electricity/gas/water/heat consumption and cost by utility type
- **Energy Balance** — energy input, output, and losses by end-use category
- **Benchmarking** — energy use intensity (EUI), carbon intensity, comparison against baseline or standard
- **Findings & Recommendations** — energy-saving measures, estimated savings, investment, payback
- **Calculations** — intermediate formulas and conversion factors

## Units and conversions

- Record raw data in the units provided by the source, but keep a dedicated conversion sheet or column for standardization.
- Common standard units:
  - Electricity: kWh
  - Thermal energy: kWh, MJ, or GJ
  - Power: kW
  - Area: m²
  - Energy Use Intensity (EUI): kWh/m²/year or kgce/m²/year
  - Carbon emissions: kgCO₂ or tCO₂
- Clearly label headers with units, e.g., `Electricity (kWh)`, `Area (m²)`, `EUI (kWh/m²/year)`.
- Do not mix units within the same data column.

## Calculation practices

- Use formulas, not hardcoded results, for all derived values:
  - EUI = Total energy consumption / Floor area
  - Equipment energy = Rated power × Quantity × Operating hours × Load factor
  - Cost = Consumption × Unit price
  - Simple payback = Investment / Annual savings
- Keep conversion factors in a visible, editable table (e.g., standard coal equivalent, CO₂ emission factor, electricity-to-primary energy factor).
- Guard denominators that can be zero (e.g., divide-by-area when area is missing).
- Avoid circular references.

## Data quality

- Do not alter original utility bill or measurement data. Place cleaned/processed data in a separate sheet.
- Document any assumptions, estimated values, or extrapolations in adjacent cells or a dedicated notes column.
- Flag missing or estimated data explicitly rather than leaving blank cells that could be misread as zero.

## Formatting

- One column per variable, one row per record.
- Avoid merged cells in data tables.
- Use consistent number formats:
  - Energy/cost: `0.00` or `#,##0`
  - Percentages: `0.0%`
  - EUI: `0.00`
- Use color only as supplementary emphasis; do not encode critical information solely with color.

## Verification

- Recalculate with `python scripts/recalc.py`.
- Cross-check totals: sum of end-use consumptions should reconcile with total utility consumption within a reasonable tolerance.
- Verify EUI values against typical benchmarks for the building type and climate zone.
- Review that energy-saving measures do not double-count savings.
