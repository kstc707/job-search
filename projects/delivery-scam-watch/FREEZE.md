# Generator A: frozen

Generator A (`scamwatch/synthetic/generator_a.py`) was written and frozen **before any real
scam data was collected or inspected**. It holds only our assumptions about what delivery-scam
domains and texts look like. `tests/test_generator_a.py` regenerates the data and compares it
with the checksums below; any later edit to generator A fails the tests. Improvements go into
generator B, which is fitted to real data.

- Frozen: 2026-11-01 in commit fc18a8b ("freeze generator A"), before any collector existed. Local Git tag `generator-a-frozen` (this environment cannot push tags; push it when the project moves to its own repository)
- Seed: 20261101

| File | Rows | Checksum |
|---|---|---|
| generator_a_domains.csv | 5,000 | generator_a_domains.csv sha256 30f22f3c26658714078803a6ab0fd94fafea9aba8a4f72c4235fc277fc1cfff6 |
| generator_a_texts.csv | 1,000 | generator_a_texts.csv sha256 25923f7542a6b6857a85fb40f3c6d34c1c04c80f843a142f55281d59c4b77fe6 |

## Actual pattern shares (as generated)

Scam domains (2,000): brand + service word 29.5% · brand as subdomain 15.6% · misspelled brand
15.0% · service word + brand 14.3% · brand + numbers 11.3% · look-alike characters 9.2% ·
random name with brand subdomain 5.1%.

Legitimate domains (3,000): innocent word containing a keyword 64.2% · legitimate use of the
name 33.9% · brand's own subdomain 1.9%. The spec asked for 25% own subdomains, but only 56
unique combinations exist in the assumed list; the shortfall is recorded here, not padded.

## Found by the tests before freezing

Misspelling one brand can produce another brand's real site: "usps" with one "s" dropped is
ups.com. The first draft labelled ups.com a scam; generator A now skips any scam candidate on a
brand's allowlist. This was fixed before the freeze, so it does not break the experiment.

## Pre-registered predictions (checked after real data is collected)

1. Real scam domains use subdomain tricks and random names more than A assumes; A over-weights
   "brand + service word".
2. A's ending mix is wrong: real data shows endings A does not list.
3. Look-alike characters are rarer in real data than A's 9%.
4. A model trained only on A catches obvious scams but misses others; its recall on real data
   is clearly lower than a model trained on real data.
5. A real-vs-synthetic classifier separates A from real scam domains easily (AUC above 0.85).
