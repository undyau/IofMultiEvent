# CombineIOF3

Combines multiple [IOF DataStandard 3.0](https://orienteering.sport/iof/it/data-standard-3-0/) `ResultList` XML files into a single HTML series standings report.

## Requirements

Python 3.10+ (standard library only, no dependencies).

## Usage

```
python combine_iof3.py [options] [FILE.xml ...]
```

### Arguments

| Argument | Description |
|---|---|
| `FILE.xml ...` | One or more IOF 3 ResultList XML files |
| `--dir DIR` | Scan a directory for all `*.xml` files |
| `-o, --output FILE` | Output HTML file (default: `report.html`) |
| `--top3` | Only show the top 3 finishers per class (ties included) |

You can mix explicit files and `--dir`.

### Examples

```bash
# Combine two specific files
python combine_iof3.py day1.xml day2.xml

# Scan a directory
python combine_iof3.py --dir results/

# Custom output file
python combine_iof3.py --output series.html --dir results/

# Top 3 only
python combine_iof3.py --top3 --dir results/
```

## Ranking rules

- Events are ordered by date (earliest first).
- A competitor receives a total time only if every event they entered has a status of `OK` with a valid time.
- Competitors with a valid total are ranked by ascending total time. Ties share the same position.
- Competitors missing a result in any event (DNS, DNF, MP, etc.) are listed below the ranked finishers without a total.
- `--top3` removes unranked competitors and shows only positions 1–3. If multiple competitors are tied at 3rd, all are included.

## Competitor matching

Competitors are matched across events by their IOF ID when present, otherwise by first name + family name (case-insensitive). The club shown is taken from the most recently processed event.

## Result status badges

| Badge | Meaning |
|---|---|
| `DNS` | Did not start / not entered in that event |
| `DNF` | Did not finish |
| `MP` | Missing punch |
| `DSQ` | Disqualified |
| `OT` | Over time |
| `SW` | Sporting withdrawal |
| `NC` | Not competing |
| `untimed` | Status OK but no time recorded in the XML |
