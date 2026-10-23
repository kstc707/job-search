# FedEx Freight project: what I did, and why

Sai Teja Koppolu · Memphis, TN · skppolu1@memphis.edu · +1 901-343-7273 · github.com/kstc707


## What I did

After applying for the Intern–Data Scientist role at FedEx Freight, I wanted to show how I would work on a real question. I chose one I expect matters to FedEx Freight right now: from mid-2021 to mid-2026, its share of daily shipments among the five largest public LTL carriers fell 16.7 log-points, about a sixth. How much of that is price, and how much is something else?

Using only public data (SEC filings for FedEx Freight and four public competitors, FRED, the FAF5 freight database and EIA), I:

- built a quarterly carrier panel in which each number is used only after it was filed, so no model sees the future;
- estimated how shipment share responds to relative price using the four competitors only, then applied it to FedEx out of sample;
- backtested models from a naive baseline to gradient boosting over 2022–2026, testing whether differences were real;
- locked a forecast of FedEx Freight's June–September shipments per day (**−6.0%**) before the October 29 report, with its fingerprint committed to GitHub.

**What I found:** price explains the 2022–23 share loss, but not the losses in the year after Yellow's shutdown or the year to mid-2026, when FedEx's relative price was falling, which points to customer retention rather than price. A carrier's own in-quarter data cut forecast error 43%; machine learning added no significant gain, and I reported that too.

## Why I did it this way

Pricing, capacity and account decisions in freight rest on numbers that have to hold up. I wanted to show that I check data before trusting it, write my methods down first, test every model against a simple baseline, and say plainly when complexity does not help. Locking the forecast in advance keeps me honest: on October 29 it will be right or wrong in public.

## Why I'm a good fit

- **Analyst experience:** as a Data Analyst Intern with the Shelby County District Attorney General's office, I produce weekly KPI reporting for leadership and automated hand counts with Python and SQL. As a Product Analyst at TCS, I turned business questions into KPIs with product managers and engineers.
- **Related projects:** a discount and margin analysis of 10,194 retail order lines (discounts above 20% turned margin negative), and late-delivery prediction on 65,752 orders, where a two-predictor logistic regression matched gradient boosting.
- **Foundation:** MS in Data Science, University of Memphis (GPA 3.9), Weil Graduate Fellowship, Teaching Assistant for Machine Learning. Tools: SQL, Python, Power BI, Excel, PowerPoint.

## Why this role matters to me

I want to build my career where models meet operations, where a forecast or a flag changes what happens on a dock or in a sales conversation. This project reached the limit of public data: quarterly numbers for five carriers. An internship at FedEx Freight would let me bring the same discipline to account-level and lane-level data, learn from a team that makes these decisions every day, and grow that career here in Memphis, where I live.

I would welcome 15 minutes to walk through the project, or to hear which questions matter most to your team. Thank you for considering my application.

Sai Teja Koppolu · Code: github.com/kstc707/job-search · Public data only; not affiliated with FedEx.
