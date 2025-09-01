=====================
=   knowledge tree  = 
=====================

Why do it?
* Help understand concepts better
* Personal recommendation system
* Make a map of what I know 
* Similar to a tech tree, you unlock new nodes over time 

What should it do?
* Find relationships between books and ideas
* Build a timeseries of events 
* Recommend and compare to wikipages
* LLM legible context for my queries 

Classes
* Book
* Highlight
* Entity 

Predicates
* inBook
* mentionsEntity

Setup
- pip3 install spacy
- python3 -m spacy download en_core_web_sm

Graph
* JSON-LD (https://www.w3.org/TR/json-ld/)
* Context JSON-LD tells the processor how to expand short term into full IRIs and how to interpret them

USAGE
> python3 ./generator.py
> python3 ./report.py read_graph.jsonld --plot kg:entity/america
