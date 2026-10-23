# Narration script (118 s)

**00:00–00:14 · slide 1**  
Hi, I'm Sai. I built a short data science project on one question: how much of FedEx Freight's lost volume is the market, and how much is FedEx?

**00:14–00:26 · slide 2**  
Among the five largest public LTL carriers, FedEx Freight's share of daily shipments fell from 43 to 36 percent between 2019 and mid-2026.

**00:26–00:47 · slide 3**  
I estimated how share responds to relative price using only FedEx's four competitors, then applied it to FedEx. Price explains the 2022–23 loss. It doesn't explain the year after Yellow's shutdown, or the year to mid-2026, when FedEx lost share while its relative price was falling.

**00:47–00:59 · slide 4**  
The relationship holds up: a placebo test, prices excluding fuel, and leaving each carrier out in turn. FedEx was never used to estimate it.

**00:59–01:12 · slide 5**  
Before FedEx Freight reports on October 29, I locked a forecast: shipments per day down about 6 percent for June to September, fingerprinted on GitHub.

**01:12–01:29 · slide 6**  
Honest result: a carrier's own in-quarter data was the only significant gain. Machine learning helped a little, but not significantly. With FedEx's daily data, the real value is at the account level, not at quarter end.

**01:29–01:43 · slide 7**  
Separately, FedEx collects about 59 percent of its published fuel surcharge. If diesel falls as EIA forecasts, fuel alone takes about 8 percent off revenue per shipment in 2027.

**01:43–01:58 · slide 8**  
The first thing I'd build with your data is account-level price response: which customers are price-sensitive, and which are leaving for other reasons. I'd value 15 minutes to walk you through it.
