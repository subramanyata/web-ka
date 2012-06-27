#!/usr/bin/python
# -*- coding: utf-8 -*-
# Author: Eric Nichols, <eric@ecei.tohoku.ac.jp>
################################################################################

'''
`espresso.py`: an implemenatation of the Espresso bootstrapping algorithm

### Usage

        Usage: espresso.py [options] [database] [collection] [rel] [seeds]

        Options:
          -h, --help            show this help message and exit
          -o HOST, --host=HOST  mongodb host machine name. default: localhost
          -p PORT, --port=PORT  mongodb host machine port number. default: 27017
          -s START, --start=START
                                iteration to start with. default: 1
          -t STOP, --stop=STOP  iteration to stop at. default: 2

### Caches Created

Creates 2 caches of bootstrapped instances and patterns for the target 
relation:

1. `<matrix>_<rel>_esp_i`: bootstrapped instances for <rel>
2. `<matrix>_<rel>_esp_p`: bootstrapped patterns for <rel>

### Bootstrapping

Bootstrapping starts with seed instances and alternates between promoting new
patterns and instances following the Espresso bootstrapping algorithm [1].

1. retrieve promoted instances/patterns
2. rank by reliability score
3. keep top 10 promoted instances/patterns
4. bootstrap patterns/instances using promoted instances/patterns

### Reliability Score

Candidate patterns and instances are ranked by reliability score, which 
reflects the pointwise mutual information score between a promoted 
pattern/instance and the set of instances/patterns that generated it.

        (1) r_i(i,P) = sum( dpmi(i,p)*r_p(p) / max_pmi ) / len(P)
                         for p in P

        (2) r_p(P,i) = sum( dpmi(i,p)*r_i(i) / max_pmi ) / len(I)
                         for i in I

where dpmi is Discounted Pointwise Mutual Information [2].
r_i and r_p are recursively defined with r_i=1.0 for the seed instances.

### References

[1] Patrick Pantel and Marco Pennacchiotti.
Espresso: Leveraging Generic Patterns for Automatically Harvesting Semantic Relations.
ACL 2006.
'''

import fileinput
import pymongo
import sys

import mongodb
from bootstrapper import Bootstrapper
from matrix2pmi import PMI


class Espresso(Bootstrapper):
    def __init__(self, db, matrix, rel, seeds, n, keep, reset):
        self.db = db
        self.matrix = matrix
        self.rel = rel
        self.n = n
        self.keep = keep
        self.boot_i = '%s_%s_esp_i' % (matrix, rel)
        self.boot_p = '%s_%s_esp_p' % (matrix, rel)
        if reset: self.reset()
        self.add_seeds(seeds)
        self.args = self.get_args()
        self.pmi = PMI(db, matrix)
        self.max_pmi = self.pmi.max_pmi()

    def _r_i(self, i):
        '''retrieves r_i for past iteration'''
        try:
            query = mongodb.make_query(i=i,p=None)
            r = self.db[self.boot_i].find_one(query, fields=['score'])
            #print >>sys.stderr, 'r_i:', r
            return r.get('score',0.0)
        except Exception as e:
            return 0.0
        
    def _r_p(self, p):
        '''retrieves r_p for past iteration'''
        try:
            query = mongodb.make_query(i=None,p=p)
            r = self.db[self.boot_p].find_one(query, fields=['score'])
                #print >>sys.stderr, 'r_p:', r
            return r.get('score',0.0)
        except Exception as e:
            return 0.0

    def r_i(self, i, P):
        '''r_i: reliability of instance i'''
        r = sum( [self.pmi.dpmi(i,p)*self._r_p(p) / self.max_pmi 
                  for p in P] ) / len(P)
        print >>sys.stderr, 'r_i:', i, r
        return r

    def r_p(self, I, p):
        '''r_p: reliability of pattern p'''
        r = sum( [self.pmi.dpmi(i,p)*self._r_i(i) / self.max_pmi 
                  for i in I] ) / len(I)
        print >>sys.stderr, 'r_p:', p, r
        return r

    def S(self, i, P):
        '''confidence in an instance'''
        T = sum ( [ self._r_p(p) for p in P ] )
        return sum ( [ self.pmi.dpmi(i,p)*self._r_p(p)/T for p in P ] )

    def rank_patterns(self, I, P, it):
        '''return a list of patterns ranked by reliability score'''
        rs = [{'rel':p, 'it':it, 'score':self.r_p(I,p)} 
              for p in P]
        rs.sort(key=lambda r: r.get('score',0.0),reverse=True)
        return rs

    def rank_instances(self, I, P, it):
        '''return a list of instances ranked by reliability score'''
        rs = []
        for i in I:
            r = {'arg%d'%n:v
                 for n,v in enumerate(i, 1)}
            r['it'] = it
            r['score'] = self.r_i(i,P)
            rs.append(r)
        rs.sort(key=lambda r: r.get('score',0.0),reverse=True)
        return rs

def main():
    from optparse import OptionParser
    usage = '''%prog [options] [database] [collection] [seeds]'''
    parser = OptionParser(usage=usage)
    parser.add_option('-k', '--keep-seeds',
                      action='store_true', dest='keep', default=False,
                      help='''keep seeds and acquired items and use for candidate selection. default: False''')        
    parser.add_option('-n', '--n-best', dest='n', type=int, default=10,
                      help='''number of candidates to keep per iteration. default: 10''')    
    parser.add_option('-o', '--host', dest='host', default='localhost',
                      help='''mongodb host machine name. default: localhost''')    
    parser.add_option('-p', '--port', dest='port', type=int, default=27017,
                      help='''mongodb host machine port number. default: 27017''')
    parser.add_option('-r', '--reset',
                      action='store_true', dest='reset', default=False,
                      help='''reset bootstrapping results. default: False''')
    parser.add_option('-s', '--start', dest='start', type=int, default=1,
                      help='''iteration to start with. default: 1''')
    parser.add_option('-t', '--stop', dest='stop', type=int, default=10,
                      help='''iteration to stop at. default: 10''')
    options, args = parser.parse_args()
    if len(args) != 3:
        parser.print_help()
        exit(1)
    db_, matrix, rel = args[:3]
    files = args[4:]
    connection = pymongo.Connection(options.host, options.port)
    db = connection[db_]
    seeds = (i.strip() for i in fileinput.input(files))
    e = Espresso(db, matrix, rel, seeds, options.n, options.keep, options.reset)
    e.bootstrap(options.start, options.stop)

if __name__ == '__main__':
    main()
