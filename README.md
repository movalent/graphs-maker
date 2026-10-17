# Introduction
GraphPad Prism software is great to make nice looking graphs and do statistical analysis for non-mathematicians. Althought you end up using the same 5 functions, which are scattered all over the interface over and over again. Plus vendor lock-in is real, as prism files are proprietary and you need to own a license to go back to historical data and adjust anything. They also started to hike the pricing recently, which can make it hard to justiry having licenses for whole team because someone needs to access plotting software once per month.

Microsoft Excel is okay for basic data analysis and storage, but it's plotting capabilities are very limited and not publication-ready. 

Matplotlib has excessive customization options, can handle huge data sets with help of pandas, and is free. But it requires python knowledge, and asking LLMs to generate graph each time you need plot data is not replication-ready. 

I created this project as a test of how easy is current agentic coding and how to efficiently use agents.md. Trying to recreate all the functions I normally use in Prism with graphic interface. I do deliberately introduce functions and check for basic security like "do not connect to internet" or "do not access windos files", but apart from that this project is fully LLM coded.

It will not try to recreate all prism functionality, only what I require in my day-to-day work. That means it will not include survival curves, heatmaps, statistical tests above t-test and ANOVA.

# Install

# Features
- Bar, scatter, box, violin, line graphs
- Optional right-side Y axis for scatter plots and vertical bar graphs
- Data preview in the main window
- All customization options in one pane

# Major to-dos
- Import/export pre-configured themes for easy graph re-creation
- Curve fitting
- Confidence intervals
- Linear regression
- Statistical tests
- Statistical annotations
- Context menus for graph elements
- Missing value handling
- Editable data preview with abiliti to exclude outliers
- Value calculation from standard curve
- Batch graph generation
- Data normalization

