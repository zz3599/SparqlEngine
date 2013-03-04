import sys
import tpg
import re

# Translates from SPARQL queries to Prolog predicates. 
# All __str__ return strings, all translate methods return lists, except at the top most ASTs (or null). It is up to caller to decide what to do 
# with the list upon calling translate

global entirequery # The root node for the entire parse tree of the SPARQL query
intermediates = 0 # For filters with expressions, keeps track of # of intermediate values

class EvalError(Exception):
    """Class of exceptions raised when an error occurs during evaluation."""

class AnalError(Exception):
    """Class of exceptions raised when an error occurs during analysis."""

class Node(object):
    """Base class of AST nodes."""
    fields = []
    def __init__(self, *args):
        """Populate fields named in "fields" with values in *args."""
        assert(len(self.fields) == len(args))
        for f, a in zip(self.fields, args): setattr(self, f, a)
    
class String(Node):
    """Class of nodes representing string literals."""
    fields = ['value']
    def __str__(self):
        return self.value

class Prefix(Node):
    fields = ['ns', 'nsuri']
    def __str__(self):
        return 'ns: %s, uri: %s' % (self.ns, self.nsuri)
    def translate(self):
        return 'prefix(\"%s\", \"%s\").' %(self.ns, self.nsuri)

class Header(Node):
    fields = ['prefixes']
    def __str__(self):
        return '\n'.join([str(x) for x in self.prefixes])        
    def translate(self):
        return '\n'.join([x.translate() for x in self.prefixes])
    
class Plist(Node):
    fields = ['params']
    def __init__(self, params):
        #self.params = [x.strip('?!%') for x in params]
        self.params = params
        global entirequery
        if self.params[0].lower() == 'distinct':
            self.params.pop(0)        
            self.distinct = True
            #entirequery.distinct = True # Distinct -> setof/3, Non-distinct -> bagof/3. 
        else : 
            self.distinct = False            
    def __str__(self):
        return ','.join([x for x in self.params])
    def translate(self):
        pass
    
class Body(Node):
    fields = ['conditionslist'] 
    def __str__(self):
        return '\n'.join([str(x)  for x in self.conditionslist])
    def translate(self):
        result = []
        for condition in self.conditionslist: 
            conditiontranslated = condition.translate()
            if isinstance(conditiontranslated, list):
                result.extend(conditiontranslated)
            else: 
                result.append(conditiontranslated)
        return result               

class BodyUnion(Node):
    fields = ['body1', 'body2']
    def __str__(self):
        return '\nBody block 1:\n' + str(self.body1) + '\nBody Block 2:\n' + str(self.body2)
    def translate(self):
        return [self.body1.translate(),self.body2.translate()]
    
class Condition(Node):
    fields = ['subject', 'predicate', 'object']
    def __str__(self):
        return 's: %s, p: %s, o: %s' %(self.subject, self.predicate, self.object)
    def translate(self):
        return "rdf3(%s, %s, %s)" %(self.subject, self.predicate, self.object)

class MainQuery(Node):
    fields = ['type', 'params', 'body']
    def __str__(self):
        result = self.type + '\n'
        if(self.params): result += 'params:' + str(self.params)
        if(self.body): result += '\nbody: ' + str(self.body)
        return result
    def translate(self):
        predicate1 = "\nresult1(%s) :- \n\t" % str(self.params)
        predicate2 = None
        if isinstance(self.body, BodyUnion):
            uniontranslation = self.body.translate()
            predicate1 += ',\n\t'.join(uniontranslation[0]) + '.'
            predicate2 = "\nresult2(%s) :- \n\t" % str(self.params)
            predicate2 += ',\n\t'.join(uniontranslation[1]) + '.'    
            return predicate1 + '\n\n' +  predicate2
        else:  
            predicate1 += ',\n\t'.join(self.body.translate()) + '.'
            return predicate1        

