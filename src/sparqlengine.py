import sys
import tpg
import os
import re

# Translates from SPARQL queries to Prolog predicates. 
# All __str__ return strings, all translate methods return lists, except at the top most ASTs (or null). It is up to caller to decide what to do 
# with the list upon calling translate

# Remove non-chars at the beginning, and put the first character to uppercase
def cleanVar(var):
    return re.sub("[^\w\-\+\*\/]+", "", var).title()

# Applies a prefix to a given string
def applyPrefix(string):
    tokens = string.split(':')
    if len(tokens) < 2 : return string
    if tokens[0] not in Globals.prefixes: return string
    r = Globals.prefixes[tokens[0]]
    parts = r.split('>')
    parts[len(parts)-2] += tokens[1]
    print("Replaced %s-> %s" %(string, '>'.join(parts)))
    return '>'.join(parts)

class Globals(object):
    entirequery = None
    intermediates = 0 # Filters need to have intermediate bindings
    prefixes = dict() # Prefixes for namespaces
    params = [] # list of parameters for result
    boundparams = [] # List of parameters that need to be bound before querying
    alreadyboundparams = [] # list of parameters already bound to a variable in the scope of the current predicate

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
        self.ns = self.ns.split(':')[0] # Remove the end colon if there is one
        Globals.prefixes[self.ns] =  self.nsuri # Assign to global prefixes for fast lookup

class Header(Node):
    fields = ['prefixes']
    def __str__(self):
        return '\n'.join([str(x) for x in self.prefixes])        
    def translate(self):
        for x in self.prefixes:
            x.translate()
        print Globals.prefixes
        return "\n"
    
class Plist(Node):
    fields = ['params']
    def __init__(self, params):
        self.params = params
        if self.params[0].lower() == 'distinct':
            self.params.pop(0)        
            self.distinct = True
            #entirequery.distinct = True # Distinct -> setof/3, Non-distinct -> bagof/3. 
        else : 
            self.distinct = False            
        self.params = [cleanVar(x) for x in self.params]
        Globals.params = self.params
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
            if isinstance(conditiontranslated, list): # optional block could be another body
                result.extend(conditiontranslated) 
            else: 
                result.append(conditiontranslated)
        return result               

class BodyUnion(Node):
    fields = ['body1', 'body2']
    def __str__(self):
        return '\nBody block 1:\n' + str(self.body1) + '\nBody Block 2:\n' + str(self.body2)
    def translate(self):
        result = [self.body1.translate()]
        Globals.alreadyboundparams = [] # Bounded variables need to be re-bound in another subquery
        result.append(self.body2.translate())
        return result
    
class Condition(Node):
    fields = ['subject', 'predicate', 'object']
    def __init__(self, *args):
        for f, a in zip(self.fields, args): 
            if a[0] == '?': 
                a = cleanVar(a)
            if a[0] == '%': # An already bound variable
                a = cleanVar(a)
                if a not in Globals.boundparams:
                    Globals.boundparams.append(a)

            setattr(self, f, a)       
    def __str__(self):
        return 's: %s, p: %s, o: %s' %(self.subject, self.predicate, self.object)
    def translate(self):
        result = ''
        if self.subject in Globals.boundparams and self.subject not in Globals.alreadyboundparams: 
            result += 'val(%s, %s),' %(self.subject.lower(), self.subject)
            Globals.alreadyboundparams.append(self.subject)
        if self.object in Globals.boundparams and self.object not in Globals.alreadyboundparams: 
            result += 'val(%s, %s),' %(self.object.lower(), self.object)
            Globals.alreadyboundparams.append(self.object)
        self.subject = applyPrefix(self.subject)
        self.predicate = applyPrefix(self.predicate)
        self.object = applyPrefix(self.object)
        result += "rdf3(%s, '%s', %s)" %(self.subject, self.predicate, self.object)

        return result

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
            return predicate1 + '\n\n' +  predicate2 + "\n"
        else:  
            predicate1 += ',\n\t'.join(self.body.translate()) + '.'
            return predicate1 + "\n"        

