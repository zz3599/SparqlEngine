Sparqlparser requires Python 2.7 or higher (but untested on Python 3.0)

REQUIREMENTS
=====
Python 2.7 or higher (but not 3.x)

HOW TO USE
=====
python sparqlparser.py [inputfile]

OUTPUT
=====
An outputfile by the name of [inputfile].P will be created in the same location as the program.
The query/1 predicate will produce be the literal translation of the SPARQL query. The predicates  

DEMO
=====
Try any of the q[.] files in this directory .

LIMITATIONS
====
1. Space sensitive. A triple like '?product bsbm:productFeature %ProductFeature2% .' works whereas one without the space before the period 
('?product bsbm:productFeature %ProductFeature2%.') fails. This is because '.' is treated as a token, and thus required to be space-separated. In general,
if there is any failure, it is most likely because of this.  
2. Requires that every statement inside an optional block end with a '.' in the same style described by the previous bullet
3. Currently only supports full-stop triples (you cannot do 'x y z; y2 z2', only 'x y z . x y2 z2').
4. Filter statements require that there be a space right before the closing parentheses - 'FILTER(!bound(var ))' works but 'FILTER(!bound(var))' will not. 
Comparison operators (<, >, ==, !=, etc.) require spaces left and right of the operator. This is again because the comparator is treated as a token.
