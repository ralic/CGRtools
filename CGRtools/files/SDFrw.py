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
from itertools import chain
from sys import stderr
from traceback import format_exc
from ._CGRrw import fromMDL, WithMixin
from ._MDLrw import MOLwrite, MOLread
from ..exceptions import EmptyMolecule


class SDFread(MOLread, WithMixin):
    def __init__(self, file, *args, is_template=None, **kwargs):
        assert not is_template, 'is_tepmlate works only for reactions'
        WithMixin.__init__(self, file)
        MOLread.__init__(self, *args, **kwargs)
        self.__data = self.__reader()

    def read(self):
        return list(self.__data)

    def __iter__(self):
        return self.__data

    def __next__(self):
        return next(self.__data)

    def __reader(self):
        im = 3
        atomcount = -1
        bondcount = -1
        failkey = False
        mkey = None
        molecule = None
        mend = False
        for n, line in enumerate(self._file):
            if failkey and not line.startswith("$$$$"):
                continue
            elif line.startswith("$$$$"):
                if molecule:
                    try:
                        yield self._get_molecule(molecule)
                    except Exception:
                        print('line %d\n previous record consist errors: %s' % (n, format_exc()), file=stderr)

                mkey = None
                im = n + 4
                failkey = False
                mend = False
                molecule = None

            elif n == im:
                try:
                    atoms = int(line[0:3])
                    if not atoms:
                        raise EmptyMolecule('Molecule without atoms')
                    atomcount = atoms + n
                    bondcount = int(line[3:6]) + atomcount
                    molecule = dict(atoms=[], bonds=[], CGR_DAT=[], meta={}, colors={})
                except (EmptyMolecule, ValueError):
                    atomcount = bondcount = -1
                    failkey = True
                    molecule = None
                    print('line %d\n\n%s\n consist errors: %s' % (n, line, format_exc()), file=stderr)

            elif n <= atomcount:
                try:
                    molecule['atoms'].append(dict(element=line[31:34].strip(), isotope=int(line[34:36]),
                                                  charge=fromMDL[int(line[38:39])],
                                                  map=int(line[60:63]), mark=line[54:57].strip(),
                                                  x=float(line[0:10]), y=float(line[10:20]), z=float(line[20:30])))
                except ValueError:
                    failkey = True
                    molecule = None
                    print('line %d\n\n%s\n consist errors: %s' % (n, line, format_exc()), file=stderr)
            elif n <= bondcount:
                try:
                    molecule['bonds'].append((int(line[0:3]), int(line[3:6]), int(line[6:9]), int(line[9:12])))
                except ValueError:
                    failkey = True
                    molecule = None
                    print('line %d\n\n%s\n consist errors: %s' % (n, line, format_exc()), file=stderr)

            elif line.startswith("M  END"):
                mend = True
                molecule['CGR_DAT'] = self._get_collected()

            elif molecule:
                if not mend:
                    try:
                        self._collect(line)
                    except ValueError:
                        self._flush_collected()
                        failkey = True
                        molecule = None
                        print('line %d\n\n%s\n consist errors: %s' % (n, line, format_exc()), file=stderr)
                elif line.startswith('>  <'):
                    mkey = line.rstrip()[4:-1].strip()
                    if mkey in ('PHTYP', 'FFTYP', 'PCTYP', 'EPTYP', 'HBONDCHG', 'CNECHG',
                                'dynPHTYP', 'dynFFTYP', 'dynPCTYP', 'dynEPTYP', 'dynHBONDCHG', 'dynCNECHG'):
                        target = 'colors'
                    elif mkey:
                        target = 'meta'
                    else:
                        continue
                    molecule[target][mkey] = []
                elif mkey:
                    data = line.strip()
                    if data:
                        molecule[target][mkey].append(data)

        if molecule:  # True for MOL file only.
            try:
                yield self._get_molecule(molecule)
            except Exception:
                print('line %d\n previous record consist errors: %s' % (n, format_exc()), file=stderr)


class SDFwrite(MOLwrite, WithMixin):
    def __init__(self, file, *args, **kwargs):
        WithMixin.__init__(self, file, 'w')
        MOLwrite.__init__(self, *args, **kwargs)
        self.write = self.__write

    def __write(self, data):
        m = self.get_formatted_cgr(data)
        self._file.write(m['CGR'])
        self._file.write("M  END\n")

        for i in chain(m['colors'].items(), m['meta'].items()):
            self._file.write(">  <%s>\n%s\n" % i)
        self._file.write("$$$$\n")


__all__ = [SDFread.__name__, SDFwrite.__name__]