# The root node
class EntireQuery(Node):
    fields = ['header', 'mainquery', 'modifier']
    def __str__(self):
        return str(self.header) + str(self.mainquery) + str(self.modifier)
    def translate(self):
        predicates = self.header.translate() + self.mainquery.translate() + self.modifier.translate()
        parameters = str(self.mainquery.params)
        query = '\n\nquery(FinalBag' + (',' if len(Globals.boundparams) > 0 else '') + ','.join(Globals.boundparams)
        query += '):-\n\t'
        querybody = []
        for boundparams in Globals.boundparams: # We cannot use this parameter in bagof, so assert it
            newassert = 'assert(val(%s, %s))' %(boundparams.lower(), boundparams)
            querybody.append(newassert)
        queryintermediate = None
        if isinstance(self.mainquery.body, BodyUnion):
            queryintermediate = '\n\nquery_intermediate(%s):- result1(%s); result2(%s).' % (parameters, parameters, parameters)
        else:
            queryintermediate = '\n\nquery_intermediate(%s):- result1(%s).' % (parameters, parameters)
            pass
        querybody.append('%s(query_intermediate(%s), query_intermediate(%s), ResultIntermediate)'% ('setof' if self.mainquery.params.distinct else 'bagof', parameters, parameters)) # Bagof always produces overflow. Try smaller datasets 
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
        return predicates + query + "\n"
             

class Regex(Node):
    fields = ['property', 'regex']
    def __init__(self, prop, regex):
        self.property = cleanVar(prop)
        self.regex = regex
        # Extract variables from regex
        
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
            return 'var(%s)' % cleanVar(self.variable)
        else :
            return 'nonvar(%s)' % cleanVar(self.variable)
    
class Filter(Node):
    fields = ['filter'] # Filter could be a string or a bound
    def __init__(self, filters):
        if isinstance(filters, str): # string is split by '&&'
            filters = filters.split('&&')
            filterstring = ''
            for f in filters:
                tokens = re.split("(<=|>=|==|!=|<|>)", f, 3) # Capture so we can reconstruct easily
                filtervar0 = cleanVar(tokens[0]) # Left expression
                filtervar = cleanVar(tokens[2]) # Right expression
                bounded = False
                if tokens[0][0] == '%' and filtervar0 not in Globals.boundparams:
                    Globals.boundparams.append(filtervar0) 
                    bounded = True
                if tokens[2][0] == '%' and filtervar not in Globals.boundparams:
                    Globals.boundparams.append(filtervar) 
                    bounded = True
                if bounded: 
                    translate = 'val(%s, FilterRight%d) ' %(filtervar.lower(), Globals.intermediates)            
                    translate += ', %s %s FilterRight%d' % (filtervar0, '=\=' if tokens[1] == '!=' else '@' + tokens[1], Globals.intermediates)
                else : 
                    translate = 'FilterRight%d is %s' %(Globals.intermediates, filtervar)            
                    translate += ', %s %s FilterRight%d' % (filtervar0, '=\=' if tokens[1] == '!=' else '@' + tokens[1], Globals.intermediates)
                Globals.intermediates += 1
                filterstring += translate
            self.filter = filterstring
        else :
            self.filter = filters
    def __str__(self):
        return '\nFilter: %s' % ('\n'.join(self.filter.split('&&') if not isinstance(self.filter, Bound) else str(self.filter)))
        
    def translate(self):
        if isinstance(self.filter, Bound): # A filter checking that a variable is bound or not
            return [self.filter.translate()]
        return [self.filter]
                

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
    def __init__(self, field):
        self.field = cleanVar(field)
    def __str__(self):
        return 'order by: %s' % self.field
    def translate(self):
        return """
%% Order by the index of the list of structures
:- reconsult('utils.P').

orderby(UnorderedBag, OrderedBag) :- quick_sort_functor(UnorderedBag, %d, OrderedBag).\n""" %(
          Globals.params.index(self.field) + 1 
        )
        
class Limit(Node):
    fields = ['amount']
    def __str__(self):
        return 'Limit: %s' % self.amount
    def translate(self):
        return """
limit(_, Count, Count, Result, Result).
limit([], _, _, Result, Result).
limit([H|T], Counter, Limit, Stack, Result):-
    Counter < Limit, 
    Counter2 is Counter + 1,
    limit(T, Counter2, Limit, [H|Stack], Result).
limit(List, Counter, Limit, Result):-
    limit(List, Counter, Limit, [], Result). """
                
class Offset(Node):
    fields = ['amount']
    def __str__(self):
        return 'Offset: %s' % self.amount
    def translate(self):
        return """
offset(List, Count, Count, List) :- !.
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
    Body/s -> BodyNormal/s | BodyUnion/s ; # BodyUnion contains a Union followed by blocks  
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
    Globals.entirequery = parser(prog)

    print('---------------TRANSLATION-----------------------------------------')
    translation = Globals.entirequery.translate()
    outfile = os.path.basename(sys.argv[1]) + ".P"
    f = open(outfile, 'w+')
    f.write(translation)

    f.close()

except tpg.Error:
    print('Parsing Error')
    raise
