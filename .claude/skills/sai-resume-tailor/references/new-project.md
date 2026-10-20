# Planned project from a job description

For a project slot that no built project fills. The project has to be one Sai can build in about two weeks if the
posting calls him, and its resume lines have to survive "walk me through this project".

1. **Reuse first.** Open the To build view. A Planned row whose Domains and Stack cover this posting's map rows is
   reused: append `<Company> - <Role>` to its Used on. Done when you have either a reusable row or a reason none fits.
2. **Design** around the posting's core problem:
   - **Problem:** the core problem, scaled to a portfolio project.
   - **Data:** a public dataset that exists today, named and linked (Kaggle, UCI, data.gov, a public API). Look it
     up; a dataset you cannot link is not chosen.
   - **Method and stack:** the posting's required tools first, then preferred ones; the techniques that answer the
     core problem.
   - **Deliverables:** what exists at the end (repo, dashboard, API, report).
   - **Evaluation:** the metric and the baseline it is judged against.
   Done when every section names something specific enough to start on tomorrow.
3. **Create the row** in Projects (`collection://a3760833-61fa-4e1c-bc57-1ed0327c5d85`): Project, Status `Planned`,
   Family, Domains, Stack, One-liner, Created for `<Company> - <Role>`, Source posting, Priority `On a sent resume`,
   Last used today, Used on `<Company> - <Role>`. Page body, in this order:
   - Problem · Data (with link) · Method · Deliverables · Evaluation
   - **Build plan:** 5-8 steps with hour estimates, about 30 hours in total
   - **Talking points:** three design decisions and why each was made
   - **Resume lines:** the bullets used, so the build can make them true
   Done when the row shows in To build.
4. **Write the resume lines** under the content rules in `SKILL.md`: finished-work voice, the result clause names the
   metric with no number, no repo link.

When Sai gets a call for that posting, he sets Priority to `Interview scheduled` and builds from the plan. Once it is
built: Status `Built`, real numbers under a "Verified numbers" heading, Repo filled in.
