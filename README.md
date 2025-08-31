=====================
= My knowledge tree = 
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

Entities
* Book
* Author
* Highlight
* Annotation
* Entity (person,org,place)
* Concept 

Graph type 
* JSON-LD (https://www.w3.org/TR/json-ld/)

JSON-LD Quickstart
* Context header in JSON-LD tells the processor how to expand short tesm into full IRIs and how to interpret them

"Book": "https://your.name/kg/Book", 
"Highlight": "https://your.name/kg/Highlight",

Book and Highlight are classes in the ontology
Every node with "type": "Book" expands to https://your.name/kg/Book
"highlightText" is a property, not a class, Highlight use it to attach a string literal

{"id": "kg:highlight/123", "type": "Highlight", "highlightText": "some quote..."}








