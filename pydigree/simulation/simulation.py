from __future__ import division
import random

from itertools import combinations_with_replacement, izip

from pydigree.common import *
from pydigree.ibs import ibs
from pydigree.io.smartopen import smartopen
from pydigree.io.plink import write_plink, write_map
from pydigree.individual import Individual
from pydigree.exceptions import SimulationError


# A base class for simulations to inherit from
class Simulation(object):

    def __init__(self, template=None, replications=1000):
        self.template = template
        self.replications = replications
        self.accuracy_threshold = 0.9
        self.constraints = {'genotype': {}, 'ibd': {}}
        self.trait = None

    def set_trait(self, architecture):
        self.trait = architecture

    def replicate(self):
        raise NotImplementedError("This is a base class don't call me")

    def get_founder_genotypes(self):
        geno_constraints = self.constraints['genotype']
        for ind in ped.founders():
            ind.clear_genotypes()
            if ind not in geno_constraints:
                ind.get_genotypes(linkeq=linkeq)
            else:
                ind.get_constrained_genotypes(geno_constraints[ind],
                                              linkeq=linkeq)
        
    def run(self, verbose=False, writeibd=False, output_predicate=None, compression=None):
        write_map(self.template, '{0}.map'.format(self.prefix))
        for x in xrange(self.replications):
            print 'Replicate %d' % (x + 1)
            self.replicate(
                verbose=verbose, writeibd=writeibd, replicatenumber=x)
            self.write_data(
                x, predicate=output_predicate, compression=compression)

    def write_data(self, replicatenumber, predicate=None, compression=None):
        filename = '{0}-{1}'.format(self.prefix, (replicatenumber + 1))
        write_plink(self.template, filename, predicate=predicate,
                    mapfile=False, compression=compression)

    def _writeibd(self, replicatenumber):
        # Warning: Don't call this function! If the individuals in the pedigree dont have
        # LABEL genotypes, you're just going to get IBS configurations at each locus, not
        # actual IBD calculations.
        #
        # If you have data you want to identify IBD segments in, check
        # pydigree.sgs
        with smartopen('{0}-{1}.ibd.gz'.format(self.prefix, replicatenumber + 1), 'w') as of:
            for ped in self.template:
                for ind1, ind2 in combinations_with_replacement(ped.individuals, 2):
                    identical = []
                    for chrom_idx, chromosome in enumerate(ind1.chromosomes):
                        if ind1 == ind2:
                            genos = izip(*ind1.genotypes[chrom_idx])
                            ibd = [2 * (x == y) for x, y in genos]
                        else:
                            genos1 = izip(*ind1.genotypes[chrom_idx])
                            genos2 = izip(*ind2.genotypes[chrom_idx])
                            ibd = [ibs(g1, g2)
                                   for g1, g2 in izip(genos1, genos2)]
                        identical.extend(ibd)
                    outline = [ped.label, ind1.label, ind2.label] + identical
                    outline = ' '.join([str(x) for x in outline])
                    of.write('{}\n'.format(outline))

    def predicted_trait_accuracy(self, ped):
        calls = [(ind.predicted_phenotype(self.trait),
                  ind.phenotypes['affected'])
                 for ind in ped
                 if ind.phenotypes['affected'] is not None]
        # Remember: in python the bools True and False are actually alternate
        # names for the integers 1 and 0, respectively, so you can do
        # arithmetic with them if you so please. Here we sum up all the
        # correct predictions and divide by the number of predictions made.
        return sum(x == y for x, y in calls) / len(calls)

    def read_constraints(self, filename):

        if not self.template:
            raise ValueError()

        with open(filename) as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith('#'):
                    continue

                l = line.split()
                if l[0].lower() == 'genotype':
                    type, ped, id, chr, index, allele, chromatid, method = l
                    locus = (chr, index)
                    ind = self.template[ped][id]
                    self.add_genotype_constraint(ind, locus, allele,
                                                 chromatid, method)
                elif l[0].lower() == 'ibd':
                    type, ped, id, ancestor, chr, index, anc_chromatid = l
                    locus = (chr, index)
                    ind = self.template[ped][id]
                    ancestor = self.template[ped][ancestor]
                    self.add_ibd_constraint(ind, ancestor,
                                            locus, anc_chromatid)
                else:
                    raise ValueError('Not a valid constraint (%s)' % l[0])

    def add_genotype_constraint(self, ind, location, allele,
                                chromatid, method='set'):
        if not ind.is_founder():
            raise ValueError('Genotype constraints only for founders')
        if chromatid not in 'PM':
            raise ValueError('Not a valid haplotype. Choose P or M')
        chromatid = 1 if chromatid == 'M' else 0
        location = tuple(int(x) for x in location)
        allele = int(allele)
        if ind not in self.constraints['genotype']:
            self.constraints['genotype'][ind] = []
        c = (location, chromatid, allele, method)
        self.constraints['genotype'][ind].append(c)

    def add_ibd_constraint(self, ind, ancestor, location, anchap):
        if anchap not in 'PM':
            raise ValueError('Not a valid haplotype. Choose P or M')
        anchap = 1 if anchap == 'M' else 0
        location = tuple(int(x) for x in location)
        if ind not in self.constraints['ibd']:
            self.constraints['ibd'][ind] = []
        c = (ancestor, location, anchap)
        self.constraints['ibd'][ind].append(c)
