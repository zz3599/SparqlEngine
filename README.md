SparqlEngine
====

Translates your SPARQL queries to Prolog

REQUIREMENTS
=====
Python 2.7 or higher (but not 3.x)  
XSB Prolog  

XSB Prolog Setup
=====
$XSB_HOME is XSB root folder.  
`cd $XSB_HOME/build`  
`./configure -enable-FEATURE`   
`./makexsb`  

HOW TO USE
=====
`python sparqlparser.py [relpath to inputfile]` produces Prolog source of [filename.P]  
`xsb`  
`['output.P'].` test data  
`reconsult('[filename.P]').`  
`query(Result, ...)` varies depending on query  
Query result in `Result`

EXAMPLES
=====
The queries are borrowed from [Berlin Benchmark](http://wifo5-03.informatik.uni-mannheim.de/bizer/berlinsparqlbenchmark/)  
These are examples for each query file. These are tested and return non-empty bag/set.   
q1: Find products for a given set of generic features  
`query(Result, '<http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/vocabulary/product>', '<http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/instances/productfeature416>', '<http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/instances/productfeature428>', '"830"^^<http://www.w3.org/2001/xmlschema#integer>').`  
q2: Retrieve basic information about a specific product for display purposes  
`query(Result, '<http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/instances/datafromproducer1/product1>').`    
q3: Find products having some specific features and not having one feature  
`query(Result, '<http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/vocabulary/product>', '<http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/instances/productfeature416>', '"738"^^<http://www.w3.org/2001/xmlschema#integer>', '"738"^^<http://www.w3.org/2001/xmlschema#integer>', '<http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/instances/productfeature418>').`      
q4: Find products matching two different sets of features  
`query(Result, '<http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/vocabulary/product>', '<http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/instances/productfeature416>', '<http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/instances/productfeature418>', '"311"^^<http://www.w3.org/2001/xmlschema#integer>', '<http://www4.wiwiss.fu-berlin.de/bizer/bsbm/v01/instances/productfeature430>', '"311"^^<http://www.w3.org/2001/xmlschema#integer>'). `  
q5: This query will not work because the SPARQL syntax is adding numeric values to a string, and hence cannot be done  
q6: Find products having a label and type.  
`query(Result).`  

LIMITATIONS
====
1. Execution time excessive in some lax queries (~ 1 minute). This is only happens if you have too many `_` in your queries.
2. Space sensitive. A triple like '?product bsbm:productFeature %ProductFeature2% .' works whereas one without the space before the period 
('?product bsbm:productFeature %ProductFeature2%.') fails. This is because '.' is treated as a token, and thus required to be space-separated. In general,
3. Currently only supports full-stop triples (you cannot do 'x y z; y2 z2', only 'x y z . x y2 z2').
4. Comparison operators (<, >, ==, !=, etc.) require spaces left and right of the operator. 
