# -*- coding: utf-8 -*-
#
#  Copyright 2017, 2018 Ramil Nugmanov <stsouko@live.ru>
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
from collections import namedtuple
from itertools import repeat, zip_longest
from .molecule import MoleculeContainer
from ..algorithms import CGRstring
from ..exceptions import InvalidData, InvalidAtom, InvalidStereo
from ..periodictable import elements


class CGRContainer(MoleculeContainer):
    """storage for CGRs. has similar to molecules behavior"""
    def __dir__(self):
        if self.__visible is None:
            self.__visible = tmp = super().__dir__()
            tmp.append(self.get_center_atoms.__name__)
        return self.__visible

    def pickle(self):
        """return json serializable CGR"""
        data = super().pickle()
        data['s_only'] = False
        return data

    @classmethod
    def unpickle(cls, data):
        """convert json serializable CGR or Molecule into MoleculeContainer or CGRcontainer object instance"""
        graph, meta = super().unpickle(data)
        g = MoleculeContainer(graph, meta) if data['s_only'] else cls(graph, meta)
        g.fix_data()
        return g

    def _signature_generator(self, *args, **kwargs):
        return CGRstring(*args, is_cgr=True, **kwargs)

    def add_atom(self, element, s_charge, p_charge=None, s_radical=None, p_radical=None, _map=None, mark='0',
                 s_x=0, s_y=0, s_z=0, p_x=None, p_y=None, p_z=None):
        """
        add new atom into CGR

        :param element: atom element symbol
        :param s_charge: reagents side charge
        :param p_charge: products side charge
        :param s_radical: reagents side radical
        :param p_radical: products side radical
        :param _map: atom map number in CGR. can be omitted
        :param mark: Fragmentor mark
        :param s_x,s_y,s_z,p_x,p_y,p_z: atom coordinates for reagents and products sides
        :return: atom map number
        """
        if element not in elements:
            raise InvalidData('element %s - not exists' % element)
        if _map is None:
            _map = max(self, default=0) + 1
        elif _map in self:
            raise InvalidData('mapping exists')
        if s_radical not in (None, 1, 2, 3) or p_radical not in (None, 1, 2, 3):
            raise InvalidData('only monovalent (2), bivalent (1 singlet, 3 triplet) or None accepted')

        if p_charge is None:
            p_charge = s_charge
        if p_x is None:
            p_x = s_x
        if p_y is None:
            p_y = s_y
        if p_z is None:
            p_z = s_z

        if not (self._check_charge_radical(element, s_charge, radical=self._radical_map[s_radical]) and
                self._check_charge_radical(element, p_charge, radical=self._radical_map[p_radical])):
            raise InvalidData('charge and/or radical values impossible for this element')

        self.add_node(_map, element=element, s_charge=s_charge, p_charge=p_charge, mark=mark,
                      s_x=s_x, s_y=s_y, s_z=s_z, p_x=p_x, p_y=p_y, p_z=p_z, map=_map)

        if s_radical:
            self.nodes[_map]['s_radical'] = s_radical
        if p_radical:
            self.nodes[_map]['p_radical'] = p_radical

        self.flush_cache()
        return _map

    def add_bond(self, atom1, atom2, s_mark, p_mark, *, ignore=False):
        if atom1 not in self or atom2 not in self:
            raise InvalidData('atoms not found')
        if self.has_edge(atom1, atom2):
            raise InvalidData('bond exists')
        if not (s_mark or p_mark):
            raise InvalidData('empty bonds not allowed')

        if s_mark not in (1, 2, 3, 4, 9, None):
            raise InvalidData('invalid bond mark')
        elif not ignore and s_mark:
            self._check_bonding(atom1, atom2, s_mark)

        if p_mark not in (1, 2, 3, 4, 9, None):
            raise InvalidData('invalid bond mark')
        elif not ignore and p_mark:
            self._check_bonding(atom1, atom2, p_mark, label='p')

        if s_mark:
            self.add_edge(atom1, atom2, s_bond=s_mark)
        if p_mark:
            self.add_edge(atom1, atom2, p_bond=p_mark)

        self.flush_cache()

    def add_stereo(self, atom1, atom2, s_mark, p_mark):
        if s_mark not in (1, -1) and p_mark not in (1, -1):
            raise InvalidData('stereo marks invalid')
        if not self.has_edge(atom1, atom2):
            raise InvalidAtom('atom or bond not found')

        n_atom1 = self.nodes[atom1]
        if n_atom1.get('s_stereo') or n_atom1.get('p_stereo'):
            raise InvalidStereo('atom has stereo. change impossible')

        tmp_s = [(x, y['s_bond']) for x, y in self[atom1].items() if y.get('s_bond')]
        tmp_p = [(x, y['p_bond']) for x, y in self[atom1].items() if y.get('p_bond')]
        neighbors = [x for x, _ in tmp_s]

        if s_mark and (n_atom1['s_z'] or any(self.nodes[x]['s_z'] for x in neighbors)):
            raise InvalidStereo('molecule have 3d coordinates. bond up/down stereo unusable')
        elif p_mark and (n_atom1['p_z'] or any(self.nodes[x]['p_z'] for x in neighbors)):
            raise InvalidStereo('molecule have 3d coordinates. bond up/down stereo unusable')

        neighbors_e = [self.nodes[x]['element'] for x in neighbors]
        implicit_s, implicit_p = self.atom_implicit_h(atom1)
        if s_mark and (implicit_s > 1 or implicit_s == 1 and 'H' in neighbors_e or neighbors_e.count('H') > 1):
            raise InvalidStereo('stereo impossible. too many H atoms')
        elif p_mark and (implicit_p > 1 or implicit_p == 1 and 'H' in neighbors_e or neighbors_e.count('H') > 1):
            raise InvalidStereo('stereo impossible. too many H atoms')

        if s_mark:
            bonds = [x for _, x in tmp_s]
            total = implicit_s + len(neighbors)
            if total == 4:  # tetrahedron
                self._tetrahedron_parse(atom1, atom2, s_mark, neighbors, bonds, implicit_s)
            else:
                raise InvalidStereo('unsupported stereo or stereo impossible. tetrahedron only supported')
        if p_mark:
            bonds = [x for _, x in tmp_p]
            total = implicit_p + len(neighbors)
            if total == 4:  # tetrahedron
                self._tetrahedron_parse(atom1, atom2, p_mark, neighbors, bonds, implicit_p, label='p')
            else:
                raise InvalidStereo('unsupported stereo or stereo impossible. tetrahedron only supported')

    def get_stereo(self, atom1, atom2):
        # todo: implement
        return None, None

    def get_center_atoms(self, stereo=False):
        """ get list of atoms of reaction center (atoms with dynamic: bonds, stereo, charges, radicals).
        """
        nodes = set()
        for n, attr in self.nodes(data=True):
            if attr['s_charge'] != attr['p_charge'] or attr.get('s_radical') != attr.get('p_radical') or \
                   stereo and attr.get('s_stereo') != attr.get('p_stereo'):
                nodes.add(n)

        for *n, attr in self.edges(data=True):
            if attr.get('s_bond') != attr.get('p_bond') or stereo and attr.get('s_stereo') != attr.get('p_stereo'):
                nodes.update(n)

        return list(nodes)

    def reset_query_marks(self, copy=False):
        """
        set or reset hyb and neighbors marks to atoms.

        :param copy: if True return copy of graph and keep existing as is
        :return: graph if copy True else None
        """
        g = self.copy() if copy else self
        for i in g:
            label = dict(s_hyb=1, p_hyb=1, sp_hyb=1, s_neighbors=0, p_neighbors=0, sp_neighbors=0)
            # hyb 1- sp3; 2- sp2; 3- sp1; 4- aromatic
            for b, h, n in (('s_bond', 's_hyb', 's_neighbors'), ('p_bond', 'p_hyb', 'p_neighbors')):
                for node, bond in g[i].items():
                    b_type = bond.get(b)
                    if b_type and g.nodes[node]['element'] != 'H':
                        label[n] += 1
                    if b_type in (1, None) or label[h] in (3, 4):
                        continue
                    elif b_type == 4:
                        label[h] = 4
                    elif b_type == 3 or (b_type == 2 and label[h] == 2):  # Если есть 3-я или две 2-х связи, то sp1
                        label[h] = 3
                    elif b_type == 2 and label[h] != 3:
                        # Если есть 2-я связь, но до этого не было найдено другой 2-й, 3-й, или аром.
                        label[h] = 2

            for n, m, h in (('s_hyb', 'p_hyb', 'sp_hyb'), ('s_neighbors', 'p_neighbors', 'sp_neighbors')):
                label[h] = (label[n], label[m]) if label[n] != label[m] else label[n]

            g.nodes[i].update(label)
        if copy:
            return g
        self.flush_cache()

    def implicify_hydrogens(self):
        """
        remove explicit hydrogens if possible

        :return: number of removed hydrogens
        """
        explicit = {}
        hydrogens = set()
        for_remove = []
        c = 0
        for n, attr in self.nodes(data=True):
            if attr['element'] == 'H':
                for m in self.neighbors(n):
                    if self.nodes[m]['element'] != 'H':
                        explicit.setdefault(m, []).append(n)
                    else:
                        hydrogens.add(m)
                        hydrogens.add(n)

        for n, h in explicit.items():
            atom = self.nodes[n]
            s_bonds = [y['s_bond'] for x, y in self[n].items() if x not in h and y.get('s_bond')]
            p_bonds = [y['p_bond'] for x, y in self[n].items() if x not in h and y.get('p_bond')]
            s_implicit = self._get_implicit_h(atom['element'], atom['s_charge'], s_bonds, atom.get('s_radical', 0))
            p_implicit = self._get_implicit_h(atom['element'], atom['p_charge'], p_bonds, atom.get('p_radical', 0))

            if not s_implicit and any(self[n][x].get('s_bond') for x in h):
                hydrogens.update(h)
            elif not p_implicit and any(self[n][x].get('p_bond') for x in h):
                hydrogens.update(h)
            else:
                for x in h:
                    for_remove.append(x)

        for x in for_remove:
            if x not in hydrogens:
                self.remove_node(x)
                c += 1

        self.flush_cache()
        return c

    def explicify_hydrogens(self):
        """
        add explicit hydrogens to atoms

        :return: number of added atoms
        """
        tmp = []
        for n, attr in self.nodes(data=True):
            if attr['element'] != 'H':
                si, pi = self.atom_implicit_h(n)
                if si or pi:
                    for s_mark, p_mark in zip_longest(repeat(1, si), repeat(1, pi)):
                        tmp.append((n, s_mark, p_mark))

        for n, s_mark, p_mark in tmp:
            self.add_bond(n, self.add_atom('H', 0), s_mark, p_mark)

        self.flush_cache()
        return len(tmp)

    def atom_implicit_h(self, atom):
        attr = self.nodes[atom]
        si = self._get_implicit_h(attr['element'], attr['s_charge'],
                                  [x['s_bond'] for x in self[atom].values() if x.get('s_bond')],
                                  radical=self._radical_map[attr.get('s_radical')])
        pi = self._get_implicit_h(attr['element'], attr['p_charge'],
                                  [x['p_bond'] for x in self[atom].values() if x.get('p_bond')],
                                  radical=self._radical_map[attr.get('p_radical')])
        return self.__implicit_container(si, pi)

    def _fix_stereo(self):
        # todo: implement
        self.flush_cache()

    @staticmethod
    def _attr_renew(attr, marks):
        new_attr = {}
        for s, p, sp in marks:
            ls = attr.get(s)
            lp = attr.get(p)

            if isinstance(ls, list):
                if isinstance(lp, list):
                    if ls == lp:
                        new_attr[sp] = new_attr[s] = new_attr[p] = list(set(ls))
                        continue
                    new_attr[sp] = list(set((x, y) for x, y in zip(ls, lp) if x != y))
                else:
                    new_attr[sp] = list(set((x, lp) for x in ls if x != lp))

                new_attr[s] = [x for x, _ in new_attr[sp]]
                new_attr[p] = [x for _, x in new_attr[sp]]
            elif isinstance(lp, list):
                new_attr[sp] = list(set((ls, x) for x in lp if x != ls))
                new_attr[s] = [x for x, _ in new_attr[sp]]
                new_attr[p] = [x for _, x in new_attr[sp]]
            elif ls != lp:
                if ls is not None:
                    new_attr[s] = ls
                if lp is not None:
                    new_attr[p] = lp
                new_attr[sp] = (ls, lp)
            elif ls is not None:
                new_attr[sp] = new_attr[s] = new_attr[p] = ls
        return new_attr

    _node_marks = tuple(('s_%s' % mark, 'p_%s' % mark, 'sp_%s' % mark)
                        for mark in ('charge', 'stereo', 'radical', 'neighbors', 'hyb'))
    _edge_marks = tuple(('s_%s' % mark, 'p_%s' % mark, 'sp_%s' % mark) for mark in ('bond', 'stereo'))

    __tmp1 = ('element', 'isotope', 'mark')
    __tmp2 = tuple(y for x in _node_marks for y in x[:2])
    __tmp3 = __tmp1 + __tmp2

    _node_base = __tmp1 + ('s_x', 's_y', 's_z', 'p_x', 'p_y', 'p_z')
    _node_save = __tmp2 + _node_base
    _edge_save = tuple(y for x in _edge_marks for y in x[:2])
    _atom_marks = {x: x for x in __tmp3}
    _bond_marks = {x: x for x in _edge_save}
    _atom_container = namedtuple('Atom', __tmp3)
    _bond_container = namedtuple('Bond', _edge_save)
    __implicit_container = namedtuple('ImplicitH', ('s_implicit', 'p_implicit'))
    __visible = None