# The root node
class EntireQuery(Node):
    fields = ['header', 'mainquery', 'modifier']
    def __str__(self):
        return str(self.header) + str(self.mainquery) + str(self.modifier)
    def translate(self):
        predicates = self.header.translate() + self.mainquery.translate() + self.modifier.translate()
        parameters = str(self.mainquery.params)
        query = '\n\nquery(FinalBag):-\n\t'
        querybody = []
        queryintermediate = None
        if isinstance(self.mainquery.body, BodyUnion):
            queryintermediate = '\n\nquery_intermediate(%s):- result1(%s); result2(%s).' % (parameters, parameters, parameters)
        else:
            queryintermediate = '\n\nquery_intermediate(%s):- result1(%s).' % (parameters, parameters)
            pass
        querybody.append('%s(query_intermediate(%s), query_intermediate(%s), ResultIntermediate)'% ('setof' if self.mainquery.params.distinct else 'bagof', parameters, parameters))
        currentResult = "ResultIntermediate"
        for modifier in self.modifier.modifierlist:
            if isinstance(modifier, OrderBy):
                querybody.append('orderby(%s, OrderedResult)' % currentResult)
                currentResult = "OrderedResult"
            elif isinstance(modifier, Limit):
                querybody.append('limit(%s, 0, %s, LimitResult)' % (currentResult, modifier.amount))
                currentResult = "LimitResult"
            elif isinstance(modifier, Offset):
                querybody.append('offset(%s, 0, %s, OffsetResult)' % (currentResult, modifier.amount))
                currentResult = "OffsetResult"
        querybody.append('FinalBag = %s' % currentResult)
        query += ',\n\t'.join(querybody) + '.' + queryintermediate
        return predicates + query
             

class Regex(Node):
    fields = ['property', 'regex']
    def __str__(self):
        return 'property: %s, regex: %s' %(self.property, self.regex)
    def translate(self):
        return """pcre:match(%s, %s, Matchlist, 'one'), Matchlist \==[]""" %(self.regex, self.property)

class Bound(Node):
    fields = ['bound', 'variable']
    def __str__(self):
        return '\n%sbound: %s\n' % ('not' if bool('!bound' == self.bound) else '', self.variable)
    def translate(self):
        if self.bound == '!bound':
            return 'var(%s)' % self.variable
        else :
            return 'nonvar(%s)' % self.variable 
    
class Filter(Node):
    fields = ['filter'] # Filter could be a string or a bound
    def __str__(self):
        return '\nFilter: %s' % ('\n'.join(self.filter.split('&&') if not isinstance(self.filter, Bound) else str(self.filter)))
    def translate(self):
        if isinstance(self.filter, Bound): # A filter checking that a variable is bound or not
            return [self.filter.translate()]
        filters = self.filter.split('&&')
        translatelist = []
        # process the text
        for i in range(len(filters)):
            filter = filters[i]
            global intermediates # For sake of avoiding variable collision
            tokens = re.split("(<=|>=|==|!=|<|>)", filter, 3) # Capture so we can reconstruct easily
            translate = 'FilterRight%d is %s' %(intermediates, tokens[2])            
            translate += ', %s %s FilterRight%d' % (tokens[0], '=\=' if tokens[1] == '!=' else tokens[1], intermediates)
            intermediates += 1
            translatelist.append(translate) 
        return translatelist
                

# Optional blocks
class Optional(Node):
    fields = ['body']
    def __str__(self):
        return 'Optional:\n' + str(self.body)
    def translate(self):
        translatelist = self.body.translate()
        resultlist = []
        for translate in translatelist:
            lines = translate.split(',') 
            formatstring = '(%s; not %s)' % (translate, translate) if re.match("<=|>=|==|!=|<|>", translate) == None else '(%s, (%s; not %s))' % (lines[0], lines[1], lines[1]) 
            resultlist.append(formatstring)
        return resultlist
    
class Modifier(Node):
    fields = ['modifierlist']
    def __str__(self):
        return '\nModifiers:\n' + '\n'.join([str(x) for x in self.modifierlist])
    def translate(self):
        return '\n'.join([x.translate() for x in self.modifierlist])
    
class OrderBy(Node):
    fields = ['field']
    def __str__(self):
        return 'order by: %s' % self.field
    def translate(self):
        global entirequery
        return """\n\norderby(UnorderedBag, OrderedBag) :- sortby(UnorderedBag, %d, OrderedBag).\n""" %(
          entirequery.mainquery.params.params.index(self.field) + 1 
        )
        
class Limit(Node):
    fields = ['amount']
    def __str__(self):
        return 'Limit: %s' % self.amount
    def translate(self):
        return """
limit(_, Count, Count, Result) :- Result = [].
limit([], _, _, Result) :- Result = [].
limit([H|T], Counter, Limit, Result):-
    Counter < Limit, 
    Counter2 is Counter + 1,
    limit(T, Counter2, Limit, Result2),
    Result = [H|Result2]. """
                
