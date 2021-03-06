# -*- coding: utf-8 -*-
#
#  Copyright 2014-2018 Ramil Nugmanov <stsouko@live.ru>
#  This file is part of CGRtools.
#
#  CGRtools is free software; you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
from functools import reduce
from itertools import product, combinations
from networkx import compose, has_path
from networkx.algorithms.isomorphism import (GraphMatcher, categorical_node_match, generic_node_match,
                                             categorical_edge_match)
from warnings import warn
from .containers import CGRTemplate, MatchContainer, CGRContainer
from .core import CGRcore
from .exceptions import InvalidConfig, InvalidData, InvalidTemplate


class CGRreactor:
    """ CGR isomorphism based operations
    """
    def __init__(self, extralabels=False, isotope=False, element=True, stereo=False):
        """
        :param extralabels: compare hybridization and neighbors count marks on isomorphism procedure
        :param isotope: compare isotope marks on isomorphism procedure
        :param element: compare elements symbols and charges on isomorphism procedure
        :param stereo: compare stereo marks on isomorphism procedure
        """
        gnm_sp, gnm_s, cnm_p = [], [], ['element', 'p_charge']
        if isotope:
            gnm_sp.append('isotope')
            gnm_s.append('isotope')
            cnm_p.append('isotope')
        if element:
            gnm_sp.extend(['sp_charge', 'element'])
            gnm_s.extend(['s_charge', 'element'])
        if extralabels:
            gnm_sp.extend(['sp_neighbors', 'sp_hyb'])
            gnm_s.extend(['s_neighbors', 's_hyb'])
        if stereo:
            gnm_sp.append('sp_stereo')
            gnm_s.append('s_stereo')
            cnm_p.append('p_stereo')

        self.__node_match = generic_node_match(gnm_sp, [None] * len(gnm_sp), [self.__list_eq] * len(gnm_sp))
        self.__node_match_reagents = generic_node_match(gnm_s, [None] * len(gnm_s), [self.__list_eq] * len(gnm_s))
        self.__node_match_products = categorical_node_match(cnm_p, [None] * len(cnm_p))

        self.__edge_match = generic_node_match('sp_bond', None, self.__list_eq)
        self.__edge_match_reagents = generic_node_match('s_bond', None, self.__list_eq)
        self.__edge_match_products = categorical_edge_match('p_bond', None)

        self.__pickle = dict(stereo=stereo, extralabels=extralabels, isotope=isotope, element=element)

    def pickle(self):
        """ return config. for pickling
        """
        return self.__pickle.copy()

    @classmethod
    def unpickle(cls, config):
        """ return CGRreactor object instance
        """
        args = {'stereo', 'extralabels', 'isotope', 'element'}
        if args != set(config):
            raise InvalidConfig('Invalid config')
        return cls(**config)

    def get_cgr_matcher(self, g, h):
        if not isinstance(g, CGRContainer):
            nm = self.__node_match_reagents
            em = self.__edge_match_reagents
        else:
            nm = self.__node_match
            em = self.__edge_match

        return GraphMatcher(g, h, node_match=nm, edge_match=em)

    def get_template_searcher(self, templates):
        def searcher(g, skip_intersection=True):
            if skip_intersection:
                found = set()

            for i in templates:
                gm = self.get_cgr_matcher(g, i.pattern)
                for j in gm.subgraph_isomorphisms_iter():
                    matched_atoms = set(j)
                    if skip_intersection:
                        if found.intersection(matched_atoms):
                            continue
                        else:
                            found.update(matched_atoms)

                    yield MatchContainer(j, self.__remap_group(i.patch, g, {y: x for x, y in j.items()})[0], i.meta)

        return searcher

    @classmethod
    def __split_graph(cls, g):
        g = g.copy()
        lost_bonds = []
        term_atoms = []

        for l, n, m in list(cls.__get_substitution_paths(g)):
            nl = (n, l)
            if nl in lost_bonds:
                continue

            lost_bonds.append(nl)
            g.remove_edge(n, l)
            g.remove_edge(n, m)

        for n, m in list(cls.__get_broken_paths(g)):
            if not any(has_path(g, *x) for x in product((y for x in lost_bonds for y in x), (n, m))):
                g.remove_edge(n, m)
                term_atoms.append(n)
                term_atoms.append(m)

        return CGRcore.split(g), lost_bonds, term_atoms

    @staticmethod
    def __get_substitution_paths(g):
        """
        get atoms paths from detached atom to attached

        :param g: CGRContainer
        :return: tuple of atoms numbers
        """
        for n, nbrdict in g.adjacency():
            for m, l in combinations(nbrdict, 2):
                nms = nbrdict[m]['sp_bond']
                nls = nbrdict[l]['sp_bond']
                if nms == (1, None) and nls == (None, 1):
                    yield m, n, l
                elif nms == (None, 1) and nls == (1, None):
                    yield l, n, m

    @staticmethod
    def __get_broken_paths(g):
        for m, n, attr in g.edges(data=True):
            if attr['sp_bond'] == (None, 1):
                yield n, m

    def clone_subgraphs(self, g):
        if not isinstance(g, CGRContainer):
            raise InvalidData('only CGRContainer acceptable')

        r_group = []
        x_group = {}
        r_group_clones = []
        newcomponents = []

        ''' search bond breaks and creations
        '''
        components, lost_bonds, term_atoms = self.__split_graph(g)
        lost_map = {x: y for x, y in lost_bonds}
        ''' extract subgraphs and sort by group type (R or X)
        '''
        x_terminals = set(lost_map.values())
        r_terminals = set(lost_map)

        for i in components:
            x_terminal_atom = x_terminals.intersection(i)
            if x_terminal_atom:
                x_group[x_terminal_atom.pop()] = i
                continue

            r_terminal_atom = r_terminals.intersection(i)
            if r_terminal_atom:
                r_group.append([r_terminal_atom, i])
                continue

            newcomponents.append(i)
        ''' search similar R groups and patch.
        '''
        tmp = g
        for i in newcomponents:
            for k, j in r_group:
                gm = GraphMatcher(j, i, node_match=self.__node_match_products,
                                  edge_match=self.__edge_match_products)
                ''' search for similar R-groups started from bond breaks.
                '''
                mapping = next((x for x in gm.subgraph_isomorphisms_iter() if k.issubset(x) and
                                all(x[y] in term_atoms for y in k)), None)
                if mapping:
                    r_group_clones.append([k, mapping])
                    tmp = compose(tmp, self.__remap_group(j, tmp, mapping)[0])
                    break

        ''' add lose X groups to R groups
        '''
        for i, j in r_group_clones:
            for k in i:
                remappedgroup, mapping = self.__remap_group(x_group[lost_map[k]], tmp, {})
                tmp = CGRcore.union(tmp, remappedgroup)
                tmp.add_edge(j[k], mapping[lost_map[k]], s_bond=1, sp_bond=(1, None))

        if r_group_clones:
            tmp.meta.update(g.meta)

        return tmp.copy()

    @staticmethod
    def __list_eq(a, b):
        return True if b is None else a in b if isinstance(b, list) else a == b

    @staticmethod
    def __simple_eq(a, b):
        return True if b is None else a == b

    @staticmethod
    def __remap_group(g, h, mapping):
        newmap = mapping.copy()
        newmap.update({x: y for x, y in zip(set(g).difference(newmap), set(range(1, 1000)).difference(h))})
        return g.remap(newmap, copy=True), newmap

    @staticmethod
    def prepare_templates(raw_templates):
        a_marks = {'element', 's_charge', 's_hyb', 's_neighbors', 'p_charge', 'p_hyb', 'p_neighbors',
                   's_stereo', 'p_stereo', 's_radical', 'p_radical'}
        b_marks = {'s_bond', 'p_bond', 's_stereo', 'p_stereo'}
        x_marks = ('s_x', 's_y', 's_z', 'p_x', 'p_y', 'p_z')
        templates = []
        for template in raw_templates:
            if isinstance(template, CGRTemplate):
                templates.append(template)
                continue

            products = reduce(CGRcore.union, template.products).copy()
            reagents = reduce(CGRcore.union, template.reagents).copy()
            if not (isinstance(reagents, CGRContainer) and isinstance(products, CGRContainer)):
                raise InvalidTemplate('Templates should be CGRContainers')

            new_atoms = set(products).difference(reagents)
            for n in new_atoms:  # if unique atoms in patch has variable properties exception is raised
                pnn = products.nodes[n]
                for j in a_marks.intersection(pnn):
                    if isinstance(pnn[j], list):
                        raise InvalidTemplate("new atoms can't be variable")

            common = set(products).intersection(reagents)
            for n in common:
                pnn = products.nodes[n]
                rnn = reagents.nodes[n]
                for j in a_marks.intersection(pnn):
                    if isinstance(pnn[j], list):
                        pnn[j] = dict(zip(rnn[j], pnn[j]))
                for j in x_marks:
                    pnn.pop(j)

            for m, n, a in products.edges(data=True):
                if reagents.has_edge(m, n):
                    rmn = reagents[m][n]
                    for j in b_marks.intersection(a):
                        if isinstance(a[j], list):
                            a[j] = dict(zip(rmn[j], a[j]))
                else:
                    for j in b_marks.intersection(a):
                        if isinstance(a[j], list):
                            raise InvalidTemplate("new bonds can't be variable")

            reagents.remap({x: x + 1000 for x in reagents})
            products.remap({x: x + 1000 for x in products})

            templates.append(CGRTemplate(reagents, products, template.meta.copy()))
        return templates

    @staticmethod
    def patcher(structure, patch):
        """
        remove edges bw common nodes. add edges from template and replace nodes data

        :param structure: MoleculeContainer or CGRContainer
        :param patch: MoleculeContainer or CGRContainer with replacement data
        """
        node_marks = ['s_charge', 's_hyb', 's_neighbors', 's_stereo', 'element', 'map', 'mark']
        bond_marks = ['s_bond', 's_stereo']
        if isinstance(structure, CGRContainer):
            node_marks.extend(('p_charge', 'p_hyb', 'p_neighbors', 'p_stereo'))
            bond_marks.extend(('p_bond', 'p_stereo'))

        p = structure.fresh_copy()
        for i, attr in patch.nodes(data=True):
            p.add_node(i, **{x: y[structure.nodes[i][x]] if isinstance(y, dict) else y
                             for x, y in attr.items() if x in node_marks})

        for m, n, attr in patch.edges(data=True):
            p.add_edge(m, n, **{x: y[structure[m][n][x]] if isinstance(y, dict) else y
                                for x, y in attr.items() if x in bond_marks})

        s = structure.copy()
        s.remove_edges_from(combinations(set(patch).intersection(structure), 2))
        out = compose(s, p)
        out.meta.update(structure.meta)
        return out

    @classmethod
    def get_templates(cls, raw_templates):
        warn('get_templates name deprecated. use prepare_templates instead', DeprecationWarning)
        return cls.prepare_templates(raw_templates)


def patcher(*args, **kwargs):
    warn('patcher moved to CGRreactor. use patcher static method.', DeprecationWarning)
    return CGRreactor.patcher(*args, **kwargs)


__all__ = [CGRreactor.__name__]
