# truewise-data

Clean, ready-to-use data on the economic value of US college programs — median earnings
versus a typical high-school graduate — derived from the U.S. Department of Education's
[College Scorecard](https://collegescorecard.ed.gov/). No API key, no 178-column bulk
files, no decoding suppression flags: one clean table, offline.

```bash
pip install truewise-data
```

```python
import truewise_data as tw

df = tw.load_value_check()          # one row per school x field of study x credential
df = tw.load_value_check(decided_only=True)   # drop insufficient-data rows

# Which programs leave graduates earning less than a typical HS grad?
fails = df[df.value_flag == "fails_earnings_premium"]
fails.groupby("cip_desc").size().sort_values(ascending=False).head(10)

tw.load_summary()   # national + state summary stats
tw.meta()           # dataset version, source release, license
```

## What's in it

One row per institution × 4-digit CIP code × credential level. Key columns:

| column | meaning |
|---|---|
| `earnings` | median earnings 4 years after completion (USD) |
| `earnings_threshold_state` / `_national` | typical high-school-graduate earnings benchmark |
| `earnings_premium_state` / `_national` | earnings minus the threshold (negative = below) |
| `value_flag` | `passes_earnings_premium` / `fails_earnings_premium` / `insufficient_data` |
| `share_earning_above_hs_grad` | fraction of graduates out-earning a HS grad |
| `debt_median`, `debt_to_earnings_ratio` | median debt at graduation; debt ÷ annual earnings |

Suppressed small-cohort values are `NULL`, never imputed. Earnings mirror what ED
publishes on the consumer College Scorecard site (4-year measure). Full methodology and
an accuracy audit: <https://github.com/ndranandraj/truewise>.

## License

Code MIT. **Data is CC-BY-4.0** — free to use with attribution to Truewise
(<https://truewise.dev>). Underlying figures are US federal public-domain works.

## Citation

If you use this dataset, please cite it (a DOI is minted per release via Zenodo — see the
repository releases page).