class Offset(Node):
    fields = ['amount']
    def __str__(self):
        return 'Offset: %s' % self.amount
    def translate(self):
        return """
offset(List, Count, Count, Result) :- Result = List.
offset([_|T], Counter, Offset, Result) :- 
    Counter < Offset, 
    Counter2 is Counter + 1,
    offset(T, Counter2, Offset, Result). """
            
class Parser(tpg.Parser):
    r"""
    
    set lexer_ignorecase = True  # enables the re.IGNORECASE option.
    
    token int:         '\d+' ;
    token string:      '\"[^\"]*\"' ;
    token ident:        '[\S]+';
    #token uri:          '[a-zA-Z0-9_?\-%./<>]+' ; 
    #token ident:       '[a-zA-Z0-9:_?\-%]+' ;
    separator spaces:  '\s*' ;
        
    START/s -> Query/s;
    Query/s -> Header/p Main/s Modifier/m $s = EntireQuery(p, s, m)$;
    Header/s -> $l=[]$ ( 'prefix' id/s  id/p  $l.append(Prefix(s,p))$)* $s = Header(l)$; 
    Main/s -> ('select'/s) Parameters/p 'where' '\{' Body/b '\}' $s = MainQuery(s, p, b)$;
    Parameters/s -> $l=[]$ (id/i $l.append(i)$)+ $s=Plist(l)$;
    Body/s ->BodyNormal/s | BodyUnion/s ; # BodyUnion contains a Union followed by blocks  
    BodyUnion/s -> '\{' BodyNormal/n '\}' 'union' '\{' BodyNormal/o '\}' $s=BodyUnion(n,o)$ ; 
    BodyNormal/s -> $l=[]$ (Condition/s $l.append(s)$ | 
                        Filter/s $l.append(s)$  |
                        Optional/s $l.append(s)$)+ $s=Body(l)$; 
    Condition/s -> id/s id/p id/o '\.' $s=Condition(s,p,o)$ ; 
    Filter/s -> 'filter' '\(' (Expr/s) '\)' $s=Filter(s)$| Regex/s;
    Optional/s -> 'optional' '\{' Body/s '\}' $s=Optional(s)$;
    Modifier/s -> $l=[]$
                (
                    'order by' id/s $l.append(OrderBy(s))$ | 
                    'limit' int/s $l.append(Limit(s))$ | 
                    'offset' int/s $l.append(Offset(s))$ 
                )*
                $s=Modifier(l)$;  

    # Filter expressions
    Regex/s -> 'filter' 'regex' '\(' literal/s ',' literal/r $s=Regex(s,r)$ '\)'; 
    Expr/s -> And/s | Bound/s;
    Bound/s -> ('bound'/b | '!bound'/b ) '\(' literal/s '\)' $s=Bound(b,s)$;
    And/s -> Test/s (AndOp/o Test/e2 $s=s+o+e2$) *;
    Test/s -> Add/s (TestOp/o Add/e2 $s=s+o+e2$) *;
    Add/s -> Atom/s (ArithOp/o Atom/e2 $s=s+o+e2$) *;
    Atom/s -> literal/s | '\('  Expr/s '\)';    
    
    # Base blocks
    AndOp/r -> '&&'/r ;
    TestOp/r -> '<='/r| '>='/r |'!='/r |'=='/r |
                 '>'/r | '<(?= )'/r ; # NOTE: less than requires there to be a space after (to avoid confusion with '<' in prefix URI)
    ArithOp/r -> AddOp/r | MulOp/r;
    AddOp/r ->   '\+'/r | '-'/r ;
    MulOp/r ->   '\*'/r | '/'/r ;
    id/s -> string/s | ident/s;
    literal/s -> id/s | int/s;
    """    
try:
    prog = open(sys.argv[1]).read()
    parser = Parser()
    global entirequery
    entirequery = parser(prog)
    #print('----------------PARSETREE---------------------------------------')
    #print(entirequery)
    print('---------------TRANSLATION-----------------------------------------')
    
    translation = entirequery.translate()
    outfile = sys.argv[1].split('.')[0] + ".P"
    f = open(outfile, 'w+')
    f.write(translation)
    print(entirequery.translate())

except tpg.Error:
    print('Parsing Error')
    raise

except AnalError as e:
    print('Analysis Error')
    #raise

except EvalError:
    print('Evaluation Error')
    #raise