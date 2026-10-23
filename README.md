# Closeout Instruction Generator

Converts Esunny `filled`/`closeP` daily exports into review-ready closeout instruction rows
for Phillip Nova (clearing member 400) and OCBC (clearing member 303). It replaces the VBA
macro in `Close out Instruction to OCBC and PN 1.7.xlsm`. It does not calculate closeouts,
match opening/closing trades, or send anything - it only prepares rows for a human to review
and submit before the desk's daily deadline.

## What it does

1. Reads `filled` and `closeP` CSV exports. Each file can be GBK (Esunny's default) or
   UTF-8 (for example after re-saving from Excel), and the encoding is detected per file.
2. Joins `closeP.平仓成交号 = filled.成交号` to pick up each closing execution's `T+1` flag
   and `成交来源` (trade source), for member-400/303 rows only.
3. Keeps only rows where the clearing member is 400 or 303 and `T+1 == 否`.
4. Routes **each raw row individually** to a broker account, using a fully configurable,
   ordered rule table (`config.yaml`).
5. Aggregates quantities by customer-account prefix + market + contract + type + member
   (+ resolved destination), so `ABC1DEFG`/`ABC2DEFG`/`ABC3DEFG`-style sub-accounts combine
   into one instruction line.
6. Converts exchange/product/month codes for the destination broker.
7. Parses Call/Put and strike out of option contracts.
8. Writes one Excel workbook with five review sheets: `PN`, `OCBC`, `summary`,
   `exceptions`, `trace`.

## For end users

Nothing needs to be installed.

1. Double-click **Closeout** (`Closeout.exe` on Windows). It can take a few seconds to open.
2. A file window asks for the **filled** file. Choose the Esunny filled export.
3. A second window asks for the **close out** file. Choose that export.
4. The program then makes the workbook by itself.

If you cancel a file window, nothing is made. Use **Browse...** to pick the files and click
**Generate instructions**. Use the same buttons to redo a run with different files.

The result is saved in the same folder as the close out file, as
`closeout_output_<date>_<time>.xlsx`. Every run makes a new file, so nothing is overwritten.
The program shows how many Phillip Nova and OCBC instructions it produced and offers to open
the file. Check the `exceptions` sheet first, then use the `PN` and `OCBC` sheets.

If the program says it could not read a file or could not load the rules, it writes nothing.
The bottom of the window shows the rules version, which is what IT will ask for.

## For IT: changing the rules

All routing/classification rules live in `config.yaml`; none of *who gets routed where* is
hardcoded in Python. The program **re-reads `config.yaml` from disk on every run**, so most
rule changes need no rebuild at all.

### Hot update (no rebuild)

Place an edited `config.yaml` in the **same folder as `Closeout.exe`**. The next
**Generate instructions** loads it, re-validates it, and shows the new `rules_version` at the
bottom of the window. If the file is inconsistent, the program lists every problem and
**generates nothing** - it never falls back to a stale or half-saved rules file.

- The external file beside the program always wins. If it is absent, the program uses the
  copy bundled inside it as the factory default.
- Command-line runs behave the same: `--config path\to\config.yaml` points at any rules file,
  and omitting it uses the external-then-bundled resolution above.
- Because the rules file is now editable outside the program, keep it in an IT-controlled
  folder. Every output workbook carries `rules_version`, so an audit can tell which rules
  produced it.

Rebuilding (below) is only needed to change the **bundled factory default**, to ship to a new
machine, or when the *engine* itself changes (a new `field`/`op`, a new broker, an output
template change) - not for ordinary account/product/routing edits.

### Releasing a new built version

A rule change is released as a new build by editing `config.yaml`, checking it, rebuilding,
and redistributing.

### 1. Edit `config.yaml`

**New subaccount at Phillip Nova or OCBC.** Add one line to `account_type_map`:

```yaml
  BNS8010: {account_type: Speculative, closeout_method: none}
```

`closeout_method` decides what happens to rows routed there: `manual_instruction` puts them
on the `PN`/`OCBC` sheet; `automatic` and `none` keep them in `summary` only.

**New client account at Phillip Nova.** Add a rule near the top of `pn_routing`, with the
other customer-prefix rules, so it is checked before the general exchange and source rules:

```yaml
  - priority: new
    label: "Customer prefix NEW"
    all_of:
      - {field: account_prefix, op: equals, value: NEW}
    destination: BNS8010
    instruction_required: false
```

If the client is special only for some products or exchanges, add conditions to `all_of`.
The existing `GLE` (UC/FE only) and `HKEX` + `SUL` rules are examples.

**New client account at OCBC with its own subaccount.** Add one line to
`ocbc_prefix_overrides`:

```yaml
  - {account_prefix: NEW, destination: "A2123N-B11", instruction_required: false}
```

A new client that uses the general accounts needs no change at all.

**New product or exchange code.** Add one line to `product_map` or `exchange_map`. Use
`null` for a broker whose code is not known yet; such trades are reported as exceptions.

Four things to keep in mind:

- The customer prefix is always the first 3 characters of `资金账号`. Put an all-digit prefix
  in quotes (`"123"`).
- The order of the rules in the file decides which one wins. `priority` is only a reference
  number.
- `instruction_required` is `true` only when the destination's `closeout_method` is
  `manual_instruction`.
- Change `rules_version` on every release.

### 2. Check it

```bash
python -m pytest tests
python main.py --filled input/filled_sample.csv --closeout "input/close out_sample.csv"
```

The program checks the whole of `config.yaml` every time it starts and refuses to run if
anything is inconsistent, listing every problem at once, for example:

```
config.yaml has 3 problem(s):
- pn_routing rule 'new' (Customer prefix NEWC): customer prefix 'NEWC' must be exactly 3 characters (the first 3 characters of 资金账号)
- pn_routing rule 'new' (Customer prefix ABC): destination 'BNS8010' is not listed in account_type_map - add the subaccount there first
- pn_routing rule 'new' (Customer prefix XYZ): instruction_required must be false because account BNS8888 has closeout_method 'none'
```

To try a draft rules file without rebuilding, pass it explicitly:
`python main.py --config draft.yaml --filled ... --closeout ...`

### 3. Build

```bash
pip install -r requirements.txt pyinstaller
pyinstaller closeout.spec
```

This produces `dist/Closeout.exe` on Windows (one self-contained file) or `dist/Closeout.app`
on macOS.

- Build on the operating system the users run. PyInstaller cannot build a Windows program
  on a Mac, or the reverse.
- Build from a clean virtual environment that has only these packages. Building from a full
  Anaconda install makes the program several times larger.
- Checked with Python 3.12, PyInstaller 6, and both pandas 2.2 and pandas 3.0. The macOS app
  and the single-file form were both built and run on macOS. The Windows build has not been
  run yet, so smoke-test the first `Closeout.exe` with the sample files.
- The built program accepts the same `--filled`, `--closeout` and `--output` arguments, which
  gives a quick check without the window.

### 4. Redistribute

Send users the new `Closeout.exe` to replace the old one. The rules version in the window
confirms which copy they are running.

## For developers: running from source

```bash
pip install -r requirements.txt
python main.py                                   # opens the window
python main.py --filled F.csv --closeout C.csv   # no window, writes output/closeout_output.xlsx
python -m pytest tests
```

On Windows, double-click `Closeout.pyw` to open only the window, with no console.

## Rule reference: what is in `config.yaml`

Nothing about *who gets routed where* is hardcoded in Python - it all lives in
`config.yaml`:

- `rules_version` - shown in the program window and printed on scripted runs.
- `electronic_sources` / `manual_sources` - which `成交来源` values count as electronic vs.
  manual. Anything not listed is `unrecognised` and becomes an `unknown_source` exception.
- `pn_routing` - an ordered list of rules for Phillip Nova. Each rule is a set of `all_of`
  conditions (`field`/`op`/`value`) plus either a `destination` + `instruction_required`, or
  `outcome: exception` + `exception_category`. **First matching rule wins** - order matters,
  exactly like the original `If / ElseIf` chain in the VBA.
- `ocbc_source_rules` - the same idea for OCBC, evaluated first.
- `ocbc_prefix_overrides` - customer-prefix rules applied **after** the source rules,
  unconditionally, and they override whatever the source rules decided (this matches the
  legacy VBA, where the prefix check is a separate block that always runs).
- `exchange_map` / `product_map` - Esunny → PN/OCBC code conversion, taken from the legacy
  workbook's `data` sheet.
- `account_type_map` - Omnibus/Speculative classification and `closeout_method`
  (`manual_instruction` / `automatic` / `none`) per broker account, kept separate from the
  routing rules themselves (see "Design decisions" below).
- `month_letters` - the Esunny month-letter sequence used for PN's `Contract_Month`.
- `input_encodings` - the encodings tried, in order, on each input CSV. The default is
  `[utf-8-sig, gbk]` and normally needs no change. Add another encoding only if a new
  export format appears.

New rules, client accounts, subaccounts and codes need no code change. Only a genuinely new
*kind* of condition (a new `field` or `op`) needs a small change in `src/routing.py`.

## How the pipeline works (and why)

The legacy macro grouped closeout rows into a single record **before** deciding which broker
sub-account each one belonged to, using whichever row happened to survive the merge to
determine the source/route for the whole group. The developer handover document flags this
as the most important bug to fix: an electronic and a manual order for the same customer and
contract could be silently combined and then routed using only one of their sources.

This implementation fixes that by reversing the order:

1. **Route first, per raw row** (`src/aggregate.py::route_eligible_rows`). Every eligible
   closeout row is resolved to a broker destination using its own trade source before
   anything is summed.
2. **Aggregate second** (`src/aggregate.py::aggregate_routed_rows`), grouping by
   `account_prefix, 市场, 合约, 合约类型, 平仓会员号` (per the new prefix-merging
   requirement) **plus the resolved destination account**. The destination is a
   deterministic function of the other grouping fields, so this never splits rows that
   would otherwise combine - it only prevents summing rows that (correctly) route
   differently, which the specified grouping key alone cannot express on its own.

Everything excluded from the final PN/OCBC sheets is either:
- **out of scope** (wrong clearing member, or `T+1 != 否`) - not an exception, just not part
  of today's batch, or
- **an exception** (`src/exceptions.py`) - unmatched/duplicate executions, blank accounts,
  unrecognised sources, missing exchange/product mappings, unparseable options, or routing
  rules with no destination - always reported, never silently dropped, or
- **"no need close-out" / "auto close"** - a valid, routed, aggregated row that simply isn't
  supposed to generate an outbound instruction. It stays in `summary` for audit with
  `exclusion_reason` set, and is excluded from `PN`/`OCBC`.

## Output sheets

- **PN** - Phillip Nova instruction rows only (`instruction_required == Yes` and every
  exchange/product/month/option field resolved). Columns match the legacy 15-column PN
  template.
- **OCBC** - the equivalent for OCBC. Populates exactly what the spec calls for
  (`*Trading Account Number`, `*Balance Type`, `*Falcon Contract Ticker`,
  `*Quantity`, `*offset with counterparty`, and `Options Type`/`Strike Price` for options).
  `Asset Type`, `Exchange MIC`, `Product Symbol Type`, `Product Symbol` and the discrete
  `Contract Month` column are left blank (as the legacy macro also left them), since the
  Falcon ticker already encodes exchange/product/month - see "Open questions" if the
  business wants those populated too.
- **summary** - every routed, aggregated group, including "no need close-out" and "auto
  close" rows, with `account_prefix`, `broker_account`, `account_type`, `closeout_method`,
  `instruction_required`, `exclusion_reason`, the raw closeP fields, the converted PN/OCBC
  fields, and `source_ids` for traceability.
- **exceptions** - one row per problem record: `unmatched`, `duplicate_execution_id`,
  `unknown_source`, `missing_exchange_mapping`, `missing_product_mapping`, `blank_account`,
  `option_parse_failed`, `no_destination`, each with a plain-English `detail`.
- **trace** - for every row that made it into `PN` or `OCBC`, which raw `平仓成交号` values
  it was built from.

## Design decisions (ambiguous points, resolved)

The spec and the attached developer handover left a handful of points to a judgment call.
Decisions taken, and why:

- **Join is scoped to member 400/303.** The handover and the legacy VBA only ever look up
  `filled` for member-400/303 rows; other member codes (e.g. `606`, `INE`) are a different
  broker's business entirely and are left untouched - not looked up, not flagged. Flagging
  every unrelated member's non-match as "unmatched" would bury genuine exceptions in noise.
- **Destination is folded into the aggregation key** (see "How the pipeline works" above) -
  a practical necessity once routing happens per-row rather than per-group, since one output
  row can only have one destination account.
- **Month-parsing failures are reported as `missing_product_mapping`.** The fixed exception
  category list has no dedicated "invalid month" category; since `Contract_Month` is part of
  the contract's identity alongside the product code, a period string that doesn't start
  with a parseable `YYMM` is reported under `missing_product_mapping` with a specific
  `detail` message rather than inventing a new category.
- **`account_type_map` entries beyond the four confirmed by name in the handover
  (`BNS8001/8002/8004/8888`, `A2123N-B1/B2/B3/B5`) are inferred, not confirmed.** Every other
  "no need close-out" destination is marked `Speculative`/`none` by the same pattern the
  handover documents for the confirmed ones. See "Open questions".
- **OCBC's `Options Type` uses the full words `Call`/`Put`**, not PN's `C`/`P`, since the
  column is named differently from PN's `Call_Put` and no same-batch OCBC options example
  was available to confirm the exact expected value.
- **The GLE-prefix legacy quirk is preserved deliberately.** In the VBA, a GLE-prefixed
  customer trading anything other than UC/FE gets no destination at all - the branch is
  entered and never falls through to the exchange/source rules. This is reproduced as an
  explicit `no_destination` exception rule (`config.yaml` priority `5b`) rather than silently
  falling through to a plausible-looking but unconfirmed destination.

## Differences from the legacy macro (expected)

Comparing this program's output against the `summary`/`ocbc` sheets in
`Closeout Logic_old.xlsm` will show differences, and they are correct, not bugs:

- **Prefix grouping** combines `ABC1DEFG`/`ABC2DEFG`/`ABC3DEFG`-style accounts that the
  legacy macro kept separate (it grouped on the full `资金账号` plus `平仓成交号`, which also
  meant it never combined anything above single closing-execution granularity).
- **Routing happens before aggregation**, so a customer/contract with mixed electronic and
  manual orders now produces two correctly-routed instruction lines instead of one line
  routed by whichever raw row happened to survive the legacy merge.
- **Nothing is silently dropped.** Unmatched executions, duplicate execution ids, blank
  accounts, unrecognised sources, and unresolvable mappings all appear in `exceptions`
  instead of vanishing or producing a blank/wrong cell.
- **Options are fully parsed** (Call/Put + strike), which the legacy macro left for staff to
  fill in by hand.
- **"No need close-out" and "auto close" rows are excluded from the outbound `PN`/`OCBC`
  sheets.** The legacy OCBC formatter copied every account starting with `A`, including rows
  explicitly labelled as not needing an instruction - this program keeps them in `summary`
  for audit but keeps them out of the file that would actually go to a broker.
- The workbook's own `summary`/`ocbc` sample sheets contain a small illustrative dataset
  (different placeholder account numbers, 19 summary rows) that is **not** the same batch as
  `filled_sample.csv`/`close out_sample.csv` - there is no row-for-row reconciliation to run
  between them; they were used to confirm the routing/mapping/month logic in isolation
  during development (see `tests/test_routing.py`, `tests/test_mapping.py`).

## Live validation by operations

Operations ran this program on a live day's exports and reconciled the output against the
legacy macro:

- **PN:** all instructions matched by account, contract, month and quantity (323 lots), apart
  from the SUM case below.
- **OCBC:** matched exactly (`A2123N-B1 / F-XSIM-PXF-202701 / 20 lots`).
- **OLY HTI Sep 2026 Put 4400, 10 lots** was correctly routed to `BNS8008` and correctly kept
  off the PN outbound sheet as "No need close-out".
- **SUM UC Dec 2026, 228 lots: a real example of routing before aggregation.** The day had
  21 lots of SUM1 electronic trades, 156 lots of SUM3 electronic trades, and 51 lots of SUM3
  manual trades (a SUM3→SUM1 position transfer booked as 人工单). The macro merged the SUM3
  records before routing and sent all 207 SUM3 lots to `BNS8002`, which put 156 electronic lots
  in the manual account. This program routes each record first: 177 lots to `BNS8001` (all
  electronic) and 51 lots to `BNS8002` (the manual transfer). The total is 228 lots both ways.
  The split between accounts is what changed, and this program's split is the intended one.

Two fixes came out of that review: input encoding is now detected automatically (see
`input_encodings`), and the `PXN` product mapping was added (see below).

## Open questions for the business

- **Phillip Nova code for `PXN`.** OCBC's code is confirmed as `PXN`: the 26 August
  instruction actually sent to OCBC was `A2123N-B1 / F-XSIM-PXN-202701`. PN's code is unknown,
  so it is left empty in `config.yaml`. A PXN closeout cleared through Phillip Nova will be
  flagged as `missing_product_mapping` until someone confirms the code. The legacy
  workbook's `ocbc code` reference sheet doesn't list PXN either, so don't rely on that sheet
  being complete.
- **`MEG` will probably be next.** The legacy workbook's saved output includes a TOR
  `F-XSIM-MEG-202610` row, but MEG has no mapping for either broker. The first MEG closeout
  will show up in `exceptions` the same way PXN did. Confirm both broker codes before then if
  possible.

- **Exact outbound account identifier for the SGX options route.** The handover confirms the
  intended allocation is "8001" but flags that the informal spelling (`BNS8001` vs. Steven's
  `BANDS8001`) should be checked against the actual broker account master before go-live.
- **`account_type_map` entries not named in the handover** (`BNS8000/8003/8889`,
  `BNS8005/6`, `BNS8007/8008`, `A2123N-B7/B8/B9/B10`) - confirm Omnibus vs. Speculative and
  closeout method for each; they are currently inferred from the documented pattern only.
- **Classification of `Bloomberg`, `Carry单`, `点价下单`, `通道费`.** These are currently
  `unrecognised` sources and are reported as `unknown_source` exceptions rather than routed.
- **OCBC `Options Type` value format** (`Call`/`Put` vs. some other Falcon-specific enum) and
  whether `Asset Type`/`Exchange MIC`/`Product Symbol Type`/`Product Symbol`/discrete
  `Contract Month` should be populated on the `OCBC` sheet in addition to the Falcon ticker.
- **Should `平仓成交号` (closing execution id) be part of the aggregation key?** Current
  decision: no - see section 3.4 of the original spec. `source_ids` on each summary/trace row
  preserves full traceability regardless.
- **Whether the destination-account split described above** (same account_prefix/market/
  contract/type/member, but two different resolved destinations because of mixed sources)
  should itself be surfaced as a distinct exception/warning rather than just being visible
  via two summary rows with the same nominal grouping fields.

## Project structure

```
closeout/
├── config.yaml              # all routing/classification rules (re-read every run; also bundled as the factory default)
├── closeout.spec            # PyInstaller build recipe
├── main.py                  # entry point: opens the window, or runs scripted with arguments
├── src/
│   ├── config.py            # load config.yaml and check every rule at startup
│   ├── gui.py               # the window: choose two files, generate
│   ├── pipeline.py          # the whole conversion, used by both the window and scripts
│   ├── io.py                # read CSVs (GBK/UTF-8 auto-detected), write output, column constants
│   ├── join.py               # closeP/filled join + T+1/成交来源 enrichment
│   ├── aggregate.py         # eligibility filter, per-row routing, prefix aggregation
│   ├── routing.py           # config-driven PN/OCBC rule engine
│   ├── mapping.py           # exchange/product/month code conversion
│   ├── options.py           # Call/Put + strike parsing
│   ├── output.py            # build PN/OCBC/summary/trace sheets
│   └── exceptions.py        # exception collection
├── tests/                   # pytest suite (see below)
├── input/                   # sample CSVs
└── output/                  # closeout_output.xlsx is written here
```

## Tests

`python -m pytest tests` runs:

- `test_config.py` - adding a new client account and a new subaccount at each broker works,
  and each likely editing mistake (unknown subaccount, wrong prefix length, unquoted digits,
  misspelled field, contradictory `instruction_required`) is caught with a clear message.
- `test_gui.py` - where the output file goes and what the finish message says.
- `test_io.py` - GBK and UTF-8 copies of the real sample files must read identically, and
  an unreadable file or a missing column gives a clear error.
- `test_join.py` - matched/unmatched/duplicate-execution-id joins, out-of-scope members.
- `test_aggregate.py` - prefix grouping (`ABC1/ABC2/ABC3` → `ABC`), mixed-source rows routing
  (and therefore aggregating) separately, blank-account handling.
- `test_routing.py` - all 14 PN priorities and every OCBC source rule/prefix override,
  loaded from the real `config.yaml` (so a config edit that breaks a rule fails a test, not
  just a production run).
- `test_mapping.py` - month/exchange/product conversion, including day-contract and option
  period strings.
- `test_options.py` - Call/Put + strike parsing, including malformed periods.
- `test_output.py` - output filtering (no-close-out / auto-close rows excluded from PN/OCBC
  but present in summary), missing-mapping and option-parse-failure exceptions.
- `test_integration.py` - end-to-end regression against the real sample CSVs, through the
  same `run()` the window uses, plus a completely empty account cell.
